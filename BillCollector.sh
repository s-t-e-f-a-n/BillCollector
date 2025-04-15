#!/bin/bash
#
# Wrapper for python app BillCollector
# - 1st param: ini-file
# - 2nd param: debug [True/False]

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"

if [[ -f .commit_id ]]; then
    COMMIT_ID=$(cat .commit_id)
    echo "Commit-ID: $COMMIT_ID"
else
    echo "Error: .commit_id not found. Check .git/hooks/pre-commit exists with following content:
    echo 'git rev-parse HEAD > .commit_id'"
fi

docker run -v $SCRIPT_DIR/apps/Downloads:/apps/Downloads --rm billcollector:latest \
       python3 ./BillCollector.py $1 $2
