#!/bin/bash

# Path to your paperless consumer directory
# This is used to create a symlink in the `apps` directory
# to the Downloads directory where the scanned documents are stored.
CONSUMER_DIR="/srv/disk-by-label/Shared-Folders/EarthG/Scans/.paperless/_BillCollector_/"
DB_DIR="/srv/disk-by-label/Shared-Folders/EarthG/Scans/.paperless/_BillCollector_/db"

# UID/GID of the non-root user the image runs as (must match the APP_UID/APP_GID build args)
APP_UID="${APP_UID:-1000}"
APP_GID="${APP_GID:-1000}"

# Set image name
IMAGE_NAME="billcollector:latest"

# Function to build Docker image
build_image() {
    echo "Building Docker image..."
    if docker build "$@"; then
        echo "Build successful!"
    else
        echo "Build failed! Check the logs above."
        exit 1
    fi
}

# No engine argument: the repository has a single Dockerfile (Playwright/Chromium).
# An optional positional argument is still accepted for back-compat with older
# .env files that pass the legacy value.
if [ "$#" -gt 1 ]; then
    echo "Usage: bash install_docker-image.sh [playwright]"
    exit 1
fi
if [ "$#" -eq 1 ] && [ "$1" != "playwright" ]; then
    echo "Invalid argument '$1': no engine argument is needed (the legacy value 'playwright' is still accepted)."
    exit 1
fi

# Build the single image; REVISION feeds the OCI image revision label
build_image --build-arg REVISION="$(git rev-parse --short HEAD)" -t "$IMAGE_NAME" .

pushd apps
rm -rf Downloads
ln -s $CONSUMER_DIR Downloads
rm -rf db
ln -s $DB_DIR db
popd

# Set ownership of the bind-mount targets for the image's non-root user, so the
# container can write to the shared Downloads folder and the database.
# Guarded: on machines without the OMV shared folders (local builds) the targets
# do not exist and the step is skipped; on the NAS they always exist.
if [ -e "$CONSUMER_DIR" ]; then
    if ! chown "${APP_UID}:${APP_GID}" "$CONSUMER_DIR"; then
        echo "[ERROR] chown ${APP_UID}:${APP_GID} failed for $CONSUMER_DIR - the container user cannot write to its download folder. Fix the NAS permissions and re-run the install." >&2
        exit 1
    fi
fi
if [ -e "$DB_DIR" ]; then
    if ! chown -r "${APP_UID}:${APP_GID}" "$DB_DIR"; then
        echo "[ERROR] chown -r ${APP_UID}:${APP_GID} failed for $DB_DIR - the container user cannot write to its database. Fix the NAS permissions and re-run the install." >&2
        exit 1
    fi
fi
