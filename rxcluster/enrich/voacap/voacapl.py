"""Real VOACAP integration via the ``voacapl`` command-line engine.

This module shells out to ``voacapl`` (https://github.com/jawatson/voacapl)
using a generated point-to-point input deck and parses the reliability (REL)
table from the output.

CLI notes (from the voacapl source):

* ``voacapl <itshfbc_dir> <input_name> <output_name> [append]``
* ``input_name`` / ``output_name`` are resolved *relative to*
  ``<itshfbc_dir>/run/``, so only base file names are passed.
* The engine writes scratch files into ``<itshfbc_dir>/run/`` and therefore
  must be run with a writable run directory. Because those scratch files have
  fixed names, runs must be serialized (one process at a time).

The deck format mirrors the canonical ``voacapx.dat`` shipped with voacapl and
the exact FORTRAN formats used by the writer in ``voacap.for``.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

# Representative frequency (MHz) for each HF band, in the column order used in
# the FREQUENCY card. Two trailing zero columns pad the card to 11 fields.
FREQS_MHZ: tuple[float, ...] = (
    1.85,   # 160m
    3.65,   # 80m
    7.05,   # 40m
    10.12,  # 30m
    14.10,  # 20m
    18.10,  # 17m
    21.10,  # 15m
    24.93,  # 12m
    28.10,  # 10m
    0.0,
    0.0,
)

BAND_FREQ_INDEX: dict[str, int] = {
    "160m": 0,
    "80m": 1,
    "40m": 2,
    "30m": 3,
    "20m": 4,
    "17m": 5,
    "15m": 6,
    "12m": 7,
    "10m": 8,
}

# Reliability thresholds used to map a VOACAP REL value (0..1) to a path class.
_REL_HIGH = 0.70
_REL_MEDIUM = 0.40
_REL_LOW = 0.15


def build_deck(
    tx_lat: float,
    tx_lon: float,
    rx_lat: float,
    rx_lon: float,
    year: int,
    month: int,
    ssn: int,
    freqs_mhz: tuple[float, ...] = FREQS_MHZ,
) -> str:
    """Build a point-to-point VOACAP input deck (as a string)."""
    lines: list[str] = []
    lines.append("COMMENT    RXCluster generated deck")
    lines.append("LINEMAX      55")
    lines.append("COEFFS    CCIR")
    lines.append(f"TIME      {1:5d}{24:5d}{1:5d}{1:5d}")
    lines.append(f"MONTH     {year:5d}{float(month):5.2f}")

    # SUNSPOT  12f5.0
    lines.append(f"SUNSPOT   {float(ssn):5.0f}")
    # LABEL    2a20
    lines.append(f"LABEL     {'RXCluster'.ljust(20)}{'target'.ljust(20)}")

    # CIRCUIT  f5.2,a1,3(f9.2,a1),2x,a1,1x,i5
    def _hemi(lat: float, lon: float) -> tuple[str, str]:
        return ("N" if lat >= 0 else "S"), ("E" if lon >= 0 else "W")

    tns, tew = _hemi(tx_lat, tx_lon)
    rns, rew = _hemi(rx_lat, rx_lon)
    circuit = (
        "CIRCUIT   "
        + f"{abs(tx_lat):5.2f}{tns}"
        + f"{abs(tx_lon):9.2f}{tew}"
        + f"{abs(rx_lat):9.2f}{rns}"
        + f"{abs(rx_lon):9.2f}{rew}"
        + "  S "
        + f"{0:5d}"
    )
    lines.append(circuit)

    # SYSTEM   f5.0,f5.0,f5.2,f5.0,3f5.2  (mult, noise, min angle, LUF, SNR, ...)
    system = (
        "SYSTEM    "
        + f"{1.0:5.0f}"
        + f"{145.0:5.0f}"
        + f"{0.10:5.2f}"
        + f"{90.0:5.0f}"
        + f"{73.0:5.2f}"
        + f"{3.0:5.2f}"
        + f"{0.10:5.2f}"
    )
    lines.append(system)
    lines.append("FPROB      1.00 1.00 1.00 0.00")

    # ANTENNA  4i5,f10.3,1h[,a21,1h],f5.1,f10.4
    def _antenna(idx: int, gain_beam: float, power: float) -> str:
        return (
            "ANTENNA   "
            + f"{idx if idx == 1 else 2:5d}"
            + f"{idx:5d}"
            + f"{2:5d}"
            + f"{30:5d}"
            + f"{0.0:10.3f}"
            + "[" + "default/isotrope".ljust(21) + "]"
            + f"{gain_beam:5.1f}"
            + f"{power:10.4f}"
        )

    lines.append(_antenna(1, 0.0, 500.0))
    lines.append(_antenna(2, 0.0, 0.0))

    # FREQUENCY  11f5.2 (MHz)
    lines.append("FREQUENCY " + "".join(f"{f:5.2f}" for f in freqs_mhz))
    lines.append(f"METHOD    {30:5d}{0:5d}")
    lines.append("EXECUTE")
    lines.append("QUIT")
    return "\n".join(lines) + "\n"


def parse_rel(text: str) -> dict[int, list[tuple[float, float | None]]]:
    """Parse the reliability table from a VOACAP output report.

    Returns a mapping ``hour -> [(frequency_mhz, reliability_or_None), ...]``.
    Reliability is ``None`` when the column is not computed (``-``).
    """
    result: dict[int, list[tuple[float, float | None]]] = {}
    last_hour: int | None = None
    last_freqs: list[str] | None = None

    for line in text.splitlines():
        stripped = line.rstrip()
        tokens = stripped.split()
        if not tokens:
            continue
        if tokens[-1] == "FREQ":
            try:
                last_hour = int(round(float(tokens[0])))
            except ValueError:
                last_hour = None
            # tokens[0] is the hour; tokens[1:-1] are hour/MUF + 11 frequencies.
            last_freqs = tokens[1:-1]
        elif tokens[-1] == "REL" and last_hour is not None and last_freqs is not None:
            rels = tokens[:-1]
            if len(rels) != len(last_freqs):
                continue
            rows: list[tuple[float, float | None]] = []
            for index, (freq_token, rel_token) in enumerate(
                zip(last_freqs, rels, strict=False)
            ):
                if index == 0:
                    # Column 0 is the path MUF, not one of our input
                    # frequencies; exclude it to avoid mis-mapping.
                    continue
                try:
                    freq = float(freq_token)
                except ValueError:
                    continue
                if freq <= 0:
                    continue
                try:
                    rel: float | None = float(rel_token)
                except ValueError:
                    rel = None
                rows.append((freq, rel))
            if rows:
                result[last_hour] = rows
    return result


def nearest_rel(
    rows: list[tuple[float, float | None]], freq_mhz: float, tolerance: float = 0.25
) -> float | None:
    """Return the reliability nearest to ``freq_mhz`` within ``tolerance``."""
    best: float | None = None
    best_delta = tolerance
    for freq, rel in rows:
        delta = abs(freq - freq_mhz)
        if delta <= best_delta:
            best_delta = delta
            best = rel
    return best


def rel_to_path(rel: float | None):
    """Map a VOACAP reliability value to a :class:`~rxcluster.models.PathClass`."""
    from ...models import PathClass

    if rel is None:
        return PathClass.INSUFFICIENT
    if rel <= 0.0:
        return PathClass.CLOSED
    if rel < _REL_LOW:
        return PathClass.UNLIKELY
    if rel < _REL_MEDIUM:
        return PathClass.LOW
    if rel < _REL_HIGH:
        return PathClass.MEDIUM
    return PathClass.HIGH


class VoacaplRunner:
    """Thin subprocess wrapper around the ``voacapl`` binary."""

    def __init__(self, engine_path: str, itshfbc_dir: str, timeout: float = 120.0) -> None:
        self.engine = self._resolve_engine(engine_path)
        self.itshfbc = self._resolve_dir(itshfbc_dir)
        self.run_dir = Path(self.itshfbc) / "run" if self.itshfbc else None
        self.timeout = timeout

    @staticmethod
    def _resolve_engine(engine_path: str) -> str | None:
        if engine_path:
            found = shutil.which(engine_path)
            if found:
                return found
        return shutil.which("voacapl")

    @staticmethod
    def _resolve_dir(itshfbc_dir: str) -> str:
        candidates: list[Path] = []
        if itshfbc_dir:
            candidates.append(Path(itshfbc_dir))
        candidates.append(Path.home() / "itshfbc")
        candidates.append(Path("/usr/local/share/voacapl/itshfbc"))
        for candidate in candidates:
            if candidate.is_dir():
                return str(candidate)
        return ""

    @property
    def available(self) -> bool:
        return bool(
            self.engine
            and self.run_dir is not None
            and self.run_dir.is_dir()
        )

    def run(self, deck: str, tag: str) -> str | None:
        """Run a single deck. Returns the output report text, or ``None``."""
        if not self.available or self.run_dir is None:
            return None
        name = self._safe_name(tag)
        in_name = f"{name}.dat"
        out_name = f"{name}.out"
        in_path = self.run_dir / in_name
        out_path = self.run_dir / out_name
        in_path.write_text(deck, encoding="ascii", errors="replace")
        try:
            completed = subprocess.run(
                [self.engine, self.itshfbc, in_name, out_name],
                cwd=str(self.run_dir),
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            if completed.returncode != 0:
                log.debug("voacapl exited %d: %s", completed.returncode, completed.stderr.strip())
            if not out_path.exists():
                return None
            return out_path.read_text(encoding="ascii", errors="replace")
        except subprocess.TimeoutExpired:
            log.warning("voacapl timed out after %.0fs", self.timeout)
            return None
        except OSError as exc:
            log.warning("voacapl execution failed: %s", exc)
            return None
        finally:
            for path in (in_path, out_path):
                try:
                    path.unlink()
                except OSError:
                    pass

    @staticmethod
    def _safe_name(tag: str) -> str:
        cleaned = "".join(ch if ch.isalnum() else "_" for ch in tag)
        return ("rxcluster_" + cleaned)[:40]