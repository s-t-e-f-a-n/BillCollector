FROM ubuntu:24.04

# Set timezone
ENV TZ="Europe/Berlin"

# Set the directory for the application
WORKDIR /apps

# Set environment variables
ENV PLAYWRIGHT_BROWSERS_PATH=/apps/browser

# Install Python3
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y python3 python3-pip

# Install pip requirements, app and browser
ARG VER=unknown
COPY apps/. .
RUN pip3 install -r requirements.txt --break-system-packages
RUN python3 -m playwright install --with-deps chromium ffmpeg

# Install dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-liberation libasound2t64 libatk-bridge2.0-0 libatk1.0-0 libatspi2.0-0 \
    libcairo2 libcups2 libdbus-1-3 libdrm2 libegl1 libgbm1 libglib2.0-0 \
    libgtk-3-0 libnspr4 libnss3 libpango-1.0-0 libx11-6 libx11-xcb1 libxcb1 \
    libxcomposite1 libxdamage1 libxext6 libxfixes3 libxrandr2 libxshmfence1 \
    xvfb fonts-noto-color-emoji fonts-unifont libfontconfig libfreetype6 \
    xfonts-cyrillic xfonts-scalable fonts-ipafont-gothic fonts-wqy-zenhei \
    fonts-tlwg-loma-otf fonts-ubuntu \
    && rm -rf /var/lib/apt/lists/*

# Creates a non-root user with an explicit UID and adds permission to access the /apps folder
# For more info, please refer to https://aka.ms/vscode-docker-python-configure-containers
# ...and https://code.visualstudio.com/remote/advancedcontainers/add-nonroot-user
#RUN adduser -u 5678 --disabled-password --gecos "" appuser && chown -R appuser /apps
#USER appuser

# Entry point
CMD ["/bin/bash"]
