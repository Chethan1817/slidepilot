"""The LangGraph agent: the conversation logic of the LangGraph pipeline's `think` step
(voice_pipeline.py), as a state graph.

    START ─┬─▶ narrate ──────────────────▶ END   the app asked for a slide's narration
           └─▶ converse ─┬───────────────▶ END   the person spoke; nothing to change
                 ▲       └─▶ tools ─┬────▶ END   slide shown after the answer, or the
                 │                  │            session ending after the goodbye
                 └──────────────────┘            otherwise give (or continue) the answer

`narrate` has no tools bound, so a narration can never wander off to another slide. The
nodes keep only what is meant to be spoken in their messages, so tool results and other
bookkeeping never are. Nor is a tool call the model writes into its reply (see spoken.py):
`converse` makes that call instead.
"""

from __future__ import annotations

import logging
from typing import Protocol

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    SystemMessage,
    ToolMessage,
    message_chunk_to_message,
)
from langchain_core.messages.tool import tool_call
from langchain_core.tools import tool
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

from .presentation import ANSWER_WORDS
from .prompts import TURN_REMINDER_PREFIX
from .spoken import LeakedCall, SpokenText

logger = logging.getLogger("slidepilot.langgraph")


class SlideActions(Protocol):
    """What the graph's tools can do to the presentation (implemented by the Presenter)."""

    async def show_slide(self, slide_number: int) -> str: ...
    async def resume_presentation(self) -> str: ...
    async def present_from_slide(self, slide_number: int) -> str: ...
    async def end_session(self) -> str: ...


def build_graph(model: BaseChatModel, actions: SlideActions) -> CompiledStateGraph:
    @tool(parse_docstring=True)
    async def show_slide(slide_number: int) -> str:
        """Show a slide while you answer a question about it: call it whenever your answer
        draws on a slide that isn't on screen. The presentation stays paused.

        Args:
            slide_number: Number of the slide to show, from 1 to the number of slides.
        """
        return await actions.show_slide(slide_number)

    @tool
    async def resume_presentation() -> str:
        """Continue the guided presentation exactly where it was interrupted, even if other
        slides were shown since. Use it when the person says to continue, go on or keep
        going."""
        return await actions.resume_presentation()

    @tool(parse_docstring=True)
    async def present_from_slide(slide_number: int) -> str:
        """Present a slide and carry on through the deck from there. Use it when the person
        asks to go to, skip to, go back to or see a particular slide, or to start over.

        Args:
            slide_number: Slide to present from, 1 to start over.
        """
        return await actions.present_from_slide(slide_number)

    @tool
    async def end_session() -> str:
        """End the session when the person says goodbye or asks to end it. Say a short
        goodbye first, in the same response."""
        return await actions.end_session()

    tools = [show_slide, resume_presentation, present_from_slide, end_session]
    model_with_tools = model.bind_tools(tools)

    async def narrate(state: MessagesState) -> dict[str, list[BaseMessage]]:
        message, _ = await _speak(model, state["messages"])
        return {"messages": [message]}

    async def converse(state: MessagesState) -> dict[str, list[BaseMessage]]:
        answering_person = not isinstance(state["messages"][-1], ToolMessage)
        message, leaked = await _speak(model_with_tools, state["messages"], answering=answering_person)
        # A call written out in reply to the person is made for them. In a follow-up to a
        # tool result, where nothing more should change, it is just dropped.
        if leaked and answering_person and not message.tool_calls:
            logger.info("making the %s call the model wrote into its reply", leaked.name)
            message = message.model_copy(
                update={"tool_calls": [tool_call(name=leaked.name, args=leaked.args, id=leaked.call_id)]}
            )
        return {"messages": [message]}

    graph = StateGraph(MessagesState)
    graph.add_node("narrate", narrate)
    graph.add_node("converse", converse)
    graph.add_node("tools", ToolNode(tools))
    graph.add_conditional_edges(START, route_start, ["narrate", "converse"])
    graph.add_edge("narrate", END)
    graph.add_conditional_edges("converse", route_after_converse, ["tools", END])
    graph.add_conditional_edges("tools", route_after_tools, ["converse", END])
    return graph.compile(name="slidepilot-presenter")


async def _speak(
    model: BaseChatModel, messages: list[BaseMessage], *, answering: bool = False
) -> tuple[AIMessage, LeakedCall | None]:
    """Voice the reply as it streams in, and return it whole for the graph's state, along
    with any tool call the model wrote into it instead of making it. An answer's closing
    "Let me show you that slide" is dropped: the slide is up by then."""
    write = get_stream_writer()
    spoken = SpokenText(drop_closing_announcement=answering)
    reply: AIMessageChunk | None = None
    async for chunk in model.astream(messages):
        if text := spoken.feed(chunk.text):
            write(text)
        reply = chunk if reply is None else reply + chunk
    if text := spoken.flush():
        write(text)
    message = message_chunk_to_message(reply) if reply is not None else AIMessage(content="")
    # The state keeps what was said, so a written-out call never reaches the next prompt.
    return message.model_copy(update={"content": spoken.text}), spoken.leaked_call()


def route_start(state: MessagesState) -> str:
    last = state["messages"][-1]
    # The app's own per-slide prompt arrives as a system message. The reminder that rides
    # along with what the person said is one too, but marked.
    if isinstance(last, SystemMessage) and not last.text.startswith(TURN_REMINDER_PREFIX):
        return "narrate"
    return "converse"


def route_after_converse(state: MessagesState) -> str:
    last = state["messages"][-1]
    return "tools" if isinstance(last, AIMessage) and last.tool_calls else END


def route_after_tools(state: MessagesState) -> str:
    # The message that asked for the tools sits just before their results.
    request = next(m for m in reversed(state["messages"]) if isinstance(m, AIMessage))
    called = {call["name"] for call in request.tool_calls}
    words = len(request.text.split())
    # Showing a slide after a spoken answer, or ending after a spoken goodbye, needs no
    # follow-up; anything else does.
    if (called == {"show_slide"} and words >= ANSWER_WORDS) or (called == {"end_session"} and words):
        return END
    return "converse"
