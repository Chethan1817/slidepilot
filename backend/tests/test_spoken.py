"""SpokenText: tool calls the model writes into a reply are kept out of the speech and
recovered, while ordinary speech streams through unchanged."""

from __future__ import annotations

import random

import pytest

from app.decks import all_decks
from app.langgraph_agent import build_graph
from app.presenter import Presenter
from app.spoken import PRESENTER_TOOLS, SpokenText

# Written-out calls GPT-4.1 actually produced, with the call each one meant.
LEAKS = [
    ("Great, let's dive in.\n\nfunctions.resume_presentation ", "resume_presentation", {}),
    ("Want me to continue from there? \n\nshow_slide(slide_number=3)", "show_slide", {"slide_number": 3}),
    ("Shall I keep going from here?\n\nshow_slide({slide_number: 3})", "show_slide", {"slide_number": 3}),
    ("Let's jump to the tools slide.\n\npresent_from_slide 5", "present_from_slide", {"slide_number": 5}),
    ('I\'ll bring up the latency slide.\n\n(functions.show_slide { "slide_number": 3 })', "show_slide", {"slide_number": 3}),
    ("Let's look at how it all fits together.\n\ncalling show_slide(slide_number=2)", "show_slide", {"slide_number": 2}),
    ("Sure, back to the tools slide.\n\nCalling functions.present_from_slide 5", "present_from_slide", {"slide_number": 5}),
]

# Speech full of near misses: words that start a tool's name, "functions.", brackets, quotes.
SPEECH = (
    "Let me show you how it works. Models call functions. Then we present the results; "
    "it's \"fast\" (really) and we'll resume shortly. Show me, present company excepted, resume. "
    "We call this a pipeline, and calling it is easy"
)


def stream(text: str, seed: int) -> tuple[str, SpokenText]:
    """Feed `text` in random token-sized pieces; return what was let through to speak."""
    rng, spoken, said, i = random.Random(seed), SpokenText(), [], 0
    while i < len(text):
        size = rng.randint(1, 6)
        said.append(spoken.feed(text[i : i + size]))
        i += size
    said.append(spoken.flush())
    return "".join(said), spoken


@pytest.mark.parametrize(("reply", "name", "args"), LEAKS)
def test_a_written_out_call_is_not_spoken_but_recovered(reply: str, name: str, args: dict[str, int]):
    speech = reply[: reply.rindex("\n\n") + 2]
    for seed in range(50):
        said, spoken = stream(reply, seed)
        assert said == spoken.text == speech
        call = spoken.leaked_call()
        assert call is not None and (call.name, call.args) == (name, args)


def test_ordinary_speech_streams_through_unchanged():
    for seed in range(50):
        said, spoken = stream(SPEECH, seed)
        assert said == SPEECH
        assert spoken.leaked_call() is None


def test_a_held_back_word_waits_for_one_more_piece_at_most():
    spoken = SpokenText()
    assert spoken.feed("Let me show") == "Let me "  # "show" might become show_slide...
    assert spoken.feed(" you") == "show you"  # ...until the next piece settles it


def test_a_call_missing_its_argument_is_dropped_but_not_made():
    said, spoken = stream("Here it comes.\n\nshow_slide(", seed=1)
    assert said == "Here it comes.\n\n"
    assert spoken.leaked_call() is None


def test_both_engines_offer_exactly_the_tools_spoken_text_knows():
    presenter = Presenter(all_decks()["voice-ai-agents"], room=None)  # type: ignore[arg-type]
    assert {tool.id for tool in presenter.tools} == set(PRESENTER_TOOLS)
    graph = build_graph(model=_NoModel(), actions=None)  # type: ignore[arg-type]
    assert set(graph.nodes["tools"].bound.tools_by_name) == set(PRESENTER_TOOLS)


class _NoModel:
    def bind_tools(self, tools: object) -> _NoModel:
        return self


ANSWER = "Great question, adults need seven to nine hours. Teenagers need more."


@pytest.mark.parametrize(
    "closing", ["Let me show you that slide now.", "Let me show you the details.", "Now, let me pull it up for you."]
)
def test_an_answer_closing_with_a_slide_announcement_drops_it(closing: str):
    for seed in range(30):
        rng, spoken, said, i = random.Random(seed), SpokenText(drop_closing_announcement=True), [], 0
        reply = f"{ANSWER} {closing}"
        while i < len(reply):
            size = rng.randint(1, 6)
            said.append(spoken.feed(reply[i : i + size]))
            i += size
        said.append(spoken.flush())
        assert "".join(said).strip() == ANSWER
        assert spoken.text.strip() == ANSWER


def test_an_announcement_followed_by_more_answer_is_kept():
    reply = "Good question! Let me pull up the latency slide. People expect a reply within a second."
    spoken = SpokenText(drop_closing_announcement=True)
    said = "".join(spoken.feed(reply[i : i + 4]) for i in range(0, len(reply), 4)) + spoken.flush()
    assert said == reply


def test_other_closing_sentences_are_kept():
    reply = "Adults need seven to nine hours. Let me know if you'd like more."
    spoken = SpokenText(drop_closing_announcement=True)
    assert spoken.feed(reply) + spoken.flush() == reply
    narration = "That's the pipeline. Let's take a look at what comes next."
    assert SpokenText().feed(narration) == narration  # narrations keep theirs
