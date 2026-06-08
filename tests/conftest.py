"""Shared test fixtures: a deterministic offline AI and an in-memory store."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_service import AIService  # noqa: E402
from config import Config  # noqa: E402
from db import Store  # noqa: E402


def fake_completer(system: str, user: str, model: str) -> str:
    """Deterministic 'translation': echoes the source so output changes when the
    source changes (drives revisions) and keeps glossary terms visible (drives
    glossary-preserved counts)."""
    if "Translate this:" in user:
        core = user.split("Translate this:")[-1].strip()
    else:
        core = user.strip().splitlines()[-1].strip()
    if system.startswith("你是会议纪要助手"):
        return "要点：" + core[:20]
    return "译文 " + core


class Clock:
    """Manually advanced clock for deterministic time-based tests."""
    def __init__(self, start: float = 1000.0):
        self.t = start

    def __call__(self) -> float:
        return self.t

    def tick(self, dt: float) -> float:
        self.t += dt
        return self.t


@pytest.fixture
def config():
    return Config(minimax_api_key="test-key", minimax_model="MiniMax-Text-01",
                  minimax_fallback_model="MiniMax-M2", revision_window_sec=5.0,
                  context_segments=4, ai_retries=1)


@pytest.fixture
def ai(config):
    return AIService(config, completer=fake_completer)


@pytest.fixture
def store():
    s = Store(":memory:")
    yield s
    s.close()


@pytest.fixture
def clock():
    return Clock()
