"""Speech and language model selection for the presenter agent.

Each stage uses the providers you hold keys for, in this order, falling back to LiveKit
Inference (which needs only LiveKit Cloud credentials):

    speech-to-text   DEEPGRAM_API_KEY -> Deepgram
    LLM              ANTHROPIC_API_KEY -> Claude, OPENAI_API_KEY -> OpenAI, GOOGLE_API_KEY -> Gemini
    text-to-speech   DEEPGRAM_API_KEY -> Deepgram Aura (fastest), ELEVEN_API_KEY -> ElevenLabs,
                     OPENAI_API_KEY -> OpenAI

When several LLM or TTS providers have keys, the first one serves and the rest stand by:
if it fails (an exhausted quota, an outage), the session moves to the next one instead of
going silent. SLIDEPILOT_{STT,LLM,TTS}_PROVIDER pins a single provider, and _MODEL
overrides the model of the first one.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from langchain_openai import ChatOpenAI
from langgraph.graph.state import CompiledStateGraph
from livekit.agents import STTContextOptions, inference, llm, stt, tts
from livekit.agents.types import NOT_GIVEN, NotGivenOr
from livekit.agents.utils import is_given
from livekit.agents.voice.turn import TurnHandlingOptions
from livekit.plugins import anthropic, deepgram, elevenlabs, google, openai

from .decks import Deck
from .langgraph_agent import SlideActions
from .voice_pipeline import build_pipeline
from .prompts import PRESENTER_NAME

DEFAULT_MODELS: dict[str, dict[str, str]] = {
    "stt": {"deepgram": "nova-3", "livekit": "deepgram/nova-3:en"},
    "llm": {
        "anthropic": "claude-opus-5-5",
        "openai": "gpt-4.1",
        "google": "gemini-2.5-flash",
        "livekit": "openai/gpt-4.1-mini",
    },
    "tts": {
        "elevenlabs": "eleven_flash_v2_5",
        "deepgram": "aura-2-asteria-en",
        "openai": "gpt-4o-mini-tts",
        "livekit": "cartesia/sonic-3",
    },
}
OPENAI_VOICE = "coral"

# The two interchangeable "brains" a session can run on (see presenter.py).
ENGINES = {"livekit": "LiveKit Agents", "langgraph_pipeline": "LangGraph pipeline"}
PRESENTER_DELIVERY = (
    "Speak like a warm, confident conference presenter: clear, friendly and engaged, "
    "with natural pacing and a touch of enthusiasm."
)


@dataclass(frozen=True)
class ModelConfig:
    stt_provider: str
    stt_model: str
    llm_providers: tuple[str, ...]
    """Primary first; the rest take over if it fails."""
    llm_model: str
    """Model for the primary LLM provider."""
    tts_providers: tuple[str, ...]
    tts_model: str
    tts_voice: str | None
    claude_effort: str
    livekit_cloud: bool
    """Cloud-only extras (LiveKit Inference, turn detector, adaptive interruption) work."""

    @property
    def llm_provider(self) -> str:
        return self.llm_providers[0]

    @property
    def tts_provider(self) -> str:
        return self.tts_providers[0]


def model_config() -> ModelConfig:
    cloud = ".livekit.cloud" in os.getenv("LIVEKIT_URL", "")
    stt_provider = _providers("STT", [("deepgram", "DEEPGRAM_API_KEY")], cloud)[0]
    llm_providers = _providers(
        "LLM",
        [("anthropic", "ANTHROPIC_API_KEY"), ("openai", "OPENAI_API_KEY"), ("google", "GOOGLE_API_KEY")],
        cloud,
    )
    tts_providers = _providers(
        "TTS",
        [("deepgram", "DEEPGRAM_API_KEY"), ("elevenlabs", "ELEVEN_API_KEY"), ("openai", "OPENAI_API_KEY")],
        cloud,
    )
    return ModelConfig(
        stt_provider=stt_provider,
        stt_model=os.getenv("SLIDEPILOT_STT_MODEL") or DEFAULT_MODELS["stt"][stt_provider],
        llm_providers=llm_providers,
        llm_model=os.getenv("SLIDEPILOT_LLM_MODEL") or DEFAULT_MODELS["llm"][llm_providers[0]],
        tts_providers=tts_providers,
        tts_model=os.getenv("SLIDEPILOT_TTS_MODEL") or DEFAULT_MODELS["tts"][tts_providers[0]],
        tts_voice=os.getenv("SLIDEPILOT_TTS_VOICE") or _default_voice(tts_providers[0]),
        claude_effort=os.getenv("SLIDEPILOT_LLM_EFFORT") or "low",
        livekit_cloud=cloud,
    )


def _providers(stage: str, keyed: list[tuple[str, str]], cloud: bool) -> tuple[str, ...]:
    """SLIDEPILOT_<stage>_PROVIDER if set, else every provider with a key, in order.
    LiveKit Inference closes the chain on LiveKit Cloud, or stands alone without keys."""
    choices = [name for name, _ in keyed] + ["livekit"]
    explicit = os.getenv(f"SLIDEPILOT_{stage}_PROVIDER", "").strip().lower()
    if explicit:
        if explicit not in choices:
            raise ValueError(f"SLIDEPILOT_{stage}_PROVIDER must be one of {choices}, got {explicit!r}")
        return (explicit,)
    chain = [name for name, env in keyed if os.getenv(env)]
    if cloud or not chain:
        chain.append("livekit")
    return tuple(chain)


def _default_voice(tts_provider: str) -> str | None:
    if tts_provider == "elevenlabs":
        return os.getenv("ELEVEN_VOICE_ID") or None
    if tts_provider == "openai":
        return OPENAI_VOICE
    return None  # Deepgram picks the voice by model; LiveKit Inference takes "model:voice"


def stt_context(deck: Deck) -> STTContextOptions:
    """Words the speech-to-text should listen for: Nova's name and the deck's jargon.
    Without them, Deepgram often heard "VAD" as "that" or "bad"."""
    return {"keyterms": list(dict.fromkeys([PRESENTER_NAME, "Slidepilot", *deck.keyterms]))}


def build_stt(cfg: ModelConfig) -> stt.STT:
    if cfg.stt_provider == "deepgram":
        return deepgram.STT(model=cfg.stt_model, language="en-US")
    return inference.STT.from_model_string(cfg.stt_model)


def build_llm(cfg: ModelConfig) -> llm.LLM:
    instances = [_llm(cfg.llm_provider, cfg.llm_model, cfg)]
    instances += [_llm(p, DEFAULT_MODELS["llm"][p], cfg) for p in cfg.llm_providers[1:]]
    return instances[0] if len(instances) == 1 else llm.FallbackAdapter(instances)


def _llm(provider: str, model: str, cfg: ModelConfig) -> llm.LLM:
    if provider == "anthropic":
        return ClaudeLLM(model=model, effort=cfg.claude_effort)
    if provider == "openai":
        return openai.LLM(model=model)
    if provider == "google":
        # Gemini 2.5 thinks by default; a spoken reply wants the first word fast.
        thinking = {"thinking_budget": 0} if model.startswith("gemini-2.5") else NOT_GIVEN
        return google.LLM(model=model, thinking_config=thinking)
    return inference.LLM(model=model)


def langgraph_model(cfg: ModelConfig) -> str:
    return cfg.llm_model if cfg.llm_provider == "openai" else DEFAULT_MODELS["llm"]["openai"]


def voice_pipeline_available() -> bool:
    """The pipeline engine transcribes with Deepgram and thinks with OpenAI through LangChain."""
    return bool(os.getenv("OPENAI_API_KEY") and os.getenv("DEEPGRAM_API_KEY"))


def build_voice_pipeline(cfg: ModelConfig, deck: Deck, actions: SlideActions) -> tuple[CompiledStateGraph, stt.STT]:
    """The LangGraph graph that runs whole turns (Deepgram, then the agent, then the voice),
    and the Deepgram listener its transcribe step finishes."""
    listener = deepgram.STT(model=DEFAULT_MODELS["stt"]["deepgram"], language="en-US", keyterm=stt_context(deck)["keyterms"])
    return build_pipeline(listener, ChatOpenAI(model=langgraph_model(cfg)), build_tts(cfg), actions), listener


def build_tts(cfg: ModelConfig) -> tts.TTS:
    instances = [_tts(cfg.tts_provider, cfg.tts_model, cfg.tts_voice)]
    instances += [_tts(p, DEFAULT_MODELS["tts"][p], _default_voice(p)) for p in cfg.tts_providers[1:]]
    return instances[0] if len(instances) == 1 else tts.FallbackAdapter(instances)


def _tts(provider: str, model: str, voice: str | None) -> tts.TTS:
    if provider == "elevenlabs":
        return elevenlabs.TTS(model=model, **({"voice_id": voice} if voice else {}))
    if provider == "deepgram":
        return deepgram.TTS(model=model)
    if provider == "openai":
        return openai.TTS(model=model, voice=voice or OPENAI_VOICE, instructions=PRESENTER_DELIVERY)
    return inference.TTS.from_model_string(model)


def turn_handling(cfg: ModelConfig) -> TurnHandlingOptions:
    """LiveKit's turn handling, tuned for this app."""
    # The streaming turn detector commits 0.3 s after you stop by default, which can beat
    # the speech-to-text's final transcript and split one question into two messages.
    # When the turn detector thinks you may not be done, it waits up to max_delay. On
    # Cloud it rated "Wait. How fast does a voice agent need to respond?" unfinished and
    # waited the default 2.5 s; 1.5 s is enough for a mid-sentence pause.
    options: TurnHandlingOptions = {"endpointing": {"min_delay": 0.6, "max_delay": 1.5}}
    # Barge-in on voice activity. LiveKit Cloud's adaptive interruption took 1.1 s to
    # notice someone talking over Nova, then timed out and turned itself off mid-session.
    options["interruption"] = {"mode": "vad"}
    if not cfg.livekit_cloud:
        # The default turn detector runs on LiveKit Inference; off Cloud, use the model
        # bundled with the SDK.
        options["turn_detection"] = inference.TurnDetector(version="v1-mini")
    return options


