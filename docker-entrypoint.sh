#!/bin/sh
#
# Container entrypoint.
#
# Persist configuration across image upgrades: the mounted /app/config volume is
# only initialised on first start (Docker copies the image contents when the
# volume is empty). Seed a real config from the bundled example if none exists,
# then hand over to the application.

set -eu

CONFIG_DIR="/app/config"
CONFIG_FILE="${CONFIG_DIR}/rxcluster.yaml"
TEMPLATE="${CONFIG_DIR}/rxcluster.example.yaml"

if [ ! -f "${CONFIG_FILE}" ] && [ -f "${TEMPLATE}" ]; then
    echo "rxcluster: seeding ${CONFIG_FILE} from ${TEMPLATE}"
    cp "${TEMPLATE}" "${CONFIG_FILE}"
fi

exec rxcluster "$@"
