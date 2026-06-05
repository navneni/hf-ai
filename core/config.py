from __future__ import annotations
import logging
import os
import threading
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


class ConfigError(Exception):
    pass


class ConfigManager:
    """
    Loads engine.yaml + us/india threshold files + .env.
    Hot-reloads when files change on disk (watchdog if available, else polling).
    Access values with dot-notation: config.get("mongodb.uri")
    """

    REQUIRED_KEYS = ["mongodb.uri", "mongodb.db_name"]

    def __init__(self, path: str = "config/engine.yaml"):
        self._path = Path(path)
        self._lock = threading.RLock()
        load_dotenv(override=False)
        self._data: dict = {}
        self._load()
        self._validate()
        self._start_watcher()

    # ------------------------------------------------------------------ load

    def _load(self) -> None:
        with self._lock:
            if not self._path.exists():
                raise ConfigError(f"Config file not found: {self._path}")
            with open(self._path) as f:
                data = yaml.safe_load(f) or {}

            # Merge threshold files if referenced
            cfg_dir = self._path.parent
            for key, filename in [
                ("us_thresholds", "us_thresholds.yaml"),
                ("india_thresholds", "india_thresholds.yaml"),
            ]:
                fp = cfg_dir / filename
                if fp.exists():
                    with open(fp) as f:
                        data[key] = yaml.safe_load(f) or {}

            # Env overrides for sensitive values
            data.setdefault("mongodb", {})
            data["mongodb"]["uri"] = os.getenv("MONGODB_URI", data["mongodb"].get("uri", "mongodb://localhost:27017"))

            self._data = data

    def _validate(self) -> None:
        for key in self.REQUIRED_KEYS:
            if self.get(key) is None:
                raise ConfigError(f"Required config key missing: '{key}'")

    # ------------------------------------------------------------------ access

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            parts = key.split(".")
            val = self._data
            for p in parts:
                if not isinstance(val, dict):
                    return default
                val = val.get(p)
                if val is None:
                    return default
            return val

    def get_section(self, key: str) -> dict:
        val = self.get(key)
        return val if isinstance(val, dict) else {}

    def reload(self) -> None:
        try:
            self._load()
            logger.info("Config reloaded from %s", self._path)
        except Exception as e:
            logger.error("Config reload failed: %s", e)

    # ------------------------------------------------------------------ hot reload

    def _start_watcher(self) -> None:
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler

            mgr = self

            class _Handler(FileSystemEventHandler):
                def on_modified(self, event):
                    if not event.is_directory and Path(event.src_path).name in (
                        self._watched_files
                    ):
                        mgr.reload()

                _watched_files = {
                    "engine.yaml", "us_thresholds.yaml", "india_thresholds.yaml"
                }

            observer = Observer()
            observer.schedule(_Handler(), str(self._path.parent), recursive=False)
            observer.daemon = True
            observer.start()
        except ImportError:
            # watchdog not installed — fall back to polling thread
            self._start_polling_watcher()

    def _start_polling_watcher(self) -> None:
        import time

        def _poll():
            last = self._path.stat().st_mtime if self._path.exists() else 0
            while True:
                time.sleep(5)
                try:
                    mtime = self._path.stat().st_mtime
                    if mtime != last:
                        self.reload()
                        last = mtime
                except OSError:
                    pass

        t = threading.Thread(target=_poll, daemon=True)
        t.start()
