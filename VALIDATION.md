# Validation and confidence tags

RXCluster runs several cheap-to-expensive checks to reject fake/busted
callsigns and to attach a confidence tag to every accepted spot.

## Checks

1. **Shape** (`rxcluster/validate/patterns.py`) - the fastest filter. Rejects
   calls that are too short/long, contain no digit or letter, or have three or
   more identical consecutive characters. Portable modifiers (`/P`, `/M`,
   `/QRP`, ...) and slashed prefixes are stripped first (`3D2/R` -> `3D2`).
2. **SCP membership** (`scp.py`) - looks the call up in `MASTER.SCP`. A hit is
   strong evidence the call is real.
3. **cty.dat** (`cty.py`) - resolves the country/prefix and derives DXCC
   entity, continent, CQ zone and an approximate grid used for enrichment.
4. **Corroboration** (`corroboration.py`) - tracks observations per frequency
   bucket within a time window and counts distinct spotters.

## Confidence symbols

| Symbol | Meaning |
| --- | --- |
| `?` | Low - little supporting evidence |
| `S` | One current report with static/recent on-band support (in SCP) |
| `P` | Corroborated below the strongest level (2 independent sources) |
| `V` | Strongly corroborated (`min_agree` sources, default 3) |
| `C` | Corrected call that passed validation |
| `B` | Suggested correction failed validation (busted) |

The `S`/`P`/`V` thresholds come from
`pipeline.validation.corroboration.min_agree` and the window
`pipeline.validation.corroboration.window_seconds`.

## Busted-call detection

When a lone report is **not** in the SCP and there is a nearby call (bounded
Levenshtein distance, default 1) at the same frequency with corroborated
support, the report is corrected or flagged:

- if the suggested call is a known-good SCP entry, the spot's callsign is
  replaced with the suggestion, it is tagged `C` and forwarded with an
  `ex <original>` comment;
- otherwise the spot keeps its original call, is tagged `B` and forwarded with a
  `bust? <suggestion>` comment.

Either way the spot is forwarded (not dropped) so the operator can see the
suspect call; use `REJECT CONFIDENCE B` to hide busts.

The edit distance is configurable via
`pipeline.validation.corroboration.edit_distance`.

## Result

Accepted spots carry a confidence symbol that:

- is emitted in the fixed confidence column (column 70) of the 76-character
  spot line when `enrichment.tags.confidence` is `true`, and
- can be filtered per client with `PASS`/`REJECT CONFIDENCE` (e.g.
  `REJECT CONFIDENCE ?`).

## Tuning for a contest

- Raise `min_agree` to be stricter about `V` (fewer, more reliable spots).
- Set `edit_distance: 2` to catch two-character busts (as N1MM can do).
- Keep `scp_enabled: true` for the best discrimination; only disable it if the
  SCP file is unavailable.
- A sensible client-side default for CW contests is
  `REJECT CONFIDENCE ?` and `PASS MINSNR CW 10`.