# VOACAP propagation enrichment

RXCluster estimates the chance of a QSO between the operator's QTH and a
spotted station and renders the result as an **N2WQ-style path symbol** in the
spot comment. This helps an operator prioritise which spots are worth chasing.

## Path symbols

| Symbol | Class | Meaning |
| --- | --- | --- |
| `>` | `HIGH` | Favorable path (VOACAP reliability >= 0.70) |
| `=` | `MEDIUM` | Workable path (0.40 - 0.70) |
| `<` | `LOW` | Weak or marginal path (0.15 - 0.40) |
| `-` | `UNLIKELY` | Poor path (0 < REL < 0.15) |
| `#` | `CLOSED` | Reliability 0 |
| (blank) | `INSUFFICIENT` | Not enough data to rate the path |

The glyph is emitted as a single character just before the DX grid locator
(column 63) of the fixed-width 76-character spot line, matching N2WQ/GoCluster
so that N1MM Logger+ can display it in the AMQ window.

Clients can filter on these with `PASS`/`REJECT PATH HIGH,MEDIUM` etc.

## The container ships a complete VOACAP

The Docker image **compiles and installs the real VOACAP engine**
([`voacapl`](https://github.com/jawatson/voacapl)) together with its `itshfbc`
coefficient/antenna/database files. No external VOACAP setup is required - the
propagation features work out of the box.

If `voacapl` is not available (for example a local install on Windows or a
host without the data files), RXCluster transparently falls back to a built-in
empirical model, so the spot stream is never blocked.

## How predictions are produced

RXCluster does **not** run VOACAP for every spot - that would be far too slow.
Instead:

1. At startup and on every solar refresh, RXCluster precomputes a coverage
   **matrix** in the background: for each coarse target grid cell
   (`voacap.target_grid_degrees`, default 15°) it runs one point-to-point
   deck covering all 24 hours and all HF bands.
2. The reliability (`REL`) table is parsed from each VOACAP report and stored
   as `matrix[(cell, band, hour)] -> PathClass`.
3. Per-spot lookups are O(1): the spotted station's grid is mapped to the
   nearest cell and the current UTC hour selects the row.

While the matrix is being built (or for bands/grids not covered) RXCluster uses
the empirical fallback, which is also memoized.

Background precompute runs in a worker thread via `asyncio.to_thread` and does
not block the pipeline.

## Input deck

RXCluster generates a standard point-to-point deck modelled on the canonical
`voacapx.dat`, using isotropic antennas and `METHOD 30` (all frequencies, all
hours). Representative band frequencies (MHz) are:

| Band | 160m | 80m | 40m | 30m | 20m | 17m | 15m | 12m | 10m |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| MHz | 1.85 | 3.65 | 7.05 | 10.12 | 14.10 | 18.10 | 21.10 | 24.93 | 28.10 |

Invocation follows the `voacapl` CLI: `voacapl <itshfbc_dir> <in> <out>`, where
`<in>`/`<out>` are resolved under `<itshfbc_dir>/run/`.

## Empirical fallback

A dependency-free heuristic based on:

- great-circle distance between the two grids,
- the solar zenith angle at the mid-path (UTC, day of year),
- the smoothed sunspot number (SSN).

It estimates a maximum usable frequency (MUF) and a lowest usable frequency
(LUF) for the path and classifies the band relative to them, with extra margin
for long-haul paths and a special case for short NVIS paths on low bands.

## Solar data

The SSN is fetched from the NOAA SWPC feed configured in
`pipeline.enrichment.voacap.solar_source` and refreshed every
`refresh_hours`. When the feed is unreachable the value falls back to
`ssn_default`. A refresh clears both caches and triggers a matrix rebuild.

## Configuration

```yaml
pipeline:
  enrichment:
    voacap:
      enabled: true
      engine_path: /usr/local/bin/voacapl
      itshfbc_dir: ""          # auto-detect ($HOME/itshfbc, /usr/local/share/voacapl/itshfbc)
      precompute: true          # build the reliability matrix in the background
      refresh_hours: 6
      target_grid_degrees: 15
      modes: [CW, SSB, RTTY, FT8]
      ssn_default: 100
      solar_source: https://services.swpc.noaa.gov/json/solar-cycle/observed-solar-cycle-indices.json
```

`station.operator_grid` must be set for predictions to be produced; it is the
node reference QTH used for all clients, so without it every spot is classified
`INSUFFICIENT`. Per-client `SET GRID` does not change propagation tags.

## Accuracy disclaimer

Path symbols are triage hints, not guarantees. The deck uses isotropic
antennas and a generic required-SNR, so real-world results depend on your
antennas and power. The empirical fallback is a rough approximation; the
container's `voacapl` path is the accurate one.