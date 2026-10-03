"""Pure presentation state: which slide is showing and where the guided run stands.

Kept free of LiveKit so the navigation rules can be unit-tested on their own.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Mode = Literal["idle", "presenting", "paused", "finished"]

# Words spoken before a show_slide call that count as an answer, not just a bridge.
ANSWER_WORDS = 12


@dataclass
class PresentationState:
    slide_count: int
    current: int = 0
    """Slide on screen (0-based)."""
    mode: Mode = "idle"
    bookmark: int = 0
    """Where the guided run is, so "continue" returns there even after Q&A jumped elsewhere."""
    started: set[int] = field(default_factory=set)
    completed: set[int] = field(default_factory=set)

    def begin(self, index: int) -> None:
        """The guided run starts presenting `index`."""
        self.mode = "presenting"
        self.current = index
        self.bookmark = index
        self.started.add(index)

    def complete(self, index: int) -> int | None:
        """`index` was presented in full. Returns the next slide, or None at the end."""
        self.completed.add(index)
        if index + 1 < self.slide_count:
            return index + 1
        self.mode = "finished"
        return None

    def pause(self) -> bool:
        """Pause the guided run (the person spoke or pressed pause). True if it was running."""
        if self.mode != "presenting":
            return False
        self.mode = "paused"
        return True

    def resume_index(self) -> int | None:
        """Where "continue" picks up: the bookmarked slide unless it was already finished."""
        index = self.bookmark if self.bookmark not in self.completed else self.bookmark + 1
        return index if index < self.slide_count else None

    def is_partial(self, index: int) -> bool:
        """The slide's narration was started but cut off before the end."""
        return index in self.started and index not in self.completed

    def valid(self, index: int) -> bool:
        return 0 <= index < self.slide_count
