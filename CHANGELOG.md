# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.2] - 2026-10-17

### Fixed

- `cty.dat` continuation lines are now parsed correctly (commas/semicolons,
  `=` overrides and `(...)`/`[...]` annotations). Previously only each entity's
  primary prefix was registered, so many callsigns (`W*`, `N*`, `SQ*`, ...)
  never resolved to a country; `DXCONT`/`DECONT`, `DXDXCC`/`DEDXCC`, CQ-zone and
  grid enrichment therefore did nothing for those spots.

## [0.2.1] - 2026-10-17

### Fixed

- `EVENT` filtering (`PASS`/`REJECT EVENT`) now works. Event tokens were
  compared case-sensitively, so the filter never matched; a
  `REJECT EVENT ALL` + `PASS EVENT <tag>` whitelist was also inverted.
- `DXDXCC`/`DEDXCC` now accept multi-word entity names (e.g.
  `REJECT DXDXCC United States`); values are split on commas, not spaces.
- `COMMENT` phrases may contain spaces (e.g. `REJECT COMMENT test me`); use
  commas to separate multiple phrases.
- `REJECT MINSNR <MODE>` now clears the threshold; previously the `REJECT` verb
  was ignored and it silently set one.
- `PASS`/`REJECT DXCALL|DECALL ALL` now clears/restricts the category like every
  other category; `ALL` was previously treated as a literal wildcard.

## [0.2.0] - 2026-10-17

### Added

- Per-client duplicate suppression: each subscriber keeps its own window,
  chosen from the `SET DEDUPE` policy through the new `pipeline.dedup.policies`
  map (`FAST`/`MED`/`SLOW`). `SET DEDUPE` now has a real effect.
- Maidenhead locator validation for `SET GRID`; malformed locators are rejected.
- Confidence `C` (corrected) and `B` (busted) are now emitted: a suspected bust
  whose suggested call is a known-good SCP entry is corrected in place and
  tagged `C`, otherwise it is forwarded with its original call, a `bust? <call>`
  comment and tag `B`.

### Changed

- Duplicate suppression moved from the shared pipeline stage to the per-client
  fan-out, so it runs after each client's filter using that client's window.
  The `rxcluster_spots_deduped_total` metric now counts per-subscriber
  duplicate suppressions.
- `station.operator_grid` is the node reference locator for `PATH` tags and
  `SHOW PROP`; per-client `SET GRID` affects only `NEARBY` and the saved
  preferences. Messages and documentation updated accordingly.
- Busted spots are forwarded (and can be hidden with `REJECT CONFIDENCE B`)
  instead of being silently rejected.
- Per-callsign settings files are written only when a mutating command is
  handled, not on a plain login.

### Fixed

- `NEARBY` with no (or a malformed) operator grid is now inert instead of
  dropping every spot.
- `REJECT NEARBY` and `PASS NEARBY FALSE` now disable `NEARBY`; previously the
  verb was ignored and they enabled it.
- Own-callsign spots stay visible when `SELF` is on, even while `NEARBY` is
  active.
- Corroboration no longer leaks memory (stale frequency buckets are swept) and
  now keys on the base callsign so portable calls match SCP consistently.

## [0.1.0] - 2026-10-16

Initial release.

### Added

- Multi-source aggregation: RBN (telnet), DX Summit (HTTP JSON API), VE7CC
  (CC Cluster, human-only feed) and PSKReporter (digimode reception reports over
  MQTT; disabled by default because the global feed is very high volume).
- Asynchronous pipeline with bounded queues and drop-oldest backpressure.
- Duplicate suppression over a sliding time window.
- Validation: callsign shape checks, SCP membership, `cty.dat` lookup and
  cross-source corroboration with busted-call detection.
- N2WQ-style confidence tags (`? S P V C B`) and path reliability tags
  (`> = < - #`).
- VOACAP propagation enrichment with a bundled `voacapl` engine (compiled into
  the container image together with the `itshfbc` data files), background
  reliability-matrix precomputation and an empirical fallback, with solar-index
  refresh.
- Fixed-width (76-character) N2WQ/GoCluster spot layout for N1MM Logger+.
- Per-client filtering (band, mode, source, calls, geography, confidence,
  path, minimum SNR, comment, event, feature switches) using the N2WQ/GoCluster
  dialect with CC Cluster / DX Spider aliases.
- Interactive session: manual spot posting (`DX`), pause/resume (`PAUSE`,
  `RESUME`, `SHOW HOLD`), propagation outlook (`SHOW PROP`), spotter summary
  (`WHOSPOTSME`), dedupe tuning (`SHOW DEDUPE` / `SET DEDUPE`), expanded
  filter read-backs (`SHOW FILTER`, `SHOW FILTER FULL`) and `HELP <command>`.
- WWV/WCY/ANNOUNCE bulletin parsing from CC Cluster sources and the
  corresponding feature switches.
- Telnet server compatible with N1MM Logger+.
- HTTP `/health` and `/metrics` endpoints.
- Docker image and `docker-compose.yml`.
- Full English documentation set.
- Test suite covering parsing, filters, dedup, validation, tags and the telnet
  server.
