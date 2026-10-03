"""Deck model and loader. Decks live as JSON files in backend/decks/."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from .config import DECKS_DIR

Layout = Literal["cover", "steps", "stat", "cards", "bullets", "closing"]


class SlideItem(BaseModel):
    title: str
    body: str = ""
    icon: str | None = None
    value: str | None = None
    share: float | None = Field(default=None, ge=0, le=1)
    """Bar length (0-1) for breakdown rows on `stat` slides."""


class Stat(BaseModel):
    value: str
    label: str


class Callout(BaseModel):
    label: str
    text: str


class Slide(BaseModel):
    id: str
    layout: Layout
    title: str
    kicker: str | None = None
    subtitle: str | None = None
    items: list[SlideItem] = []
    stat: Stat | None = None
    callout: Callout | None = None
    footnote: str | None = None
    notes: str
    """Speaker notes: what the presenter knows beyond the visible text. Never sent to the browser."""


class Deck(BaseModel):
    id: str
    title: str
    description: str
    category: str
    theme: str
    minutes: int
    suggested_questions: list[str] = []
    keyterms: list[str] = []
    """Words people may say that speech recognition could miss (acronyms, jargon, names).
    The agent's speech-to-text listens for them. Not sent to the browser."""
    slides: list[Slide] = Field(min_length=1)


def load_deck(path: Path) -> Deck:
    return Deck.model_validate_json(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def all_decks() -> dict[str, Deck]:
    decks = (load_deck(path) for path in sorted(DECKS_DIR.glob("*.json")))
    return {deck.id: deck for deck in decks}


def get_deck(deck_id: str) -> Deck | None:
    return all_decks().get(deck_id)
