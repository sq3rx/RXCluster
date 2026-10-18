# Filters

RXCluster implements the **N2WQ/GoCluster** filter dialect and accepts common
**CC Cluster / DX Spider** aliases. Filtering happens at the node, before spots
are written to a client, which reduces telnet traffic and CPU load on N1MM.

## Semantics

- Within a category, **REJECT wins over PASS**.
- Different categories are combined with logical **AND**.
- `PASS <CATEGORY> <values>` adds values to the category's allow-set. A
  category starts **unrestricted**, so a lone `PASS` leaves it unrestricted.
  To show only selected values use `REJECT <CATEGORY> ALL` first and then
  `PASS <CATEGORY> a,b`; `PASS <CATEGORY> ALL` clears the restriction again.
  This applies to every exact category, e.g. band:
  `REJECT BAND ALL` + `PASS BAND 20,40`, or mode:
  `REJECT MODE ALL` + `PASS MODE CW`.
- `REJECT <CATEGORY> <values>` blacklists values without restricting the rest.
- `COMMENT` matches literal, case-insensitive substrings; any allowed phrase
  matches, a rejected phrase always wins.
- `MINSNR` applies a per-mode threshold and **exempts human reports and spots
  without an SNR**. `REJECT MINSNR <MODE>` (or `PASS MINSNR <MODE> ALL`) clears
  the threshold.
- `EVENT` uses key presence: untagged spots always pass.

Values for `DXDXCC`/`DEDXCC` (entity names) and `COMMENT` (phrases) may contain
spaces; separate multiple values with commas, e.g. `REJECT COMMENT QRT,QSY`.
`DXDXCC`/`DEDXCC` values are resolved through `cty.dat`, so a canonical prefix
matches every call of that entity: `REJECT DXDXCC SP` blocks `SQ9ABC` as well,
because both resolve to Poland.

## Categories

| Category | Matches | Values |
| --- | --- | --- |
| `BAND` | band | `160m`, `80m`, `40m`, `20m`, ... |
| `MODE` | mode | `CW`, `SSB`, `RTTY`, `FT8`, `FT4`, `PSK`, `UNKNOWN` |
| `SOURCE` | source type | `HUMAN`, `SKIMMER` |
| `DXCALL` | spotted call (wildcards) | `K1ABC`, `W1*` |
| `DECALL` | spotter call (wildcards) | `W3LPL`, `W3*` |
| `DXCONT` / `DECONT` | continent | `NA`, `EU`, `AS`, ... |
| `DXZONE` / `DEZONE` | CQ zone | `1`..`40` |
| `DXDXCC` / `DEDXCC` | DXCC entity | entity name or canonical prefix (e.g. `DL`, `IT9`) |
| `DXGRID2` / `DEGRID2` | 2-character grid field | `FN`, `JO`, ... |
| `CONFIDENCE` | confidence symbol | `?`, `S`, `P`, `V`, `C`, `B` |
| `PATH` | path class | `HIGH`, `MEDIUM`, `LOW`, `UNLIKELY`, `CLOSED`, `INSUFFICIENT` |
| `COMMENT` | free-text phrase | any string |
| `EVENT` | event tag | `POTA`, `SOTA`, `IOTA`, `WWFF`, `LLOTA` |

Feature switches (enabled with `PASS`, disabled with `REJECT`):
`BEACON`, `WWV`, `WCY`, `ANNOUNCE`, `SELF`, `TOXIC`.

`WWV`, `WCY` and `ANNOUNCE` control propagation bulletins and announcements
received from CC Cluster sources; `BEACON` hides NCDXF/beacon spots; `SELF`
controls spots of your own callsign; `TOXIC` hides human spots already flagged
as toxic (fail-open when nothing is classified).

## NEARBY

