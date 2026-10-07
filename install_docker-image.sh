#!/bin/bash

# Build the BillCollector docker image and set up the bind-mount targets for
# the NAS deployment.
#
# The mount targets (paperless consumer folder + database folder) are NOT
# hardcoded. They are resolved in this order:
#   1. CONSUMER_DIR / DB_DIR environment variables (deploy_remote.sh forwards
#      them from its .env),
#   2. a .env file next to this script (plain KEY=VALUE lines only - no shell
#      code is executed, and variables already set keep their value),
#   3. otherwise the script exits with an error before building anything.
# Both values must be absolute paths to existing directories.
#
# Local image builds without NAS mount setup: SKIP_MOUNT_SETUP=1
# (skips the symlink + chown step entirely, apps/ is left untouched).

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Fill variables that are not set (non-empty) yet from a .env file next to
# this script, if present. Only plain KEY=VALUE lines are read, only the keys
# this script understands are exported, and no shell code is executed.
if [ -f "$SCRIPT_DIR/.env" ]; then
    while IFS= read -r line || [ -n "$line" ]; do
        if [[ "$line" =~ ^[[:space:]]*(export[[:space:]]+)?([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*=[[:space:]]*(.*)$ ]]; then
            key="${BASH_REMATCH[2]}"
            value="${BASH_REMATCH[3]}"
            if [[ "$value" == \"*\" && "${#value}" -ge 2 ]]; then
                value="${value:1:${#value}-2}"
            elif [[ "$value" == \'*\' && "${#value}" -ge 2 ]]; then
                value="${value:1:${#value}-2}"
            fi
            case "$key" in
                CONSUMER_DIR|DB_DIR|APP_UID|APP_GID|SKIP_MOUNT_SETUP)
                    if [ -z "${!key:-}" ]; then
                        export "$key=$value"
                    fi
                    ;;
            esac
        fi
    done < "$SCRIPT_DIR/.env"
fi

# UID/GID of the non-root user the image runs as (must match the APP_UID/APP_GID
# build args); defaults apply only when neither the environment nor the .env
# file provided a value
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

SETUP_MOUNTS=1
if [ "${SKIP_MOUNT_SETUP:-0}" = "1" ]; then
    SETUP_MOUNTS=0
    echo "[INFO] SKIP_MOUNT_SETUP=1 - the bind-mount setup (symlinks + chown) will be skipped."
fi

# Validate the mount targets before building, so a misconfiguration fails
# immediately instead of at the first production run.
if [ "$SETUP_MOUNTS" = "1" ]; then
    for var in CONSUMER_DIR DB_DIR; do
        value="${!var:-}"
        if [ -z "$value" ]; then
            echo "[ERROR] ${var} is not set. Define it in the .env file next to this script (see .env.example) or in the environment (deploy_remote.sh forwards it from the deploy machine's .env)." >&2
            exit 1
        fi
        if [[ "$value" != /* ]]; then
            echo "[ERROR] ${var} must be an absolute path (got: '${value}')." >&2
            exit 1
        fi
        if [ ! -d "$value" ]; then
            echo "[ERROR] ${var} does not exist or is not a directory: '${value}'." >&2
            exit 1
        fi
    done
fi

# Build the single image; APP_UID/APP_GID keep the image's user in sync with
# the host-side chown. The build context is the script's own directory, so
# the script works from any working directory.
#
# There is deliberately NO REVISION build arg: a Dockerfile ARG value is part
# of the BuildKit cache key of every RUN step, so a changing REVISION (every
# deploy checks out a new commit) invalidated the whole layer cache and
# forced the network-bound pip/playwright rebuild on every deploy. The
# deployed commit is recorded in the deploy log (deploy_remote.sh prints
# `git log -1`), so no image label is needed for traceability.
build_image --build-arg APP_UID="$APP_UID" --build-arg APP_GID="$APP_GID" \
    -t "$IMAGE_NAME" "$SCRIPT_DIR"

if [ "$SETUP_MOUNTS" = "1" ]; then
    # Replace apps/Downloads + apps/db with symlinks to the shared folders.
    # A real, non-empty directory is never replaced (it would destroy local
    # data, e.g. on a dev machine); symlinks (previous installs) and empty
    # directories are.
    for entry in "Downloads:$CONSUMER_DIR" "db:$DB_DIR"; do
        name="${entry%%:*}"
        target="${entry#*:}"
        path="$SCRIPT_DIR/apps/$name"
        if [ -e "$path" ] && [ ! -L "$path" ] && [ -n "$(ls -A "$path" 2>/dev/null)" ]; then
            echo "[ERROR] apps/$name is a real, non-empty directory - refusing to replace it with a symlink to $target. Empty it or remove it first, or use SKIP_MOUNT_SETUP=1 for a local image build." >&2
            exit 1
        fi
        rm -rf "$path"
        ln -s "$target" "$path"
    done

    # Set ownership of the bind-mount targets for the image's non-root user,
    # so the container can write to the shared Downloads folder and the
    # database. A failure here must abort the deploy, not the next cron run.
    if ! chown "${APP_UID}:${APP_GID}" "$CONSUMER_DIR"; then
        echo "[ERROR] chown ${APP_UID}:${APP_GID} failed for $CONSUMER_DIR - the container user cannot write to its download folder. Fix the NAS permissions and re-run the install." >&2
        exit 1
    fi
    if ! chown -R "${APP_UID}:${APP_GID}" "$DB_DIR"; then
        echo "[ERROR] chown -R ${APP_UID}:${APP_GID} failed for $DB_DIR - the container user cannot write to its database. Fix the NAS permissions and re-run the install." >&2
        exit 1
    fi
fi
