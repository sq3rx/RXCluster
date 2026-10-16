# Operations

## Health and metrics

The HTTP server (default port 8080) exposes:

- `GET /health` - liveness probe, returns `{"status": "ok", "forwarded": N}`.
- `GET /metrics` - Prometheus-format counters and gauges:
  - `rxcluster_spots_total` - spots received from all sources
  - `rxcluster_spots_deduped_total` - suppressed as duplicates
  - `rxcluster_spots_rejected_total` - rejected by validation
  - `rxcluster_spots_forwarded_total` - forwarded to at least one client
  - `rxcluster_spots_by_source_total{source=...}` - per-source counters
  - `rxcluster_clients` - connected telnet clients
  - `rxcluster_subscribers` - bus subscribers
  - `rxcluster_queue_depth` - current intake queue depth

## Logging

Logging is configured under the `logging` section. `format: json` produces one
JSON object per line (ideal for log shippers); `format: text` produces
human-readable lines. Set `file` to also write to a file (the container image
writes to `/var/log/rxcluster`).

## Container operations

```bash
docker compose up -d                 # start
docker compose logs -f rxcluster     # follow logs
docker compose restart rxcluster     # apply a config change
docker compose down                  # stop and remove
```

Configuration lives in the `rxcluster-config` volume and is preserved across
image upgrades. Apply a change by exporting it, editing, copying it back and
restarting; no rebuild is needed:

```bash
docker compose cp rxcluster:/app/config/rxcluster.yaml ./rxcluster.yaml
# edit ./rxcluster.yaml
docker compose cp ./rxcluster.yaml rxcluster:/app/config/rxcluster.yaml
docker compose restart rxcluster
```

## Performance tuning

| Symptom | Action |
| --- | --- |
| Intake queue always full | Increase `pipeline.raw_queue_size`; check source health |
| Clients report missing spots | Increase `server.telnet.client_queue_size` |
| Too many spots reaching N1MM | Tighten client filters (band/mode/confidence) |
| Too many busted spots | Raise `corroboration.min_agree`; set `edit_distance: 2` |
| CPU saturated by enrichment | Increase `voacap.refresh_hours`; predictions are already cached |

The drop-oldest policy means that under sustained overload the *newest* spots
are always kept. If you see sustained drops, the bottleneck is downstream
(client too slow) or the host is under-provisioned.

## Soak / load testing

The test suite includes unit and integration tests. For a load test, generate
synthetic `DX de` lines and feed them through `Pipeline.process`, or connect a
scripted client and publish a burst through `SpotBus`. A useful target is
~3000 spots/minute (RBN contest peak) with sub-second end-to-end latency.

## Troubleshooting

### No spots arrive

- Check source connectivity in the logs (connection errors are logged with
  backoff).
- Verify the `callsign` for RBN/VE7CC is accepted.
- Confirm `enabled: true` for the desired sources.

### N1MM shows no spots

- Ensure the cluster is selected and connected on the **Clusters** tab.
- Check N1MM's **Bands/Modes** and **Filters** tabs - node filtering plus local
  filtering are cumulative.
- Run `SHOW FILTER` over telnet to confirm the effective filters.

### Login rejected / banner only

- Enter a valid callsign at the `login:` prompt;
  `max_clients` may also have been reached.

### VOACAP path symbols are blank

- Set `station.operator_grid` and `SET GRID` for the client.
- The target grid may be unknown (missing `cty.dat` or no country match).

### Reference data missing

- Check the logs for download warnings.
- Place `MASTER.SCP`, `cty.dat` and `patt3ch.lst` manually in the `data/`
  directory if the upstream URLs are unavailable.

## Signals

`SIGINT` / `SIGTERM` trigger a graceful shutdown: source tasks are cancelled,
clients are closed, and servers are stopped.