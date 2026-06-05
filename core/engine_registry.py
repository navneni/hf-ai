from __future__ import annotations
import importlib
import logging
import pkgutil
from pathlib import Path

from core.engine_base import BaseSignalEngine

logger = logging.getLogger(__name__)


class EngineRegistry:
    """Auto-discovers and manages all signal engine plugins."""

    def __init__(self):
        self._engines: dict[str, BaseSignalEngine] = {}

    def register(self, engine: BaseSignalEngine) -> None:
        if engine.name in self._engines:
            raise ValueError(f"Engine '{engine.name}' already registered. Use unique names.")
        self._engines[engine.name] = engine
        logger.debug("Registered engine: %s (weight=%.4f)", engine.name, engine.weight)

    def discover(self, package_path: str = "signals") -> None:
        """
        Walk package_path recursively, instantiate every class that extends
        BaseSignalEngine, and register it. Broken modules are skipped with a warning.
        """
        path_obj = Path(package_path)
        if not path_obj.exists():
            logger.warning("signals/ directory not found — no engines registered")
            return

        for finder, mod_name, _ in pkgutil.walk_packages(
            [str(path_obj)], prefix=f"{package_path.replace('/', '.')}."
        ):
            try:
                module = importlib.import_module(mod_name)
            except Exception as e:
                logger.warning("Could not import %s: %s", mod_name, e)
                continue

            for attr_name in dir(module):
                obj = getattr(module, attr_name)
                if (
                    isinstance(obj, type)
                    and issubclass(obj, BaseSignalEngine)
                    and obj is not BaseSignalEngine
                    and hasattr(obj, "name")
                    and hasattr(obj, "weight")
                ):
                    try:
                        self.register(obj())
                    except ValueError:
                        pass  # duplicate — already registered from another import path

    def resolve(self, names: list[str] | str) -> list[BaseSignalEngine]:
        if names == "all":
            return list(self._engines.values())
        if isinstance(names, str):
            names = [names]
        missing = [n for n in names if n not in self._engines]
        if missing:
            logger.warning("Requested engines not found: %s", missing)
        return [self._engines[n] for n in names if n in self._engines]

    def initialize_all(self, config: dict) -> None:
        """Call initialize(config) on every registered engine (sequential, not threaded)."""
        for engine in self._engines.values():
            try:
                engine.initialize(config)
            except Exception as e:
                logger.error("Engine %s failed to initialize: %s", engine.name, e)

    def list_active(self) -> list[dict]:
        return [e.get_metadata() for e in self._engines.values()]

    def __len__(self) -> int:
        return len(self._engines)

    def __contains__(self, name: str) -> bool:
        return name in self._engines
