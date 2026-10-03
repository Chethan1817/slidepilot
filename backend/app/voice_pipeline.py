"""The LangGraph pipeline engine: one LangGraph graph runs each whole turn, speech-to-text
and voice included.

    START ─┬─▶ transcribe ─┬─▶ think ──▶ END    the person spoke
           │               └─▶ speak ──▶ END
           └─────────────────▶ think + speak    the app asked for a narration

- transcribe: the session's one Deepgram stream hears everything the person says as they
  say it (Listening); this node takes the utterance's transcript once they stop, asking
  Deepgram to finalize any last words. A recording works too.
- think: the LangGraph agent from langgraph_agent.py (GPT-4.1 and the slide tools). It hands
  the reply to `speak` word by word as it writes it.
- speak: runs alongside `think` and voices each sentence (ElevenLabs, with fallbacks) as soon
  as it's complete, streaming the audio out of the graph.

Streaming between the steps keeps the reply time close to LiveKit's own pipeline: the
transcript is ready moments after the person stops, and the first sentence is voiced while
the rest is still being written.

LiveKit only carries the audio. VoicePipeline listens to the person's microphone with a
voice activity detector, cuts Nova off when they start talking, runs the graph once they
stop, and plays the graph's audio with session.say(), which also captions it.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any, Protocol, TypedDict, TypeVar

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from livekit import rtc
from livekit.agents import AgentSession, inference, stt, tokenize, tts, utils, vad
from livekit.agents.voice import SpeechHandle
from livekit.agents.voice.room_io import TextInputEvent

from .langgraph_agent import SlideActions, build_graph

logger = logging.getLogger("slidepilot.pipeline")

OUTPUT_SAMPLE_RATE = 24000  # what LiveKit's room audio output plays
INTERRUPT_AFTER = 0.4  # seconds of speech before Nova is cut off, so a cough doesn't
MIN_UTTERANCE = 0.3  # shorter sounds aren't sent for transcription
END_OF_TURN_SILENCE = 0.6  # silence that ends what the person said (LiveKit's engine waits 0.6 s too)
ECHO_WARMUP = 3.0  # ignore barge-in at the start, while echo cancellation settles
FINALIZE_TIMEOUT = 1.0  # longest wait for Deepgram to finalize the last words

T = TypeVar("T")


class Hearing:
    """What the person says in one utterance, as the session's speech-to-text transcribes it."""

    def __init__(self, request_final: Callable[[], None]) -> None:
        self._request_final = request_final
        self._finals: list[str] = []
        self._interim = ""
        self._changed = asyncio.Event()

    @property
    def has_words(self) -> bool:
        return bool(self._finals or self._interim)

    def heard(self, text: str, *, final: bool) -> None:
        if final:
            if text:
                self._finals.append(text)
            self._interim = ""
        else:
            self._interim = text
        self._changed.set()

    async def finish(self) -> str:
        """The person stopped talking: everything they said. Usually it's all final by now;
        otherwise speech-to-text is asked to finalize the last words."""
        if self._interim:
            self._request_final()
            try:
                async with asyncio.timeout(FINALIZE_TIMEOUT):
                    while self._interim:
                        self._changed.clear()
                        await self._changed.wait()
            except TimeoutError:
                pass  # go with the last interim words
        return " ".join([*self._finals, self._interim]).strip()


class Listening:
    """The session's one speech-to-text stream, fed every frame of the person's microphone
    as LiveKit's own pipeline does, so there's no connection to set up per utterance."""

    def __init__(self, listener: stt.STT) -> None:
        self._stream = listener.stream()
        self._current: Hearing | None = None
        self._reading = asyncio.create_task(self._read())

    def push(self, frame: rtc.AudioFrame) -> None:
        self._stream.push_frame(frame)

    def hear(self) -> Hearing:
        """The person started talking: collect what they say from here."""
        self._current = Hearing(request_final=self._stream.flush)  # flush sends Deepgram "Finalize"
        return self._current

    async def close(self) -> None:
        self._reading.cancel()
        await self._stream.aclose()

    async def _read(self) -> None:
        async for event in self._stream:
            if self._current is None or not event.alternatives:
                continue
            text = event.alternatives[0].text.strip()
            if event.type == stt.SpeechEventType.FINAL_TRANSCRIPT:
                self._current.heard(text, final=True)
            elif event.type == stt.SpeechEventType.INTERIM_TRANSCRIPT:
                self._current.heard(text, final=False)


@dataclass
class Words:
    """Part of the reply as `think` writes it, streamed out of the graph for the captions."""

    text: str


