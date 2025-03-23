#!/bin/bash

# install bash command if not installed yet
enable_bash_cmd() {
  local cmd=$1

  if ! command -v $cmd 2>&1 >/dev/null
    then
      echo "* $cmd could not be found, will be installed"
      sudo apt-get install $cmd -y >/dev/null
  fi
}

# install required bash commands
echo "* Check and install required bash commands"
enable_bash_cmd jq
enable_bash_cmd wget
enable_bash_cmd curl
enable_bash_cmd unzip

# prepare apps
if test ! -d apps; then mkdir apps; else echo "* apps folder already exists"; fi
cd apps

## Run Selenium and Chrome on WSL2 using Python and Selenium webdriver  https://cloudbytes.dev/snippets/run-selenium-and-chrome-on-wsl2
# install Chrome for Testing 
meta_data=$(curl -s 'https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json')
url=$(echo "$meta_data" | jq -r '.channels.Stable.downloads.chrome[0].url')
file=$(echo "${url##*/}")
if test ! -f $file; then wget $url; else echo "* $file already downloaded"; fi
dir=$(echo "${file%%.*}")
if test ! -d $dir; then unzip $file; else echo "* $file already unzipped in folder"; fi

echo "* Installing Chrome dependencies"
sudo apt-get install ca-certificates fonts-liberation \
    libappindicator3-1 libasound2 libatk-bridge2.0-0 libatk1.0-0 libc6 \
    libcairo2 libcups2 libdbus-1-3 libexpat1 libfontconfig1 libgbm1 \
    libgcc1 libglib2.0-0 libgtk-3-0 libnspr4 libnss3 libpango-1.0-0 \
    libpangocairo-1.0-0 libstdc++6 libx11-6 libx11-xcb1 libxcb1 \
    libxcomposite1 libxcursor1 libxdamage1 libxext6 libxfixes3 libxi6 \
    libxrandr2 libxrender1 libxss1 libxtst6 lsb-release wget xdg-utils -y > /dev/null

works=$(./$dir/chrome --version)
if $(echo $works | grep -q "Google Chrome for Testing"); then echo "* Chrome runs: $works"; else "* FAILURE: $works"; fi

# install latest Chromedriver
url=$(echo "$meta_data" | jq -r '.channels.Stable.downloads.chromedriver[0].url')
file=$(echo "${url##*/}")
if test ! -f $file; then wget $url; else echo "* $file already downloaded"; fi
dir=$(echo "${file%%.*}")
if test ! -d $dir; then unzip $file; else echo "* $file already unzipped in folder"; fi
works=$(./$dir/chromedriver --version)
if $(echo $works | grep -q "ChromeDriver"); then echo "* ChromeDriver runs: $works"; else "* FAILURE: $works"; fi

# install selenium und pytest
echo "* install Python virtual env and activate it"
enable_bash_cmd python3-venv
python3 -m venv .venv

echo "* Finish"
echo "* For usage invoke following commands on console:"
echo "** source .venv/bin/activate"
echo "** pip install selenium"
echo "** python3 test_selenium.py"
