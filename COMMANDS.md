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
| `SHOW NEARBY` | Show NEARBY state, grid and radius |
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
| `PASS/REJECT NEARBY ON\|OFF` | Keep only spots near your grid (requires `SET GRID`); `PASS NEARBY <km>` overrides the radius |
| `PASS/REJECT BEACON\|WWV\|WCY\|ANNOUNCE\|SELF` | Toggle feature switches |
| `RESET [ALL\|<CATEGORY>\|MINSNR\|NEARBY\|SWITCHES]` | Clear one category or restore the node-level defaults; `CLEAR` is an alias |

### Session / preferences

| Command | Description |
| --- | --- |
| `SET GRID <locator>` | Set your Maidenhead locator (affects NEARBY filtering and saved preferences; propagation tags use the node reference `station.operator_grid`) |
| `SET NOISE <class>` | Set your receive-noise class |
| `SET DEDUPE <FAST\|MED\|SLOW>` | Per-client duplicate-suppression window (FAST 10 s, MED 20 s, SLOW 30 s) |
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
| `ACCEPT/CONT <v>` / `REJECT/CONT <v>` | Allow/reject DX continents (`PASS`/`REJECT DXCONT`) |
| `SET/DXCONT <v>` / `SET/DECONT <v>` | Allow DX/spotter continents; `SET/NODXCONT` clears |
| `SET DX FILTER ...` | Accepted and acknowledged |
| `ACCEPT/SPOTS` | Continue streaming |

## Keep-alive

A bare space (as sent by N1MM's *Cluster Keep Alive* setting) is treated as a
keep-alive and ignored.

## Examples

### Contest CQ WW: 20/40 m CW only, good paths

```text
login: SQ9ABC
*** Connected as SQ9ABC. Type HELP for commands, BYE to disconnect.

# Only 20 m and 40 m (restrict, then re-add)
REJECT BAND ALL
PASS BAND 20,40

# Only CW
REJECT MODE ALL
PASS MODE CW

# Drop weak/likely-fake spots and paths that will not work
REJECT CONFIDENCE ?,B
REJECT PATH UNLIKELY,CLOSED

# Require a decent skimmer SNR on CW (human reports and spots without SNR are exempt)
PASS MINSNR CW 10

SHOW FILTER FULL
```

### Watching a station, a spotter or a region

```text
# Only spots of calls starting with K1 (wildcards are case-insensitive)
REJECT DXCALL ALL
PASS DXCALL K1*

# Ignore a noisy spotter
REJECT DECALL W3LPL

# Only EU DX in CQ zone 14 with a JO grid field
REJECT DXCONT ALL
PASS DXCONT EU
REJECT DXZONE ALL
PASS DXZONE 14
REJECT DXGRID2 ALL
PASS DXGRID2 JO

# Whole countries (multi-word entity names are allowed; separate several with commas)
REJECT DXDXCC North Korea
REJECT DEDXCC United States,Canada
```

### Comment and event filters

```text
# Require a phrase and ban others (phrases may contain spaces)
PASS COMMENT CQ
REJECT COMMENT QRT,test me

# Only park / summit / field activity
REJECT EVENT ALL
PASS EVENT POTA,SOTA,WWFF
```

### Local ("nearby") mode

```text
SET GRID JO90AA         # validate a Maidenhead locator first
PASS NEARBY ON          # 700 km, or 1500 km on 160/80/60 m
PASS NEARBY 1000        # override the radius (km) for this session
SHOW NEARBY
PASS NEARBY OFF         # back to the full feed
```

### Feature switches

```text
REJECT BEACON           # hide NCDXF/beacon spots
PASS SELF               # show spots of your own callsign
REJECT WWV              # hide WWV bulletin traffic
```

### Session preferences

```text
SET DEDUPE FAST         # tighter per-client duplicate window (10 s)
SET DEDUPE SLOW         # 30 s (default)
SHOW DEDUPE
SET NOISE URBAN         # receive-noise class used for VOACAP
```

### Posting, querying and pausing

```text
DX 7001.0 K1ABC CW up 599      # post a spot you heard
SHOW DX 20                     # last 20 spots matching your filters
SHOW DX K1ABC 5                # last 5 spots of K1ABC
SHOW PROP K1ABC 20m CW         # 24 h propagation outlook
WHOSPOTSME 20m                 # countries that recently spotted you
PAUSE                          # pause the live feed for 30 s
...read the output...
RESUME
```

### CC Cluster / DX Spider aliases

```text
SET/DX                  # enable spots
SET/SKIMMER OFF         # hide skimmer-sourced spots
SET/NOFT8               # hide FT8
ACCEPT/SPOTS            # continue streaming
```

### Inspecting the result

```text
SHOW FILTER             # concise summary
SHOW FILTER FULL        # includes feature switches and MINSNR
SHOW FILTER BAND        # a single category
SHOW SETTINGS
```

> All commands are case-insensitive. A category starts **unrestricted**, so a
> lone `PASS <CATEGORY> <values>` adds to the allow-set without removing
> anything; use `REJECT <CATEGORY> ALL` first to show only selected values. See
> [FILTERS.md](FILTERS.md) for the full semantics.