`PASS NEARBY ON` (requires `SET GRID`) keeps only spots where either the DX
station or the spotter is near your grid: within 700 km, or 1500 km on 160 m,
80 m and 60 m. While NEARBY is active the geography categories
(`DXCONT`/`DECONT`, `DXZONE`/`DEZONE`, `DXDXCC`/`DEDXCC`, `DXGRID2`/`DEGRID2`)
are suspended; their rules are retained and restored by `PASS NEARBY OFF`.

NEARBY is inert (no spots removed) until a valid grid is set: `SET GRID` rejects
malformed locators, and enabling NEARBY without a grid keeps the full feed with
a reminder. Once a grid is set, a spot with neither a DX grid nor a spotter grid
cannot be proven near and is therefore dropped, as is any spot outside the
radius. `REJECT NEARBY` (or `PASS NEARBY OFF`) switches it back off.

## Examples

```text
# Only 20m and 40m
REJECT BAND ALL
PASS BAND 20,40
SHOW FILTER

# Only CW
REJECT MODE ALL
PASS MODE CW

# Hide a mode without affecting others
REJECT MODE FT8

# Require a minimum CW SNR of 10 dB (skimmer spots only)
PASS MINSNR CW 10

# Reject low-confidence and unlikely-path spots
REJECT CONFIDENCE ?
REJECT PATH UNLIKELY

# Require a comment phrase
PASS COMMENT CQ
REJECT COMMENT QRT

# Block one spotter
REJECT DECALL W3LPL
```

## CC Cluster / DX Spider aliases

| Alias | Effect |
| --- | --- |
| `SET/DX` | enable spots |
| `SET/SKIMMER ON\|OFF` | allow/reject skimmer-sourced spots |
| `SET/FT8` / `SET/NOFT8` | allow/reject FT8 |
| `ACCEPT/CONT <v>` / `PASS CONT <v>` | allow DX continents (alias for `PASS DXCONT`) |
| `REJECT/CONT <v>` | reject DX continents (alias for `REJECT DXCONT`) |
| `SET/DXCONT <v>` / `SET/DECONT <v>` | allow DX/spotter continents |
| `SET/NODXCONT` / `SET/NODECONT` | clear the continent selection |
| `SET DX FILTER ...` | accepted (acknowledged) |
| `ACCEPT/SPOTS` | continue streaming |

## Node-level defaults

The `defaults` section of the configuration is the template applied to every
new client. Typical contest defaults:

```yaml
defaults:
  bands: all
  modes: all
  reject_confidence: []
  path: [HIGH, MEDIUM, LOW, UNLIKELY, CLOSED, INSUFFICIENT]
  min_snr: { CW: 10 }
  switches: { beacon: false, wwv: true }
```

Clients can override any of these at runtime. Use `SHOW FILTER` to inspect the
effective settings.

## Performance notes

Filter state is compiled into an immutable `CompiledFilter` and interned by
signature, so identical filter configurations share one object. Evaluation
skips categories that are unrestricted, which keeps the hot path cheap even
with many connected clients.

## Persisted per-callsign settings

When `users.enabled` is set (default), the settings of every operator are saved
to `data/users/<CALL>.json` and restored automatically the next time the same
callsign logs in. This covers all `PASS`/`REJECT` selections, `MINSNR`,
`NEARBY`, the feature switches, and the session preferences `SET GRID`,
`SET NOISE` and `SET DEDUPE`. A record is written as soon as a mutating command
is handled; a plain login that changes nothing creates no file. Note that the
saved `SET GRID` only affects the per-client NEARBY filter — propagation `PATH`
tags and `SHOW PROP` always use the node reference `station.operator_grid`.
`SET DEDUPE` selects a per-client duplicate-suppression window (FAST 10 s,
MED 20 s, SLOW 30 s) that is applied to your own spot stream after your filter.

Persistence is keyed solely on the callsign typed at the login prompt; the DX
cluster protocol has no authentication, so treat the stored settings as a
convenience rather than an access-control boundary. Set `users.enabled: false`
to fall back to the node-level `defaults` on every login.
