#!/bin/bash
#
# Wrapper for python app BillCollector
# - 1st param: ini-file
# - 2nd param: debug [True/False]

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"

if [[ -f .commit_id ]]; then
    COMMIT_ID=$(cat .commit_id)
    echo "Commit-ID: $COMMIT_ID"
fi

docker run -v $SCRIPT_DIR/apps/Downloads:/apps/Downloads \
        -v $SCRIPT_DIR/apps/db:/apps/db \
        --rm billcollector:latest \
        python3 ./BillCollector.py $1 $2
