# SysPulse CLI (syspulse-cli)

> Fastfetch-inspired, industrial-grade cross-platform system telemetry and active process dashboard for **Linux** and **Windows**.

[![GitHub Release](https://img.shields.io/github/v/release/P374R/syspulse-cli?style=flat-square&color=38bdf8)](https://github.com/P374R/syspulse-cli/releases/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](https://opensource.org/licenses/MIT)
[![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20Windows-red?style=flat-square)](https://github.com/P374R/syspulse-cli)

---

##  Quick Install

###  Linux (Ubuntu, Debian, Mint, Raspberry Pi, Arch, Fedora)

#### Option 1: Via APT (`sudo apt install syspulse-cli`)
Set up the repository once, then install natively via apt:
```bash
curl -fsSL https://raw.githubusercontent.com/P374R/syspulse-cli/main/setup-apt.sh | sudo bash
sudo apt install syspulse-cli
```
Now run it anywhere:
```bash
syspulse
```

#### Option 2: 1-Line Universal Linux Install
```bash
curl -fsSL https://raw.githubusercontent.com/P374R/syspulse-cli/main/install.sh | sudo bash
syspulse
```

#### Option 3: Manual Debian Package (.deb)
```bash
sudo apt install ./syspulse-cli_1.0.0_all.deb
syspulse
```

#### Option 4: Via pipx (Python Standard)
```bash
pipx install syspulse-cli
syspulse
```

---

###  Windows (Windows 10 & 11)

#### Option 1: Via Winget (Official Windows Package Manager)
```powershell
winget install P374R.SysPulse
```
Then run it anywhere:
```powershell
syspulse
```

#### Option 2: 1-Line PowerShell Install
```powershell
irm https://raw.githubusercontent.com/P374R/syspulse-cli/main/install.ps1 | iex
syspulse
```

#### Option 3: Standalone `.exe`
Download `syspulse-windows-x64.exe` from [Releases](https://github.com/P374R/syspulse-cli/releases), drop it in your folder, and run!

---

##  Controls & Live Hotkeys

Click inside your terminal pane to use real-time controls:

| Key | Action |
| :---: | :--- |
| **`C`** | Sort processes by **CPU%** (default) |
| **`M`** | Sort processes by **RAM / Memory%** |
| **`P`** | Sort processes by **PID** |
| **`T`** | Sort processes by **Thread Count** |
| **`R`** | Toggle Sort Direction (**Ascending / Descending**) |
| **`Q`** or **`Ctrl+C`** | Clean Exit (Restores terminal and cursor) |

---

##  CLI Options & Flags

```text
usage: syspulse [-h] [-i INTERVAL] [-t THRESHOLD] [-s {cpu,mem,pid,thr}] [--once]

Options:
  -i, --interval INTERVAL   Refresh interval in seconds (default: 1.0, minimum: 0.25)
  -t, --threshold THRESHOLD Alert threshold percentage for breach alert (default: 90.0)
  -s, --sort {cpu,mem,pid,thr} Initial process sort column (default: cpu)
  --once                    Emit a single JSON snapshot and exit (useful for scripts & automation)
```

### Script & Automation Mode (JSON)
```bash
syspulse --once
```
```json
{
  "user": "Master@CreatorsLapotp",
  "os": "Windows 11",
  "cpu_model": "Intel Core i7",
  "cpu_percent": 4.73,
  "memory_percent": 53.9,
  "cache_standby_gb": 5.46,
  "prefetch": "SysMain Active",
  "gpu_name": "NVIDIA GeForce RTX 4050",
  "gpu_load_percent": 0.0,
  "breach": false
}
```

---

##  Local Package Builds

### Build Debian `.deb` Package:
Can be built on Windows, Linux, or macOS:
```bash
python build_deb.py
```
Output: `dist/syspulse-cli_1.0.0_all.deb`

### Build Windows `.exe`:
```powershell
pip install pyinstaller
pyinstaller --onefile --console --name syspulse-windows-x64 main.py
```
Output: `dist/syspulse-windows-x64.exe`

---

##  License
MIT License © 2026 [P374R](https://github.com/P374R).
