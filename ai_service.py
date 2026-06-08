"""Unified AI backend for EchoTranslate.

Everything that needs a language model goes through :class:`AIService`:

* ``translate``    — source segment -> fluent Chinese
* ``retranslate``  — same, but with extra context for *correcting* an earlier line
* ``summarize``    — condense a batch of segments into a short Chinese summary

Provider strategy (chosen after measuring latency, see README §架构):

1. **MiniMax-Text-01** via the MiniMax Anthropic-compatible endpoint — ~0.9 s,
   no "thinking" overhead, the real-time primary.
2. **MiniMax-M2** — higher quality, emits ``thinking`` blocks we strip; used when
   the primary errors.
3. **Hermes WebUI** (optional, VPN-only) — last-resort failover on 429/outage.

The HTTP layer is isolated behind ``_completer`` so unit tests inject a fake and
run fully offline. Real runtime uses :meth:`_http_complete`.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Callable, Optional

import requests

from config import Config


@dataclass
class AIResult:
    text: str
    model: str           # which model actually answered
    latency_ms: float
    fallback_used: bool  # True if the primary model failed and we fell back


class AIError(RuntimeError):
    """Raised when every configured provider fails."""


# A completer turns (system, user) into raw model text. Injectable for tests.
Completer = Callable[[str, str, str], str]


class AIService:
    SUMMARY_SENTINEL = "[no-content]"

    def __init__(self, config: Config, *, completer: Optional[Completer] = None,
                 session: Optional[requests.Session] = None) -> None:
        self.cfg = config
        self._session = session or requests.Session()
        # Test seam: if provided, every completion goes through this instead of HTTP.
        self._completer = completer
        # ordered provider list: (model, kind)
        self._providers: list[tuple[str, str]] = []
        if config.minimax_model:
            self._providers.append((config.minimax_model, "minimax"))
        if config.minimax_fallback_model and config.minimax_fallback_model != config.minimax_model:
            self._providers.append((config.minimax_fallback_model, "minimax"))
        if config.hermes_enabled and config.hermes_model:
            self._providers.append((config.hermes_model, "hermes"))
        # observability counters
        self.calls = 0
        self.errors = 0

    # ------------------------------------------------------------------ public
    def translate(self, source: str, *, source_lang: str = "English",
                  context: Optional[list[tuple[str, str]]] = None,
                  glossary_lines: str = "", mode: str = "presentation") -> AIResult:
        """Translate one segment to Chinese."""
        source = (source or "").strip()
        if not source:
            return AIResult(text="", model="(noop)", latency_ms=0.0, fallback_used=False)
        system = self._system_prompt(source_lang, glossary_lines, mode, correcting=False)
        user = self._user_prompt(source, context)
        return self._complete(system, user)

    def retranslate(self, source: str, *, source_lang: str = "English",
                    context: Optional[list[tuple[str, str]]] = None,
                    glossary_lines: str = "", mode: str = "presentation") -> AIResult:
        """Re-translate a segment for correction, given improved context."""
        source = (source or "").strip()
        if not source:
            return AIResult(text="", model="(noop)", latency_ms=0.0, fallback_used=False)
        system = self._system_prompt(source_lang, glossary_lines, mode, correcting=True)
        user = self._user_prompt(source, context)
        return self._complete(system, user)

    def summarize(self, chinese_text: str) -> AIResult:
        chinese_text = (chinese_text or "").strip()
        if not chinese_text:
            return AIResult(text="", model="(noop)", latency_ms=0.0, fallback_used=False)
        system = ("你是会议纪要助手。请用简体中文，将下面的同传译文压缩成 3-5 条要点，"
                  "保留关键术语，不要添加未出现的信息。")
        return self._complete(system, chinese_text)

    # --------------------------------------------------------------- prompting
    def _system_prompt(self, source_lang: str, glossary_lines: str,
                       mode: str, *, correcting: bool) -> str:
        base = (
            f"You are a professional real-time interpreter translating {source_lang} "
            "speech into natural, fluent Simplified Chinese. "
            "Output ONLY the Chinese translation — no quotes, no notes, no source text."
        )
        if mode == "meeting":
            style = (" Optimize for low latency and brevity: translate the given chunk "
                     "directly even if the sentence is incomplete; keep it concise.")
        else:  # presentation
            style = (" Optimize for a complete, well-formed rendering that reads smoothly "
                     "for an audience; you may smooth minor disfluencies.")
        correct = ""
        if correcting:
            correct = (" The recognized text was just revised/extended; produce the best "
                       "corrected translation of the full text below.")
        glo = f"\n{glossary_lines}" if glossary_lines else ""
        return base + style + correct + glo

    def _user_prompt(self, source: str, context: Optional[list[tuple[str, str]]]) -> str:
        if context:
            lines = ["Recent context (source => prior translation):"]
            for src, dst in context:
                lines.append(f"  {src} => {dst}")
            lines.append("")
            lines.append(f"Translate this: {source}")
            return "\n".join(lines)
        return source

    # ------------------------------------------------------------- completion
    def _complete(self, system: str, user: str) -> AIResult:
        if self._completer is not None:
            model = self._providers[0][0] if self._providers else "test"
            t0 = time.time()
            try:
                text = self._completer(system, user, model)
            except Exception as e:  # surface as AIError so callers handle uniformly
                self.errors += 1
                raise AIError(str(e)) from e
            self.calls += 1
            return AIResult(text=_clean(text), model=model,
                            latency_ms=(time.time() - t0) * 1000, fallback_used=False)

        last_err: Exception | None = None
        for idx, (model, kind) in enumerate(self._providers):
            for attempt in range(max(1, self.cfg.ai_retries)):
                t0 = time.time()
                try:
                    raw = (self._http_complete(system, user, model) if kind == "minimax"
                           else self._hermes_complete(system, user, model))
                    self.calls += 1
                    return AIResult(text=_clean(raw), model=model,
                                    latency_ms=(time.time() - t0) * 1000,
                                    fallback_used=idx > 0)
                except _Retryable as e:  # transient -> retry then fall through to next provider
                    last_err = e
                    self.errors += 1
                    time.sleep(0.4 * (attempt + 1))
                except Exception as e:  # non-retryable -> next provider immediately
                    last_err = e
                    self.errors += 1
                    break
        raise AIError(f"all providers failed: {last_err}")

    def _http_complete(self, system: str, user: str, model: str) -> str:
        """Call the MiniMax Anthropic-compatible endpoint; return concatenated text."""
        url = f"{self.cfg.minimax_base_url}/v1/messages"
        headers = {
            "x-api-key": self.cfg.minimax_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        body = {
            "model": model,
            "max_tokens": 1024,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        try:
            r = self._session.post(url, headers=headers, json=body,
                                   timeout=self.cfg.ai_timeout_sec)
        except requests.RequestException as e:
            raise _Retryable(str(e)) from e
        if r.status_code == 429 or r.status_code >= 500:
            raise _Retryable(f"http {r.status_code}")
        if r.status_code != 200:
            raise RuntimeError(f"http {r.status_code}: {r.text[:200]}")
        data = r.json()
        return _extract_text(data)

    def _hermes_complete(self, system: str, user: str, model: str) -> str:
        """Minimal Hermes (8787) SSE call used only as a last-resort failover."""
        base = self.cfg.hermes_base
        sid = self._session.post(f"{base}/api/session/new", json={"model": model},
                                 timeout=15).json()["session"]["session_id"]
        try:
            message = f"{system}\n\n{user}"
            stream_id = self._session.post(
                f"{base}/api/chat/start",
                json={"session_id": sid, "message": message, "model": model},
                timeout=15).json()["stream_id"]
            full, event, deadline = "", "", time.time() + self.cfg.ai_timeout_sec
            with self._session.get(f"{base}/api/chat/stream",
                                   params={"stream_id": stream_id},
                                   stream=True, timeout=(10, self.cfg.ai_timeout_sec)) as resp:
                for raw in resp.iter_lines():
                    if time.time() > deadline:
                        break
                    if not raw:
                        continue
                    line = raw.decode("utf-8")
                    if line.startswith("event:"):
                        event = line[6:].strip()
                    elif line.startswith("data:"):
                        payload = json.loads(line[5:].strip())
                        if event == "token":
                            full += payload.get("text", "")
                        elif event in ("done", "error"):
                            break
            if not full:
                raise _Retryable("hermes empty response")
            return full
        finally:
            try:
                self._session.post(f"{base}/api/chat/cancel",
                                   json={"session_id": sid}, timeout=5)
            except Exception:
                pass


class _Retryable(Exception):
    """Transient error worth a retry / provider switch (429, 5xx, network)."""


def _extract_text(anthropic_response: dict) -> str:
    """Pull only ``text`` blocks from an Anthropic-style response (drops thinking)."""
    parts = []
    for block in anthropic_response.get("content", []) or []:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "".join(parts)


def _clean(text: str) -> str:
    text = (text or "").strip()
    # models sometimes wrap output in quotes or add a leading label — strip lightly
    if len(text) >= 2 and text[0] in "“\"'「" and text[-1] in "”\"'」":
        text = text[1:-1].strip()
    return text
