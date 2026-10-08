#!/bin/bash
#
# Wrapper for python app BillCollector
# - Arguments are forwarded unchanged: <ini-file> [debug] [--service <NAME>]
# - Runs as the invoking non-root user (see doc/nonroot_runtime.md)

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"

RUN_UID="$(id -u)"
RUN_GID="$(id -g)"
if [[ "$RUN_UID" == 0 ]]; then
    echo "Error: run BillCollector as the non-root owner of its runtime directories." >&2
    exit 1
fi
# Validate configuration before creating any runtime directory.
if [[ ! -f "$SCRIPT_DIR/apps/.env" || ! -r "$SCRIPT_DIR/apps/.env" ]]; then
    echo "Error: apps/.env must be a readable configuration file." >&2
    exit 1
fi
for RUNTIME_DIR in "$SCRIPT_DIR/apps/db" "$SCRIPT_DIR/apps/Downloads"; do
    if [[ ! -e "$RUNTIME_DIR" && ! -L "$RUNTIME_DIR" ]]; then
        (umask 077; mkdir -p "$RUNTIME_DIR") || exit 1
    fi
    if [[ ! -d "$RUNTIME_DIR" || ! -w "$RUNTIME_DIR" || ! -x "$RUNTIME_DIR" ]]; then
        echo "Error: runtime directory is not writable/traversable: $RUNTIME_DIR" >&2
        exit 1
    fi
done

# Reject a double start: hold an exclusive, non-blocking lock on the host
# lock file for the whole duration of the docker run, shared with local UI
# runs. The container also locks /apps/db/.bc.lock on the DB mount. The lock
# is released automatically when this script exits.
LOCK_FILE="$SCRIPT_DIR/apps/.bc.lock"
if ! touch "$LOCK_FILE" 2>/dev/null; then
    echo "Error: cannot create lock file $LOCK_FILE (check its ownership; see doc/nonroot_runtime.md)" >&2
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

RUN_GROUPS="$(id -G)" || exit 1
read -r -a GROUP_IDS <<< "$RUN_GROUPS"
GROUP_ARGS=()
for GROUP_ID in "${GROUP_IDS[@]}"; do
    if [[ "$GROUP_ID" != "$RUN_GID" ]]; then
        GROUP_ARGS+=(--group-add "$GROUP_ID")
    fi
done

docker run --user "$RUN_UID:$RUN_GID" "${GROUP_ARGS[@]}" \
        -v "$SCRIPT_DIR/apps/.env:/apps/.env:ro" \
        --tmpfs "/apps/runtime:uid=$RUN_UID,gid=$RUN_GID,mode=0700" \
        -v "$SCRIPT_DIR/apps/Downloads:/apps/Downloads" \
        -v "$SCRIPT_DIR/apps/db:/apps/db" \
        --rm billcollector:latest \
        python3 ./BillCollector.py "$@"
