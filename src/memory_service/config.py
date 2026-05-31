"""Configuration for the background memory service.

Priority (highest first):
  1. Environment variables (MEMORY_SERVICE_*)
  2. memory_service_config.yaml in the project root
  3. Hard-coded defaults
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

from config.settings import DATA_DIR, LOGS_DIR, PROJECT_ROOT

_DEFAULT_CONFIG_PATH = PROJECT_ROOT / "memory_service_config.yaml"
_DEFAULT_STORAGE = DATA_DIR / "segments"


@dataclass
class MemoryServiceConfig:
    # How often to compile a segment (seconds); default 1 hour.
    interval_seconds: int = 3600

    # Where segment SQLite index and JSON data files live.
    storage_path: Path = _DEFAULT_STORAGE

    # The audit.log written by src/audit_log.py.
    audit_log_path: Path = LOGS_DIR / "audit.log"

    # Control files (written into storage_path at runtime).
    @property
    def pid_file(self) -> Path:
        return self.storage_path / "memory_service.pid"

    @property
    def stop_file(self) -> Path:
        return self.storage_path / "memory_service.stop"

    @property
    def db_path(self) -> Path:
        return self.storage_path / "segments.db"

    @property
    def read_state_path(self) -> Path:
        return self.storage_path / "audit_read_state.json"

    @property
    def service_log_path(self) -> Path:
        return self.storage_path / "memory_service.log"

    # Retention policies.
    retention_hourly_days: int = 7
    retention_daily_weeks: int = 4
    retention_weekly_months: int = 6

    # Compression of old segment JSON files.
    compression_enabled: bool = True
    compress_after_days: int = 1

    # --------------------------------------------------------------------------

    @classmethod
    def load(cls, path: Path = _DEFAULT_CONFIG_PATH) -> MemoryServiceConfig:
        cfg = cls()

        if path.exists():
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

            if "interval_seconds" in data:
                cfg.interval_seconds = int(data["interval_seconds"])
            if "storage_path" in data:
                p = Path(data["storage_path"])
                cfg.storage_path = p if p.is_absolute() else PROJECT_ROOT / p
            if "audit_log_path" in data:
                p = Path(data["audit_log_path"])
                cfg.audit_log_path = p if p.is_absolute() else PROJECT_ROOT / p

            ret = data.get("retention", {})
            if "hourly_days" in ret:
                cfg.retention_hourly_days = int(ret["hourly_days"])
            if "daily_weeks" in ret:
                cfg.retention_daily_weeks = int(ret["daily_weeks"])
            if "weekly_months" in ret:
                cfg.retention_weekly_months = int(ret["weekly_months"])

            comp = data.get("compression", {})
            if "enabled" in comp:
                cfg.compression_enabled = bool(comp["enabled"])
            if "after_days" in comp:
                cfg.compress_after_days = int(comp["after_days"])

        # Environment overrides.
        if os.getenv("MEMORY_SERVICE_INTERVAL"):
            cfg.interval_seconds = int(os.environ["MEMORY_SERVICE_INTERVAL"])
        if os.getenv("MEMORY_SERVICE_STORAGE"):
            cfg.storage_path = Path(os.environ["MEMORY_SERVICE_STORAGE"])
        if os.getenv("MEMORY_SERVICE_AUDIT_LOG"):
            cfg.audit_log_path = Path(os.environ["MEMORY_SERVICE_AUDIT_LOG"])

        cfg.storage_path.mkdir(parents=True, exist_ok=True)
        return cfg
