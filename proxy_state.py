#!/usr/bin/env python3
"""Remember how often each proxy failed so dead ones are not retested forever.

State is kept in a small JSON file that lives outside the repository (CI uses
the actions cache), so the published data stays clean. A proxy is skipped only
after it failed several runs in a row, and only for a limited time: after
``skip_hours`` it is tried again in case it came back to life.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

DEFAULT_STATE_PATH = Path(".cache") / "proxy-state.json"
DEFAULT_SKIP_HOURS = 24.0
DEFAULT_MIN_FAILURES = 2
DEFAULT_MAX_AGE_DAYS = 14.0
SCHEMA_VERSION = 1


def _iso(timestamp: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(timestamp))


def _parse(value: object) -> float | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return None


class ProxyState:
    """Failure history for proxy addresses."""

    def __init__(
        self,
        path: Path,
        entries: dict[str, dict] | None = None,
        min_failures: int = DEFAULT_MIN_FAILURES,
        skip_hours: float = DEFAULT_SKIP_HOURS,
    ) -> None:
        self.path = Path(path)
        self.entries: dict[str, dict] = entries or {}
        self.min_failures = max(1, min_failures)
        self.skip_hours = skip_hours

    @classmethod
    def load(
        cls,
        path: Path,
        min_failures: int = DEFAULT_MIN_FAILURES,
        skip_hours: float = DEFAULT_SKIP_HOURS,
    ) -> ProxyState:
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        entries = payload.get("proxies") if isinstance(payload, dict) else None
        if not isinstance(entries, dict):
            entries = {}
        clean = {address: entry for address, entry in entries.items() if isinstance(entry, dict)}
        return cls(Path(path), clean, min_failures=min_failures, skip_hours=skip_hours)

    def should_skip(self, address: str, now: float | None = None) -> bool:
        """Skip proxies that keep failing, but retry them after skip_hours."""
        if self.skip_hours <= 0:
            return False
        entry = self.entries.get(address)
        if not entry:
            return False
        if entry.get("consecutive_failures", 0) < self.min_failures:
            return False
        last_seen = _parse(entry.get("last_seen"))
        if last_seen is None:
            return False
        now = time.time() if now is None else now
        return now - last_seen < self.skip_hours * 3600

    def record(self, address: str, ok: bool, now: float | None = None) -> None:
        now = time.time() if now is None else now
        stamp = _iso(now)
        entry = self.entries.setdefault(
            address,
            {
                "first_seen": stamp,
                "last_seen": stamp,
                "last_ok": None,
                "successes": 0,
                "failures": 0,
                "consecutive_failures": 0,
            },
        )
        entry["last_seen"] = stamp
        if ok:
            entry["last_ok"] = stamp
            entry["successes"] = entry.get("successes", 0) + 1
            entry["consecutive_failures"] = 0
        else:
            entry["failures"] = entry.get("failures", 0) + 1
            entry["consecutive_failures"] = entry.get("consecutive_failures", 0) + 1

    def prune(self, max_age_days: float = DEFAULT_MAX_AGE_DAYS, now: float | None = None) -> int:
        """Drop addresses that have not been seen for a long time."""
        now = time.time() if now is None else now
        cutoff = now - max_age_days * 86400
        stale = [
            address
            for address, entry in self.entries.items()
            if (seen := _parse(entry.get("last_seen"))) is None or seen < cutoff
        ]
        for address in stale:
            del self.entries[address]
        return len(stale)

    def save(self, now: float | None = None) -> None:
        now = time.time() if now is None else now
        payload = {
            "schema": SCHEMA_VERSION,
            "updated_at": _iso(now),
            "proxies": dict(sorted(self.entries.items())),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".tmp")
        temporary.write_text(json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8")
        temporary.replace(self.path)