class Turn(TypedDict, total=False):
    hearing: Hearing
    """What the person is saying, transcribed as they talk."""
    audio: list[rtc.AudioFrame]
    """Or a recording of it. Neither is there when the app asks for a narration."""
    prompt: list[BaseMessage]
    """Instructions and the conversation so far (plus the app's prompt for a narration)."""
    transcript: str
    """What the person said or typed, as text."""
    reminder: str
    """Added next to what the person said; see prompts.turn_reminder()."""
    words: asyncio.Queue[str | None]
    """The reply passing from `think` to `speak` as it's written; None ends it."""
    reply: str


class Presenter(Protocol):
    """What the pipeline needs from the presenter (presenter.Presenter)."""

    @property
    def instructions(self) -> str: ...
    def turn_reminder(self) -> str: ...
    def on_person_spoke(self) -> None: ...
    def answering(self, busy: bool) -> None: ...
    def person_speaking(self, speaking: bool) -> None: ...
    def attach_to(self, handle: SpeechHandle) -> None: ...
    def forget_pending(self) -> None: ...


def build_pipeline(
    stt_: stt.STT, model: BaseChatModel, tts_: tts.TTS, actions: SlideActions
) -> CompiledStateGraph:
    agent = build_graph(model, actions)
    sentences = tokenize.basic.SentenceTokenizer()

    async def transcribe(state: Turn) -> dict[str, Any]:
        if (hearing := state.get("hearing")) is not None:
            return {"transcript": await hearing.finish()}
        event = await stt_.recognize(state["audio"])
        return {"transcript": event.alternatives[0].text.strip() if event.alternatives else ""}

    async def think(state: Turn) -> dict[str, Any]:
        write = get_stream_writer()
        words = state["words"]
        messages = list(state["prompt"])
        if state.get("transcript"):
            messages += [HumanMessage(content=state["transcript"]), SystemMessage(content=state["reminder"])]
        said: list[str] = []
        try:
            async for mode, data in agent.astream(
                {"messages": messages}, {"recursion_limit": 8}, stream_mode=["custom", "updates"]
            ):
                if mode == "custom" and isinstance(data, str):
                    words.put_nowait(data)
                    write(Words(data))
                elif mode == "updates":
                    for update in data.values():
                        for message in (update or {}).get("messages", []):
                            if isinstance(message, AIMessage) and message.text.strip():
                                said.append(message.text)
                                # A space between replies, e.g. a bridge and its follow-up.
                                words.put_nowait(" ")
                                write(Words(" "))
        finally:
            words.put_nowait(None)
        return {"reply": " ".join(said)}

    async def speak(state: Turn) -> dict[str, Any]:
        write = get_stream_writer()
        words = state["words"]
        split = sentences.stream()

        async def feed() -> None:
            while (text := await words.get()) is not None:
                split.push_text(text)
            split.end_input()

        feeding = asyncio.create_task(feed())
        resampler: rtc.AudioResampler | None = None
        try:
            async for sentence in split:
                async with tts_.synthesize(sentence.token) as stream:
                    async for audio in stream:
                        frame = audio.frame
                        if frame.sample_rate == OUTPUT_SAMPLE_RATE:
                            write(frame)
                            continue
                        if resampler is None:
                            resampler = rtc.AudioResampler(
                                frame.sample_rate, OUTPUT_SAMPLE_RATE, num_channels=frame.num_channels
                            )
                        for out in resampler.push(frame):
                            write(out)
            for out in resampler.flush() if resampler else []:
                write(out)
        finally:
            feeding.cancel()
            await split.aclose()
        return {}

    def start(state: Turn) -> str | list[str]:
        return "transcribe" if state.get("hearing") or state.get("audio") else ["think", "speak"]

    def after_transcribe(state: Turn) -> str | list[str]:
        return ["think", "speak"] if state.get("transcript") else END

    graph = StateGraph(Turn)
    graph.add_node("transcribe", transcribe)
    graph.add_node("think", think)
    graph.add_node("speak", speak)
    graph.add_conditional_edges(START, start, ["transcribe", "think", "speak"])
    graph.add_conditional_edges("transcribe", after_transcribe, ["think", "speak", END])
    graph.add_edge("think", END)
    graph.add_edge("speak", END)
    return graph.compile(name="slidepilot-voice-pipeline")


