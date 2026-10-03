"""The LangGraph engine: graph routing on its own, then the full presenter on a real
LiveKit AgentSession through LiveKit's LangChain adapter. A scripted chat model stands in
for the LLM."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.messages.tool import tool_call_chunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import ConfigDict, Field

from app.langgraph_agent import build_graph
from app.prompts import TURN_REMINDER_PREFIX

LONG_ANSWER = "Good question, that's on the latency slide. People expect a reply within a fraction of a second."


class ScriptedChat(BaseChatModel):
    """Answers like a cooperative model, and records each call and whether tools were bound."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    calls: list[dict[str, Any]] = Field(default_factory=list)
    tools_bound: bool = False
    hold_slide_two: asyncio.Event | None = None
    leak_in_follow_up: bool = False  # write a tool call into replies to tool results
    answer_delay: float = 0.0  # seconds before answering the person, like a slow first token

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Any, **kwargs: Any) -> ScriptedChat:  # type: ignore[override]
        return self.model_copy(update={"tools_bound": True})  # shares `calls`

    def _script(self, messages: list[BaseMessage]) -> tuple[str, list[tuple[str, dict[str, Any]]]]:
        conversation = [
            m for m in messages if not (isinstance(m, SystemMessage) and m.text.startswith(TURN_REMINDER_PREFIX))
        ]
        last = conversation[-1]
        self.calls.append({"last": last.text, "tools_bound": self.tools_bound})
        if isinstance(last, ToolMessage) and "goodbye" in last.text:
            return "Goodbye, and thanks for listening.", []
        if isinstance(last, ToolMessage):
            text = "Great question. Here is the answer from that slide." if "Answer" in last.text else "Narrating the resumed slide."
            return text + ("\n\nfunctions.resume_presentation" if self.leak_in_follow_up else ""), []
        if isinstance(last, SystemMessage):
            return f"Narrating: {last.text[:40]}", []
        text = last.text.lower()
        if "bye" in text:
            return "Thanks for listening, and goodbye!", [("end_session", {})]
        if "end it" in text:  # a bare call: the follow-up says goodbye
            return "", [("end_session", {})]
        if "continue" in text:
            return "Sure, picking up where we left off.", [("resume_presentation", {})]
        if "skip" in text:  # the call written into the reply instead of made
            return "Sure, jumping to the tools slide.\n\npresent_from_slide 5", []
        if "answer first" in text:
            return LONG_ANSWER, [("show_slide", {"slide_number": 3})]
        if "fast" in text:
            return "Let me pull up the latency slide.", [("show_slide", {"slide_number": 3})]
        return "Good question.", []

    def _generate(self, messages: list[BaseMessage], stop: Any = None, run_manager: Any = None, **kwargs: Any) -> ChatResult:
        text, calls = self._script(messages)
        tool_calls = [{"name": n, "args": a, "id": f"call_{i}"} for i, (n, a) in enumerate(calls)]
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text, tool_calls=tool_calls))])

    async def _astream(self, messages: list[BaseMessage], stop: Any = None, run_manager: Any = None, **kwargs: Any):  # type: ignore[override]
        text, calls = self._script(messages)
        if self.hold_slide_two and "slide 2 of" in text and not self.hold_slide_two.is_set():
            await self.hold_slide_two.wait()
        if self.answer_delay and any(isinstance(m, HumanMessage) for m in messages[-2:]):
            await asyncio.sleep(self.answer_delay)
        for i in range(0, len(text), 5):  # token-sized pieces, like a real stream
            yield ChatGenerationChunk(message=AIMessageChunk(content=text[i : i + 5]))
        for i, (name, args) in enumerate(calls):
            chunk = tool_call_chunk(name=name, args=json.dumps(args), id=f"call_{name}_{len(self.calls)}", index=i)
            yield ChatGenerationChunk(message=AIMessageChunk(content="", tool_call_chunks=[chunk]))


class RecordingActions:
    def __init__(self) -> None:
        self.done: list[str] = []

    async def show_slide(self, slide_number: int) -> str:
        self.done.append(f"show {slide_number}")
        return f"Slide {slide_number} is now on screen. Answer the person using it."

    async def resume_presentation(self) -> str:
        self.done.append("resume")
        return "The presentation resumed at slide 2. Present it now."

    async def present_from_slide(self, slide_number: int) -> str:
        self.done.append(f"present from {slide_number}")
        return f"The presentation resumed at slide {slide_number}. Present it now."

    async def end_session(self) -> str:
        self.done.append("end")
        return "The session closes when you finish. Say a short goodbye now."


