#!/bin/bash

# Load environment variables from .env
ENV_FILE=".env"
if [ ! -f "$ENV_FILE" ]; then
  echo "[ERROR] .env file not found."
  exit 1
fi

# Import all variables from .env
set -a
source "$ENV_FILE"
set +a

# Check required variables
if [ -z "$REMOTE_USER" ] || [ -z "$REMOTE_HOST" ] || [ -z "$REMOTE_PATH" ] || [ -z "$INSTALL_SCRIPT" ] || [ -z "$GIT_BRANCH" ]; then
  echo "[ERROR] Missing required configuration variables in .env."
  exit 1
fi

REMOTE="${REMOTE_USER}@${REMOTE_HOST}"

echo "[INFO] Starting remote deployment on ${REMOTE_HOST}..."

# Execute commands on the remote system
ssh ${REMOTE} "
  set -e

  echo '[INFO] Checking access on remote system...'
  whoami >/dev/null || { echo '[ERROR] Cannot determine remote user'; exit 1; }

  echo '[INFO] Verifying target directory: ${REMOTE_PATH}'
  if [ ! -d '${REMOTE_PATH}' ]; then
    echo '[ERROR] Target directory does not exist: ${REMOTE_PATH}'
    exit 1
  fi

  cd '${REMOTE_PATH}'

  echo '[INFO] Checking Git installation...'
  if ! command -v git >/dev/null; then
    echo '[ERROR] Git is not installed on remote system.'
    exit 1
  fi

  echo '[INFO] Fetching latest repository updates...'
  if ! git fetch origin ${GIT_BRANCH}; then
    echo "[ERROR] Git fetch from ${GIT_BRANCH} failed."
    exit 1
  fi

  echo '[INFO] Resetting to origin/main...'
  if ! git reset --hard origin/${GIT_BRANCH}; then
    echo "[ERROR] Git reset to ${GIT_BRANCH} failed."
    exit 1
  fi

  echo '[INFO] Current commit info:'
  git log -1

  echo '[INFO] Verifying installtion script: ${INSTALL_SCRIPT}'
  if [ ! -f '${INSTALL_SCRIPT}' ]; then
    echo '[ERROR] Installation script not found: ${INSTALL_SCRIPT}'
    exit 1
  fi

  chmod +x '${INSTALL_SCRIPT}'
  echo '[INFO] Running installation script with arguments: ${INSTALL_SCRIPT_ARGS}'
  ./'${INSTALL_SCRIPT}' ${INSTALL_SCRIPT_ARGS}

  echo '[INFO] Remote deployment completed successfully.'
"
