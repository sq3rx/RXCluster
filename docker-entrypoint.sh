#!/bin/sh
#
# Container entrypoint.
#
# Starts as root, seeds the configuration from the bundled example on first
# start, fixes the ownership of the bind-mounted directories (they may be owned
# by root on the host) and then drops to the PUID/PGID runtime user.
#
# PUID/PGID come from the environment (set them in .env). They default to
# 1000:1000; use 0:0 to keep running as root.

set -eu

PUID="${PUID:-1000}"
PGID="${PGID:-1000}"

CONFIG_DIR="/app/config"
CONFIG_FILE="${CONFIG_DIR}/rxcluster.yaml"
TEMPLATE="${CONFIG_DIR}/rxcluster.example.yaml"

echo "rxcluster: entrypoint uid=$(id -u) gid=$(id -g) -> PUID=${PUID} PGID=${PGID}"

if [ ! -f "${CONFIG_FILE}" ] && [ -f "${TEMPLATE}" ]; then
    echo "rxcluster: seeding ${CONFIG_FILE} from ${TEMPLATE}"
    cp "${TEMPLATE}" "${CONFIG_FILE}"
fi

if [ "$(id -u)" = "0" ]; then
    # Hand the bind-mounted directories to the runtime user. This makes the
    # container work regardless of who owns them on the host.
    chown -R "${PUID}:${PGID}" /app/config /app/data /var/log/rxcluster 2>/dev/null || true

    if [ "${PUID}" != "0" ]; then
        if command -v gosu >/dev/null 2>&1; then
            exec gosu "${PUID}:${PGID}" rxcluster "$@"
        fi
        echo "rxcluster: gosu not found; continuing as root" >&2
    fi
fi

exec rxcluster "$@"
