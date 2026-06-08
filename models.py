"""Shared data types for the translation pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

INTERIM = "interim"
FINAL = "final"


@dataclass
class Segment:
    """One unit of recognized speech and its evolving translation.

    A segment is born ``interim`` (volatile ASR preview), becomes ``final`` when the
    recognizer commits, and may be **revised** afterwards while inside the revision
    window — each revision bumps :attr:`version` and sets :attr:`corrected`.
    """
    id: int
    session_id: str
    source: str
    translation: str = ""
    status: str = INTERIM
    version: int = 1
    corrected: bool = False
    source_lang: str = "English"
    glossary_hits: int = 0
    # timeline (epoch seconds)
    t_audio: float = 0.0        # when the speech happened (client-reported)
    t_recognized: float = 0.0   # when ASR committed the text (server clock)
    t_translated: float = 0.0   # when the translation completed (server clock)

    @property
    def latency_ms(self) -> float:
        """End-to-end latency: audio in -> subtitle out."""
        if self.t_translated and self.t_audio:
            return max(0.0, (self.t_translated - self.t_audio) * 1000.0)
        return 0.0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["latency_ms"] = round(self.latency_ms, 1)
        return d
