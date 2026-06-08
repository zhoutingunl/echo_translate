"""Revision window — the auto-correction policy (核心功能).

Traditional live-caption systems can never take a word back: once a wrong
subtitle is shown, it stays wrong. EchoTranslate keeps the most recent N seconds
of subtitles *mutable*. This module decides **what** may still be corrected and
**why**; the actual re-translation is done by the translation engine.

Three correction triggers:

* **ASR revision** — the recognizer changed a segment's source text.
* **Glossary update** — a term was added/changed, so in-window lines mentioning it
  should be re-rendered.
"""
from __future__ import annotations

import time
from typing import Callable, Iterable

from models import Segment, FINAL


class RevisionWindow:
    def __init__(self, window_sec: float = 5.0,
                 clock: Callable[[], float] = time.time) -> None:
        self.window_sec = window_sec
        self._clock = clock

    def in_window(self, seg: Segment, now: float | None = None) -> bool:
        now = self._clock() if now is None else now
        return (now - seg.t_recognized) <= self.window_sec

    def revisable(self, seg: Segment, now: float | None = None) -> bool:
        """A segment may still be corrected if it is final and inside the window."""
        return seg.status == FINAL and self.in_window(seg, now)

    def glossary_targets(self, segments: Iterable[Segment], term: str,
                         now: float | None = None) -> list[Segment]:
        """In-window segments whose source mentions ``term`` (need re-render)."""
        term_low = term.lower()
        out = []
        for seg in segments:
            if self.revisable(seg, now) and term_low in seg.source.lower():
                out.append(seg)
        return out

    @staticmethod
    def mark_corrected(seg: Segment) -> Segment:
        seg.version += 1
        seg.corrected = True
        return seg
