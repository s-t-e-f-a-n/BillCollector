FROM ubuntu:24.04

ARG TARGETARCH
ARG APP_UID=1000
ARG APP_GID=1000
ARG VERSION=dev
ARG REVISION=unknown

LABEL org.opencontainers.image.title="BillCollector" \
      org.opencontainers.image.description="Collect documents from web portals using Selenium recipes" \
      org.opencontainers.image.source="https://github.com/flowcool/BillCollector" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${REVISION}" \
      org.opencontainers.image.licenses="MIT"

ENV TZ="Europe/Zurich" \
    HOME="/home/billcollector" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /apps

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN set -eux; \
    if [[ "${TARGETARCH:-amd64}" != "amd64" ]]; then \
      echo "BillCollector currently supports linux/amd64 only" >&2; \
      exit 1; \
    fi; \
    apt-get update; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      fonts-liberation \
      jq \
      libappindicator3-1 \
      libasound2t64 \
      libatk-bridge2.0-0 \
      libatk1.0-0 \
      libc6 \
      libcairo2 \
      libcups2 \
      libdbus-1-3 \
      libexpat1 \
      libfontconfig1 \
      libgbm1 \
      libgcc1 \
      libglib2.0-0 \
      libgtk-3-0 \
      libnspr4 \
      libnss3 \
      libpango-1.0-0 \
      libpangocairo-1.0-0 \
      libstdc++6 \
      libx11-6 \
      libx11-xcb1 \
      libxcb1 \
      libxcomposite1 \
      libxcursor1 \
      libxdamage1 \
      libxext6 \
      libxfixes3 \
      libxi6 \
      libxrandr2 \
      libxrender1 \
      libxss1 \
      libxtst6 \
      lsb-release \
      python3 \
      python3-pip \
      unzip \
      wget \
      xdg-utils; \
    rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    metadata="$(curl --fail --silent --show-error --location \
      https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json)"; \
    chrome_url="$(jq -r '.channels.Stable.downloads.chrome[] | select(.platform == "linux64") | .url' <<< "${metadata}")"; \
    driver_url="$(jq -r '.channels.Stable.downloads.chromedriver[] | select(.platform == "linux64") | .url' <<< "${metadata}")"; \
    wget --quiet "${chrome_url}" -O chrome.zip; \
    wget --quiet "${driver_url}" -O chromedriver.zip; \
    unzip -q chrome.zip; \
    unzip -q chromedriver.zip; \
    rm chrome.zip chromedriver.zip

COPY apps/requirements.txt ./requirements.txt
RUN python3 -m pip install --break-system-packages -r requirements.txt

RUN set -eux; \
    mkdir -p /apps/Downloads "${HOME}"; \
    chown "${APP_UID}:${APP_GID}" /apps /apps/Downloads "${HOME}"

COPY --chown=${APP_UID}:${APP_GID} apps/ .

USER ${APP_UID}:${APP_GID}

VOLUME ["/apps/Downloads"]

CMD ["python3", "./BillCollector.py", "./bc_default.ini"]
