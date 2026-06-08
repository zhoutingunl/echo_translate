"""ASR ingestion engine.

Speech recognition itself runs in the browser (Web Speech API) for true
zero-latency streaming; this server-side engine owns the *segment lifecycle*:
it turns a stream of ``(text, is_final)`` recognizer updates into stable
:class:`Segment` objects, assigns ids/timestamps, and decides when a new final
is actually a **revision** of the previous one rather than a fresh utterance.

Keeping this logic server-side (and pure) means it is unit-testable and shared by
both the live microphone path and the scripted replay/demo path.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Callable, Optional

from models import Segment, INTERIM, FINAL

# what kind of change an ingest produced
NEW = "new"           # a brand-new committed segment
REVISE = "revise"     # the previous segment's source was corrected/extended
INTERIM_PREVIEW = "interim"  # volatile preview, not yet committed


@dataclass
class ASREvent:
    kind: str
    segment: Optional[Segment]      # the affected committed segment (None for pure interim)
    interim_text: str = ""          # volatile preview text (for INTERIM_PREVIEW)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _tokens(text: str) -> list[str]:
    return _norm(text).lower().split()


def _is_extension(prev: str, new: str) -> bool:
    """True if ``new`` looks like a corrected extension of ``prev``.

    Captures the design's canonical case ("storage" -> "distributed storage")
    and simple prefix growth ("we are" -> "we are building"). We require the
    shorter token sequence to be a sub-run of the longer at either end.
    """
    pt, nt = _tokens(prev), _tokens(new)
    if not pt or not nt or pt == nt:
        return False
    short, long = (pt, nt) if len(pt) <= len(nt) else (nt, pt)
    if len(short) > len(long) * 0.8 + 1:
        return False  # too different in length to be the same utterance
    # prefix or suffix containment of the shorter run inside the longer
    return long[: len(short)] == short or long[-len(short):] == short


class ASRIngestor:
    """Maintains the ordered list of segments for one session."""

    def __init__(self, session_id: str, *, source_lang: str = "English",
                 revision_window_sec: float = 5.0,
                 clock: Callable[[], float] = time.time) -> None:
        self.session_id = session_id
        self.source_lang = source_lang
        self.revision_window_sec = revision_window_sec
        self._clock = clock
        self.segments: list[Segment] = []
        self._next_id = 1
        self._interim = ""

    # ----------------------------------------------------------------- helpers
    @property
    def last_final(self) -> Optional[Segment]:
        for seg in reversed(self.segments):
            if seg.status == FINAL:
                return seg
        return None

    def _new_segment(self, source: str, t_audio: float, now: float) -> Segment:
        seg = Segment(
            id=self._next_id, session_id=self.session_id, source=source,
            status=FINAL, source_lang=self.source_lang,
            t_audio=t_audio or now, t_recognized=now,
        )
        self._next_id += 1
        self.segments.append(seg)
        return seg

    # ------------------------------------------------------------------- ingest
    def ingest(self, text: str, *, is_final: bool, t_audio: float = 0.0,
               now: Optional[float] = None) -> ASREvent:
        """Feed one recognizer update; return the resulting :class:`ASREvent`."""
        now = self._clock() if now is None else now
        text = _norm(text)
        if not text:
            return ASREvent(kind=INTERIM_PREVIEW, segment=None, interim_text="")

        if not is_final:
            self._interim = text
            return ASREvent(kind=INTERIM_PREVIEW, segment=None, interim_text=text)

        # committed (final) result
        self._interim = ""
        prev = self.last_final
        if prev is not None and (now - prev.t_recognized) <= self.revision_window_sec \
                and _is_extension(prev.source, text) and len(text) >= len(prev.source):
            # the recognizer revised/extended the previous utterance in place
            prev.source = text
            prev.version += 1
            prev.t_recognized = now
            return ASREvent(kind=REVISE, segment=prev)

        return ASREvent(kind=NEW, segment=self._new_segment(text, t_audio, now))

    def revise(self, seg_id: int, new_source: str,
               now: Optional[float] = None) -> Optional[ASREvent]:
        """Explicitly revise a committed segment's source (used by replay mode)."""
        now = self._clock() if now is None else now
        for seg in self.segments:
            if seg.id == seg_id:
                seg.source = _norm(new_source)
                seg.version += 1
                seg.t_recognized = now
                return ASREvent(kind=REVISE, segment=seg)
        return None
