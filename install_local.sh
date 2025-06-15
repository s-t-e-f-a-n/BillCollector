#!/bin/bash

# install_local.sh
# This script is a part of the BillCollector project.
#
# Run the script with the following command:
# bash install_local.sh <selenium|playwright>
#   or 
# chmod +x install_local.sh
# ./install_local.sh <selenium|playwright>
#   or
# source install_local.sh <selenium|playwright>
#
# When called with selenium:
# This script installs Chrome for Testing, ChromeDriver, Python3, and required Python modules for BillCollector in a local environment.
#
# When called with playwright:
# This script installs Playwright, Chromium, and required Python modules for BillCollector in a local environment.
#
# The script is tested on Ubuntu 20.04 LTS and WSL2.
#
# resources:
# https://cloudbytes.dev/snippets/run-selenium-and-chrome-on-wsl2

# usage: enable_bash_cmd <check_command> [install_package] [custom_check]
enable_bash_cmd() {
  local cmd="$1"
  local pkg="${2:-$cmd}"
  local custom_check="${3:-command -v $cmd >/dev/null 2>&1}"

  if ! eval "$custom_check"; then
    echo "* Command/module '$cmd' not found, installing package '$pkg'..."
    $SUDO apt-get install "$pkg" -y >/dev/null
  fi
}

# usage: check_for_folder <folder_name>
check_for_folder() {
    # Check if we are in the apps folder
    folder=$(basename "$(pwd)")
    if [[ "$folder" != "$1" ]]; then
        echo "!Exiting. We are in $folder, but this function is run in the $1 folder."
    exit 1
    fi
}

init() {

    # Red color variable
    RED='\033[0;31m'
    NC='\033[0m' # No Color

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
}

install_python3() {
    # install Python3 if not installed
    echo "* Check and install Python3"
    enable_bash_cmd python3
    echo "* Check and install pip3"
    enable_bash_cmd pip3 python3-pip
    echo "* Check and install Python virtual env, install all required Python modules and activate .venv"
    enable_bash_cmd "venv" "python3-venv" "python3 -m venv --help >/dev/null 2>&1"
    python3 -m venv .venv
    echo
}

install_selenium() {

    check_for_folder "apps"

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
    install_python3

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
}

install_playwright() {

    # install Python3 if not installed
    install_python3

    # Check if the script is called directly or sourced
    # https://stackoverflow.com/questions/2683279/how-to-detect-if-a-script-is-being-sourced
    if [[ "$0" == "bash" || "$0" == "-bash" ]]; then
        echo "* Sourced: source activate .venv and install python modules in .venv."
        source ./.venv/bin/activate
        pip install -r requirements-pw.txt
    else
        echo -e "${RED}* Called: activate .venv and install python modules in .venv.${NC}"
        source .venv/bin/activate
        pip install -r requirements-pw.txt
        echo "* To re-activate the virtual environment, run the following commands:"
        echo -e "${RED}** cd apps${NC}"
        echo "** source .venv/bin/activate"
    fi

    check_for_folder "apps"

    # Ensure browser directory exists
    BROWSER_DIR="$(pwd)/browser"
    if [ -d "$BROWSER_DIR" ]; then 
        echo "* Directory 'browser' already exists at: $BROWSER_DIR"
    else
        mkdir -p "$BROWSER_DIR"
        echo "* Created directory: $BROWSER_DIR"
    fi
    # Check for subdirectories starting with chromium or ffmpeg
    found_any=0
    for keyword in "chromium" "ffmpeg"; do
        match=$(find "$BROWSER_DIR" -maxdepth 1 -type d -name "${keyword}*")
        if [ -n "$match" ]; then
            echo "* Found subfolder(s) starting with '$keyword': $match"
            found_any=1
        fi
    done

    if [ "$found_any" -ne 0 ]; then
        echo "!Exiting. Check manually if the subfolders are correct or delete them manually first."
        exit 1
    fi

    echo "* Installing chromiumd and ffmpeg for Playwright"
    PLAYWRIGHT_BROWSERS_PATH=$(pwd)/browser playwright install chromium ffmpeg
    echo "* Installing Chrome dependencies"
    $SUDO apt-get install --no-install-recommends \
        fonts-liberation libasound2 libatk-bridge2.0-0 libatk1.0-0 libatspi2.0-0 \
        libcairo2 libcups2 libdbus-1-3 libdrm2 libegl1 libgbm1 libglib2.0-0 \
        libgtk-3-0 libnspr4 libnss3 libpango-1.0-0 libx11-6 libx11-xcb1 libxcb1 \
        libxcomposite1 libxdamage1 libxext6 libxfixes3 libxrandr2 libxshmfence1 \
        xvfb fonts-noto-color-emoji ttf-unifont libfontconfig libfreetype6 \
        xfonts-cyrillic xfonts-scalable fonts-ipafont-gothic fonts-wqy-zenhei \
        fonts-tlwg-loma-otf ttf-ubuntu-font-family -y > /dev/null

}

if [ "$#" -ne 1 ]; then
    echo "Usage: bash install_local.sh <selenium|playwright>"
    exit 1
fi
if [ "$1" == "selenium" ]; then
    init
    install_selenium
elif [ "$1" == "playwright" ]; then
    init
    install_playwright
else
    echo "Invalid argument. Use 'selenium' or 'playwright'."
    exit 1
fi