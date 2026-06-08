"""QoS metrics (避免伪指标).

A small, pure, in-memory aggregator. Everything it reports is derived from real
events recorded by the pipeline — no fabricated numbers:

* **End-to-end latency** (audio in -> subtitle out): avg / P50 / P95 / P99
* **Translation latency** (the AI call alone)
* **Translation success rate**
* **Correction rate** — share of segments revised after first render
* **Glossary hit rate** — of glossary terms that appeared, how many kept their form
* **RTF (real-time factor)** — processing time / wall-clock; < 1 means we keep up
"""
from __future__ import annotations

import time
from collections import deque
from typing import Callable


def percentile(values: list[float], p: float) -> float:
    """Nearest-rank percentile (p in 0..100)."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    k = (p / 100.0) * (len(ordered) - 1)
    lo = int(k)
    hi = min(lo + 1, len(ordered) - 1)
    frac = k - lo
    return ordered[lo] * (1 - frac) + ordered[hi] * frac


class MetricsCollector:
    def __init__(self, maxlen: int = 2000, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self.e2e_ms: deque[float] = deque(maxlen=maxlen)
        self.translate_ms: deque[float] = deque(maxlen=maxlen)
        self.segments = 0
        self.corrections = 0
        self.translation_success = 0
        self.translation_error = 0
        self.glossary_present = 0
        self.glossary_preserved = 0
        self.total_source_chars = 0
        self.total_target_chars = 0
        self.events: dict[str, int] = {}
        self._first_ts: float | None = None
        self._last_ts: float | None = None
        self._processing_ms = 0.0

    # ------------------------------------------------------------------ record
    def _touch(self) -> None:
        now = self._clock()
        if self._first_ts is None:
            self._first_ts = now
        self._last_ts = now

    def record_translation(self, *, end_to_end_ms: float, translate_ms: float,
                           source_chars: int = 0, target_chars: int = 0,
                           glossary_present: int = 0, glossary_preserved: int = 0,
                           success: bool = True) -> None:
        self._touch()
        self.segments += 1
        if success:
            self.translation_success += 1
            if end_to_end_ms > 0:
                self.e2e_ms.append(end_to_end_ms)
            if translate_ms > 0:
                self.translate_ms.append(translate_ms)
                self._processing_ms += translate_ms
            self.total_source_chars += source_chars
            self.total_target_chars += target_chars
            self.glossary_present += glossary_present
            self.glossary_preserved += glossary_preserved
        else:
            self.translation_error += 1

    def record_correction(self) -> None:
        self._touch()
        self.corrections += 1

    def track(self, event: str) -> None:
        self.events[event] = self.events.get(event, 0) + 1

    # ---------------------------------------------------------------- reporting
    def session_elapsed_sec(self) -> float:
        if self._first_ts is None or self._last_ts is None:
            return 0.0
        return max(0.0, self._last_ts - self._first_ts)

    def rtf(self) -> float:
        elapsed = self.session_elapsed_sec()
        if elapsed <= 0:
            return 0.0
        return (self._processing_ms / 1000.0) / elapsed

    def snapshot(self) -> dict:
        e2e = list(self.e2e_ms)
        attempts = self.translation_success + self.translation_error
        return {
            "segments": self.segments,
            "corrections": self.corrections,
            "correction_rate": round(self.corrections / self.segments, 4) if self.segments else 0.0,
            "translation_success_rate": round(self.translation_success / attempts, 4) if attempts else 0.0,
            "translation_error": self.translation_error,
            "glossary_hit_rate": round(self.glossary_preserved / self.glossary_present, 4) if self.glossary_present else 1.0,
            "glossary_present": self.glossary_present,
            "latency_ms": {
                "avg": round(sum(e2e) / len(e2e), 1) if e2e else 0.0,
                "p50": round(percentile(e2e, 50), 1),
                "p95": round(percentile(e2e, 95), 1),
                "p99": round(percentile(e2e, 99), 1),
                "max": round(max(e2e), 1) if e2e else 0.0,
            },
            "translate_ms": {
                "avg": round(sum(self.translate_ms) / len(self.translate_ms), 1) if self.translate_ms else 0.0,
                "p95": round(percentile(list(self.translate_ms), 95), 1),
            },
            "rtf": round(self.rtf(), 3),
            "session_elapsed_sec": round(self.session_elapsed_sec(), 1),
            "total_source_chars": self.total_source_chars,
            "total_target_chars": self.total_target_chars,
            "events": dict(self.events),
        }
