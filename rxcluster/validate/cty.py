"""cty.dat database: country prefix -> DXCC entity metadata.

Provides :class:`CtyDatabase`, used both for callsign/country validation and
for geography enrichment (DXCC entity, continent, CQ zone, approximate grid).
The parser is tolerant and only relies on the fields needed by RXCluster.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..grid import latlon_to_grid
from .patterns import base_call

_HEADER_RE = re.compile(
    r"^(?P<name>[^:]+?):\s*"
    r"(?P<cq>\d+):\s*"
    r"(?P<itu>\d+):\s*"
    r"(?P<cont>[A-Z]{2}):\s*"
    r"(?P<lat>[-\d.]+):\s*"
    r"(?P<lon>[-\d.]+):\s*"
    r"(?P<tz>[-\d.]+):\s*"
    r"(?P<primary>[A-Z0-9/]+):\s*$"
)


@dataclass(slots=True, frozen=True)
class CtyEntity:
    name: str
    cq_zone: int
    itu_zone: int
    continent: str
    lat: float
    lon: float
    grid: str


class CtyDatabase:
    """Prefix lookup with longest-prefix matching."""

    def __init__(self) -> None:
        self._prefixes: dict[str, CtyEntity] = {}
        self._max_prefix_len = 1
        self.loaded = False

    def load(self, path: str | Path) -> int:
        p = Path(path)
        if not p.exists():
            return 0
        with p.open("r", encoding="utf-8", errors="ignore") as fh:
            self._parse(fh)
        self.loaded = True
        return len(self._prefixes)

    def _parse(self, fh) -> None:
        current: CtyEntity | None = None
        for raw in fh:
            # Blank lines separate entities but may also be spurious (e.g. files
            # with CR-CR-LF line endings). Do NOT clear ``current`` here, or the
            # continuation prefixes that follow would be dropped; a new header
            # replaces ``current`` anyway.
            if not raw.strip():
                continue
            header = _HEADER_RE.match(raw.rstrip("\r\n"))
            if header:
                lat = float(header.group("lat"))
                # cty.dat stores longitude as positive-west; convert it to the
                # standard east-positive convention used by the grid helpers,
                # otherwise grids (and NEARBY distances) come out mirrored,
                # e.g. Poland IO02 instead of JO92.
                lon = -float(header.group("lon"))
                current = CtyEntity(
                    name=header.group("name").strip(),
                    cq_zone=int(header.group("cq")),
                    itu_zone=int(header.group("itu")),
                    continent=header.group("cont"),
                    lat=lat,
                    lon=lon,
                    grid=latlon_to_grid(lat, lon, precision=4),
                )
                self._add_prefix(header.group("primary"), current)
                continue
            if current is None:
                continue
            # Continuation line: prefixes separated by commas and terminated by
            # a semicolon, e.g. "AA,AB,...,K,N,W,=4U1WB(5)[8],...;" with the
            # occasional '=' override and "(...)"/"[...]" annotation.
            for token in re.split(r"[,;\s]+", raw):
                prefix = token.lstrip("=").strip().upper()
                prefix = re.sub(r"[\(\[]([^\)\]]*)[\)\]]", "", prefix).strip()
                if prefix:
                    self._add_prefix(prefix, current)

    def _add_prefix(self, prefix: str, entity: CtyEntity) -> None:
        prefix = prefix.upper()
        if prefix and prefix not in self._prefixes:
            self._prefixes[prefix] = entity
            self._max_prefix_len = max(self._max_prefix_len, len(prefix))

    def lookup(self, call: str) -> CtyEntity | None:
        """Longest-prefix match for ``call``."""
        c = base_call(call)
        if not c:
            return None
        for length in range(min(self._max_prefix_len, len(c)), 0, -1):
            entity = self._prefixes.get(c[:length])
            if entity is not None:
                return entity
        return None

    def __len__(self) -> int:
        return len(self._prefixes)