"""Reference data file download (SCP, cty.dat, patt3ch.lst).

Downloads are best-effort: when a file cannot be fetched the application keeps
running with degraded validation/enrichment rather than failing to start.
"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

from .config import DataConfig

log = logging.getLogger(__name__)

# Default upstream locations. These are maintained by the respective projects
# and may change over time; they can be overridden by placing the files manually
# in the data directory.
DEFAULT_URLS: dict[str, str] = {
    "MASTER.SCP": "https://supercheckpartial.com/MASTER.SCP",
    "cty.dat": "https://www.country-files.com/cty/cty.dat",
    "patt3ch.lst": "https://data.reversebeacon.net/downloads/patt3ch/patt3ch.lst",
}


async def ensure_data_files(cfg: DataConfig) -> None:
    """Ensure the configured data files exist; download the ones that are missing."""
    targets = {
        Path(cfg.scp_file): DEFAULT_URLS["MASTER.SCP"],
        Path(cfg.cty_file): DEFAULT_URLS["cty.dat"],
        Path(cfg.patt3ch_file): DEFAULT_URLS["patt3ch.lst"],
    }
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for path, url in targets.items():
            if path.exists():
                continue
            try:
                await _download(client, url, path)
                log.info("downloaded %s (%d bytes)", path, path.stat().st_size)
            except Exception as exc:
                log.warning("could not download %s from %s: %s", path, url, exc)


async def _download(client: httpx.AsyncClient, url: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    resp = await client.get(url, timeout=30.0)
    resp.raise_for_status()
    path.write_bytes(resp.content)