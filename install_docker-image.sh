#!/bin/bash

# Path to your paperless consumer directory
# This is used to create a symlink in the `apps` directory
# to the Downloads directory where the scanned documents are stored.
CONSUMER_DIR="/srv/disk-by-label/Shared-Folders/EarthG/Scans/.paperless/_BillCollector_/"
DB_DIR="/srv/disk-by-label/Shared-Folders/EarthG/Scans/.paperless/_BillCollector_/db"

# Set image name
IMAGE_NAME="billcollector:latest"

# Function to build Docker image
build_image() {
    echo "Building Docker image for $1..."
    if docker build "$@"; then
        echo "Build successful!"
    else
        echo "Build failed! Check the logs above."
        exit 1
    fi
}

# Ensure exactly one argument is provided
if [ "$#" -ne 1 ]; then
    echo "Usage: bash install_docker-image.sh <selenium|playwright>"
    exit 1
fi

# Determine which Dockerfile to use
case "$1" in
    selenium)
        build_image -t "$IMAGE_NAME" .
        ;;
    playwright)
        build_image -f Dockerfile_pw -t "$IMAGE_NAME" .
        ;;
    *)
        echo "Invalid argument. Use 'selenium' or 'playwright'."
        exit 1
        ;;
esac

pushd apps
rm -rf Downloads
ln -s $CONSUMER_DIR Downloads
rm -rf db
ln -s $DB_DIR db
popd
