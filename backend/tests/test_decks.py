import re
from pathlib import Path

from app.decks import all_decks
from app.presentation import PresentationState
from app.prompts import build_instructions, present_prompt


def test_every_deck_has_five_or_six_slides():
    decks = all_decks()
    assert decks, "no decks found"
    for deck in decks.values():
        assert 5 <= len(deck.slides) <= 6, deck.id
        assert len({slide.id for slide in deck.slides}) == len(deck.slides), deck.id


def test_every_deck_uses_themes_and_icons_the_web_app_has():
    web = Path(__file__).resolve().parents[2] / "frontend" / "src"
    themes = set(re.findall(r"\.slide-theme-([a-z-]+)", (web / "index.css").read_text()))
    icon_map = (web / "components" / "Icon.tsx").read_text().split("const ICONS", 1)[1]
    icons = set(re.findall(r"^\s+'?([a-z-]+)'?: [A-Z]", icon_map, re.MULTILINE))
    for deck in all_decks().values():
        assert deck.theme in themes, deck.id
        for slide in deck.slides:
            for item in slide.items:
                assert item.icon is None or item.icon in icons, (deck.id, slide.id, item.icon)


def test_instructions_cover_every_slide_and_current_state():
    deck = all_decks()["voice-ai-agents"]
    state = PresentationState(slide_count=len(deck.slides), current=2, mode="paused", bookmark=1)
    text = build_instructions(deck, state)

    for index, slide in enumerate(deck.slides, start=1):
        assert f"## Slide {index} of {len(deck.slides)}: {slide.title}" in text
        assert slide.notes in text
    assert 'Slide 3 of 6, "The 800 ms budget" is on screen.' in text
    assert "would continue at slide 2" in text


def test_last_slide_prompt_asks_for_wrap_up():
    deck = all_decks()["science-of-sleep"]
    assert "final slide" in present_prompt(deck, len(deck.slides) - 1)
    assert "final slide" not in present_prompt(deck, 0, opening=True)
