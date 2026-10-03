"""Runs the presenter on a real AgentSession (text-only, no room or network) with a
scripted LLM, covering the guided run, a question that jumps slides, and resuming."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from livekit.agents import AgentSession, llm
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS

from app.decks import all_decks
from app import presenter as presenter_module
from app.presenter import STATE_ATTRIBUTE, Presenter, _replying_to_person
from app.prompts import TURN_REMINDER_PREFIX


SKIP_REPLY = "Sure, jumping to the tools slide.\n\npresent_from_slide 5"


class ScriptedLLM(llm.LLM):
    """Behaves like a cooperative model: narrates when the app asks it to, calls
    show_slide for a question about latency, and resume_presentation on "continue"."""

    def __init__(self) -> None:
        super().__init__()
        self.narrated: list[str] = []
        self.hold_slide_two = asyncio.Event()  # set() to let slide 2's narration finish
        self.calls = 0

    def chat(self, *, chat_ctx, tools=None, conn_options=DEFAULT_API_CONNECT_OPTIONS, **_: Any):
        self.calls += 1
        return _ScriptedStream(self, chat_ctx=chat_ctx, tools=tools or [], conn_options=conn_options)


class _ScriptedStream(llm.LLMStream):
    async def _run(self) -> None:
        script: ScriptedLLM = self._llm  # type: ignore[assignment]
        # Like real providers, ignore bookkeeping items such as instruction updates, and read
        # past the per-turn reminder to what the person actually said.
        conversation = [
            item for item in self._chat_ctx.items
            if item.type in ("message", "function_call_output")
            and not (item.type == "message" and (item.text_content or "").startswith(TURN_REMINDER_PREFIX))
        ]
        last = conversation[-1]

        if last.type == "function_call_output":
            return self._say(f"(reply to tool result: {last.output[:40]})")

        text = last.text_content or "" if last.type == "message" else ""
        if last.type == "message" and last.role == "system":  # per-step app instructions
            script.narrated.append(text)
            if "slide 2 of" in text and len(script.narrated) == 2:
                await script.hold_slide_two.wait()
            return self._say(f"(narration: {text[:30]})")

        if "bye" in text.lower():
            self._say("Thanks for listening, and goodbye!")
            return self._call("end_session", {})
        if "end it" in text.lower():  # a bare call: the follow-up says goodbye
            return self._call("end_session", {})
        if "continue" in text.lower():
            return self._call("resume_presentation", {})
        if "answer first" in text.lower():
            self._say("Good question, that's on the latency slide. People expect a reply within a fraction of a second, so agents aim for well under one.")
            return self._call("show_slide", {"slide_number": 3})
        if "fast" in text.lower():
            return self._call("show_slide", {"slide_number": 3})
        if "skip" in text.lower():  # the call written into the reply instead of made
            for i in range(0, len(SKIP_REPLY), 5):
                self._say(SKIP_REPLY[i : i + 5])
            return None
        return self._say("(small talk)")

    def _say(self, text: str) -> None:
        self._event_ch.send_nowait(
            llm.ChatChunk(id="scripted", delta=llm.ChoiceDelta(role="assistant", content=text))
        )

    def _call(self, name: str, args: dict[str, Any]) -> None:
        call = llm.FunctionToolCall(name=name, arguments=json.dumps(args), call_id=f"call_{name}")
        self._event_ch.send_nowait(
            llm.ChatChunk(id="scripted", delta=llm.ChoiceDelta(role="assistant", tool_calls=[call]))
        )


class FakeParticipant:
    def __init__(self) -> None:
        self.states: list[dict[str, Any]] = []

    async def set_attributes(self, attributes: dict[str, str]) -> None:
        self.states.append(json.loads(attributes[STATE_ATTRIBUTE]))


class FakeRoom:
    def __init__(self) -> None:
        self.local_participant = FakeParticipant()

    def isconnected(self) -> bool:
        return True


async def wait_for(condition, timeout: float = 5.0) -> None:
    async with asyncio.timeout(timeout):
        while not condition():
            await asyncio.sleep(0.01)


async def test_guided_run_question_jump_and_resume():
    deck = all_decks()["voice-ai-agents"]
    room = FakeRoom()
    presenter = Presenter(deck, room)  # type: ignore[arg-type]
    script = ScriptedLLM()
    published = room.local_participant.states

    async with AgentSession(llm=script, vad=None, turn_handling={"turn_detection": "manual"}) as session:
        await session.start(presenter)

        # The opening narrates slide 1, then the guided run moves to slide 2 by itself.
        await wait_for(lambda: len(script.narrated) == 2)
        assert "Open the session" in script.narrated[0]
        assert "slide 2 of 6" in script.narrated[1]
        assert published[-1] == {"slide": 1, "mode": "presenting", "reason": "advance", "seq": 2, "engine": "livekit"}

        # The person cuts in during slide 2: the guided run pauses at slide 2...
        await session.interrupt()
        await wait_for(lambda: presenter._state.mode == "paused")

        # ...and a question about latency jumps to slide 3 without resuming the run.
        await session.run(user_input="How fast does an agent need to respond?")
        assert presenter._state.current == 2
        assert presenter._state.mode == "paused"
        assert published[-1]["reason"] == "agent"

        # "Continue" goes back to the interrupted slide 2, then on through the deck.
        script.hold_slide_two.set()
        await session.run(user_input="Great, please continue")
        await wait_for(lambda: presenter._state.mode == "finished")

    slides_shown = [state["slide"] for state in published]
    resumed_at = slides_shown.index(1, slides_shown.index(2))  # back to slide 2 after the jump
    assert slides_shown[resumed_at:] == [1, 2, 3, 4, 5, 5]  # last entry: the "finish" update
    assert published[resumed_at]["reason"] == "resume"
    assert published[-1]["reason"] == "finish"
    assert presenter._state.completed == set(range(6))
    assert "final slide" in script.narrated[-1]


async def test_clicking_a_slide_mid_presentation_keeps_presenting():
    deck = all_decks()["voice-ai-agents"]
    presenter = Presenter(deck, FakeRoom())  # type: ignore[arg-type]
    script = ScriptedLLM()

    async with AgentSession(llm=script, vad=None, turn_handling={"turn_detection": "manual"}) as session:
        await session.start(presenter)
        await wait_for(lambda: len(script.narrated) == 2)  # slide 2 is mid-narration

        await presenter.select_slide(4)

        assert presenter._state.mode == "presenting"
        assert presenter._state.current == 4
        script.hold_slide_two.set()  # let the cut-off narration's stream finish
        await wait_for(lambda: presenter._state.mode == "finished")

    # The run carried on from slide 5; the cut-off slide 2 never counted as presented.
    assert ["slide 5 of 6" in text for text in script.narrated[2:]] == [True, False]
    assert presenter._state.completed == {0, 4, 5}


async def test_an_answer_spoken_before_show_slide_needs_no_follow_up_call():
    deck = all_decks()["voice-ai-agents"]
    presenter = Presenter(deck, FakeRoom())  # type: ignore[arg-type]
    script = ScriptedLLM()

    async with AgentSession(llm=script, vad=None, turn_handling={"turn_detection": "manual"}) as session:
        await session.start(presenter)
        await wait_for(lambda: len(script.narrated) == 2)
        await session.interrupt()
        await wait_for(lambda: presenter._state.mode == "paused")

        calls_before = script.calls
        await session.run(user_input="Answer first: how fast should it respond?")

        assert presenter._state.current == 2
        assert script.calls == calls_before + 1  # one LLM round trip, no tool follow-up
        script.hold_slide_two.set()


async def test_a_tool_call_written_into_the_reply_is_made_instead_of_spoken():
    deck = all_decks()["voice-ai-agents"]
    room = FakeRoom()
    presenter = Presenter(deck, room)  # type: ignore[arg-type]
    script = ScriptedLLM()

    async with AgentSession(llm=script, vad=None, turn_handling={"turn_detection": "manual"}) as session:
        await session.start(presenter)
        await wait_for(lambda: len(script.narrated) == 2)
        await session.interrupt()
        await wait_for(lambda: presenter._state.mode == "paused")

        result = await session.run(user_input="Can we skip to the tools slide?")
        script.hold_slide_two.set()
        await wait_for(lambda: presenter._state.mode == "finished")

    calls = [(e.item.name, json.loads(e.item.arguments)) for e in result.events if e.type == "function_call"]
    assert calls == [("present_from_slide", {"slide_number": 5})]
    said = [e.item.text_content for e in result.events if e.type == "message"]
    assert said[0].strip() == "Sure, jumping to the tools slide."
    assert not any("present_from" in text for text in said)
    resumed = [state for state in room.local_participant.states if state["reason"] == "resume"]
    assert resumed[0]["slide"] == 4  # the tools slide, presented by the recovered call


@pytest.mark.parametrize(("said", "llm_calls"), [("Okay, bye bye", 1), ("Please end it now", 2)])
async def test_saying_goodbye_ends_the_session_once_the_goodbye_has_played(said: str, llm_calls: int):
    deck = all_decks()["voice-ai-agents"]
    room = FakeRoom()
    presenter = Presenter(deck, room)  # type: ignore[arg-type]
    script = ScriptedLLM()

    async with AgentSession(llm=script, vad=None, turn_handling={"turn_detection": "manual"}) as session:
        await session.start(presenter)
        await wait_for(lambda: len(script.narrated) == 2)
        await session.interrupt()
        await wait_for(lambda: presenter._state.mode == "paused")

        calls_before = script.calls
        await session.run(user_input=said)
        await wait_for(lambda: room.local_participant.states[-1]["reason"] == "end")

        # A spoken goodbye needs no follow-up; a bare call gets one that says goodbye.
        assert script.calls == calls_before + llm_calls
        narrated = len(script.narrated)
        script.hold_slide_two.set()
        await asyncio.sleep(0.2)
        assert len(script.narrated) == narrated  # the guided run stays stopped


async def test_after_an_answer_the_presentation_continues_by_itself(monkeypatch):
    monkeypatch.setattr(presenter_module, "CONTINUE_AFTER", 0.05)
    deck = all_decks()["voice-ai-agents"]
    room = FakeRoom()
    presenter = Presenter(deck, room)  # type: ignore[arg-type]
    script = ScriptedLLM()

    async with AgentSession(llm=script, vad=None, turn_handling={"turn_detection": "manual"}) as session:
        await session.start(presenter)
        await wait_for(lambda: len(script.narrated) == 2)  # slide 2 is mid-narration
        await session.interrupt()
        await wait_for(lambda: presenter._state.mode == "paused")
        script.hold_slide_two.set()
        await session.run(user_input="How fast does an agent need to respond?")
        assert presenter._state.current == 2  # jumped to slide 3 to answer

        # Nobody says "continue": once the answer is done, it goes back and carries on.
        await wait_for(lambda: presenter._state.mode == "finished", timeout=10)

    changes = [(state["reason"], state["slide"]) for state in room.local_participant.states]
    assert changes.index(("resume", 1)) > changes.index(("agent", 2))  # back to slide 2


async def test_the_pause_button_holds_the_presentation(monkeypatch):
    monkeypatch.setattr(presenter_module, "CONTINUE_AFTER", 0.05)
    deck = all_decks()["voice-ai-agents"]
    presenter = Presenter(deck, FakeRoom())  # type: ignore[arg-type]
    script = ScriptedLLM()

    async with AgentSession(llm=script, vad=None, turn_handling={"turn_detection": "manual"}) as session:
        await session.start(presenter)
        await wait_for(lambda: len(script.narrated) == 2)
        await presenter.pause()
        script.hold_slide_two.set()
        await asyncio.sleep(0.3)
        assert presenter._state.mode == "paused"
        assert len(script.narrated) == 2  # nothing new was presented


def test_the_turn_reminder_applies_only_to_what_the_person_said():
    ctx = llm.ChatContext.empty()
    ctx.add_message(role="system", content="instructions")
    ctx.add_message(role="assistant", content="narration")
    assert not _replying_to_person(ctx)
    ctx.add_message(role="user", content="How fast?")
    assert _replying_to_person(ctx)
    ctx.add_message(role="system", content="Present slide 2")  # the guided run's own prompt
    assert not _replying_to_person(ctx)
