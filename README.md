# SysPulse CLI (syspulse-cli)

> Fastfetch-inspired, industrial-grade cross-platform system telemetry and active process dashboard for **Linux** and **Windows**.

[![GitHub Release](https://img.shields.io/github/v/release/P374R/syspulse-cli?style=flat-square&color=38bdf8)](https://github.com/P374R/syspulse-cli/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](https://opensource.org/licenses/MIT)
[![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20Windows-blue?style=flat-square)](https://github.com/P374R/syspulse-cli)

```text
╭─ SYSPULSE-CLI SYSTEM IDENTITY ───────────────────────────────────────────────────────────────────────────────╮
│   ██████████  ██████████     Master@CreatorsLapotp   [SYSTEM NOMINAL]                                        │
│   ██████████  ██████████     ─────────────────────                                                           │
│   ██████████  ██████████     OS      │ Windows 11 (AMD64)  [Kernel 10.0.26300]                               │
│   ██████████  ██████████     Uptime  │ 19:54:57   Power:  97% (AC)                                           │
│                              Shell   │ PowerShell   Term: ConPTY / TTY                                       │
│   ██████████  ██████████     CPU     │ Intel Core i7 (10P/16L) @ 2400MHz                                     │
│   ██████████  ██████████     GPU     │ NVIDIA GeForce RTX 4050 [NVML]                                        │
│   ██████████  ██████████     Memory  │ 8.35 GiB / 15.63 GiB (53.4%)  Cache: 5.45 GiB                         │
│   ██████████  ██████████     Colors  │ ████████████████████████                                              │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ COMPUTE TELEMETRY ─────────────────────────────────╮  ╭─ MEMORY, CACHE & PREFETCH ──────────────────────────╮
│ Load ████░░░░░░░░░░  28.4% Pk:  82% Av:  31%        │  │ RAM  ███████░░░░░░░  53.4%  8.4/15.6 GiB            │
│ Wave ▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁                   │  │ Wave ▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▄                   │
│ Ctx/s: 248000  IRQ/s: 80000  Tmp: 52.0°C            │  │ Standby/Cache: 5.45G  Paged/NP: 0.53/0.48G          │
│ C0▅ 55% C1▃ 22% C2▂ 12% C3▆ 78%                     │  │ Win Prefetch: SysMain Active                        │
│ C4▂ 10% C5  0% C6▂ 15% C7▄ 45%                     │  │ SWAP ░░░░░░░░░░░░░░   0.0%  0.0/ 0.0 GiB            │
╰─────────────────────────────────────────────────────╯  ╰─────────────────────────────────────────────────────╯
```

---

## ⚡ Quick Install

### 🐧 Linux (Ubuntu, Debian, Mint, Raspberry Pi, Arch, Fedora)

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

### 🪟 Windows (Windows 10 & 11)

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

## ⌨️ Controls & Live Hotkeys

Click inside your terminal pane to use real-time controls:

| Key | Action |
| :---: | :--- |
| **`C`** or **`1`** | Sort processes by **CPU%** (default) |
| **`M`** or **`2`** | Sort processes by **RAM / Memory%** |
| **`P`** or **`3`** | Sort processes by **PID** |
| **`T`** or **`4`** | Sort processes by **Thread Count** |
| **`R`** | Toggle Sort Direction (**Ascending / Descending**) |
| **`Q`** or **`Ctrl+C`** | Clean Exit (Restores terminal and cursor) |

---

## ⚙️ CLI Options & Flags

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

## 🛠️ Local Package Builds

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

## 📄 License
MIT License © 2026 [P374R](https://github.com/P374R).
