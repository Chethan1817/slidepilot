"""LiveKit agent worker: joins each presentation room and runs the presenter.

    uv run python -m app.agent dev        # local development, hot reload
    uv run python -m app.agent start      # production
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from collections.abc import Awaitable, Callable
from typing import Any

from livekit import rtc
from livekit.agents import (
    AgentServer,
    AgentSession,
    ConversationItemAddedEvent,
    ErrorEvent,
    JobContext,
    cli,
    room_io,
)

from .config import AGENT_NAME
from .decks import Deck, all_decks, get_deck
from .models import (
    ENGINES,
    build_llm,
    build_stt,
    build_tts,
    build_voice_pipeline,
    model_config,
    stt_context,
    turn_handling,
    voice_pipeline_available,
)
from .presenter import Engine, Presenter
from .voice_pipeline import VoicePipeline

logger = logging.getLogger("slidepilot.agent")

LATENCY_ATTRIBUTE = "slidepilot.latency_ms"
ERROR_ATTRIBUTE = "slidepilot.error"


def _is_known_ffi_noise(unraisable: Any) -> bool:
    """livekit 1.1.20 releases a room's audio sources natively when a session ends, then
    drops them again from Python as they're garbage-collected (livekit/python-sdks#845).
    Nothing is wrong, but each double drop logged a warning and an AssertionError
    traceback. Remove this filter once the SDK is fixed."""
    return isinstance(unraisable.exc_value, AssertionError) and (
        getattr(unraisable.object, "__qualname__", "") == "FfiHandle.__del__"
    )


def _quiet_known_ffi_noise() -> None:
    previous = sys.unraisablehook

    def hook(unraisable: sys.UnraisableHookArgs) -> None:
        if not _is_known_ffi_noise(unraisable):
            previous(unraisable)

    sys.unraisablehook = hook
    logging.getLogger("livekit").addFilter(lambda record: "drop unknown FFI handle" not in record.getMessage())


_quiet_known_ffi_noise()  # module level, so it runs in every job process

server = AgentServer()


@server.rtc_session(agent_name=AGENT_NAME)
async def entrypoint(ctx: JobContext) -> None:
    deck, engine = _job_options(ctx)
    cfg = model_config()
    notice = None
    if engine == "langgraph_pipeline" and not voice_pipeline_available():
        notice = "The LangGraph pipeline needs OPENAI_API_KEY and DEEPGRAM_API_KEY, so this session runs on LiveKit Agents."
        engine = "livekit"
    logger.info(
        "presenting %r on %s: stt=%s llm=%s (%s) tts=%s (%s)",
        deck.id,
        ENGINES[engine],
        cfg.stt_provider,
        " -> ".join(cfg.llm_providers),
        cfg.llm_model,
        " -> ".join(cfg.tts_providers),
        cfg.tts_model,
    )

    presenter = Presenter(deck, ctx.room, engine=engine)
    background: set[asyncio.Task[Any]] = set()

    def publish(attributes: dict[str, str]) -> None:
        task = asyncio.create_task(ctx.room.local_participant.set_attributes(attributes))
        background.add(task)
        task.add_done_callback(background.discard)

    def report_error(message: str) -> None:
        publish({ERROR_ATTRIBUTE: json.dumps({"message": message, "at": time.time()})})

    voice: VoicePipeline | None = None
    room_options = room_io.RoomOptions()
    if engine == "langgraph_pipeline":
        # The graph does the listening, thinking and speaking; the session only plays
        # the audio it makes. No STT, LLM, TTS or VAD of its own.
        session = AgentSession(vad=None, turn_handling={"turn_detection": "manual"})
        graph, listener = build_voice_pipeline(cfg, deck, presenter.slide_actions())
        voice = VoicePipeline(
            session=session,
            room=ctx.room,
            presenter=presenter,
            graph=graph,
            listener=listener,
            publish_latency=lambda seconds: publish({LATENCY_ATTRIBUTE: str(round(seconds * 1000))}),
            report_error=report_error,
        )
        presenter.speak_with, presenter.cancel_speaking = voice.narrate, voice.cancel
        room_options = room_io.RoomOptions(
            audio_input=False, text_input=room_io.TextInputOptions(text_input_cb=voice.on_typed)
        )
    else:
        session = AgentSession(
            stt=build_stt(cfg),
            llm=build_llm(cfg),
            tts=build_tts(cfg),
            turn_handling=turn_handling(cfg),
            stt_context_options=stt_context(deck),
        )

    @session.on("conversation_item_added")
    def _on_item(ev: ConversationItemAddedEvent) -> None:
        item = ev.item
        if item.type != "message":
            return
        if item.role == "user":
            presenter.on_person_spoke()
        elif item.role == "assistant" and (latency := item.metrics.get("e2e_latency")):
            # Time from the person finishing their sentence to the agent's first audio.
            publish({LATENCY_ATTRIBUTE: str(round(latency * 1000))})
            metrics = item.metrics
            logger.info(
                "replied in %.1f s (first LLM token %.1f s, first sentence to the voice %.1f s, first audio %.1f s)",
                latency,
                metrics.get("llm_node_ttft", float("nan")),
                metrics.get("llm_node_ttfs", float("nan")),
                metrics.get("tts_node_ttfb", float("nan")),
            )

    @session.on("error")
    def _on_error(ev: ErrorEvent) -> None:
        if getattr(ev.error, "recoverable", False):
            return  # the session is retrying
        message = describe_error(ev)
        logger.error(message)
        report_error(message)

    # The session closes when the viewer leaves, and LiveKit removes the empty room. (Deleting
    # it from here as well cut the agent's own connection and logged errors on Cloud.)
    await session.start(agent=presenter, room=ctx.room, room_options=room_options)
    # on_enter may have run before the room finished connecting.
    await presenter.publish_state()
    if voice is not None:
        voice.listen(await ctx.wait_for_participant())
    _register_controls(ctx.room, presenter)
    if notice:
        publish({ERROR_ATTRIBUTE: json.dumps({"message": notice, "at": time.time()})})


def describe_error(ev: ErrorEvent) -> str:
    """A plain-language account of a pipeline failure, for the person in the room."""
    stage = {"llm_error": "language model", "stt_error": "speech-to-text", "tts_error": "voice"}.get(
        getattr(ev.error, "type", ""), "voice pipeline"
    )
    provider = getattr(ev.source, "provider", "") or "the provider"
    detail = str(getattr(ev.error, "error", ev.error))
    lowered = detail.lower()
    if "insufficient_quota" in lowered or "credit" in lowered:
        reason = f"{provider} says the account is out of credits"
    elif "401" in detail or "invalid api key" in lowered or "incorrect api key" in lowered:
        reason = f"{provider} rejected the API key"
    elif "429" in detail:
        reason = f"{provider} is rate limiting requests"
    else:
        reason = detail[:160]
    return f"The {stage} failed: {reason}."


def _job_options(ctx: JobContext) -> tuple[Deck, Engine]:
    """The deck and engine the browser asked for, from the dispatch metadata."""
    try:
        options = json.loads(ctx.job.metadata or "{}")
    except json.JSONDecodeError:
        options = {}
    deck_id = options.get("deck_id", "")
    deck = get_deck(deck_id)
    if deck is None:
        deck = next(iter(all_decks().values()))
        logger.warning("unknown deck %r in dispatch metadata, using %r", deck_id, deck.id)
    engine: Engine = options.get("engine") if options.get("engine") in ENGINES else "livekit"
    return deck, engine


def _register_controls(room: rtc.Room, presenter: Presenter) -> None:
    """RPC methods the browser calls: slide clicks, pause and continue."""

    def method(handler: Callable[[dict[str, Any]], Awaitable[None]]):
        async def wrapper(data: rtc.RpcInvocationData) -> str:
            await handler(json.loads(data.payload) if data.payload else {})
            return "ok"

        return wrapper

    async def goto(payload: dict[str, Any]) -> None:
        await presenter.select_slide(int(payload["slide"]))

    async def pause(_: dict[str, Any]) -> None:
        await presenter.pause()

    async def resume(payload: dict[str, Any]) -> None:
        slide = payload.get("slide")
        await presenter.resume(None if slide is None else int(slide))

    participant = room.local_participant
    participant.register_rpc_method("slidepilot.goto", method(goto))
    participant.register_rpc_method("slidepilot.pause", method(pause))
    participant.register_rpc_method("slidepilot.resume", method(resume))


if __name__ == "__main__":
    cli.run_app(server)
