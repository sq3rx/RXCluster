# syntax=docker/dockerfile:1
#
# RXCluster container image.
#
# The build is self-contained: the application sources are cloned straight from
# git (see the RXCLUSTER_REPO/RXCLUSTER_REF build args) and the `voacapl` VOACAP
# engine plus its `itshfbc` data files are compiled in, so propagation
# enrichment works out of the box with no external VOACAP setup.
#
# The runtime image ships only the example configuration under /app/config (a
# container path; on the host this is RXCluster/config). The entrypoint seeds
# /app/config/rxcluster.yaml from it on first start, fixes the ownership of the
# bind-mounted directories and drops to the PUID/PGID runtime user, so settings
# survive image upgrades. Nothing is written outside the project directory on
# the host.

# ---- Builder: compile voacapl and install the application -----------------
FROM python:3.12-slim AS builder

ARG RXCLUSTER_REPO=https://github.com/sq3rx/RXCluster.git
ARG RXCLUSTER_REF=master

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# Build toolchain for voacapl (Fortran).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        git \
        build-essential \
        gfortran \
        automake \
        autoconf \
        libtool \
    && rm -rf /var/lib/apt/lists/*

# Build and install voacapl into /usr/local (carried into the runtime stage).
RUN git clone --depth 1 https://github.com/jawatson/voacapl.git /opt/voacapl \
    && cd /opt/voacapl \
    && (autoreconf -i || true) \
    && ./configure --prefix=/usr/local \
    && make -j"$(nproc)" \
    && make install \
    && cd / \
    && rm -rf /opt/voacapl

# Fetch the application sources directly from git.
RUN git clone --depth 1 --branch "${RXCLUSTER_REF}" "${RXCLUSTER_REPO}" /src/app

# Install the application and its Python dependencies into /usr/local.
RUN pip install --no-cache-dir /src/app

# ---- Runtime: minimal image with the app, voacapl and seeded config -------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/home/rxcluster

# libgfortran5 is the Fortran runtime required by voacapl; gosu lets the
# entrypoint drop from root to the PUID/PGID runtime user.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgfortran5 gosu \
    && rm -rf /var/lib/apt/lists/*

# Carry over the Python environment (app + deps) and voacapl.
COPY --from=builder /usr/local /usr/local

# voacapl ships its itshfbc data under /usr/local/share; the engine writes
# scratch files into itshfbc/run, so make it writable for the runtime user.
RUN chmod -R a+rwX /usr/local/share/voacapl/itshfbc 2>/dev/null || true

# Entrypoint is taken from the build context (this repository checkout).
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

WORKDIR /app

# Runtime layout and the configuration template used to seed a fresh volume.
RUN mkdir -p /app/config /app/data/users /var/log/rxcluster \
    && useradd --create-home --uid 10001 rxcluster \
    && chown -R rxcluster:rxcluster /app /var/log/rxcluster
COPY --from=builder /src/app/config/rxcluster.example.yaml /app/config/rxcluster.example.yaml
RUN chown rxcluster:rxcluster /app/config/rxcluster.example.yaml

# Create the VOACAP itshfbc data once, as the unprivileged build user, then make
# it usable by any runtime UID (the container runs as PUID/PGID and voacapl
# writes scratch files into itshfbc/run).
USER rxcluster
RUN makeitshfbc \
    && chmod 755 "$HOME" \
    && chmod -R a+rwX "$HOME/itshfbc"

# The entrypoint starts as root so it can fix bind-mount ownership, then drops
# to PUID/PGID.
USER root

EXPOSE 7300 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3).status==200 else 1)"

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["--config", "config/rxcluster.yaml"]
