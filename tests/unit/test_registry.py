"""Unit tests for EngineRegistry."""
from __future__ import annotations
import pytest

from core.engine_base import BaseSignalEngine, DataBundle, Signal
from core.engine_registry import EngineRegistry


class _DummyEngine(BaseSignalEngine):
    name = "dummy"
    weight = 0.10

    def compute(self, data: DataBundle) -> Signal:
        return Signal("neutral", 50.0, self.weight, "dummy", {})


class _DummyEngine2(BaseSignalEngine):
    name = "dummy2"
    weight = 0.05

    def compute(self, data: DataBundle) -> Signal:
        return Signal("bullish", 70.0, self.weight, "dummy2", {})


def test_register_engine():
    reg = EngineRegistry()
    reg.register(_DummyEngine())
    assert "dummy" in reg
    assert len(reg) == 1


def test_register_duplicate_raises():
    reg = EngineRegistry()
    reg.register(_DummyEngine())
    with pytest.raises(ValueError, match="already registered"):
        reg.register(_DummyEngine())


def test_list_active():
    reg = EngineRegistry()
    reg.register(_DummyEngine())
    reg.register(_DummyEngine2())
    active = reg.list_active()
    names = [e["name"] for e in active]
    assert "dummy" in names
    assert "dummy2" in names


def test_resolve_all():
    reg = EngineRegistry()
    reg.register(_DummyEngine())
    reg.register(_DummyEngine2())
    engines = reg.resolve("all")
    assert len(engines) == 2


def test_resolve_by_name():
    reg = EngineRegistry()
    reg.register(_DummyEngine())
    reg.register(_DummyEngine2())
    engines = reg.resolve(["dummy"])
    assert len(engines) == 1
    assert engines[0].name == "dummy"


def test_resolve_missing_name_skipped(caplog):
    reg = EngineRegistry()
    reg.register(_DummyEngine())
    engines = reg.resolve(["dummy", "nonexistent"])
    assert len(engines) == 1


def test_discover_empty_dir(tmp_path):
    reg = EngineRegistry()
    reg.discover(str(tmp_path))  # empty dir — no crash
    assert len(reg) == 0


def test_engine_metadata():
    e = _DummyEngine()
    meta = e.get_metadata()
    assert meta["name"] == "dummy"
    assert meta["weight"] == 0.10
    assert "required_data" in meta
