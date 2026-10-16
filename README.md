# RXCluster

High-performance **DX Cluster aggregator/proxy**. RXCluster merges multiple
spot sources into a single, de-duplicated, validated and propagation-enriched
stream that is served over Telnet and can be consumed natively by
**N1MM Logger+** during the heaviest contests (CQWW CW, thousands of spots per
minute).

## Features

- **Multi-source aggregation**: Reverse Beacon Network (RBN), DX Summit,
  VE7CC (CC Cluster, human-only feed) and PSKReporter (digimode reception
  reports over MQTT; disabled by default).
- **Advanced validation** that rejects fake/busted calls using
  [Super Check Partial](https://www.supercheckpartial.com/) (SCP), callsign
  shape rules, `cty.dat` country patterns and cross-source corroboration.
- **Rich filtering** per client: band, mode, source, calls, geography,
  confidence, propagation path, minimum SNR, comments and events - with the
  N2WQ/GoCluster dialect plus CC Cluster / DX Spider aliases.
- **Interactive session**: post spots (`DX`), pause/resume the live feed,
  request a per-path propagation outlook (`SHOW PROP`), summarise who is
  spotting you (`WHOSPOTSME`), and inspect full filter/settings read-backs.
- **Propagation enrichment**: per-spot VOACAP path prediction between the
  operator's QTH and the spotted station, rendered as N2WQ-style path symbols.
  The container **compiles and bundles the real `voacapl` engine**, so this
  works out of the box (an empirical fallback is used elsewhere).
- **N2WQ/GoCluster spot layout**: a fixed-width (76-character) line with the
  propagation glyph just before the DX grid (column 63) and the callsign
  confidence symbol between the grid and the time (column 70), matching the
  GoCluster output that N1MM Logger+'s AMQ window reads.
- **Built for volume**: `asyncio` + `uvloop`, bounded queues with a drop-oldest
  policy so a slow client can never introduce lag.
- **Fully containerised**: `Dockerfile` and `docker-compose.yml` included.

## Architecture at a glance

```
 RBN telnet ─────┐
 DX Summit HTTP ─┤   raw queue    ┌────────────┐   ┌───────────┐
 VE7CC telnet ───┤─► (bounded) ──►│ Normalizer │──►│   Dedup   │
 PSKReporter MQTT ┘                └────────────┘   └─────┬─────┘
                                                         ▼
                                             ┌───────────────────────┐
                                             │ Validator (SCP, cty,  │
                                             │ corroboration)        │
                                             └───────────┬───────────┘
                                                         ▼
                                             ┌───────────────────────┐
                                             │ Enricher (VOACAP +    │
                                             │ N2WQ tags)            │
                                             └───────────┬───────────┘
                                                         ▼
                                       ┌────────────────────────────┐
                                       │ SpotBus (per-client filters│
                                       │ bounded queues, drop-oldest)│
                                       └───────┬─────────────┬──────┘
                                               ▼             ▼
                                        Telnet (N1MM)   HTTP /health
```

## Quick start (Docker)

```bash
cp config/rxcluster.example.yaml config/rxcluster.yaml
# edit your callsign, grid and source settings
docker compose up --build
```

Point N1MM Logger+ at `your-host:7300` and log in with your callsign. See
[INSTALL.md](INSTALL.md) for details and local (non-Docker) installation.

## Documentation

| Document | Contents |
| --- | --- |
| [INSTALL.md](INSTALL.md) | Installation, Docker and local, N1MM setup |
| [CONFIGURATION.md](CONFIGURATION.md) | Every configuration option |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Pipeline, concurrency and performance model |
| [FILTERS.md](FILTERS.md) | Filter categories and semantics |
| [VALIDATION.md](VALIDATION.md) | Busted-call rejection and confidence tags |
| [VOACAP.md](VOACAP.md) | Propagation prediction and path symbols |
| [COMMANDS.md](COMMANDS.md) | Telnet command reference |
| [OPERATIONS.md](OPERATIONS.md) | Monitoring, tuning, troubleshooting |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Development workflow |

## License

[MIT](LICENSE)