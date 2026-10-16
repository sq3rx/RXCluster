# syntax=docker/dockerfile:1
#
# RXCluster container image.
#
# The image is self-contained: it compiles and installs the `voacapl` VOACAP
# engine together with its `itshfbc` data files, so propagation enrichment
# works out of the box (no external VOACAP setup required).

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# Build toolchain for voacapl (Fortran) plus runtime utilities.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
        build-essential \
        gfortran \
        automake \
        autoconf \
        libtool \
    && rm -rf /var/lib/apt/lists/*

# ---- Build and install voacapl -------------------------------------------
WORKDIR /opt
RUN git clone --depth 1 https://github.com/jawatson/voacapl.git voacapl \
    && cd voacapl \
    && (autoreconf -i || true) \
    && ./configure --prefix=/usr/local \
    && make -j"$(nproc)" \
    && make install \
    && cd /opt \
    && rm -rf voacapl

# Keep the Fortran runtime required by the voacapl binary, drop the toolchain.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgfortran5 \
    && apt-get purge -y --auto-remove build-essential gfortran automake autoconf libtool git \
    && rm -rf /var/lib/apt/lists/*

# ---- Install the application ---------------------------------------------
WORKDIR /app
COPY pyproject.toml README.md ./
COPY rxcluster ./rxcluster
RUN pip install --no-cache-dir .

RUN mkdir -p /app/data /app/data/users /app/config /var/log/rxcluster

# ---- Unprivileged user + itshfbc data ------------------------------------
RUN useradd --create-home --uid 10001 rxcluster \
    && chown -R rxcluster:rxcluster /app /var/log/rxcluster

ENV HOME=/home/rxcluster
USER rxcluster
# Creates $HOME/itshfbc with the VOACAP coefficient/antenna/database files.
RUN makeitshfbc

EXPOSE 7300 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3).status==200 else 1)"

ENTRYPOINT ["rxcluster"]
CMD ["--config", "config/rxcluster.yaml"]