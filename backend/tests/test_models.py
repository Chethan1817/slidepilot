from types import SimpleNamespace

import pytest
from livekit.agents import llm, tts

from livekit.rtc._ffi_client import FfiHandle

from app.agent import _is_known_ffi_noise, describe_error
from app.decks import all_decks
from app.models import build_llm, build_tts, describe, model_config, stt_context, turn_handling

KEYS = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GOOGLE_API_KEY",
    "DEEPGRAM_API_KEY",
    "ELEVEN_API_KEY",
    "ELEVEN_VOICE_ID",
    "SLIDEPILOT_STT_PROVIDER",
    "SLIDEPILOT_LLM_PROVIDER",
    "SLIDEPILOT_TTS_PROVIDER",
    "SLIDEPILOT_STT_MODEL",
    "SLIDEPILOT_LLM_MODEL",
    "SLIDEPILOT_TTS_MODEL",
    "SLIDEPILOT_TTS_VOICE",
)


@pytest.fixture
def env(monkeypatch):
    """A clean slate: backend/.env.local is loaded on import, so clear every key."""
    for key in KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("LIVEKIT_URL", "ws://127.0.0.1:7880")
    return monkeypatch


def test_without_provider_keys_everything_runs_on_livekit_inference(env):
    cfg = model_config()
    assert (cfg.stt_provider, cfg.llm_provider, cfg.tts_provider) == ("livekit", "livekit", "livekit")
    assert describe(cfg) == {"llm": "openai/gpt-4.1-mini", "stt": "deepgram/nova-3", "tts": "cartesia/sonic-3"}


def test_deepgram_and_openai_keys(env):
    env.setenv("DEEPGRAM_API_KEY", "dg")
    env.setenv("OPENAI_API_KEY", "sk")
    cfg = model_config()
    assert (cfg.stt_provider, cfg.llm_provider, cfg.tts_provider) == ("deepgram", "openai", "deepgram")
    assert cfg.llm_model == "gpt-4.1"


def test_claude_wins_the_llm_and_elevenlabs_uses_the_voice_id(env):
    env.setenv("ANTHROPIC_API_KEY", "sk-ant")
    env.setenv("OPENAI_API_KEY", "sk")
    env.setenv("ELEVEN_API_KEY", "sk_el")
    env.setenv("ELEVEN_VOICE_ID", "voice123")
    cfg = model_config()
    assert (cfg.llm_provider, cfg.llm_model) == ("anthropic", "claude-opus-5-5")
    assert (cfg.tts_provider, cfg.tts_voice) == ("elevenlabs", "voice123")


def test_an_elevenlabs_voice_id_never_leaks_into_another_tts(env):
    env.setenv("OPENAI_API_KEY", "sk")
    env.setenv("ELEVEN_VOICE_ID", "voice123")
    cfg = model_config()
    assert cfg.tts_provider == "openai"
    assert cfg.tts_voice == "coral"


def test_explicit_provider_and_validation(env):
    env.setenv("OPENAI_API_KEY", "sk")
    env.setenv("SLIDEPILOT_LLM_PROVIDER", "google")
    assert model_config().llm_model == "gemini-2.5-flash"
    env.setenv("SLIDEPILOT_LLM_PROVIDER", "nope")
    with pytest.raises(ValueError, match="SLIDEPILOT_LLM_PROVIDER"):
        model_config()


def test_turn_handling_uses_local_models_off_cloud(env):
    local = turn_handling(model_config())
    assert "turn_detection" in local

    env.setenv("LIVEKIT_URL", "wss://demo.livekit.cloud")
    cloud = turn_handling(model_config())
    assert "turn_detection" not in cloud  # LiveKit's cloud turn detector
    for options in (local, cloud):
        assert options["endpointing"] == {"min_delay": 0.6, "max_delay": 1.5}
        assert options["interruption"] == {"mode": "vad"}


@pytest.mark.parametrize(
    ("detail", "expected"),
    [
        ("Error code: 429 - {'code': 'insufficient_quota'}", "says the account is out of credits"),
        ("Error code: 401 - Incorrect API key provided", "rejected the API key"),
        ("Error code: 429 - too many requests", "is rate limiting requests"),
    ],
)
def test_errors_are_described_in_plain_language(detail, expected):
    ev = SimpleNamespace(
        error=SimpleNamespace(type="llm_error", error=Exception(detail)),
        source=SimpleNamespace(provider="api.openai.com"),
    )
    message = describe_error(ev)  # type: ignore[arg-type]
    assert message.startswith("The language model failed: api.openai.com")
    assert expected in message


def test_every_keyed_provider_joins_the_fallback_chain(env):
    for key in ("OPENAI_API_KEY", "GOOGLE_API_KEY", "DEEPGRAM_API_KEY", "ELEVEN_API_KEY"):
        env.setenv(key, "test-key")
    cfg = model_config()
    assert cfg.llm_providers == ("openai", "google")
    assert cfg.tts_providers == ("deepgram", "elevenlabs", "openai")
    assert isinstance(build_llm(cfg), llm.FallbackAdapter)
    assert isinstance(build_tts(cfg), tts.FallbackAdapter)


def test_a_single_provider_is_used_directly(env):
    env.setenv("DEEPGRAM_API_KEY", "test-key")
    env.setenv("OPENAI_API_KEY", "test-key")
    env.setenv("SLIDEPILOT_TTS_PROVIDER", "deepgram")
    cfg = model_config()
    assert cfg.tts_providers == ("deepgram",)
    assert not isinstance(build_tts(cfg), tts.FallbackAdapter)
    assert not isinstance(build_llm(cfg), llm.FallbackAdapter)


def test_livekit_inference_backs_up_the_chain_on_cloud(env):
    env.setenv("LIVEKIT_URL", "wss://demo.livekit.cloud")
    env.setenv("OPENAI_API_KEY", "test-key")
    assert model_config().llm_providers == ("openai", "livekit")


def test_speech_to_text_listens_for_nova_and_each_decks_jargon():
    for deck in all_decks().values():
        keyterms = stt_context(deck)["keyterms"]
        assert keyterms[0] == "Nova"
        assert deck.keyterms and set(deck.keyterms) <= set(keyterms)
        assert len(keyterms) == len(set(keyterms))
    assert "VAD" in stt_context(all_decks()["voice-ai-agents"])["keyterms"]


def test_only_the_known_sdk_shutdown_noise_is_hidden():
    def unraisable(error: BaseException, where: object) -> SimpleNamespace:
        return SimpleNamespace(exc_value=error, object=where)

    assert _is_known_ffi_noise(unraisable(AssertionError(), FfiHandle.__del__))
    assert not _is_known_ffi_noise(unraisable(RuntimeError("real bug"), FfiHandle.__del__))
    assert not _is_known_ffi_noise(unraisable(AssertionError(), describe_error))
