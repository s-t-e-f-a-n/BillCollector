FROM ubuntu:24.04

# Set timezone
ENV TZ="Europe/Berlin"

# install command line tools
RUN apt-get update && apt-get install -y wget && apt-get install -y zip && apt-get install -y curl && apt-get install -y jq

###
WORKDIR /apps

# install latest chrome testing
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
RUN <<'EOT' bash
  set -eux
  meta_data=$(curl -s "https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json")
  url=$(echo "$meta_data" | jq -r ".channels.Stable.downloads.chrome[0].url")
  file=$(echo "${url##*/}")
  wget "$url"
  unzip "$file" && rm -f "$file"
  apt-get install ca-certificates fonts-liberation \
    libappindicator3-1 libasound2t64 libatk-bridge2.0-0 libatk1.0-0 libc6 \
    libcairo2 libcups2 libdbus-1-3 libexpat1 libfontconfig1 libgbm1 \
    libgcc1 libglib2.0-0 libgtk-3-0 libnspr4 libnss3 libpango-1.0-0 \
    libpangocairo-1.0-0 libstdc++6 libx11-6 libx11-xcb1 libxcb1 \
    libxcomposite1 libxcursor1 libxdamage1 libxext6 libxfixes3 libxi6 \
    libxrandr2 libxrender1 libxss1 libxtst6 lsb-release wget xdg-utils -y > /dev/null
EOT

# install latest chromedriver
RUN <<'EOT' bash
  set -eux
  meta_data=$(curl -s "https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json")
  url=$(echo "$meta_data" | jq -r '.channels.Stable.downloads.chromedriver[0].url')
  file=$(echo "${url##*/}")
  wget "$url"
  unzip "$file" && rm -f "$file"
EOT

# Install python3
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
RUN apt-get update
RUN apt-get install -y python3 && apt-get install -y python3-pip

# Install pip requirements and app
ARG VER=unknown
COPY apps/.  .
RUN pip3 install -r requirements.txt --break-system-packages

# Creates a non-root user with an explicit UID and adds permission to access the /app folder
# For more info, please refer to https://aka.ms/vscode-docker-python-configure-containers
# ...and https://code.visualstudio.com/remote/advancedcontainers/add-nonroot-user
#RUN adduser -u 5678 --disabled-password --gecos "" appuser && chown -R appuser /apps
#USER appuser

# During debugging, this entry point will be overridden. For more information, please refer to https://aka.ms/vscode-docker-python-debug
CMD ["/bin/bash"]

