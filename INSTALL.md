# Installation

## Requirements

- Python 3.11+ (developed and tested on 3.12/3.14) **or** Docker.
- Network access to the spot sources (including `mqtt.pskreporter.info` when
  the PSKReporter source is enabled) and (optionally) the NOAA SWPC solar feed.
- For VOACAP predictions: the `voacapl` command-line engine. The Docker image
  **compiles and installs `voacapl` and its `itshfbc` data files automatically**,
  so no extra setup is needed. For local (non-Docker) installs without
  `voacapl`, RXCluster falls back to a built-in empirical model - see
  [VOACAP.md](VOACAP.md).

## Docker (recommended)

1. Set the runtime user/group in `.env`. The entrypoint starts as root, gives
   ownership of `./config`, `./data` and `./logs` to this user, then drops
   privileges (so it works even if the directories are root-owned):

   ```bash
   cp .env.example .env
   sed -i "s/^PUID=.*/PUID=$(id -u)/; s/^PGID=.*/PGID=$(id -g)/" .env
   ```

   On a root-based install you can instead leave `PUID=0` and `PGID=0` to keep
   running as root.

2. Build and start. The image is built straight from git and the configuration
   is seeded automatically from the bundled example on first start:

   ```bash
   docker compose up --build -d
   ```

3. Edit at least `station.callsign` and `station.operator_grid`, then restart:

   ```bash
   nano config/rxcluster.yaml
   docker compose restart rxcluster
   ```

4. Check health and logs:

   ```bash
   curl http://localhost:8080/health
   docker compose logs -f rxcluster
   ```

All mutable state (configuration, reference data, per-callsign users, logs)
lives inside this directory through relative bind mounts, so
`docker compose up --build` picks up new image versions without touching your
settings. To build from a different branch or tag, override `RXCLUSTER_REF`
(and optionally `RXCLUSTER_REPO`) under the service's `build.args`.

Because the application sources are cloned from git **inside** the build,
Docker would otherwise reuse the cached clone and ignore new commits. To update,
bump `RXCLUSTER_CACHEBUST` in `.env` so the clone layer is refreshed:

```bash
git pull
sed -i "s/^RXCLUSTER_CACHEBUST=.*/RXCLUSTER_CACHEBUST=$(date +%s)/" .env
docker compose up --build -d
```

Your configuration, data and logs are preserved (they live in the bind-mounted
directories).

Paths such as `/app/config` are container paths only; they never exist on the
host. The bind mounts map them into this project directory:

| Host (inside `RXCluster/`) | Container |
| --- | --- |
| `./config` | `/app/config` |
| `./data` | `/app/data` |
| `./logs` | `/var/log/rxcluster` |

## Local installation (Python)

```bash
python -m venv .venv
. .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp config/rxcluster.example.yaml config/rxcluster.yaml
rxcluster --config config/rxcluster.yaml
```

To use `uvloop` (Linux/macOS only) it is installed automatically; on Windows
the default asyncio event loop is used.

## Ports

| Port | Purpose |
| --- | --- |
| 7300 | Telnet server for N1MM Logger+ and other clients |
| 8080 | HTTP `/health` and `/metrics` (Prometheus format) |

Both are configurable under `server.telnet` and `server.http`.

## Reference data files

RXCluster uses three data files, downloaded automatically at startup when
`data.auto_update` is `true` and the files are missing:

| File | Used for |
| --- | --- |
| `MASTER.SCP` | Super Check Partial membership checks |
| `cty.dat` | Country/prefix, continent, CQ zone and grid resolution |
| `patt3ch.lst` | RBN pattern list (reserved for additional validation) |

If a file cannot be downloaded the application still starts, with the relevant
validation/enrichment degraded. You can also place the files manually in the
`data/` directory.

## Connecting N1MM Logger+

1. Open the **Telnet** window in N1MM Logger+.
2. On the **Clusters** tab, add a cluster with host and port
   (e.g. `your-host:7300`) or use the *Stored/Edit list*.
3. Set the **Logon with** field to your callsign.
4. Optionally check *Automatically log on*.
5. On the **Filters** tab you may restrict bands/modes, but remember that
   filtering at the cluster (RXCluster) is more powerful - see
   [FILTERS.md](FILTERS.md) and [COMMANDS.md](COMMANDS.md).

You can test the connection with a plain telnet client:

```bash
telnet your-host 7300
# at the "login:" prompt type your callsign
```

## Verifying the deployment

- `http://localhost:8080/health` returns `{"status": "ok", ...}`.
- `http://localhost:8080/metrics` exposes counters for received, deduped,
  rejected and forwarded spots plus client/queue gauges.
- The Telnet banner appears immediately on connect.

## Uninstalling / resetting

The application keeps no persistent state of its own; stopping the container is
enough. To reset, remove the generated files inside the project directory:
`config/rxcluster.yaml`, `data/*` (except `data/.gitkeep`) and `logs/*` (except
`logs/.gitkeep`); they are re-created on the next start.