"""Per-callsign settings storage.

Settings (filter selections plus grid, noise class and dedupe policy) are
persisted as one JSON file per callsign under a configured directory. Records
are cached in memory so an unchanged session never rewrites the disk. Writes
are atomic (``tempfile`` + :func:`os.replace`) to avoid corrupting a record if
the process is interrupted.

The callsign comes from the unauthenticated login prompt, so a record is a
convenience for the operator, not an access-control boundary.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import threading
from datetime import UTC, datetime
from pathlib import Path

from ..config import UserStoreConfig

log = logging.getLogger(__name__)

# Callsign characters that are safe to use in a filename. Anything else is
# dropped; the path separator is mapped to a hyphen to keep realm calls flat.
_UNSAFE = re.compile(r"[^A-Z0-9/\-]")

RECORD_VERSION = 1


def _slug(callsign: str) -> str:
    cleaned = _UNSAFE.sub("", callsign.strip().upper()).replace("/", "-")
    return cleaned or "N0CALL"


class UserStore:
    """Load and store per-callsign settings as JSON files."""

    def __init__(self, cfg: UserStoreConfig) -> None:
        self.enabled = bool(cfg.enabled)
        self._dir = Path(cfg.directory)
        self._cache: dict[str, dict] = {}
        self._lock = threading.Lock()
        if self.enabled:
            try:
                self._dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                log.warning(
                    "settings directory %s is not writable (%s); "
                    "per-callsign persistence disabled",
                    self._dir,
                    exc,
                )
                self.enabled = False

    def load(self, callsign: str) -> dict | None:
        """Return the stored record for ``callsign`` or ``None``."""
        if not self.enabled:
            return None
        key = _slug(callsign)
        with self._lock:
            cached = self._cache.get(key)
        if cached is not None:
            return cached

        path = self._dir / f"{key}.json"
        try:
            with path.open("r", encoding="utf-8") as fh:
                record = json.load(fh)
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as exc:
            log.warning("cannot read settings for %s: %s", key, exc)
            return None
        if not isinstance(record, dict):
            log.warning("ignoring malformed settings for %s", key)
            return None
        with self._lock:
            self._cache[key] = record
        return record

    def save(self, callsign: str, record: dict) -> None:
        """Persist ``record`` for ``callsign``; skip identical writes."""
        if not self.enabled:
            return
        key = _slug(callsign)
        with self._lock:
            if self._cache.get(key) == record:
                return
            self._cache[key] = record

        path = self._dir / f"{key}.json"
        try:
            fd, tmp = tempfile.mkstemp(dir=str(self._dir), suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(record, fh, indent=2, sort_keys=True)
                os.replace(tmp, path)
            except BaseException:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
        except OSError as exc:
            log.warning("cannot write settings for %s: %s", key, exc)

    @staticmethod
    def build_record(
        callsign: str,
        filter_state: dict,
        grid: str = "",
        noise: str = "SUBURBAN",
        dedupe: str = "SLOW",
        nearby: dict | None = None,
    ) -> dict:
        """Assemble a versioned record ready for :meth:`save`."""
        return {
            "version": RECORD_VERSION,
            "callsign": callsign.strip().upper(),
            "updated": datetime.now(tz=UTC).isoformat(),
            "filter": filter_state,
            "grid": grid,
            "noise": noise,
            "dedupe": dedupe,
            "nearby": nearby or {"enabled": False},
        }