async def run_graph(model: ScriptedChat, actions: RecordingActions, *messages: BaseMessage) -> str:
    graph = build_graph(model, actions)
    spoken = [chunk async for chunk in graph.astream({"messages": list(messages)}, stream_mode="custom")]
    return "".join(spoken)


SYSTEM = SystemMessage(content="You are Nova.")


async def test_app_prompts_are_narrated_without_tools():
    model, actions = ScriptedChat(), RecordingActions()
    spoken = await run_graph(model, actions, SYSTEM, SystemMessage(content="Present slide 2 of 6 now."))
    assert spoken.startswith("Narrating: Present slide 2 of 6")
    assert model.calls == [{"last": "Present slide 2 of 6 now.", "tools_bound": False}]
    assert actions.done == []


async def test_an_answer_given_before_show_slide_ends_the_turn():
    model, actions = ScriptedChat(), RecordingActions()
    reminder = SystemMessage(content=f"{TURN_REMINDER_PREFIX} Slide 1 is on screen.")
    spoken = await run_graph(model, actions, SYSTEM, HumanMessage(content="Answer first: how fast?"), reminder)
    assert spoken == LONG_ANSWER
    assert actions.done == ["show 3"]
    assert len(model.calls) == 1  # no follow-up round trip
    assert model.calls[0]["tools_bound"]


async def test_a_bare_bridge_gets_a_follow_up_answer_and_tool_results_stay_silent():
    model, actions = ScriptedChat(), RecordingActions()
    spoken = await run_graph(model, actions, SYSTEM, HumanMessage(content="How fast should it respond?"))
    assert spoken == "Let me pull up the latency slide.Great question. Here is the answer from that slide."
    assert "is now on screen" not in spoken
    assert actions.done == ["show 3"]
    assert len(model.calls) == 2


async def test_continue_resumes_and_narrates():
    model, actions = ScriptedChat(), RecordingActions()
    spoken = await run_graph(model, actions, SYSTEM, HumanMessage(content="Okay, continue please"))
    assert spoken == "Sure, picking up where we left off.Narrating the resumed slide."
    assert actions.done == ["resume"]


async def test_a_call_written_into_the_reply_is_made_instead_of_spoken():
    model, actions = ScriptedChat(), RecordingActions()
    spoken = await run_graph(model, actions, SYSTEM, HumanMessage(content="Can we skip to the tools slide?"))
    assert spoken == "Sure, jumping to the tools slide.\n\nNarrating the resumed slide."
    assert actions.done == ["present from 5"]


async def test_a_call_written_into_a_follow_up_is_dropped():
    model, actions = ScriptedChat(leak_in_follow_up=True), RecordingActions()
    spoken = await run_graph(model, actions, SYSTEM, HumanMessage(content="Okay, continue please"))
    assert spoken == "Sure, picking up where we left off.Narrating the resumed slide.\n\n"
    assert actions.done == ["resume"]  # not resumed a second time


@pytest.mark.parametrize(
    ("said", "spoken", "llm_calls"),
    [
        ("Okay, bye bye", "Thanks for listening, and goodbye!", 1),
        ("Please end it now", "Goodbye, and thanks for listening.", 2),
    ],
)
async def test_a_goodbye_ends_the_session(said: str, spoken: str, llm_calls: int):
    model, actions = ScriptedChat(), RecordingActions()
    assert await run_graph(model, actions, SYSTEM, HumanMessage(content=said)) == spoken
    assert actions.done == ["end"]
    assert len(model.calls) == llm_calls  # a spoken goodbye needs no follow-up


class FakeParticipant:
    def __init__(self) -> None:
        self.states: list[dict[str, Any]] = []

    async def set_attributes(self, attributes: dict[str, str]) -> None:
        self.states.append(json.loads(attributes["slidepilot.state"]))


class FakeRoom:
    def __init__(self) -> None:
        self.local_participant = FakeParticipant()

    def isconnected(self) -> bool:
        return True


async def wait_for(condition, timeout: float = 5.0) -> None:
    async with asyncio.timeout(timeout):
        while not condition():
            await asyncio.sleep(0.01)
