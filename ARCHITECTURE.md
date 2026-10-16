# Architecture

RXCluster is a single-process, fully asynchronous application built on
`asyncio` (with `uvloop` on Linux/macOS). It is designed so that **a slow
client can never introduce latency for the rest of the system**.

## Pipeline

```
Source connectors ──► raw queue ──► consumer task ──► Pipeline
                                                    ├─ normalize (band/mode)
                                                    ├─ dedup
                                                    ├─ validate
                                                    ├─ enrich (VOACAP + tags)
                                                    └─ SpotBus.publish
                                                              │
                                       per-client CompiledFilter + queue
                                                              │
                                                     telnet writer task
```

### Stages

1. **Sources** (`rxcluster/sources/`) - one asyncio task per source. Each
   connector maintains its connection with exponential-backoff reconnection
   and emits normalized `Spot` objects through an async callback.
2. **Raw queue** - a bounded `asyncio.Queue` between the sources and the single
   consumer task. When full the *oldest* spot is dropped, protecting memory
   under bursts.
3. **Normalizer** (`rxcluster/parse/`) - resolves band from frequency
   (`bisect`) and mode from source token or the sub-band plan.
4. **Dedup** (`rxcluster/dedup/`) - sliding-window suppression of repeated
   reports (same spotter, call and quantized frequency).
5. **Validator** (`rxcluster/validate/`) - shape check, SCP membership,
   geography and cross-source corroboration; assigns a confidence tag and
   rejects malformed/busted calls.
6. **Enricher** (`rxcluster/enrich/`) - sets the propagation path class and
   renders the N1MM-compatible line.
7. **SpotBus** (`rxcluster/bus/`) - fans the line out to subscribers. Each
   subscriber has a compiled filter and a bounded queue.

## Concurrency model

- A **single consumer task** runs the pipeline, so stages need no locking.
- Each source is its own task; they only touch the shared queue.
- Each client has a **writer task** draining its own queue. TCP backpressure
  (`writer.drain()`) blocks only that task; its queue absorbs the difference
  and drops the oldest entries when full.
- Compilation of filters is interned by signature, so clients sharing a preset
  share one immutable `CompiledFilter`.

## Backpressure and freshness

The design prioritises **freshness over completeness**: under load, old spots
are dropped rather than delaying new ones. This matches contest usage where the
latest spot is the most valuable. The counters
`rxcluster_spots_deduped_total`, `..._rejected_total` and the per-subscriber
`dropped` counter make this observable.

## Performance budget

- Band lookup: O(log n) `bisect` over band boundaries.
- Filter evaluation: O(1) bitmask/set checks; pattern and comment checks are
  skipped entirely for clients that do not restrict those categories.
- Dedup and corroboration run in memory; there is no per-spot network or disk
  I/O.
- VOACAP predictions are memoized in a lazily-filled matrix keyed by
  `(target_grid, band, hour, ssn)`, so the expensive computation happens at
  most once per cell per solar state.

## Module map

| Path | Responsibility |
| --- | --- |
| `rxcluster/config.py` | Configuration models and loading |
| `rxcluster/models.py` | `Spot`, enums, stats |
| `rxcluster/parse/` | Line parsing, band/mode resolution |
| `rxcluster/dedup/` | Duplicate suppression |
| `rxcluster/validate/` | SCP, cty.dat, patterns, corroboration |
| `rxcluster/enrich/` | VOACAP engine, solar data, tag rendering |
| `rxcluster/filters/` | Filter state, compilation, command parsing |
| `rxcluster/bus/` | Publish/subscribe fan-out |
| `rxcluster/sources/` | RBN, DX Summit, VE7CC, PSKReporter connectors |
| `rxcluster/server/` | Telnet server and command execution |
| `rxcluster/users/` | Per-callsign settings persistence |
| `rxcluster/web/` | Health and metrics HTTP server |
| `rxcluster/main.py` | Wiring, logging, signal handling |