import json

import pytest
from fastapi.testclient import TestClient
from livekit import api

from app.config import AGENT_NAME
from app.server import app

client = TestClient(app)


@pytest.fixture
def livekit_env(monkeypatch):
    monkeypatch.setenv("LIVEKIT_URL", "wss://example.livekit.cloud")
    monkeypatch.setenv("LIVEKIT_API_KEY", "devkey")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "a-test-secret-that-is-at-least-32-chars")


def test_deck_list_hides_speaker_notes():
    decks = client.get("/api/decks").json()
    assert {deck["id"] for deck in decks} == {"voice-ai-agents", "science-of-sleep", "lab-to-pharmacy"}
    for deck in decks:
        assert deck["slide_count"] == 6
        assert "notes" not in deck["cover"]

    detail = client.get("/api/decks/voice-ai-agents").json()
    assert len(detail["slides"]) == 6
    assert all("notes" not in slide for slide in detail["slides"])


def test_unknown_deck_is_404():
    assert client.get("/api/decks/nope").status_code == 404


def test_session_token_dispatches_presenter_with_deck(livekit_env):
    response = client.post("/api/sessions", json={"deck_id": "science-of-sleep", "name": "Chethan"})
    assert response.status_code == 200
    body = response.json()
    assert body["server_url"] == "wss://example.livekit.cloud"

    claims = api.TokenVerifier("devkey", "a-test-secret-that-is-at-least-32-chars").verify(
        body["participant_token"]
    )
    assert claims.identity == body["participant_identity"]
    assert claims.name == "Chethan"
    assert claims.video.room == body["room_name"]
    assert claims.video.room_join
    (dispatch,) = claims.room_config.agents
    assert dispatch.agent_name == AGENT_NAME
    assert json.loads(dispatch.metadata) == {"deck_id": "science-of-sleep", "engine": "livekit"}


def test_session_without_livekit_config_explains_what_to_set(monkeypatch):
    for name in ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"):
        monkeypatch.setenv(name, "")
    response = client.post("/api/sessions", json={"deck_id": "voice-ai-agents"})
    assert response.status_code == 503
    assert "LIVEKIT_URL" in response.json()["detail"]


def test_health_reports_the_pipeline_without_secrets(monkeypatch):
    monkeypatch.setenv("LIVEKIT_URL", "ws://127.0.0.1:7880")
    body = client.get("/api/health").json()
    assert body["livekit"] == {"url": "ws://127.0.0.1:7880", "cloud": False}
    assert set(body["pipeline"]) == {"stt", "llm", "tts"}
    assert all(step.keys() == {"provider", "model"} for chain in body["pipeline"].values() for step in chain)
    assert "secret" not in str(body).lower()


def test_session_can_ask_for_the_langgraph_pipeline(livekit_env, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("DEEPGRAM_API_KEY", "test-key")
    engines = {engine["id"]: engine["available"] for engine in client.get("/api/health").json()["engines"]}
    assert engines == {"livekit": True, "langgraph_pipeline": True}
    body = client.post("/api/sessions", json={"deck_id": "voice-ai-agents", "engine": "langgraph_pipeline"}).json()
    claims = api.TokenVerifier("devkey", "a-test-secret-that-is-at-least-32-chars").verify(body["participant_token"])
    assert json.loads(claims.room_config.agents[0].metadata)["engine"] == "langgraph_pipeline"


def test_the_pipeline_without_a_deepgram_key_is_refused(livekit_env, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("DEEPGRAM_API_KEY", raising=False)
    response = client.post("/api/sessions", json={"deck_id": "voice-ai-agents", "engine": "langgraph_pipeline"})
    assert response.status_code == 400
    assert "DEEPGRAM_API_KEY" in response.json()["detail"]
    assert client.post("/api/sessions", json={"deck_id": "voice-ai-agents", "engine": "langgraph"}).status_code == 422
