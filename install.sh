#!/usr/bin/env bash
# SysPulse Linux Installer (https://github.com/P374R/syspulse-cli)
set -e

echo -e "\033[1;36m==>\033[0m Installing \033[1;97mSysPulse CLI\033[0m (syspulse-cli)..."

# Ensure Python 3 and dependencies
if command -v apt-get &> /dev/null; then
    echo -e "\033[1;34m==>\033[0m Ensuring python3 and psutil via apt..."
    apt-get update -qq && apt-get install -y -qq python3 python3-psutil curl
elif command -v dnf &> /dev/null; then
    dnf install -y -q python3 python3-psutil curl
elif command -v pacman &> /dev/null; then
    pacman -Sy --noconfirm --needed python python-psutil curl
fi

INSTALL_DIR="/usr/local/bin"
mkdir -p "$INSTALL_DIR"

echo -e "\033[1;34m==>\033[0m Downloading syspulse..."
curl -fsSL "https://raw.githubusercontent.com/P374R/syspulse-cli/main/main.py" -o "$INSTALL_DIR/syspulse"
chmod +x "$INSTALL_DIR/syspulse"

# Create symlink for syspulse-cli
ln -sf "$INSTALL_DIR/syspulse" "$INSTALL_DIR/syspulse-cli"

echo -e "\033[1;32m==>\033[0m \033[1mSysPulse CLI successfully installed!\033[0m"
echo -e "    Run \033[1;97msyspulse\033[0m or \033[1;97msyspulse-cli\033[0m to launch."

