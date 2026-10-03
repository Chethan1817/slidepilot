"""The LangGraph pipeline engine: the transcribe → think → speak graph with stand-in speech
services, then the presenter running on it inside a real LiveKit AgentSession."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from langchain_core.messages import SystemMessage
from livekit import rtc
from livekit.agents import AgentSession

from app.decks import all_decks
from app import presenter as presenter_module
from app.presenter import Presenter
from app.voice_pipeline import OUTPUT_SAMPLE_RATE, Hearing, VoicePipeline, build_pipeline
from tests.test_langgraph_engine import FakeRoom, RecordingActions, ScriptedChat, wait_for

SYSTEM = SystemMessage(content="You are Nova.")
REMINDER = "Before you reply: slide 1 is on screen."


class FakeSTT:
    """Hears whatever text the test put in the 'audio'."""

    def __init__(self) -> None:
        self.heard = 0

    async def recognize(self, frames: Any) -> SimpleNamespace:
        self.heard += 1
        return SimpleNamespace(alternatives=[SimpleNamespace(text=frames[0].said)])


class FakeTTS:
    """Ten 10 ms frames of silence per reply, at a rate the room has to resample."""

    def __init__(self) -> None:
        self.spoken: list[str] = []

    def synthesize(self, text: str) -> _Speech:
        self.spoken.append(text)
        return _Speech()


class _Speech:
    async def __aenter__(self) -> _Speech:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def __aiter__(self):
        for _ in range(10):
            yield SimpleNamespace(frame=rtc.AudioFrame(bytes(2 * 220), 22050, 1, 220))


def utterance(said: str) -> list[Any]:
    return [SimpleNamespace(said=said)]


async def run(graph: Any, turn: dict[str, Any]) -> tuple[dict[str, Any], list[rtc.AudioFrame]]:
    frames: list[rtc.AudioFrame] = []
    final: dict[str, Any] = {}
    turn = {**turn, "words": asyncio.Queue()}
    async for mode, data in graph.astream(turn, stream_mode=["custom", "values"]):
        if mode == "custom" and isinstance(data, rtc.AudioFrame):
            frames.append(data)
        elif mode == "values":
            final = data
    return final, frames


async def test_a_spoken_question_is_transcribed_answered_and_voiced():
    listener, model, voice, actions = FakeSTT(), ScriptedChat(), FakeTTS(), RecordingActions()
    graph = build_pipeline(listener, model, voice, actions)  # type: ignore[arg-type]

    state, frames = await run(graph, {"prompt": [SYSTEM], "audio": utterance("Answer first: how fast?"), "reminder": REMINDER})

    assert state["transcript"] == "Answer first: how fast?"
    assert actions.done == ["show 3"]  # the agent's slide tool ran inside the graph
    assert state["reply"].startswith("Good question")
    assert len(voice.spoken) == 2 and " ".join(voice.spoken) == state["reply"]  # voiced sentence by sentence
    assert frames and {f.sample_rate for f in frames} == {OUTPUT_SAMPLE_RATE}


async def test_a_narration_skips_transcription():
    listener, model, voice, actions = FakeSTT(), ScriptedChat(), FakeTTS(), RecordingActions()
    graph = build_pipeline(listener, model, voice, actions)  # type: ignore[arg-type]

    state, frames = await run(graph, {"prompt": [SYSTEM, SystemMessage(content="Present slide 2 of 6 now.")], "reminder": REMINDER})

    assert listener.heard == 0
    assert state["reply"].startswith("Narrating: Present slide 2 of 6")
    assert model.calls[0]["tools_bound"] is False  # narrations can't change slides
    assert frames


async def test_silence_or_noise_gets_no_reply():
    listener, model, voice, actions = FakeSTT(), ScriptedChat(), FakeTTS(), RecordingActions()
    graph = build_pipeline(listener, model, voice, actions)  # type: ignore[arg-type]

    state, frames = await run(graph, {"prompt": [SYSTEM], "audio": utterance("  "), "reminder": REMINDER})

    assert "reply" not in state and not frames and model.calls == [] and voice.spoken == []


async def test_presenter_runs_on_the_pipeline_engine():
    deck = all_decks()["voice-ai-agents"]
    room = FakeRoom()
    presenter = Presenter(deck, room, engine="langgraph_pipeline")  # type: ignore[arg-type]
    model, voice = ScriptedChat(hold_slide_two=asyncio.Event()), FakeTTS()
    graph = build_pipeline(FakeSTT(), model, voice, presenter.slide_actions())  # type: ignore[arg-type]
    latencies: list[float] = []

    async with AgentSession(vad=None, turn_handling={"turn_detection": "manual"}) as session:
        pipeline = VoicePipeline(
            session=session, room=room, presenter=presenter, graph=graph, listener=FakeSTT(),  # type: ignore[arg-type]
            publish_latency=latencies.append, report_error=lambda message: None,
        )
        presenter.speak_with, presenter.cancel_speaking = pipeline.narrate, pipeline.cancel
        await session.start(presenter)

        # The opening narration plays, then the guided run asks for slide 2, which is held.
        await wait_for(lambda: any("slide 2 of" in c["last"] for c in model.calls))
        assert voice.spoken[0].startswith("Narrating: Open the session")

        # The person cuts in and asks about latency: the answer jumps to slide 3.
        await pipeline._interrupt()
        assert presenter._state.mode == "paused"
        model.hold_slide_two.set()
        await pipeline._answer(utterance("How fast does an agent need to respond?"), speech_ended=0.0)
        assert presenter._state.current == 2 and presenter._state.mode == "paused"

        # "Continue" resumes slide 2 and the guided run carries on to the end.
        await pipeline._answer(utterance("Great, please continue"), speech_ended=0.0)
        await wait_for(lambda: presenter._state.mode == "finished", timeout=10)

    assert presenter._state.completed == set(range(6))
    assert latencies  # each answer reported how long it took


async def test_saying_goodbye_on_the_pipeline_ends_the_session():
    deck = all_decks()["voice-ai-agents"]
    room = FakeRoom()
    presenter = Presenter(deck, room, engine="langgraph_pipeline")  # type: ignore[arg-type]
    model, voice = ScriptedChat(hold_slide_two=asyncio.Event()), FakeTTS()
    graph = build_pipeline(FakeSTT(), model, voice, presenter.slide_actions())  # type: ignore[arg-type]

    async with AgentSession(vad=None, turn_handling={"turn_detection": "manual"}) as session:
        pipeline = VoicePipeline(
            session=session, room=room, presenter=presenter, graph=graph, listener=FakeSTT(),  # type: ignore[arg-type]
            publish_latency=lambda seconds: None, report_error=lambda message: None,
        )
        presenter.speak_with, presenter.cancel_speaking = pipeline.narrate, pipeline.cancel
        await session.start(presenter)
        await wait_for(lambda: any("slide 2 of" in c["last"] for c in model.calls))
        await pipeline._interrupt()
        await pipeline._answer(utterance("Okay, bye bye"), speech_ended=0.0)

        # The goodbye is spoken first; the session ends once it has played.
        assert voice.spoken[-1] == "Thanks for listening, and goodbye!"
        await wait_for(lambda: room.local_participant.states[-1]["reason"] == "end")
        model.hold_slide_two.set()


async def test_the_pipeline_continues_by_itself_after_an_answer(monkeypatch):
    monkeypatch.setattr(presenter_module, "CONTINUE_AFTER", 0.05)
    deck = all_decks()["voice-ai-agents"]
    room = FakeRoom()
    presenter = Presenter(deck, room, engine="langgraph_pipeline")  # type: ignore[arg-type]
    model, voice = ScriptedChat(hold_slide_two=asyncio.Event()), FakeTTS()
    graph = build_pipeline(FakeSTT(), model, voice, presenter.slide_actions())  # type: ignore[arg-type]

    async with AgentSession(vad=None, turn_handling={"turn_detection": "manual"}) as session:
        pipeline = VoicePipeline(
            session=session, room=room, presenter=presenter, graph=graph, listener=FakeSTT(),  # type: ignore[arg-type]
            publish_latency=lambda seconds: None, report_error=lambda message: None,
        )
        presenter.speak_with, presenter.cancel_speaking = pipeline.narrate, pipeline.cancel
        await session.start(presenter)
        await wait_for(lambda: any("slide 2 of" in c["last"] for c in model.calls))
        await pipeline._interrupt()
        model.hold_slide_two.set()
        await pipeline._answer(utterance("How fast does an agent need to respond?"), speech_ended=0.0)
        assert presenter._state.current == 2

        # Nobody says "continue": once the answer has played, it goes back and carries on.
        await wait_for(lambda: presenter._state.mode == "finished", timeout=10)

    changes = [(state["reason"], state["slide"]) for state in room.local_participant.states]
    assert changes.index(("resume", 1)) > changes.index(("agent", 2))


async def test_the_transcript_is_ready_when_the_person_stops():
    asked_to_finalize: list[bool] = []
    hearing = Hearing(request_final=lambda: asked_to_finalize.append(True))
    hearing.heard("How fast does an agent need to respond?", final=True)  # streamed while they spoke
    model, voice, actions = ScriptedChat(), FakeTTS(), RecordingActions()
    graph = build_pipeline(FakeSTT(), model, voice, actions)  # type: ignore[arg-type]

    state, frames = await run(graph, {"prompt": [SYSTEM], "hearing": hearing, "reminder": REMINDER})

    assert state["transcript"] == "How fast does an agent need to respond?"
    assert asked_to_finalize == []  # nothing left to finalize, so no wait
    assert actions.done == ["show 3"] and frames


async def test_last_words_still_in_progress_are_finalized():
    hearing = Hearing(request_final=lambda: asyncio.get_running_loop().call_later(
        0.01, lambda: hearing.heard("an agent need to respond?", final=True)
    ))
    hearing.heard("How fast does", final=True)
    hearing.heard("an agent need to", final=False)
    assert await hearing.finish() == "How fast does an agent need to respond?"


async def test_a_typed_question_is_answered_before_the_presentation_goes_back(monkeypatch):
    # The answer takes longer to start than the pause before going back: the pause must wait.
    monkeypatch.setattr(presenter_module, "CONTINUE_AFTER", 0.05)
    deck = all_decks()["voice-ai-agents"]
    room = FakeRoom()
    presenter = Presenter(deck, room, engine="langgraph_pipeline")  # type: ignore[arg-type]
    model, voice = ScriptedChat(hold_slide_two=asyncio.Event(), answer_delay=0.3), FakeTTS()
    graph = build_pipeline(FakeSTT(), model, voice, presenter.slide_actions())  # type: ignore[arg-type]

    async with AgentSession(vad=None, turn_handling={"turn_detection": "manual"}) as session:
        pipeline = VoicePipeline(
            session=session, room=room, presenter=presenter, graph=graph, listener=FakeSTT(),  # type: ignore[arg-type]
            publish_latency=lambda seconds: None, report_error=lambda message: None,
        )
        presenter.speak_with, presenter.cancel_speaking = pipeline.narrate, pipeline.cancel
        await session.start(presenter)
        await wait_for(lambda: any("slide 2 of" in c["last"] for c in model.calls))

        await pipeline.on_typed(session, SimpleNamespace(text="Answer first: how fast?"))  # type: ignore[arg-type]
        assert any(sentence.startswith("Good question") for sentence in voice.spoken)  # answered, not skipped
        await wait_for(lambda: presenter._state.mode == "finished", timeout=10)
        model.hold_slide_two.set()

    changes = [(state["reason"], state["slide"]) for state in room.local_participant.states]
    assert changes.index(("resume", 1)) > changes.index(("agent", 2))  # then back to slide 2


async def test_the_presentation_never_goes_back_while_an_answer_is_prepared(monkeypatch):
    monkeypatch.setattr(presenter_module, "CONTINUE_AFTER", 0.05)
    deck = all_decks()["voice-ai-agents"]
    room = FakeRoom()
    presenter = Presenter(deck, room, engine="langgraph_pipeline")  # type: ignore[arg-type]
    model, voice = ScriptedChat(hold_slide_two=asyncio.Event()), FakeTTS()
    graph = build_pipeline(FakeSTT(), model, voice, presenter.slide_actions())  # type: ignore[arg-type]

    async with AgentSession(vad=None, turn_handling={"turn_detection": "manual"}) as session:
        pipeline = VoicePipeline(
            session=session, room=room, presenter=presenter, graph=graph, listener=FakeSTT(),  # type: ignore[arg-type]
            publish_latency=lambda seconds: None, report_error=lambda message: None,
        )
        presenter.speak_with, presenter.cancel_speaking = pipeline.narrate, pipeline.cancel
        await session.start(presenter)
        await wait_for(lambda: any("slide 2 of" in c["last"] for c in model.calls))
        await pipeline._interrupt()  # the person asked something: paused until they're answered

        # The answer is still being written when the interrupted voice reports Nova as quiet.
        presenter.answering(True)
        session._update_agent_state("thinking")
        session._update_agent_state("listening")
        await asyncio.sleep(0.3)
        assert presenter._state.mode == "paused"  # it didn't go back mid-answer

        presenter.answering(False)  # the answer has played
        await wait_for(lambda: presenter._state.mode == "presenting")
        model.hold_slide_two.set()
