"""HTTP API: the deck catalogue and LiveKit session tokens.

    uv run uvicorn app.server:app --reload --port 8000

When frontend/dist exists (after `npm run build`), the built web app is served too, so
the whole product runs from one URL.
"""

from __future__ import annotations

import json
import secrets
from datetime import timedelta
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from livekit import api
from pydantic import BaseModel, Field

from .config import AGENT_NAME, FRONTEND_DIST, cors_origins, livekit_settings
from .decks import Deck, all_decks, get_deck
from .models import (
    ENGINES,
    describe,
    langgraph_model,
    model_config,
    pipeline,
    voice_pipeline_available,
)

app = FastAPI(title="Slidepilot API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class SessionRequest(BaseModel):
    deck_id: str
    name: str = Field(default="Guest", max_length=64)
    engine: Literal["livekit", "langgraph_pipeline"] = "livekit"


class SessionResponse(BaseModel):
    server_url: str
    participant_token: str
    room_name: str
    participant_identity: str


@app.get("/api/health")
def health() -> dict[str, Any]:
    cfg = model_config()
    lk = livekit_settings()
    return {
        "status": "ok",
        "livekit_configured": lk.configured,
        "livekit": {"url": lk.url, "cloud": cfg.livekit_cloud},
        "models": describe(cfg),
        "pipeline": pipeline(cfg),
        "engines": [
            {"id": "livekit", "name": ENGINES["livekit"], "available": True, "llm": cfg.llm_model},
            {
                "id": "langgraph_pipeline",
                "name": ENGINES["langgraph_pipeline"],
                "available": voice_pipeline_available(),
                "llm": langgraph_model(cfg),
            },
        ],
    }


@app.get("/api/decks")
def list_decks() -> list[dict[str, Any]]:
    return [
        {**_summary(deck), "slide_count": len(deck.slides), "cover": _public_slides(deck)[0]}
        for deck in all_decks().values()
    ]


@app.get("/api/decks/{deck_id}")
def deck_detail(deck_id: str) -> dict[str, Any]:
    deck = _deck_or_404(deck_id)
    return {**_summary(deck), "slides": _public_slides(deck)}


@app.post("/api/sessions")
def create_session(request: SessionRequest) -> SessionResponse:
    """Mint a token for a fresh room; joining it dispatches the presenter with this deck."""
    lk = livekit_settings()
    if not lk.configured:
        raise HTTPException(
            status_code=503,
            detail="LiveKit isn't configured. Set LIVEKIT_URL, LIVEKIT_API_KEY and "
            "LIVEKIT_API_SECRET in backend/.env.local, then restart the API.",
        )
    deck = _deck_or_404(request.deck_id)
    if request.engine == "langgraph_pipeline" and not voice_pipeline_available():
        raise HTTPException(
            status_code=400,
            detail="The LangGraph pipeline needs OPENAI_API_KEY and DEEPGRAM_API_KEY in backend/.env.local.",
        )

    room_name = f"slidepilot-{deck.id}-{secrets.token_hex(4)}"
    identity = f"viewer-{secrets.token_hex(4)}"
    metadata = json.dumps({"deck_id": deck.id, "engine": request.engine})
    dispatch = api.RoomAgentDispatch(agent_name=AGENT_NAME, metadata=metadata)
    token = (
        api.AccessToken(lk.api_key, lk.api_secret)
        .with_identity(identity)
        .with_name(request.name)
        .with_ttl(timedelta(hours=1))
        .with_grants(api.VideoGrants(room_join=True, room=room_name))
        .with_room_config(api.RoomConfiguration(agents=[dispatch]))
        .to_jwt()
    )
    return SessionResponse(
        server_url=lk.url,
        participant_token=token,
        room_name=room_name,
        participant_identity=identity,
    )


def _deck_or_404(deck_id: str) -> Deck:
    deck = get_deck(deck_id)
    if deck is None:
        raise HTTPException(status_code=404, detail=f"No deck called {deck_id!r}.")
    return deck


def _summary(deck: Deck) -> dict[str, Any]:
    return deck.model_dump(exclude={"slides", "keyterms"})


def _public_slides(deck: Deck) -> list[dict[str, Any]]:
    # Speaker notes are the presenter's private material.
    return [slide.model_dump(exclude={"notes"}) for slide in deck.slides]


if FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def web_app(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(status_code=404)
        file = (FRONTEND_DIST / path).resolve()
        if path and file.is_file() and FRONTEND_DIST in file.parents:
            return FileResponse(file)
        return FileResponse(FRONTEND_DIST / "index.html")
