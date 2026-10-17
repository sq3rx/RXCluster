# Telnet command reference

Connect to the telnet port (default 7300) and enter your callsign at the
`login:` prompt. Commands are case-insensitive. Line endings may be `CR` or
`CRLF`.

## Spot output format

```
DX de W1ABC:     14074.00  K1XYZ       FT8 -12 dB             > FN31 V 1830Z
      ─spotter─ ──freq─  ─dx──────  ──comment──────  ─tail: p─grid─c─timeZ
```

The line is fixed-width (76 characters, excluding CRLF) with stable columns so
N1MM Logger+ can read the propagation/quality tags from its AMQ window:

- Columns `1-6` are `DX de `; the spotter follows with a `:` suffix, padded so
  the **frequency** ends at column 25 (right-aligned, two decimals).
- The **DX callsign** starts at column 28 (padded to 8, truncated to 10).
- The **mode token** starts at column 40, using the N2WQ/GoCluster spellings
  (`CW`, `RTTY`, `PSK`, `FT8`, `FT4`, `USB`/`LSB`); SSB is emitted as
  `USB`/`LSB` by band. Signal reports carry a `+` sign for non-negative values
  on modes other than CW/RTTY.
- The fixed **tail** holds the **path symbol** (`>`/`=`/`<`/`-`/`#`/blank) at
  column 63, the **grid** at column 65, the **confidence symbol** at column 70
  and the time (`HHMMZ`) at columns 72-76.

## Commands

### Reading spots

| Command | Description |
| --- | --- |
| `SHOW DX [n]` / `SHOW MYDX [n]` | Show the most recent `n` spots matching your filters (default 10) |
| `SHOW DX <call> [n]` | Show recent spots for one DX station |
| `SHOW FILTER` | Show your current filter selections |
| `SHOW FILTER FULL` | Show the complete effective selections, including switches |
| `SHOW FILTER <CATEGORY>` | Show one category (e.g. `SHOW FILTER BAND`) |
| `SHOW SETTINGS` | Show your current filter selections |
| `SHOW DEDUPE` | Show your duplicate-suppression policy |
| `SHOW HOLD` | Show pause state and how many spots were suppressed |
| `SHOW PROP <call\|prefix\|grid> [band] [mode]` | Hourly propagation outlook using the node reference `station.operator_grid` |
| `WHOSPOTSME [band]` | Countries that recently spotted your own callsign |

Read-backs (`SHOW FILTER`, `SHOW SETTINGS`, `SHOW PROP`) pause live spots for
30 s so the reply is readable; type `RESUME` when ready.

### Posting spots

| Command | Description |
| --- | --- |
| `DX <freq_khz> <callsign> [comment]` | Post a spot you have heard (e.g. `DX 7001.0 K1ABC CW`) |

The comment accepts ASCII letters, digits, spaces and `/ # @ - . , * ? _`.

### Filtering

See [FILTERS.md](FILTERS.md) for the full category list and semantics.

| Command | Description |
| --- | --- |
| `PASS <CATEGORY> <values>` | Allow values (e.g. `PASS BAND 20,40`) |
| `REJECT <CATEGORY> <values>` | Block values (e.g. `REJECT MODE FT8`) |
| `PASS/REJECT <CATEGORY> ALL` | Clear / restrict an entire category |
| `PASS MINSNR <MODE> <dB\|ALL>` | Set a per-mode minimum SNR (e.g. `PASS MINSNR CW 10`) |
| `PASS/REJECT NEARBY ON\|OFF` | Keep only spots near your grid (requires `SET GRID`) |
| `PASS/REJECT BEACON\|WWV\|WCY\|ANNOUNCE\|SELF\|TOXIC` | Toggle feature switches |

### Session / preferences

| Command | Description |
| --- | --- |
| `SET GRID <locator>` | Set your Maidenhead locator (affects NEARBY filtering and saved preferences; propagation tags use the node reference `station.operator_grid`) |
| `SET NOISE <class>` | Set your receive-noise class |
| `SET DEDUPE <FAST\|MED\|SLOW>` | Duplicate-suppression policy (session preference) |
| `PAUSE [seconds]` | Pause live spots (default 30 s, max 300) |
| `RESUME` | Resume live spots immediately |
| `HELP [command]` | Show the help text, or help for one command |
| `BYE` | Disconnect |

### CC Cluster / DX Spider aliases

| Command | Description |
| --- | --- |
| `SET/DX` | Enable spots |
| `SET/SKIMMER ON\|OFF` | Enable/disable skimmer-sourced spots |
| `SET/FT8` / `SET/NOFT8` | Enable/disable FT8 |
| `SET DX FILTER ...` | Accepted and acknowledged |
| `ACCEPT/SPOTS` | Continue streaming |

## Keep-alive

A bare space (as sent by N1MM's *Cluster Keep Alive* setting) is treated as a
keep-alive and ignored.

## Examples

```text
login: SQ9ABC
*** Connected as SQ9ABC. Type HELP for commands, BYE to disconnect.
REJECT BAND ALL
REJECT BAND 20m,40m
REJECT MODE ALL
PASS MODE CW
PASS MINSNR CW 10
SET GRID JO90AA
SHOW FILTER
```