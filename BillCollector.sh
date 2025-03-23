#!/bin/bash
#
# Wrapper for python app BillCollector
# - 1st param: ini-file
# - 2nd param: debug [True/False]

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"

docker run -v $SCRIPT_DIR/apps/Downloads:/apps/Downloads --rm billcollector:latest \
       python3 ./BillCollector.py $1 $2
