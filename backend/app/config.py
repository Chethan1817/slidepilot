"""Settings shared by the API server and the agent worker, read from the environment
(the package loads backend/.env.local first, so local development needs no exports)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DECKS_DIR = BACKEND_DIR / "decks"
FRONTEND_DIST = BACKEND_DIR.parent / "frontend" / "dist"

# The API dispatches this agent into every new presentation room; the worker registers
# under the same name (explicit dispatch, so the agent never joins unrelated rooms).
# Give a second stack its own name to share one LiveKit server.
AGENT_NAME = os.getenv("SLIDEPILOT_AGENT_NAME", "slidepilot-presenter")


@dataclass(frozen=True)
class LiveKitSettings:
    url: str
    api_key: str
    api_secret: str

    @property
    def configured(self) -> bool:
        return bool(self.url and self.api_key and self.api_secret)


def livekit_settings() -> LiveKitSettings:
    return LiveKitSettings(
        url=os.getenv("LIVEKIT_URL", ""),
        api_key=os.getenv("LIVEKIT_API_KEY", ""),
        api_secret=os.getenv("LIVEKIT_API_SECRET", ""),
    )


def cors_origins() -> list[str]:
    raw = os.getenv("SLIDEPILOT_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]
