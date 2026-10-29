#!/usr/bin/env bash
# SysPulse APT Repository Setup (https://github.com/P374R/syspulse-cli)
set -e

echo -e "\033[1;36m==>\033[0m Setting up APT repository for \033[1;97mSysPulse CLI\033[0m..."

# Ensure curl is installed
if ! command -v curl &> /dev/null; then
    apt-get update -qq && apt-get install -y -qq curl
fi

# Download the latest .deb package from GitHub Releases directly to apt archives
DEB_URL="https://github.com/P374R/syspulse-cli/releases/latest/download/syspulse-cli_1.0.0_all.deb"
CACHE_DIR="/var/cache/apt/archives"
mkdir -p "$CACHE_DIR"

echo -e "\033[1;34m==>\033[0m Fetching latest package index..."
curl -fsSL "$DEB_URL" -o "$CACHE_DIR/syspulse-cli_1.0.0_all.deb"

# Register package in a local apt pool so 'sudo apt install syspulse-cli' works natively
POOL_DIR="/var/lib/syspulse-apt"
mkdir -p "$POOL_DIR"
cp "$CACHE_DIR/syspulse-cli_1.0.0_all.deb" "$POOL_DIR/"

# Create local Packages index
cd "$POOL_DIR"
if command -v dpkg-scanpackages &> /dev/null; then
    dpkg-scanpackages . /dev/null > Packages
    gzip -fk Packages
else
    # Fallback direct install if scanpackages is not present
    dpkg -i "$CACHE_DIR/syspulse-cli_1.0.0_all.deb" || apt-get install -f -y
fi

# Add local source list
SOURCE_FILE="/etc/apt/sources.list.d/syspulse-cli.list"
if [ -f "$POOL_DIR/Packages" ]; then
    echo "deb [trusted=yes] file:$POOL_DIR ./" > "$SOURCE_FILE"
    apt-get update -qq
fi

echo -e "\033[1;32m==>\033[0m \033[1mSysPulse repository successfully configured!\033[0m"
echo -e "    You can now install and update anytime via:"
echo -e "    \033[1;97msudo apt install syspulse-cli\033[0m"

