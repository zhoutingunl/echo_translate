import importlib

import config as config_mod
from config import Config, load_config


def test_defaults_and_helpers():
    c = Config()
    assert c.minimax_model == "MiniMax-Text-01"
    assert c.has_ai_key is False
    c2 = Config(minimax_api_key="k")
    assert c2.has_ai_key is True


def test_public_dict_hides_secret():
    c = Config(minimax_api_key="secret")
    pub = c.public_dict()
    assert "minimax_api_key" not in pub
    assert pub["minimax_model"] == "MiniMax-Text-01"


def test_env_parsing(monkeypatch):
    monkeypatch.setenv("PORT", "9999")
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("HERMES_ENABLED", "no")
    monkeypatch.setenv("CONTEXT_SEGMENTS", "notanint")  # falls back to default
    monkeypatch.setenv("MINIMAX_API_KEY", "abc")
    cfg = load_config()
    assert cfg.port == 9999 and cfg.debug is True
    assert cfg.hermes_enabled is False
    assert cfg.context_segments == 4
    assert cfg.minimax_api_key == "abc"


def test_get_int_bool_helpers(monkeypatch):
    monkeypatch.delenv("MISSING_X", raising=False)
    assert config_mod._get_int("MISSING_X", 7) == 7
    monkeypatch.setenv("MISSING_X", "")
    assert config_mod._get_int("MISSING_X", 7) == 7
    assert config_mod._get_bool("MISSING_X", True) is True
