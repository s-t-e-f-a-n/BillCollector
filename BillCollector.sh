#!/bin/bash
#
# Wrapper for python app BillCollector
# - 1st param: ini-file
# - 2nd param: debug [True/False]

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"

# Reject a double start: hold an exclusive, non-blocking lock on the shared
# lock file for the whole duration of the docker run (the container's /apps
# is image-owned, so only a host-side lock is visible to two runs). The lock
# is released automatically when this script exits.
LOCK_FILE="$SCRIPT_DIR/apps/.bc.lock"
if ! touch "$LOCK_FILE" 2>/dev/null; then
    echo "Error: cannot create lock file $LOCK_FILE" >&2
    exit 1
fi
exec 9>>"$LOCK_FILE"
if ! flock -n 9; then
    echo "BillCollector is already running (lock file: $LOCK_FILE). Skipping this start." >&2
    exit 1
fi

if [[ -f .commit_id ]]; then
    COMMIT_ID=$(cat .commit_id)
    echo "Commit-ID: $COMMIT_ID"
fi

if [[ ! -f "$SCRIPT_DIR/apps/.env" || ! -r "$SCRIPT_DIR/apps/.env" ]]; then
    echo "Error: apps/.env must be a readable configuration file." >&2
    exit 1
fi

docker run -v "$SCRIPT_DIR/apps/.env:/apps/.env:ro" \
        -v $SCRIPT_DIR/apps/Downloads:/apps/Downloads \
        -v $SCRIPT_DIR/apps/db:/apps/db \
        --rm billcollector:latest \
        python3 ./BillCollector.py $1 $2
