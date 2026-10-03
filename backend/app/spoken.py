"""What the presenter says out loud: its reply, minus any tool call written into it.

Now and then GPT-4.1 writes the call it means to make into its reply instead of making
it, usually as the last line: "Sure, let's jump ahead.\n\npresent_from_slide 5" or
'(functions.show_slide { "slide_number": 3 })'. Spoken, that is gibberish, and the slide
never changes. Both engines run every reply through SpokenText, which keeps such a call
out of the voice and the transcript and recovers it, so the engine can make it instead.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

# The presenter's tools in both engines, with the whole-number arguments each takes.
PRESENTER_TOOLS: Mapping[str, Sequence[str]] = {
    "show_slide": ("slide_number",),
    "resume_presentation": (),
    "present_from_slide": ("slide_number",),
    "end_session": (),
}

# Brackets and quotes a written-out call may open with.
_OPENERS = "(`'\"[{<"
# Words a written-out call may follow: "calling show_slide(slide_number=2)".
_LEAD_INS = ("calling", "call", "invoking")

# How a sentence announcing a slide change starts and what it says: "Let me show you that
# slide now", "Now let me pull it up".
_ANNOUNCE_STARTS = tuple(
    lead + core
    for lead in ("", "now ", "now, ", "so ", "so, ", "okay, ", "ok, ", "alright, ", "great, ", "sure, ")
    for core in ("let me ", "let's ", "i'll ", "i will ", "i'm going to ", "here's ", "here is ")
)
_ANNOUNCES = re.compile(
    r"\b(show|pull(ing)? (it |that |this )?up|bring(ing)? (it |that |this )?up|put (it |that )?up|"
    r"take (a )?look|switch|jump|turn to|go to)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class LeakedCall:
    """A tool call the model wrote into its reply."""

    name: str
    args: dict[str, int]
    call_id: str = field(default_factory=lambda: f"call_{uuid.uuid4().hex[:24]}")


class SpokenText:
    """Filters a streamed reply: feed() it each piece as it arrives and speak what it returns.

    Text that might be the start of a call (a trailing "show" could become "show_slide") is
    held back until the next piece settles it, which delays speech by a token at most.
    """

    def __init__(
        self, tools: Mapping[str, Sequence[str]] = PRESENTER_TOOLS, *, drop_closing_announcement: bool = False
    ) -> None:
        self._tools = tools
        # For answers: the slide is already up when the answer ends, so a closing "Let me
        # show you that slide now" is wrong.
        self._closing = _ClosingLine() if drop_closing_announcement else None
        names = "|".join(re.escape(name) for name in sorted(tools, key=len, reverse=True))
        # A tool's name, maybe after a word like "calling", in OpenAI's internal "functions."
        # namespace and opened with a bracket or quote. Its arguments, if any, follow it.
        self._call = re.compile(
            rf"(?<!\w)(?:(?i:{'|'.join(_LEAD_INS)})\s*:?\s*)?[{re.escape(_OPENERS)}]*(?:functions\.)?(?P<name>{names})(?!\w)"
        )
        names_written = [*tools, *(f"functions.{name}" for name in tools)]
        self._call_starts = [lead + name for lead in ("", *(f"{word} " for word in _LEAD_INS)) for name in names_written]
        self._reach = max(map(len, self._call_starts)) + 2
        self.text = ""
        """Everything let through so far."""
        self._held = ""
        self._leak: str | None = None

    def feed(self, piece: str) -> str:
        """Take the next piece of the reply; return the part that can be spoken now."""
        if self._leak is not None:
            self._leak += piece
            return ""
        text = self._held + piece
        if match := self._call.search(text):
            speak, self._leak, self._held = text[: match.start()], text[match.start() :], ""
        else:
            cut = self._hold_from(text)
            speak, self._held = text[:cut], text[cut:]
        if self._closing is not None:
            speak = self._closing.feed(speak)
        self.text += speak
        return speak

    def flush(self) -> str:
        """The reply is complete: return what was held back but turned out to be speech."""
        speak, self._held = self._held, ""
        if self._closing is not None:
            speak = self._closing.feed(speak) + self._closing.flush()
        self.text += speak
        return speak

    def leaked_call(self) -> LeakedCall | None:
        """The call the model wrote out, if the reply had one with all its arguments."""
        if self._leak is None:
            return None
        match = self._call.match(self._leak)
        assert match is not None  # the leak begins where the pattern matched
        params = self._tools[match["name"]]
        numbers = [int(n) for n in re.findall(r"\d+", self._leak[match.end() :])]
        if len(numbers) < len(params):
            return None
        return LeakedCall(match["name"], dict(zip(params, numbers, strict=False)))

    def _hold_from(self, text: str) -> int:
        """Where a call might be starting at the end of `text` (its length if nowhere)."""
        for start in range(max(0, len(text) - self._reach), len(text)):
            if start and _is_word_char(text[start - 1]):
                continue  # mid-word, so not the start of a name
            tail = " ".join(text[start:].lstrip(_OPENERS).lower().split(" "))
            if any(call_start.startswith(tail) for call_start in self._call_starts):
                return start
        return len(text)


class _ClosingLine:
    """Holds back a sentence that announces a slide ("Let me show you that slide now") and
    drops it if it turns out to end an answer. Followed by more of the answer, it's spoken
    after all, and a reply that is only the announcement (a bridge while the answer is
    fetched) keeps it. Other sentences are held for a word at most, while their start is
    unclear."""

    def __init__(self) -> None:
        self._said = False  # some of the answer has been let through
        self._held = ""
        self._announced = 0  # length of the finished announcements at the start of _held
        self._mode = "start"  # deciding about a new sentence, "candidate" or "pass"
        self._last = ""

    def feed(self, text: str) -> str:
        return "".join(self._step(char) for char in text)

    def flush(self) -> str:
        sentence = self._held[self._announced :]
        if not self._said:
            text = self._held  # nothing but the announcement: it's the bridge, so keep it
        elif self._mode == "candidate" and _ANNOUNCES.search(sentence):
            text = ""  # it closes an answer; finished announcements before it go too
        else:
            text = sentence
        self._held, self._announced, self._mode, self._last = "", 0, "start", ""
        return text

    def _step(self, char: str) -> str:
        sentence_ended = self._last in ".!?" and char.isspace()
        self._last = char
        if self._mode == "pass":
            if sentence_ended:
                self._mode = "start"
            self._said = self._said or not char.isspace()
            return char
        self._held += char
        if self._mode == "start":
            sentence = self._held[self._announced :].lstrip().lower().replace("\u2019", "'")
            if not sentence:
                return ""
            if sentence.startswith(_ANNOUNCE_STARTS):
                self._mode = "candidate"
            elif any(start.startswith(sentence) for start in _ANNOUNCE_STARTS):
                return ""  # could still become one
            else:
                self._mode = "pass"
                return self._release()
        if self._mode == "candidate" and sentence_ended:
            self._mode = "start"
            if _ANNOUNCES.search(self._held[self._announced :]):
                self._announced = len(self._held)
                return ""
            return self._release()
        return ""

    def _release(self) -> str:
        text, self._held, self._announced = self._held, "", 0
        self._said = self._said or bool(text.strip())
        return text


def _is_word_char(char: str) -> bool:
    return char.isalnum() or char == "_"
