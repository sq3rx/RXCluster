"""Super Check Partial (SCP) database.

The SCP file (``MASTER.SCP``) contains one known-good callsign per line.
Membership in the SCP is a strong indicator that a spotted call is real.
"""

from __future__ import annotations

from pathlib import Path

from .patterns import base_call


class ScpDatabase:
    """Set-backed lookup of known callsigns."""

    def __init__(self) -> None:
        self._calls: set[str] = set()
        self.loaded = False

    def load(self, path: str | Path) -> int:
        """Load callsigns from ``path``. Returns the number of entries."""
        count = 0
        with Path(path).open("r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                call = line.strip().upper()
                if not call or call.startswith("!"):
                    continue
                self._calls.add(call)
                count += 1
        self.loaded = True
        return count

    def load_lines(self, lines) -> int:
        count = 0
        for line in lines:
            call = line.strip().upper()
            if call:
                self._calls.add(call)
                count += 1
        self.loaded = True
        return count

    def contains(self, call: str) -> bool:
        if not self._calls:
            return False
        c = call.strip().upper()
        if c in self._calls:
            return True
        base = base_call(c)
        return base in self._calls

    def __len__(self) -> int:
        return len(self._calls)