"""Translation engine — incremental, context-aware, glossary-aware.

Wraps :class:`AIService` with the policy that turns a recognized :class:`Segment`
into a Chinese translation:

* feeds the last few segments as **context** so renderings stay coherent;
* injects the **glossary** and measures adherence;
* honours the active **mode** (``presentation`` = fluent / ``meeting`` = low-latency).

It mutates the segment in place (``translation``, ``glossary_hits``, ``version``,
``t_translated``) and returns it.
"""
from __future__ import annotations

import time
from typing import Callable, Optional

from ai_service import AIService, AIResult
from glossary import Glossary
from models import Segment, FINAL

PRESENTATION = "presentation"
MEETING = "meeting"


class TranslationEngine:
    def __init__(self, ai: AIService, glossary: Optional[Glossary] = None, *,
                 mode: str = PRESENTATION, context_segments: int = 4,
                 clock: Callable[[], float] = time.time) -> None:
        self.ai = ai
        self.glossary = glossary or Glossary()
        self.mode = mode
        self.context_segments = context_segments
        self._clock = clock
        # last AIResult, exposed so callers can record model/latency for metrics
        self.last_result: Optional[AIResult] = None

    def set_mode(self, mode: str) -> None:
        self.mode = MEETING if mode == MEETING else PRESENTATION

    def context_pairs(self, segments: list[Segment], before: Segment) -> list[tuple[str, str]]:
        """Up to ``context_segments`` translated finals preceding ``before``."""
        out: list[tuple[str, str]] = []
        for seg in segments:
            if seg.id >= before.id:
                break
            if seg.status == FINAL and seg.translation:
                out.append((seg.source, seg.translation))
        return out[-self.context_segments:]

    def translate_segment(self, seg: Segment, segments: Optional[list[Segment]] = None,
                          *, correcting: bool = False) -> Segment:
        """Translate ``seg`` in place. ``segments`` supplies context if given."""
        context = self.context_pairs(segments, seg) if segments else None
        glo_lines = self.glossary.prompt_lines()
        fn = self.ai.retranslate if correcting else self.ai.translate
        result = fn(seg.source, source_lang=seg.source_lang, context=context,
                    glossary_lines=glo_lines, mode=self.mode)
        self.last_result = result
        seg.translation = result.text
        seg.glossary_hits = self.glossary.enforce(result.text, seg.source).hits
        seg.t_translated = self._clock()
        if correcting:
            seg.corrected = True
            seg.version += 1
        return seg
