"""Terminology memory (术语记忆).

A :class:`Glossary` maps a source-language term to its required Chinese rendering.
For technical terms the "translation" is often the term itself (e.g. ``Kubernetes``
should stay ``Kubernetes`` rather than become ``库伯内特斯``).

The glossary plays two roles:

1. **Prompting** — :meth:`prompt_lines` is injected into the translator's system
   prompt so the model produces the right term up front.
2. **Measurement** — :meth:`enforce` reports how many glossary terms were hit and
   whether the required rendering survived, feeding the *glossary hit rate* metric.

We deliberately do **not** blindly string-replace the model output: a naive
replace corrupts inflected text and produces dishonest metrics. Enforcement only
*measures*; correctness is driven by the prompt.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class GlossaryResult:
    text: str
    hits: int          # glossary terms present in the source
    preserved: int     # of those, how many kept the required rendering


@dataclass
class Glossary:
    terms: dict[str, str] = field(default_factory=dict)

    def add(self, term: str, translation: str | None = None) -> None:
        term = term.strip()
        if not term:
            return
        self.terms[term] = (translation or term).strip()

    def remove(self, term: str) -> None:
        self.terms.pop(term.strip(), None)

    def update(self, mapping: dict[str, str]) -> None:
        for k, v in mapping.items():
            self.add(k, v)

    def __len__(self) -> int:
        return len(self.terms)

    def prompt_lines(self) -> str:
        """Glossary rendered for injection into the system prompt."""
        if not self.terms:
            return ""
        rows = [f"  - {src} -> {dst}" for src, dst in sorted(self.terms.items())]
        return "Keep these terms fixed (do not transliterate or re-translate):\n" + "\n".join(rows)

    def find_terms(self, source: str) -> list[str]:
        """Glossary source-terms that appear in ``source`` (case-insensitive, word-ish)."""
        found = []
        low = source.lower()
        for term in self.terms:
            # word boundary for ascii terms; plain containment for CJK terms
            if re.search(r"[a-z0-9]", term.lower()):
                if re.search(rf"\b{re.escape(term.lower())}\b", low):
                    found.append(term)
            elif term in source:
                found.append(term)
        return found

    def enforce(self, translation: str, source: str) -> GlossaryResult:
        """Measure glossary adherence of a translation against its source."""
        present = self.find_terms(source)
        preserved = 0
        for term in present:
            required = self.terms[term]
            if required.lower() in translation.lower():
                preserved += 1
        return GlossaryResult(text=translation, hits=len(present), preserved=preserved)
