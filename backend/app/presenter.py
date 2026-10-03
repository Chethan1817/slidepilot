"""The presenter agent: narrates slides, follows questions to the right slide, and keeps
the browser in sync.

Who drives what:
- The guided run is driven by code, not the LLM: each slide is one reply, and when that
  reply finishes playing without being interrupted, the next slide goes up. That keeps the
  slide change exactly on the boundary between narrations.
- Questions are handled by the LLM, which calls `show_slide` to jump to the slide that
  answers them, and `resume_presentation` / `present_from_slide` to hand control back to
  the guided run. A goodbye ends with `end_session`, which tells the browser to close the
  session once the goodbye has played.
- The browser sees state through the agent participant's `slidepilot.state` attribute and
  controls the agent through RPC (see agent.py).

Two engines share this class. With "livekit", LiveKit runs the whole turn and the tools
below are LiveKit function tools. With "langgraph_pipeline", a LangGraph graph runs the
whole turn, speech-to-text and voice included (voice_pipeline.py): the presenter speaks
through it via `speak_with`, and the graph's own tools call back in through
`slide_actions()`.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterable, Awaitable, Callable, Coroutine
from typing import Any, Literal

from livekit import rtc
from livekit.agents import Agent, ModelSettings, RunContext, ToolError, ToolResult, function_tool, llm
from livekit.agents.voice import SpeechHandle

from . import prompts
from .decks import Deck
from .presentation import ANSWER_WORDS, PresentationState
from .spoken import SpokenText

logger = logging.getLogger("slidepilot.presenter")

STATE_ATTRIBUTE = "slidepilot.state"

# After answering, how long the person must stay quiet before the presentation picks up
# again by itself (the same pause that ends their turn). Starting to talk holds it, and
# talking over the pick-up interrupts it like any other reply.
CONTINUE_AFTER = 0.6

Reason = Literal["start", "advance", "agent", "resume", "user", "pause", "finish", "end"]
Engine = Literal["livekit", "langgraph_pipeline"]


class Presenter(Agent):
    def __init__(self, deck: Deck, room: rtc.Room, engine: Engine = "livekit") -> None:
        self.engine: Engine = engine
        self._deck = deck
        self._room = room
        self._state = PresentationState(slide_count=len(deck.slides))
        self._reason: Reason = "start"
        self._seq = 0
        # Bumped on every new guided step, so a stale step's completion can't advance a
        # newer one (e.g. after the person clicks a slide mid-narration).
        self._run = 0
        self._tasks: set[asyncio.Task[Any]] = set()
        self._publish_lock = asyncio.Lock()
        self._words_spoken = 0
        # Set by the LangGraph pipeline engine, which speaks through its own graph instead
        # of the session's LLM and TTS.
        self.speak_with: Callable[[str], Awaitable[SpeechHandle | None]] | None = None
        self.cancel_speaking: Callable[[], None] | None = None
        # That engine's tools run before the reply they belong to exists, so what they need
        # to watch waits here until attach_to() gets the reply.
        self._pending_watch: tuple[int, int] | None = None
        self._pending_end = False
        # The person paused the run by talking, so it continues once they've been answered
        # (unlike the pause button, which holds it until they continue).
        self._continue_after_answer = False
        self._answers_in_progress = 0
        self._person_speaking = False
        self._continue_timer: asyncio.TimerHandle | None = None
        super().__init__(instructions=prompts.build_instructions(deck, self._state))

    async def on_enter(self) -> None:
        self.session.on("agent_state_changed", lambda _ev: self._consider_continuing())
        self.session.on("user_state_changed", lambda ev: self.person_speaking(ev.new_state == "speaking"))
        await self._present(0, opening=True)

    async def llm_node(
        self, chat_ctx: llm.ChatContext, tools: list[llm.Tool], model_settings: ModelSettings
    ) -> AsyncIterable[llm.ChatChunk | str]:
        replying = _replying_to_person(chat_ctx)
        if replying:
            # A one-line reminder next to the question makes slide changes far more reliable
            # than the system prompt alone.
            chat_ctx = chat_ctx.copy()
            chat_ctx.add_message(role="system", content=prompts.turn_reminder(self._deck, self._state))
        # Count what each LLM step says before any tool call, so show_slide can tell an
        # answer that was already spoken from a bare bridge.
        self._words_spoken = 0
        # Keeps a tool call the model writes into its reply from being spoken (spoken.py).
        spoken = SpokenText(drop_closing_announcement=replying)
        made_call = False
        async for chunk in Agent.default.llm_node(self, chat_ctx, tools, model_settings):
            if isinstance(chunk, llm.ChatChunk) and chunk.delta:
                made_call = made_call or bool(chunk.delta.tool_calls)
                if chunk.delta.content:
                    delta = chunk.delta.model_copy(update={"content": spoken.feed(chunk.delta.content)})
                    chunk = chunk.model_copy(update={"delta": delta})
                    self._words_spoken = len(spoken.text.split())
            yield chunk
        if text := spoken.flush():
            yield text
        # A call written out in reply to the person is made for them. Elsewhere (a
        # narration, a follow-up to a tool result) nothing should change, so it's dropped.
        if replying and not made_call and (leaked := spoken.leaked_call()):
            logger.info("making the %s call the model wrote into its reply", leaked.name)
            call = llm.FunctionToolCall(name=leaked.name, arguments=json.dumps(leaked.args), call_id=leaked.call_id)
            yield llm.ChatChunk(id=leaked.call_id, delta=llm.ChoiceDelta(role="assistant", tool_calls=[call]))

    # -- tools the LLM can call ------------------------------------------------------

    @function_tool
    async def show_slide(self, context: RunContext, slide_number: int) -> ToolResult:
        """Show a slide while you answer a question about it: call it whenever your answer
        draws on a slide that isn't on screen. The presentation stays paused.

        Args:
            slide_number: Number of the slide to show, from 1 to the number of slides.
        """
        index = self._index_from_number(slide_number)
        answered = self._words_spoken >= ANSWER_WORDS
        result = await self._show_for_answer(context.speech_handle, index)
        # If the answer came before the call, the slide was the last step: skip the
        # follow-up LLM round trip. After a bare bridge, the follow-up gives the answer.
        return ToolResult(result, reply_required=not answered)

    @function_tool
    async def resume_presentation(self, context: RunContext) -> str:
        """Continue the guided presentation exactly where it was interrupted, even if other
        slides were shown since. Use it when the person says to continue, go on or keep
        going."""
        return await self._resume_where_left_off(context.speech_handle)

    @function_tool
    async def present_from_slide(self, context: RunContext, slide_number: int) -> str:
        """Present a slide and carry on through the deck from there. Use it when the person
        asks to go to, skip to, go back to or see a particular slide, or to start over.

        Args:
            slide_number: Slide to present from, 1 to start over.
        """
        return await self._resume_at(context.speech_handle, self._index_from_number(slide_number))

    @function_tool
    async def end_session(self, context: RunContext) -> ToolResult:
        """End the session when the person says goodbye or asks to end it. Say a short
        goodbye first, in the same response."""
        said_goodbye = self._words_spoken > 0
        self._end_after(context.speech_handle)
        # After a spoken goodbye there's nothing left to say; otherwise the follow-up says it.
        return ToolResult(prompts.ENDING_RESULT, reply_required=not said_goodbye)

    def slide_actions(self) -> _GraphSlideActions:
        """The slide controls the LangGraph pipeline's tools call."""
        return _GraphSlideActions(self)

    def turn_reminder(self) -> str:
        return prompts.turn_reminder(self._deck, self._state)

    def attach_to(self, handle: SpeechHandle) -> None:
        """The pipeline engine's reply is about to play: start what its tools set up."""
        if self._pending_watch is not None:
            self._watch(handle, *self._pending_watch)
        if self._pending_end:
            self._end_after(handle)
        self.forget_pending()

    def forget_pending(self) -> None:
        self._pending_watch, self._pending_end = None, False

    # -- events from the session and the browser --------------------------------------

    def on_person_spoke(self) -> None:
        """The person asked something (by voice or text), so the guided run pauses until
        they've been answered."""
        if self._state.pause():
            self._continue_after_answer = True
            self._spawn(self._refresh("pause"))

    def answering(self, busy: bool) -> None:
        """The pipeline engine started (or finished playing) an answer. AgentSession's own
        "thinking" state covers this for the LiveKit engine."""
        self._answers_in_progress = max(0, self._answers_in_progress + (1 if busy else -1))
        self._consider_continuing()

    def person_speaking(self, speaking: bool) -> None:
        """The person started or stopped talking (LiveKit's voice activity, or the
        pipeline's own)."""
        self._person_speaking = speaking
        self._consider_continuing()

    async def select_slide(self, index: int) -> None:
        """The person clicked a slide or used the arrow keys."""
        if not self._state.valid(index):
            raise ValueError(f"no slide {index}")
        was_presenting = self._state.mode == "presenting"
        await self._stop_current_step()
        if was_presenting:
            await self._present(index)
            return
        self._state.bookmark = index
        self._hold()  # they picked a slide to look at; Nova asks before going on
        await self._show(index, "user")
        self._spawn(self._say(prompts.overview_prompt(self._deck, index)))

    async def pause(self) -> None:
        """The pause button: stop talking and hold the guided run where it is."""
        self._state.pause()
        self._hold()
        await self._interrupt()
        await self._refresh("pause")

    async def resume(self, index: int | None = None) -> None:
        """The continue button. `index` restarts from a given slide (e.g. 0 to replay)."""
        if index is None:
            index = self._state.resume_index()
            if index is None:
                index = 0
        if not self._state.valid(index):
            raise ValueError(f"no slide {index}")
        await self._stop_current_step()
        await self._present(index, resuming=self._state.is_partial(index))

    async def publish_state(self) -> None:
        """Push the current state to the browser (also called once the room is connected)."""
        if not self._room.isconnected():
            return  # the entrypoint publishes again as soon as the room is connected
        # Serialized, and the payload is read inside the lock, so the last write is always
        # the latest state even when several changes land at once.
        async with self._publish_lock:
            payload = {
                "slide": self._state.current,
                "mode": self._state.mode,
                "reason": self._reason,
                "seq": self._seq,
                "engine": self.engine,
            }
            try:
                await self._room.local_participant.set_attributes(
                    {STATE_ATTRIBUTE: json.dumps(payload)}
                )
            except Exception:
                logger.warning("could not publish presentation state", exc_info=True)

    # -- internals ---------------------------------------------------------------------

    async def _show_for_answer(self, speech: SpeechHandle | None, index: int) -> str:
        if speech is not None and speech.interrupted:
            return "The person interrupted before the slide changed."
        # Switch right away, while the answer (or a bridge) is still being spoken.
        await self._show(index, "agent")
        return prompts.shown_result(self._deck, index)

    async def _resume_where_left_off(self, speech: SpeechHandle | None) -> str:
        index = self._state.resume_index()
        if index is None:
            return prompts.FINISHED_RESULT
        return await self._resume_at(speech, index)

    async def _resume_at(self, speech: SpeechHandle | None, index: int) -> str:
        if speech is not None and speech.interrupted:
            return "The person interrupted before the presentation resumed."
        resuming = self._state.is_partial(index)
        run = self._begin(index)
        await self._show(index, "resume")
        # The LLM narrates this slide in its reply to the tool result, inside the same
        # speech; the guided run continues once that reply has played.
        if speech is not None:
            self._watch(speech, index, run)
        else:
            self._pending_watch = (index, run)
        return prompts.resumed_result(self._deck, index, resuming=resuming)

    async def _present(
        self, index: int, *, opening: bool = False, resuming: bool = False, after_answer: bool = False
    ) -> None:
        """Run one step of the guided presentation: show the slide, then narrate it."""
        run = self._begin(index)
        await self._show(index, "start" if opening else "resume" if resuming else "advance")
        if run != self._run:
            return  # a newer step started while this slide was going up
        handle = await self._reply(
            prompts.present_prompt(self._deck, index, opening=opening, resuming=resuming, after_answer=after_answer)
        )
        if handle is not None:
            self._watch(handle, index, run)

    async def _reply(self, instructions: str) -> SpeechHandle | None:
        """Speak a reply to the app's instructions, through the engine in use."""
        if self.speak_with is not None:
            return await self.speak_with(instructions)
        return self.session.generate_reply(instructions=instructions)

    async def _say(self, instructions: str) -> None:
        await self._reply(instructions)

    def _end_after(self, speech: SpeechHandle | None) -> None:
        """Close the session once the goodbye has played, unless the person cut in."""
        if speech is None:
            self._pending_end = True  # the goodbye is still to come (pipeline engine)
            return

        def on_done(handle: SpeechHandle) -> None:
            if not handle.interrupted:
                self._spawn(self._end())

        speech.add_done_callback(on_done)

    async def _end(self) -> None:
        self._run += 1  # no guided step may start after this
        self._hold()
        await self._refresh("end")  # the browser closes the session when it sees this

    def _begin(self, index: int) -> int:
        self._run += 1
        self._state.begin(index)
        self._hold()  # presenting again; nothing left to continue
        return self._run

    def _hold(self) -> None:
        """Don't continue by itself: the run is presenting, ended, or paused on purpose."""
        self._continue_after_answer = False
        self._consider_continuing()

    def _consider_continuing(self) -> None:
        """Once the person has been answered and gone quiet, pick the presentation back up
        where it stopped. Anything else happening (Nova talking or thinking, the person
        talking) resets the wait."""
        if self._continue_timer is not None:
            self._continue_timer.cancel()
            self._continue_timer = None
        if self._ready_to_continue():
            self._continue_timer = asyncio.get_running_loop().call_later(CONTINUE_AFTER, self._continue_now)

    def _ready_to_continue(self) -> bool:
        return (
            self._continue_after_answer
            and self._state.mode == "paused"
            and self._state.resume_index() is not None
            and self.session.agent_state in ("listening", "idle")
            and not self._person_speaking
            and not self._answers_in_progress
        )

    def _continue_now(self) -> None:
        self._continue_timer = None
        if self._ready_to_continue():
            self._spawn(self._go_back())

    async def _go_back(self) -> None:
        """After an answer: back to the slide the presentation stopped on, and on from there."""
        index = self._state.resume_index()
        if index is None:
            return
        await self._stop_current_step()
        await self._present(index, resuming=self._state.is_partial(index), after_answer=True)

    def _watch(self, handle: SpeechHandle, index: int, run: int) -> None:
        handle.add_done_callback(lambda h: self._on_step_done(h, index, run))

    def _on_step_done(self, handle: SpeechHandle, index: int, run: int) -> None:
        if run != self._run or self._state.mode != "presenting":
            return  # superseded by a newer step, or paused in the meantime
        if handle.interrupted or handle.exception() is not None:
            # Covers interruptions that never turned into a question (a cough, say): the run
            # pauses, then continues by itself once things are quiet again.
            self._state.pause()
            self._continue_after_answer = True
            self._spawn(self._refresh("pause"))
            return
        next_index = self._state.complete(index)
        if next_index is None:
            self._spawn(self._refresh("finish"))
        else:
            self._spawn(self._present(next_index))

    async def _stop_current_step(self) -> None:
        """Stop whatever is playing on our own initiative. Invalidating the current step
        first keeps its interruption from being read as the person cutting in."""
        self._run += 1
        await self._interrupt()

    async def _interrupt(self) -> None:
        if self.cancel_speaking is not None:
            self.cancel_speaking()
        await self.session.interrupt()

    async def _show(self, index: int, reason: Reason) -> None:
        self._state.current = index
        await self._refresh(reason)

    async def _refresh(self, reason: Reason) -> None:
        """Sync the LLM's instructions and the browser with the current state."""
        self._reason = reason
        self._seq += 1
        await self.update_instructions(prompts.build_instructions(self._deck, self._state))
        await self.publish_state()

    def _index_from_number(self, slide_number: int) -> int:
        index = slide_number - 1
        if not self._state.valid(index):
            raise ToolError(f"There is no slide {slide_number}; the deck has slides 1 to {self._state.slide_count}.")
        return index

    def _spawn(self, coro: Coroutine[Any, Any, None]) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)


def _replying_to_person(chat_ctx: llm.ChatContext) -> bool:
    """The reply answers something the person said (not app instructions or a tool result)."""
    conversation = [i for i in chat_ctx.items if i.type in ("message", "function_call_output")]
    return bool(conversation) and conversation[-1].type == "message" and conversation[-1].role == "user"


class _GraphSlideActions:
    """Slide controls for the LangGraph pipeline (see langgraph_agent.SlideActions).

    Its tools run before the reply they belong to exists, so what they set up waits for
    Presenter.attach_to().
    """

    def __init__(self, presenter: Presenter) -> None:
        self._presenter = presenter

    async def show_slide(self, slide_number: int) -> str:
        p = self._presenter
        return await p._show_for_answer(None, p._index_from_number(slide_number))

    async def resume_presentation(self) -> str:
        return await self._presenter._resume_where_left_off(None)

    async def present_from_slide(self, slide_number: int) -> str:
        p = self._presenter
        return await p._resume_at(None, p._index_from_number(slide_number))

    async def end_session(self) -> str:
        self._presenter._end_after(None)
        return prompts.ENDING_RESULT