def pipeline(cfg: ModelConfig) -> dict[str, list[dict[str, str]]]:
    """Each stage's providers in order (primary first), for the settings page."""

    def chain(stage: str, providers: tuple[str, ...], primary_model: str) -> list[dict[str, str]]:
        return [
            {"provider": p, "model": primary_model if i == 0 else DEFAULT_MODELS[stage][p]}
            for i, p in enumerate(providers)
        ]

    return {
        "stt": chain("stt", (cfg.stt_provider,), cfg.stt_model),
        "llm": chain("llm", cfg.llm_providers, cfg.llm_model),
        "tts": chain("tts", cfg.tts_providers, cfg.tts_model),
    }


def describe(cfg: ModelConfig) -> dict[str, str]:
    """Vendor-qualified model names for the UI's status pill."""

    def qualified(provider: str, model: str) -> str:
        return model.split(":")[0] if provider == "livekit" else f"{provider}/{model}"

    return {
        "llm": cfg.llm_model,
        "stt": qualified(cfg.stt_provider, cfg.stt_model),
        "tts": qualified(cfg.tts_provider, cfg.tts_model),
    }


# Models that accept `output_config.effort` (Claude 4.6 and newer, except Haiku).
_EFFORT_MODEL_PREFIXES = (
    "claude-fable-5",
    "claude-mythos-5",
    "claude-opus-5",
    "claude-sonnet-5",
    "claude-opus-4-8",
    "claude-opus-4-7",
    "claude-opus-4-6",
    "claude-sonnet-4-6",
)
# Models that take the server-side refusal fallback in its `"default"` form.
_FALLBACK_MODELS = {"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"}


