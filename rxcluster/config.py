"""Configuration loading and validation.

Configuration is loaded from a single YAML file (``config/rxcluster.yaml`` by
default), layered over the built-in defaults defined by the pydantic models
below. There is no environment-variable layer: everything lives in the YAML
file.

Secrets (callsigns, passwords) may live directly in the YAML file; the real
file is git-ignored, only ``rxcluster.example.yaml`` is committed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StationConfig(_Base):
    callsign: str = "N0CALL"
    operator_grid: str = ""
    noise_class: Literal["QUIET", "RURAL", "SUBURBAN", "URBAN", "INDUSTRIAL"] = "SUBURBAN"


class TelnetServerConfig(_Base):
    host: str = "0.0.0.0"
    port: int = 7300
    max_clients: int = 100
    client_queue_size: int = 5000
    # Fixed DX cluster line width (excluding CRLF). N2WQ/GoCluster ships 76.
    line_width: int = Field(default=76, ge=65)
    banner: str = "RXCluster DX Aggregator"


class HttpServerConfig(_Base):
    host: str = "0.0.0.0"
    port: int = 8080
    enabled: bool = True
    metrics_enabled: bool = True


class ServerConfig(_Base):
    telnet: TelnetServerConfig = Field(default_factory=TelnetServerConfig)
    http: HttpServerConfig = Field(default_factory=HttpServerConfig)


class RbnConfig(_Base):
    enabled: bool = True
    host: str = "telnet.reversebeacon.net"
    port: int = 7000
    callsign: str = ""
    reconnect_delay: float = 5.0
    max_reconnect_delay: float = 120.0


class DxSummitConfig(_Base):
    enabled: bool = True
    api_url: str = "https://dxsummit.fi/api/v1/spots"
    poll_interval: float = 15.0
    limit: int = 100
    timeout: float = 10.0


class Ve7ccConfig(_Base):
    enabled: bool = True
    host: str = "dxc.ve7cc.net"
    port: int = 23
    callsign: str = ""
    password: str = ""
    human_only: bool = True
    reconnect_delay: float = 5.0
    max_reconnect_delay: float = 120.0


class PskReporterConfig(_Base):
    enabled: bool = False
    host: str = "mqtt.pskreporter.info"
    port: int = 1883
    tls: bool = False
    topic: str = "pskr/filter/v2/#"
    client_id: str = ""
    keepalive: int = 60
    reconnect_delay: float = 5.0
    max_reconnect_delay: float = 120.0


class SourcesConfig(_Base):
    rbn: RbnConfig = Field(default_factory=RbnConfig)
    dxsummit: DxSummitConfig = Field(default_factory=DxSummitConfig)
    ve7cc: Ve7ccConfig = Field(default_factory=Ve7ccConfig)
    psk_reporter: PskReporterConfig = Field(default_factory=PskReporterConfig)


class DedupConfig(_Base):
    # Duplicate suppression runs per client (after that client's filter), so the
    # window is chosen from the client's SET DEDUPE policy. ``window_seconds``
    # is the fallback used for an unknown policy.
    freq_tolerance_khz: float = 0.1
    window_seconds: float = 30.0
    policies: dict[str, float] = Field(
        default_factory=lambda: {"FAST": 10.0, "MED": 20.0, "SLOW": 30.0}
    )

    def window_for(self, policy: str) -> float:
        """Return the dedup window in seconds for a ``SET DEDUPE`` policy."""
        return self.policies.get(policy.strip().upper(), self.window_seconds)


class CorroborationConfig(_Base):
    enabled: bool = True
    window_seconds: float = 120.0
    min_agree: int = 3
    edit_distance: int = 1


class ValidationConfig(_Base):
    scp_enabled: bool = True
    patt3ch_enabled: bool = True
    cty_enabled: bool = True
    corroboration: CorroborationConfig = Field(default_factory=CorroborationConfig)


class VoacapConfig(_Base):
    enabled: bool = True
    engine_path: str = "/usr/local/bin/voacapl"
    # Path to the itshfbc data directory created by `makeitshfbc`. When empty
    # the engine looks in $HOME/itshfbc and /usr/local/share/voacapl/itshfbc.
    itshfbc_dir: str = ""
    # Precompute the VOACAP reliability matrix in the background (recommended).
    precompute: bool = True
    refresh_hours: float = 6.0
    target_grid_degrees: int = 15
    modes: list[str] = Field(default_factory=lambda: ["CW", "SSB", "RTTY", "FT8"])
    ssn_default: int = 100
    solar_source: str = (
        "https://services.swpc.noaa.gov/json/solar-cycle/observed-solar-cycle-indices.json"
    )


class TagsConfig(_Base):
    confidence: bool = True
    path: bool = True
    mode_token: bool = True
    style: Literal["n2wq", "arcluster"] = "n2wq"


class EnrichmentConfig(_Base):
    voacap: VoacapConfig = Field(default_factory=VoacapConfig)
    tags: TagsConfig = Field(default_factory=TagsConfig)


class NearbyConfig(_Base):
    # NEARBY keeps spots whose DX or spotter grid is within these radii (km).
    # The low bands get a wider radius because ground-wave/short-skip reaches
    # further there.
    radius_km: float = Field(default=700.0, gt=0)
    low_band_radius_km: float = Field(default=1500.0, gt=0)
    low_bands: list[str] = Field(default_factory=lambda: ["160m", "80m", "60m"])


class PipelineConfig(_Base):
    raw_queue_size: int = 50000
    dedup: DedupConfig = Field(default_factory=DedupConfig)
    validation: ValidationConfig = Field(default_factory=ValidationConfig)
    enrichment: EnrichmentConfig = Field(default_factory=EnrichmentConfig)
    nearby: NearbyConfig = Field(default_factory=NearbyConfig)


class BandConfig(_Base):
    name: str
    low: float  # kHz
    high: float  # kHz


class SwitchConfig(_Base):
    beacon: bool = False
    wwv: bool = True
    wcy: bool = True
    announce: bool = True
    self: bool = False

    @model_validator(mode="before")
    @classmethod
    def _drop_removed(cls, data: object) -> object:
        # The ``toxic`` switch was removed in 0.3.0; accept but ignore it so
        # existing configuration files keep loading.
        if isinstance(data, dict) and "toxic" in data:
            return {k: v for k, v in data.items() if k != "toxic"}
        return data


Selection = Literal["all"] | list[str]


class DefaultFilterConfig(_Base):
    bands: Selection = "all"
    modes: Selection = "all"
    reject_confidence: list[str] = Field(default_factory=list)
    path: list[str] = Field(
        default_factory=lambda: ["HIGH", "MEDIUM", "LOW", "UNLIKELY", "CLOSED", "INSUFFICIENT"]
    )
    min_snr: dict[str, int] = Field(default_factory=dict)
    switches: SwitchConfig = Field(default_factory=SwitchConfig)


class DataConfig(_Base):
    scp_file: str = "data/MASTER.SCP"
    cty_file: str = "data/cty.dat"
    patt3ch_file: str = "data/patt3ch.lst"
    auto_update: bool = True
    update_interval_hours: float = 24.0


class LoggingConfig(_Base):
    level: str = "INFO"
    format: Literal["json", "text"] = "json"
    file: str = ""


class UserStoreConfig(_Base):
    # Persist per-callsign filter/session settings as JSON files and restore
    # them when the same callsign logs in again.
    enabled: bool = True
    directory: str = "data/users"


class Config(_Base):
    station: StationConfig = Field(default_factory=StationConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    sources: SourcesConfig = Field(default_factory=SourcesConfig)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    bands: list[BandConfig] = Field(
        default_factory=lambda: [
            BandConfig(name="160m", low=1800, high=2000),
            BandConfig(name="80m", low=3500, high=4000),
            BandConfig(name="60m", low=5330, high=5410),
            BandConfig(name="40m", low=7000, high=7300),
            BandConfig(name="30m", low=10100, high=10150),
            BandConfig(name="20m", low=14000, high=14350),
            BandConfig(name="17m", low=18068, high=18168),
            BandConfig(name="15m", low=21000, high=21450),
            BandConfig(name="12m", low=24890, high=24990),
            BandConfig(name="10m", low=28000, high=29700),
            BandConfig(name="6m", low=50000, high=54000),
        ]
    )
    mode_subbands: dict[str, dict[str, float]] = Field(default_factory=dict)
    defaults: DefaultFilterConfig = Field(default_factory=DefaultFilterConfig)
    data: DataConfig = Field(default_factory=DataConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    users: UserStoreConfig = Field(default_factory=UserStoreConfig)

    @field_validator("bands")
    @classmethod
    def _check_bands(cls, bands: list[BandConfig]) -> list[BandConfig]:
        for b in bands:
            if b.low >= b.high:
                raise ValueError(f"band {b.name!r}: low ({b.low}) must be < high ({b.high})")
        ordered = sorted(bands, key=lambda b: b.low)
        for prev, cur in zip(ordered, ordered[1:], strict=False):
            if cur.low < prev.high:
                raise ValueError(
                    f"bands {prev.name!r} and {cur.name!r} overlap: "
                    f"{prev.low}-{prev.high} vs {cur.low}-{cur.high}"
                )
        return bands

    @model_validator(mode="after")
    def _check_subbands(self) -> Config:
        names = {b.name for b in self.bands}
        for band_name, split in self.mode_subbands.items():
            if band_name not in names:
                raise ValueError(f"mode_subbands references unknown band {band_name!r}")
            for key in ("cw_high", "ssb_low"):
                if key not in split:
                    raise ValueError(f"mode_subbands[{band_name!r}] missing {key!r}")
        return self

    @property
    def band_ranges(self) -> list[tuple[float, float, str]]:
        return [(b.low, b.high, b.name) for b in sorted(self.bands, key=lambda x: x.low)]


def load_config(path: str | Path | None = None) -> Config:
    """Load and validate configuration from a YAML file.

    ``path`` may be ``None`` to use the built-in defaults only. A missing file
    is tolerated only when ``path`` is ``None``.
    """
    data: dict[str, object] = {}
    if path is not None:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"configuration file not found: {p}")
        with p.open("r", encoding="utf-8") as fh:
            loaded = yaml.safe_load(fh) or {}
        if not isinstance(loaded, dict):
            raise ValueError(f"configuration file {p} must contain a YAML mapping")
        data = loaded
    return Config.model_validate(data)