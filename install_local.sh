#!/bin/bash

# install_local.sh
# This script is a part of the BillCollector project.
#
# Run the script with the following command:
# bash install_local.sh
#   or 
# chmod +x install_local.sh
# ./install_local.sh
#   or
# source install_local.sh
#
# This script installs Chrome for Testing, ChromeDriver, Python3, and required Python modules for BillCollector in a local environment.
# The script is tested on Ubuntu 20.04 LTS and WSL2.
#
# resources:
# https://cloudbytes.dev/snippets/run-selenium-and-chrome-on-wsl2

# Red color variable
RED='\033[0;31m'
NC='\033[0m' # No Color

# install bash command if not installed yet
enable_bash_cmd() {
  local cmd=$1

  if ! command -v $cmd 2>&1 >/dev/null
    then
      echo "* $cmd could not be found, will be installed"
      $SUDO apt-get install $cmd -y >/dev/null
  fi
}

# Check if the script is running as root or with sudo permissions
# https://stackoverflow.com/questions/18215973/how-to-check-if-running-as-root-in-a-bash-script
if [ "$(id -u)" -eq 0 ]; then
    SUDO=""
else
    # Check if sudo is available
    if command -v sudo &> /dev/null; then
        SUDO="sudo"
    else
        echo "* Sudo is not available. Please run the script as root or install sudo."
        exit 1
    fi
fi

echo "* Update package list"
$SUDO apt-get update

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
$SUDO apt-get install ca-certificates fonts-liberation \
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

# install Python3 if not installed
echo "* Check and install Python3"
enable_bash_cmd python3
echo "* Check and install pip3"
enable_bash_cmd python3-pip
echo "* Check and install Python virtual env, install all required Python modules and activate .venv"
enable_bash_cmd python3-venv
python3 -m venv .venv
echo

# Check if the script is called directly or sourced
# https://stackoverflow.com/questions/2683279/how-to-detect-if-a-script-is-being-sourced
if [[ "$0" == "bash" || "$0" == "-bash" ]]; then
    echo "* Sourced: source activate .venv and install python modules in .venv."
    source ./.venv/bin/activate
    pip install -r requirements.txt
else
    echo -e "${RED}* Called: activate .venv and install python modules in .venv.${NC}"
    source .venv/bin/activate
    pip install -r requirements.txt
    echo "* To re-activate the virtual environment, run the following commands:"
    echo -e "${RED}** cd apps${NC}"
    echo "** source .venv/bin/activate"
fi

echo
echo "* To deactivate the virtual environment, run the following command:"
echo "** deactivate"
echo 
echo "* Finished installing local environment: Chrome for Testing, ChromeDriver, Python3, and required Python modules"
echo
echo "* You may check the installation by running the following command:"
echo "** python3 test_selenium.py"
echo
