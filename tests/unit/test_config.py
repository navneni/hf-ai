"""Unit tests for ConfigManager."""
from __future__ import annotations
import pytest

from core.config import ConfigManager, ConfigError


def test_get_dot_notation(config_file):
    cfg = ConfigManager(config_file)
    assert cfg.get("mongodb.uri") == "mongodb://localhost:27017"
    assert cfg.get("mongodb.db_name") == "hf_ai_engine_test"


def test_get_nested_key(config_file):
    cfg = ConfigManager(config_file)
    assert cfg.get("engines.technical.weight") == 0.20
    assert cfg.get("engines.technical.enabled") is True


def test_missing_key_returns_default(config_file):
    cfg = ConfigManager(config_file)
    assert cfg.get("nonexistent.key") is None
    assert cfg.get("nonexistent.key", "fallback") == "fallback"


def test_missing_file_raises():
    with pytest.raises(ConfigError):
        ConfigManager("nonexistent/path.yaml")


def test_get_section(config_file):
    cfg = ConfigManager(config_file)
    section = cfg.get_section("mongodb")
    assert isinstance(section, dict)
    assert "uri" in section


def test_threshold_files_loaded(tmp_path):
    engine_yaml = tmp_path / "engine.yaml"
    us_yaml = tmp_path / "us_thresholds.yaml"
    engine_yaml.write_text("mongodb:\n  uri: mongodb://localhost:27017\n  db_name: test\n")
    us_yaml.write_text("graham_pe: 15\nbuffett_roe: 15\n")
    cfg = ConfigManager(str(engine_yaml))
    assert cfg.get("us_thresholds.graham_pe") == 15
