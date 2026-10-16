# Configuration

RXCluster is configured with a single YAML file (default
`config/rxcluster.yaml`). The committed template is
`config/rxcluster.example.yaml`.

## Precedence

1. Built-in defaults (defined by the pydantic models in `rxcluster/config.py`).
2. The YAML file.

Everything lives in the YAML file; there is no environment-variable layer.
Values omitted from the file fall back to the built-in defaults.

Secrets (callsigns, passwords) may live directly in the YAML file; the real
file is git-ignored. Only the example is committed.

Validation is fail-fast: overlapping or inverted band ranges, unknown bands in
`mode_subbands`, and missing required fields abort startup.

## Reference

### `station`

| Key | Default | Description |
| --- | --- | --- |
| `callsign` | `N0CALL` | Callsign used for source login and self-spot detection |
| `operator_grid` | `""` | Maidenhead locator of the operator's QTH (VOACAP paths) |
| `noise_class` | `SUBURBAN` | `QUIET`/`RURAL`/`SUBURBAN`/`URBAN`/`INDUSTRIAL` |

### `server.telnet`

| Key | Default | Description |
| --- | --- | --- |
| `host` | `0.0.0.0` | Bind address |
| `port` | `7300` | Telnet port |
| `max_clients` | `100` | Maximum concurrent clients |
| `client_queue_size` | `5000` | Per-client outbound queue (drop-oldest when full) |
| `line_width` | `76` | Fixed spot line width, excluding CRLF (minimum `65`; N2WQ/GoCluster ships `76`) |
| `banner` | `RXCluster DX Aggregator` | Banner shown on connect |

### `server.http`

| Key | Default | Description |
| --- | --- | --- |
| `host` | `0.0.0.0` | Bind address |
| `port` | `8080` | HTTP port |
| `enabled` | `true` | Enable the health/metrics server |
| `metrics_enabled` | `true` | Expose `/metrics` |

### `sources.rbn`

| Key | Default | Description |
| --- | --- | --- |
| `enabled` | `true` | Enable the RBN feed |
| `host` | `telnet.reversebeacon.net` | RBN relay host |
| `port` | `7000` | RBN relay port |
| `callsign` | `""` | Login callsign |
| `reconnect_delay` | `5` | Initial reconnect delay (seconds) |
| `max_reconnect_delay` | `120` | Maximum backoff (seconds) |

### `sources.dxsummit`

| Key | Default | Description |
| --- | --- | --- |
| `enabled` | `true` | Enable the DX Summit feed |
| `api_url` | `https://dxsummit.fi/api/v1/spots` | JSON API endpoint |
| `poll_interval` | `15` | Polling interval (seconds) |
| `limit` | `100` | Spots per request |
| `timeout` | `10` | HTTP timeout (seconds) |

### `sources.ve7cc`

| Key | Default | Description |
| --- | --- | --- |
| `enabled` | `true` | Enable the VE7CC feed |
| `host` | `dxc.ve7cc.net` | CC Cluster host |
| `port` | `23` | Port |
| `callsign` | `""` | Login callsign |
| `password` | `""` | Optional password |
| `human_only` | `true` | Send `set/skimmer off` to avoid duplicating RBN |
| `reconnect_delay` | `5` | Initial reconnect delay |
| `max_reconnect_delay` | `120` | Maximum backoff |

### `sources.psk_reporter`

| Key | Default | Description |
| --- | --- | --- |
| `enabled` | `false` | Enable the PSKReporter MQTT feed |
| `host` | `mqtt.pskreporter.info` | MQTT broker host |
| `port` | `1883` | MQTT broker port |
| `tls` | `false` | Use TLS (connect to a TLS port, e.g. `1884`) |
| `topic` | `pskr/filter/v2/#` | MQTT topic filter (`band/mode/tx/rx/grids/dxcc`) |
| `client_id` | `""` | MQTT client id; auto-generated when empty |
| `keepalive` | `60` | MQTT keepalive (seconds) |
| `reconnect_delay` | `5` | Initial reconnect delay |
| `max_reconnect_delay` | `120` | Maximum backoff |

The PSKReporter global feed is very high volume, hence `enabled: false` by
default. Narrow `topic` (e.g. `pskr/filter/v2/20m/FT8/#`) before enabling it.

### `pipeline`

| Key | Default | Description |
| --- | --- | --- |
| `raw_queue_size` | `50000` | Bounded intake queue size |
| `dedup.window_seconds` | `30` | Duplicate suppression window |
| `dedup.freq_tolerance_khz` | `0.1` | Frequency quantization for dedup |
| `validation.scp_enabled` | `true` | Use SCP membership |
| `validation.patt3ch_enabled` | `true` | Use the patt3ch list |
| `validation.cty_enabled` | `true` | Resolve geography from cty.dat |
| `validation.corroboration.enabled` | `true` | Enable cross-source corroboration |
| `validation.corroboration.window_seconds` | `120` | Corroboration window |
| `validation.corroboration.min_agree` | `3` | Confirmations required for `V` |
| `validation.corroboration.edit_distance` | `1` | Busted-call edit distance |
| `enrichment.voacap.*` | see [VOACAP.md](VOACAP.md) | Propagation engine |
| `enrichment.tags.*` | see below | Output tagging |

`enrichment.tags`:

| Key | Default | Description |
| --- | --- | --- |
| `confidence` | `true` | Append the confidence symbol |
| `path` | `true` | Append the path symbol |
| `mode_token` | `true` | Inject the N2WQ/GoCluster mode token (`CW`/`RTTY`/`PSK`/`FT8`/`FT4`/`USB`/`LSB`) |
| `style` | `n2wq` | `n2wq` or `arcluster` |

### `bands`

A list of `{ name, low, high }` frequency ranges in kHz. Ranges must not
overlap and each `low` must be less than `high`.

### `mode_subbands`

Per-band `{ cw_high, ssb_low }` split (kHz) used to infer the mode of human
spots that carry no explicit mode token. Frequencies between the two limits are
left as `UNKNOWN`.

### `defaults`

Node-level filter template applied to every new client (clients can override at
runtime with `PASS`/`REJECT`). See [FILTERS.md](FILTERS.md).

### `data`

| Key | Default | Description |
| --- | --- | --- |
| `scp_file` | `data/MASTER.SCP` | SCP file path |
| `cty_file` | `data/cty.dat` | cty.dat path |
| `patt3ch_file` | `data/patt3ch.lst` | patt3ch list path |
| `auto_update` | `true` | Download missing files and refresh periodically |
| `update_interval_hours` | `24` | Refresh interval |

### `logging`

| Key | Default | Description |
| --- | --- | --- |
| `level` | `INFO` | Log level |
| `format` | `json` | `json` or `text` |
| `file` | `""` | Optional log file path |

### `users`

Per-callsign settings persistence. When enabled, each operator's filter
selections plus grid, noise class and dedupe policy are stored as JSON files and
restored on the next login with the same callsign (no authentication).

| Key | Default | Description |
| --- | --- | --- |
| `enabled` | `true` | Persist and restore settings per callsign |
| `directory` | `data/users` | Directory holding one `<CALL>.json` per operator |
