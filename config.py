"""Central configuration for EchoTranslate.

All tunables come from environment variables (loaded from a git-ignored ``.env``
by :func:`load_config`). Nothing here ever hard-codes a secret — the API key
lives only in ``.env``. Tests construct :class:`Config` directly with overrides,
so this module has no import-time side effects beyond reading ``os.environ``.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from typing import Any


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _get_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _get_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Config:
    # --- MiniMax (primary AI backend) ---
    minimax_base_url: str = "https://api.minimaxi.com/anthropic"
    minimax_api_key: str = ""
    minimax_model: str = "MiniMax-Text-01"
    minimax_fallback_model: str = "MiniMax-M2"

    # --- Hermes (secondary AI backend) ---
    hermes_enabled: bool = False
    hermes_base: str = "http://10.210.32.30:8787"
    hermes_model: str = "MiniMax-M3"

    # --- server ---
    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = False

    # --- storage ---
    db_path: str = "data/echo.db"

    # --- pipeline tuning ---
    revision_window_sec: float = 5.0
    context_segments: int = 4
    ai_timeout_sec: float = 20.0
    ai_retries: int = 2

    # supported source languages -> human label (extensible)
    languages: dict[str, str] = field(default_factory=lambda: {
        "en-US": "English",
        "ja-JP": "Japanese",
        "ko-KR": "Korean",
    })

    @property
    def has_ai_key(self) -> bool:
        return bool(self.minimax_api_key)

    def public_dict(self) -> dict[str, Any]:
        """Config safe to expose to the browser (no secrets)."""
        d = asdict(self)
        d.pop("minimax_api_key", None)
        return d


def load_config() -> Config:
    """Build a :class:`Config` from the environment, loading ``.env`` first."""
    try:
        from dotenv import load_dotenv

        load_dotenv()  # loads ./.env if present; never overrides real env vars
    except Exception:
        # python-dotenv is optional at runtime; env vars still work without it.
        pass

    return Config(
        minimax_base_url=_get("MINIMAX_BASE_URL", "https://api.minimaxi.com/anthropic").rstrip("/"),
        minimax_api_key=_get("MINIMAX_API_KEY", ""),
        minimax_model=_get("MINIMAX_MODEL", "MiniMax-Text-01"),
        minimax_fallback_model=_get("MINIMAX_FALLBACK_MODEL", "MiniMax-M2"),
        hermes_enabled=_get_bool("HERMES_ENABLED", False),
        hermes_base=_get("HERMES_BASE", "http://10.210.32.30:8787").rstrip("/"),
        hermes_model=_get("HERMES_MODEL", "MiniMax-M3"),
        host=_get("HOST", "127.0.0.1"),
        port=_get_int("PORT", 8000),
        debug=_get_bool("DEBUG", False),
        db_path=_get("DB_PATH", "data/echo.db"),
        revision_window_sec=float(_get_int("REVISION_WINDOW_SEC", 5)),
        context_segments=_get_int("CONTEXT_SEGMENTS", 4),
        ai_timeout_sec=float(_get_int("AI_TIMEOUT_SEC", 20)),
        ai_retries=_get_int("AI_RETRIES", 2),
    )
