"""Per-session orchestration: ASR -> translate -> revise -> emit.

:class:`SessionPipeline` wires the engines together and pushes UI events through an
``emit`` callback (the app forwards them over the WebSocket). It is transport- and
framework-agnostic, so the same object is driven by the live mic path, the scripted
replay path, and the integration tests.

Latency note: ``end_to_end_ms`` is measured server-side from *recognition commit*
(``t_recognized``) to *subtitle ready* (``t_translated``) — a single, skew-free
clock. Browser ASR adds a separate, client-measured delay shown in the UI.
"""
from __future__ import annotations

import time
from typing import Callable, Optional

from ai_service import AIService, AIError
from asr_engine import ASRIngestor, NEW, REVISE, INTERIM_PREVIEW
from config import Config
from db import Store
from glossary import Glossary
from metrics import MetricsCollector
from models import Segment, FINAL
from revision_engine import RevisionWindow
from translation_engine import TranslationEngine, PRESENTATION

Emit = Callable[[dict], None]


class SessionPipeline:
    def __init__(self, session_id: str, ai: AIService, config: Config, *,
                 store: Optional[Store] = None, glossary: Optional[Glossary] = None,
                 mode: str = PRESENTATION, source_lang: str = "English",
                 emit: Optional[Emit] = None,
                 shared_metrics: Optional[MetricsCollector] = None,
                 clock: Callable[[], float] = time.time) -> None:
        self.session_id = session_id
        self.ai = ai
        self.cfg = config
        self.store = store
        self.source_lang = source_lang
        self._clock = clock
        self.emit = emit or (lambda ev: None)
        self.glossary = glossary or Glossary()
        self.asr = ASRIngestor(session_id, source_lang=source_lang,
                               revision_window_sec=config.revision_window_sec, clock=clock)
        self.translator = TranslationEngine(ai, self.glossary, mode=mode,
                                            context_segments=config.context_segments, clock=clock)
        self.revision = RevisionWindow(config.revision_window_sec, clock=clock)
        self.metrics = MetricsCollector(clock=clock)
        # optional process-wide collector the dashboard aggregates over
        self.shared_metrics = shared_metrics
        if store:
            store.create_session(session_id, source_lang, mode, started_at=clock())

    # ------------------------------------------------------------------ config
    def set_mode(self, mode: str) -> None:
        self.translator.set_mode(mode)
        self.track("mode_switch", {"mode": self.translator.mode})

    def add_glossary_term(self, term: str, translation: str | None = None) -> list[Segment]:
        """Add a term and re-render any in-window segment that mentions it."""
        self.glossary.add(term, translation)
        if self.store:
            self.store.save_glossary({term: self.glossary.terms[term]})
        targets = self.revision.glossary_targets(self.asr.segments, term)
        revised = [self._retranslate(seg, reason="glossary") for seg in targets]
        return revised

    # -------------------------------------------------------------------- input
    def on_interim(self, text: str) -> None:
        ev = self.asr.ingest(text, is_final=False)
        if ev.kind == INTERIM_PREVIEW:
            self.emit({"type": "interim", "text": ev.interim_text})

    def on_final(self, text: str, t_audio: float = 0.0) -> Optional[Segment]:
        """Ingest a committed ASR result and run it through translate/revise."""
        ev = self.asr.ingest(text, is_final=True, t_audio=t_audio)
        if ev.segment is None:
            return None
        self.track("subtitle_render")
        if ev.kind == NEW:
            return self._translate(ev.segment)
        if ev.kind == REVISE:
            return self._retranslate(ev.segment, reason="asr")
        return None

    # ------------------------------------------------------------- translation
    def _translate(self, seg: Segment) -> Segment:
        try:
            self.translator.translate_segment(seg, self.asr.segments)
            ok = True
        except AIError:
            seg.translation = "[翻译失败]"
            seg.t_translated = self._clock()
            ok = False
            self.track("translation_error")
        self._record(seg, success=ok)
        if ok:
            self.track("translation_success")
        self.emit({"type": "segment", "segment": seg.to_dict()})
        self._persist(seg)
        return seg

    def _retranslate(self, seg: Segment, *, reason: str) -> Segment:
        before = seg.translation
        try:
            self.translator.translate_segment(seg, self.asr.segments, correcting=True)
        except AIError:
            return seg  # keep the previous (good) translation on failure
        if seg.translation and seg.translation != before:
            self.revision.mark_corrected(seg)
            self.metrics.record_correction()
            if self.shared_metrics:
                self.shared_metrics.record_correction()
            self.track("subtitle_corrected", {"reason": reason})
            self.emit({"type": "revision", "reason": reason,
                       "previous": before, "segment": seg.to_dict()})
            self._persist(seg)
        return seg

    # --------------------------------------------------------------- summarize
    def summarize(self) -> str:
        body = "\n".join(s.translation for s in self.asr.segments
                         if s.status == FINAL and s.translation)
        if not body:
            return ""
        try:
            text = self.ai.summarize(body).text
        except AIError:
            return ""
        self.emit({"type": "summary", "text": text})
        return text

    # ---------------------------------------------------------------- internals
    def _record(self, seg: Segment, *, success: bool) -> None:
        e2e = max(0.0, (seg.t_translated - seg.t_recognized) * 1000.0)
        glo = self.glossary.enforce(seg.translation, seg.source)
        translate_ms = self.translator.last_result.latency_ms if self.translator.last_result else 0.0
        for sink in (self.metrics, self.shared_metrics):
            if sink is not None:
                sink.record_translation(
                    end_to_end_ms=e2e, translate_ms=translate_ms,
                    source_chars=len(seg.source), target_chars=len(seg.translation),
                    glossary_present=glo.hits, glossary_preserved=glo.preserved, success=success)

    def _persist(self, seg: Segment) -> None:
        if self.store:
            self.store.upsert_segment(seg)

    def track(self, event: str, meta: Optional[dict] = None) -> None:
        self.metrics.track(event)
        if self.shared_metrics:
            self.shared_metrics.track(event)
        if self.store:
            self.store.log_event(self.session_id, event, meta)

    def snapshot(self) -> dict:
        snap = self.metrics.snapshot()
        if self.store:
            self.store.save_metrics(self.session_id, snap)
        return snap

    def close(self) -> None:
        if self.store:
            self.store.end_session(self.session_id, self._clock())
