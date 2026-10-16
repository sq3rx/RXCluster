# syntax=docker/dockerfile:1
#
# RXCluster container image.
#
# The build is self-contained: sources are cloned straight from git (see the
# RXCLUSTER_REPO/RXCLUSTER_REF build args) and the `voacapl` VOACAP engine plus
# its `itshfbc` data files are compiled in, so propagation enrichment works out
# of the box with no external VOACAP setup.
#
# The runtime image ships only the example configuration under /app/config; the
# entrypoint seeds /app/config/rxcluster.yaml from it on first start. Mount a
# volume at /app/config and the settings survive image upgrades.

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

# Fortran runtime required by the voacapl binary.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgfortran5 \
    && rm -rf /var/lib/apt/lists/*

# Carry over the Python environment (app + deps + entrypoint) and voacapl.
COPY --from=builder /usr/local /usr/local
COPY --from=builder /src/app/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

WORKDIR /app

# Runtime layout and the configuration template used to seed a fresh volume.
RUN mkdir -p /app/config /app/data/users /var/log/rxcluster \
    && useradd --create-home --uid 10001 rxcluster \
    && chown -R rxcluster:rxcluster /app /var/log/rxcluster
COPY --from=builder /src/app/config/rxcluster.example.yaml /app/config/rxcluster.example.yaml
RUN chown rxcluster:rxcluster /app/config/rxcluster.example.yaml

USER rxcluster
# Creates $HOME/itshfbc with the VOACAP coefficient/antenna/database files.
RUN makeitshfbc

EXPOSE 7300 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3).status==200 else 1)"

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["--config", "config/rxcluster.yaml"]
