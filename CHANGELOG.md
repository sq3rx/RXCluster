# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