class ClaudeLLM(anthropic.LLM):
    """LiveKit's Anthropic LLM, plus the request options current Claude models want.

    - Effort: current models always think; low effort keeps time-to-first-token short,
      which matters more than depth for short spoken replies.
    - max_tokens: thinking counts toward it, so leave room beyond the plugin's 1024 default.
    - Refusal fallback: if a safety classifier declines a request, the API retries it on
      Anthropic's recommended fallback model instead of returning an empty reply.
    """

    def __init__(self, *, model: str, effort: str = "low", max_tokens: int = 8192) -> None:
        super().__init__(model=model, max_tokens=max_tokens)
        self._request_extras: dict[str, Any] = {}
        if model.startswith(_EFFORT_MODEL_PREFIXES):
            self._request_extras["output_config"] = {"effort": effort}
        if model in _FALLBACK_MODELS:
            self._request_extras["extra_headers"] = {
                "anthropic-beta": "server-side-fallback-2026-07-01"
            }
            self._request_extras["extra_body"] = {"fallbacks": "default"}

    def chat(
        self, *, extra_kwargs: NotGivenOr[dict[str, Any]] = NOT_GIVEN, **kwargs: Any
    ) -> anthropic.LLMStream:
        extra = {**self._request_extras, **(extra_kwargs if is_given(extra_kwargs) else {})}
        return super().chat(extra_kwargs=extra, **kwargs)