class VoicePipeline:
    """Runs the pipeline graph for one session: hears the person, interrupts Nova, and plays
    each reply."""

    def __init__(
        self,
        *,
        session: AgentSession,
        room: rtc.Room,
        presenter: Presenter,
        graph: CompiledStateGraph,
        listener: stt.STT,
        publish_latency: Callable[[float], None],
        report_error: Callable[[str], None],
    ) -> None:
        self._session = session
        self._room = room
        self._presenter = presenter
        self._graph = graph
        self._listener = listener
        self._publish_latency = publish_latency
        self._report_error = report_error
        self._history: list[BaseMessage] = []
        self._current: asyncio.Task[SpeechHandle | None] | None = None
        self._tasks: set[asyncio.Task[Any]] = set()
        self._started = time.monotonic()
        self._participant: rtc.RemoteParticipant | None = None
        self._hearing: Hearing | None = None
        self._closed = False
        session.on("close", self._on_close)

    def _on_close(self, _event: object) -> None:
        # The viewer left: whatever was being prepared has no one to play to.
        self._closed = True
        self.cancel()

    # -- speaking ----------------------------------------------------------------------

    async def narrate(self, instructions: str) -> SpeechHandle | None:
        """Speak a reply to the app's instructions (the presenter's speak_with)."""
        return await self._turn({"prompt": [*self._prompt(), SystemMessage(content=instructions)]})

    def cancel(self) -> None:
        """Drop the turn in progress (the presenter's cancel_speaking)."""
        if self._current is not None and not self._current.done():
            self._current.cancel()

    async def on_typed(self, _session: AgentSession, ev: TextInputEvent) -> None:
        """A question typed in the browser: skips transcription."""
        await self._reply_to_person({"prompt": self._prompt(), "transcript": ev.text}, interrupt=True)

    async def _reply_to_person(
        self, turn: Turn, *, speech_ended: float | None = None, interrupt: bool
    ) -> SpeechHandle | None:
        """Answer the person. Until the answer has played, the presentation doesn't pick up
        again by itself (the presenter would otherwise go back mid-answer)."""
        self._presenter.answering(True)
        handle: SpeechHandle | None = None
        try:
            if interrupt:
                await self._interrupt()
            self._set_agent_state("thinking")
            handle = await self._turn(turn, speech_ended=speech_ended)
        finally:
            if handle is None:
                self._presenter.answering(False)
                self._set_agent_state("listening")  # nothing to say (noise, or a newer turn)
            else:
                handle.add_done_callback(lambda _handle: self._presenter.answering(False))
        return handle

    def _prompt(self) -> list[BaseMessage]:
        return [SystemMessage(content=self._presenter.instructions), *self._history]

    async def _turn(self, turn: Turn, *, speech_ended: float | None = None) -> SpeechHandle | None:
        self.cancel()
        task = asyncio.create_task(self._run(turn, speech_ended))
        self._current = task
        try:
            return await task
        except asyncio.CancelledError:
            task.cancel()
            current = asyncio.current_task()
            if current is not None and current.cancelling():
                raise  # we were cancelled ourselves
            return None  # the turn was dropped for a newer one
        except Exception as error:
            if self._closed:
                return None
            logger.exception("pipeline turn failed")
            self._report_error(f"The LangGraph pipeline failed: {str(error)[:160]}.")
            return None

    async def _run(self, turn: Turn, speech_ended: float | None) -> SpeechHandle | None:
        self._presenter.forget_pending()
        turn["reminder"] = self._presenter.turn_reminder()
        turn["words"] = asyncio.Queue()
        captions: asyncio.Queue[str | None] = asyncio.Queue()
        audio: asyncio.Queue[rtc.AudioFrame | None] = asyncio.Queue()
        handle: SpeechHandle | None = None
        transcript, reply = turn.get("transcript", ""), ""
        marks: dict[str, float] = {}
        try:
            async for mode, data in self._graph.astream(turn, stream_mode=["custom", "updates"]):
                if mode == "updates" and "transcribe" in data:
                    marks["transcribe"] = time.monotonic()
                    transcript = data["transcribe"]["transcript"]
                    if transcript:
                        self._spawn(self._caption_person(transcript))
                elif mode == "updates" and "think" in data:
                    reply = data["think"]["reply"]
                elif isinstance(data, Words):
                    marks.setdefault("first words", time.monotonic())
                    captions.put_nowait(data.text)
                elif isinstance(data, rtc.AudioFrame):
                    if handle is None:
                        marks["first audio"] = time.monotonic()
                        self._report(speech_ended, marks)
                        handle = self._session.say(_drain(captions), audio=_drain(audio))
                    audio.put_nowait(data)
        finally:
            captions.put_nowait(None)
            audio.put_nowait(None)
        if handle is not None:
            self._presenter.attach_to(handle)  # its tools have all run by now
        if transcript:
            self._history.append(HumanMessage(content=transcript))
        if reply:
            self._history.append(AIMessage(content=reply))
        return handle

    def _report(self, speech_ended: float | None, marks: dict[str, float]) -> None:
        if speech_ended is None:
            return  # a narration, not an answer
        latency = marks["first audio"] - speech_ended
        self._publish_latency(latency)
        start = speech_ended
        steps = []
        for name in ("transcribe", "first words", "first audio"):
            if name in marks:
                steps.append(f"{name} {marks[name] - start:.1f} s")
                start = marks[name]
        logger.info("replied in %.1f s (%s)", latency, ", ".join(steps))

    async def _caption_person(self, text: str) -> None:
        """Show what the person said in the transcript, as LiveKit's own STT would."""
        person = self._participant
        if person is None:
            return
        track = next(
            (p.sid for p in person.track_publications.values() if p.source == rtc.TrackSource.SOURCE_MICROPHONE), ""
        )
        writer = await self._room.local_participant.stream_text(
            topic="lk.transcription",
            sender_identity=person.identity,
            attributes={
                "lk.transcription_final": "true",
                "lk.segment_id": utils.shortuuid("SG_"),
                "lk.transcribed_track_id": track,
            },
        )
        await writer.write(text)
        await writer.aclose()

    # -- listening ---------------------------------------------------------------------

    def listen(self, participant: rtc.RemoteParticipant) -> None:
        self._participant = participant
        self._spawn(self._listen(participant))

    async def _listen(self, participant: rtc.RemoteParticipant) -> None:
        mic = rtc.AudioStream.from_participant(
            participant=participant, track_source=rtc.TrackSource.SOURCE_MICROPHONE, sample_rate=16000, num_channels=1
        )
        detector = inference.VAD(min_silence_duration=END_OF_TURN_SILENCE).stream()
        listening = Listening(self._listener)

        async def feed() -> None:
            async for event in mic:
                detector.push_frame(event.frame)
                listening.push(event.frame)

        feeding = asyncio.create_task(feed())
        cut_in = False
        try:
            async for event in detector:
                if event.type == vad.VADEventType.START_OF_SPEECH:
                    cut_in = False
                    self._presenter.person_speaking(True)
                    self._hearing = listening.hear()
                elif event.type == vad.VADEventType.INFERENCE_DONE:
                    # Cut Nova off only for words, not a cough, background noise or its own
                    # echo: speech-to-text has to hear something, as in LiveKit's engine.
                    warmed_up = time.monotonic() - self._started > ECHO_WARMUP
                    words = self._hearing is not None and self._hearing.has_words
                    if event.speaking and not cut_in and warmed_up and words and event.speech_duration >= INTERRUPT_AFTER:
                        cut_in = True
                        await self._interrupt()
                elif event.type == vad.VADEventType.END_OF_SPEECH:
                    hearing, self._hearing = self._hearing, None
                    self._presenter.person_speaking(False)
                    if event.speech_duration < MIN_UTTERANCE:
                        continue
                    speech_ended = time.monotonic() - event.silence_duration
                    if cut_in or hearing is None or hearing.has_words:
                        turn: Turn = {"prompt": self._prompt()}
                        if hearing is not None:
                            turn["hearing"] = hearing
                        else:
                            turn["audio"] = event.frames
                        self._spawn(self._reply_to_person(turn, speech_ended=speech_ended, interrupt=not cut_in))
                    else:
                        self._spawn(self._reply_if_words(hearing, speech_ended))
        finally:
            feeding.cancel()
            await listening.close()
            await detector.aclose()
            await mic.aclose()

    async def _reply_if_words(self, hearing: Hearing, speech_ended: float) -> None:
        """No words had come through by the end of the sound: it was probably noise. If
        speech-to-text finds some after all, answer them."""
        if text := await hearing.finish():
            self._spawn(self._caption_person(text))
            turn: Turn = {"prompt": self._prompt(), "transcript": text}
            await self._reply_to_person(turn, speech_ended=speech_ended, interrupt=True)

    async def _answer(self, heard: Hearing | list[rtc.AudioFrame], speech_ended: float) -> None:
        """Answer what the person said (once Nova has already been cut off)."""
        turn: Turn = {"prompt": self._prompt()}
        if isinstance(heard, Hearing):
            turn["hearing"] = heard
        else:
            turn["audio"] = heard
        await self._reply_to_person(turn, speech_ended=speech_ended, interrupt=False)

    async def _interrupt(self) -> None:
        self.cancel()
        self._presenter.on_person_spoke()  # pauses the guided presentation
        await self._session.interrupt()

    def _set_agent_state(self, state: str) -> None:
        # The orb in the browser follows the agent state; AgentSession sets it for the
        # replies it generates itself, which the pipeline doesn't use.
        update = getattr(self._session, "_update_agent_state", None)
        if update is not None:
            update(state)

    def _spawn(self, coro: Any) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)


async def _drain(queue: asyncio.Queue[T | None]) -> AsyncIterator[T]:
    while (item := await queue.get()) is not None:
        yield item
