# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `SHOW DX` / `SH/DX` accept an optional callsign or prefix, band and mode
  (`SH/DX DL 20m CW`), matched case-insensitively; prefix and `*`/`?` wildcard
  matching is supported.

### Fixed

- `SHOW DX` / `SH/DX` now return only spots that pass the requesting client's
  filters (and NEARBY), matching the documented behaviour, instead of the
  unfiltered node-wide history.
- `SH/DX` no longer replies with nothing when there are no matches: it answers
  `No spots available.` (N1MM Logger+'s `SH/DX` appeared to be accepted but
  produced no output).

## [0.3.0] - 2026-10-18

### Added

- `RESET` (alias `CLEAR`) restores the node-level filter defaults;
  `RESET <CATEGORY>` clears a single category, and `RESET MINSNR|NEARBY|SWITCHES`
  clears those groups. Previously each category had to be cleared by hand (or
  the persisted user file deleted).
- CC Cluster / DX Spider continent aliases: `ACCEPT/CONT`, `REJECT/CONT`,
  `PASS/REJECT CONT`, and `SET/DXCONT` / `SET/DECONT` (with `SET/NOCONT`,
  `SET/NODXCONT` and `SET/NODECONT` to clear the selection).
- Startup warning when `cty.dat` loads suspiciously few prefixes, pointing at a
  missing or malformed reference file.

### Changed

- `NEARBY` is now a session-level feature instead of a filter switch. It
  combines with the other categories using AND (it no longer suspends the
  geography filters), the radii are configurable (`pipeline.nearby`, or
  `PASS NEARBY <km> [<low_km>]`), and `SHOW NEARBY` reports its state. The
  `nearby` flag moved out of the persisted filter record into a separate field.
- A lone `PASS <CATEGORY> <values>` on an unrestricted exact category (e.g.
  `PASS DXCONT EU`) now reports that it has no effect until the category is
  narrowed with `REJECT <CATEGORY> ALL`, instead of silently reporting success.

### Removed

- The `TOXIC` feature switch was removed. It was inert (nothing in the pipeline
  ever flagged a spot as toxic), so `REJECT TOXIC` never had an effect. A
  leftover `switches.toxic` entry in the configuration is accepted and ignored.

### Fixed

- `cty.dat` stores longitude positive-west but it was used as-is, so every
  derived locator was mirrored (e.g. Poland `IO02` instead of `JO92`). This
  made `DXGRID2`/`DEGRID2` wrong and skewed `NEARBY` distances for spots
  without a source-provided grid.
- Geography and country filters now work: `cty.dat` continuation lines
  (comma/semicolon lists, `=` overrides and `(...)`/`[...]` annotations) and
  spurious blank lines are parsed correctly, so callsigns such as `W*`, `N*` and
  `SQ*` resolve to a country. This restores `DXCONT`/`DECONT`,
  `DXDXCC`/`DEDXCC`, CQ-zone and grid enrichment.
- `DXDXCC`/`DEDXCC` now match a canonical prefix resolved through `cty.dat`
  (e.g. `REJECT DXDXCC SP` blocks `SQ9ABC`) as well as a multi-word entity name
  (`REJECT DXDXCC United States`); separate multiple values with commas.
- `EVENT` filtering (`PASS`/`REJECT EVENT`) now works: event tokens are compared
  case-insensitively and the `REJECT EVENT ALL` + `PASS EVENT <tag>` whitelist is
  no longer inverted.
- `COMMENT` phrases may contain spaces (e.g. `REJECT COMMENT test me`); use
  commas to separate multiple phrases.
- `REJECT MINSNR <MODE>` clears the threshold; previously the `REJECT` verb was
  ignored and it silently set one.
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
