FROM ubuntu:24.04

ARG TARGETARCH
ARG APP_UID=1000
ARG APP_GID=1000
ARG VERSION=dev
ARG SOURCE=https://github.com/s-t-e-f-a-n/BillCollector

LABEL org.opencontainers.image.title="BillCollector" \
    org.opencontainers.image.description="Collect documents from web portals using Playwright recipes" \
    org.opencontainers.image.source="${SOURCE}" \
    org.opencontainers.image.version="${VERSION}" \
    org.opencontainers.image.licenses="MIT"

# Set timezone and environment
ENV TZ="Europe/Berlin" HOME="/home/billcollector" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

# Set the directory for the application
WORKDIR /apps

# Set environment variables
ENV PLAYWRIGHT_BROWSERS_PATH=/apps/browser

# Install Python3 (the image builds for linux/amd64 only)
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
RUN if [[ "${TARGETARCH:-amd64}" != "amd64" ]]; then \
        echo "BillCollector image builds for linux/amd64 only" >&2; exit 1; \
    fi && apt-get update && apt-get install -y --no-install-recommends python3 python3-pip

# Install the Python dependencies and the browser BEFORE the application
# code: BuildKit reuses every layer whose inputs and stage environment are
# unchanged, so a code-only deploy re-runs only the final app COPY + chown
# (seconds) instead of the network-bound pip/playwright steps.
COPY apps/requirements.txt .
RUN pip3 install -r requirements.txt --break-system-packages
RUN python3 -m playwright install --with-deps chromium ffmpeg

# Install dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-liberation fonts-dejavu-core fonts-dejavu-mono \
    libasound2t64 libatk-bridge2.0-0 libatk1.0-0 libatspi2.0-0 \
    libcairo2 libcups2 libdbus-1-3 libdrm2 libegl1 libgbm1 libglib2.0-0 \
    libgtk-3-0 libnspr4 libnss3 libpango-1.0-0 libx11-6 libx11-xcb1 libxcb1 \
    libxcomposite1 libxdamage1 libxext6 libxfixes3 libxrandr2 libxshmfence1 \
    xvfb fonts-noto-color-emoji fonts-unifont libfontconfig libfreetype6 \
    xfonts-cyrillic xfonts-scalable fonts-ipafont-gothic fonts-wqy-zenhei \
    fonts-tlwg-loma-otf fonts-ubuntu \
    && rm -rf /var/lib/apt/lists/*

# Install the application
COPY --chown=${APP_UID}:${APP_GID} apps/. .

# Create the download folder and the app user's home, then hand ownership of
# the whole /apps tree (app code, browser, downloads) and $HOME to the
# non-root app user
RUN mkdir -p /apps/Downloads "$HOME" && chown -R ${APP_UID}:${APP_GID} /apps "$HOME"

# Run as the non-root app user (numeric, no user account needed)
USER ${APP_UID}:${APP_GID}

# Expose the download folder as a volume
VOLUME ["/apps/Downloads"]

# Entry point
CMD ["/bin/bash"]
