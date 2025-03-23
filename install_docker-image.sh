#!/bin/bash

docker build -t billcollector:latest .

pushd apps
rm -rf Downloads
ln -s /srv/disk-by-label/Shared-Folders/EarthG/Scans/.paperless/_BillCollector_/ Downloads
popd
