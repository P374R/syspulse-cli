from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import glob
import json
import os
import platform
import queue
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import timedelta
from typing import Deque, Dict, List, Optional, Set, Tuple

import psutil

# Ensure terminal stdout/stderr handles UTF-8 on Windows and Linux consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ANSI control sequences
ESC = "\x1b"
ALT_BUFFER_ON = f"{ESC}[?1049h"
ALT_BUFFER_OFF = f"{ESC}[?1049l"
CURSOR_HIDE = f"{ESC}[?25l"
CURSOR_SHOW = f"{ESC}[?25h"
CURSOR_HOME = f"{ESC}[H"
CLEAR_LINE = f"{ESC}[K"
CLEAR_EOS = f"{ESC}[J"

# Industrial typography palette
RESET = f"{ESC}[0m"
BOLD = f"{ESC}[1m"
DIM = f"{ESC}[2m"
FG_WHITE = f"{ESC}[97m"
FG_MUTED = f"{ESC}[38;5;240m"
FG_SLATE = f"{ESC}[38;5;246m"
FG_BORDER = f"{ESC}[38;5;238m"
FG_GREEN = f"{ESC}[38;5;78m"
FG_AMBER = f"{ESC}[38;5;214m"
FG_RED = f"{ESC}[38;5;203m"
FG_CYAN = f"{ESC}[38;5;117m"
FG_BLUE = f"{ESC}[38;5;75m"
FG_MAGENTA = f"{ESC}[38;5;176m"

# Authentic Microsoft 4-Square Palette (TrueColor / 256-Color safe)
MS_RED = f"{ESC}[38;5;202m"
MS_GREEN = f"{ESC}[38;5;112m"
MS_BLUE = f"{ESC}[38;5;39m"
MS_YELLOW = f"{ESC}[38;5;214m"

SPARK_CHARS = "▁▂▃▄▅▆▇█"
IGNORED_PROCESS_NAMES = {"system idle process", "idle"}
ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


if os.name == "nt":
    class PERFORMANCE_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("CommitTotal", ctypes.c_size_t),
            ("CommitLimit", ctypes.c_size_t),
            ("CommitPeak", ctypes.c_size_t),
            ("PhysicalTotal", ctypes.c_size_t),
            ("PhysicalAvailable", ctypes.c_size_t),
            ("SystemCache", ctypes.c_size_t),
            ("KernelTotal", ctypes.c_size_t),
            ("KernelPaged", ctypes.c_size_t),
            ("KernelNonpaged", ctypes.c_size_t),
            ("PageSize", ctypes.c_size_t),
            ("HandleCount", wintypes.DWORD),
            ("ProcessCount", wintypes.DWORD),
            ("ThreadCount", wintypes.DWORD),
        ]


@dataclass(frozen=True)
class GpuSnapshot:
    available: bool
    name: str
    load_pct: float
    vram_used_mb: float
    vram_total_mb: float
    vram_pct: float
    temp_c: Optional[float]
    power_w: Optional[float]
    backend: str


@dataclass(frozen=True)
class CachePrefetchStat:
    cache_gb: float
    buffers_or_paged_gb: float
    slab_or_nonpaged_gb: float
    commit_used_gb: float
    commit_limit_gb: float
    prefetch_label: str
    prefetch_detail: str


@dataclass(frozen=True)
class PartitionStat:
    mount: str
    fstype: str
    pct: float
    used_gb: float
    total_gb: float


@dataclass(frozen=True)
class ProcessStat:
    pid: int
    name: str
    status: str
    threads: int
    cpu_pct: float
    mem_pct: float
    mem_mb: float


@dataclass(frozen=True)
class SystemSnapshot:
    username: str
    hostname: str
    os_label: str
    kernel_ver: str
    arch: str
    shell_name: str
    terminal_name: str
    uptime_str: str
    power_label: str
    cpu_model: str
    cpu_total: float
    cpu_peak: float
    cpu_avg: float
    cpu_cores: List[float]
    cpu_phys_cores: int
    cpu_log_cores: int
    cpu_freq_cur: float
    cpu_freq_max: float
    load_avg: Tuple[float, float, float]
    ctx_switches_sec: float
    interrupts_sec: float
    cpu_temp_c: Optional[float]
    mem_pct: float
    mem_used_gb: float
    mem_avail_gb: float
    mem_total_gb: float
    swap_pct: float
    swap_used_gb: float
    swap_total_gb: float
    cache_stats: CachePrefetchStat
    gpu: GpuSnapshot
    partitions: List[PartitionStat]
    disk_read_rate: float
    disk_write_rate: float
    disk_read_iops: float
    disk_write_iops: float
    net_ip: str
    net_rx_rate: float
    net_tx_rate: float
    net_rx_total_gb: float
    net_tx_total_gb: float
    tcp_established: int
    tcp_listen: int
    total_procs: int
    total_threads: int
    top_processes: List[ProcessStat]
    breach: bool


class InputEngine:
    # Hybrid ConPTY pipe + hardware console input multiplexer for Windows & Linux
    def __init__(self) -> None:
        self._queue: queue.Queue[str] = queue.Queue()
        self._stop = threading.Event()
        self._is_win = os.name == "nt"
        self._fd: Optional[int] = None
        self._opened_fd: bool = False
        self._old_term = None
        self._old_win_in_mode: Optional[int] = None

    def __enter__(self) -> InputEngine:
        if self._is_win:
            self._configure_win_console()
        else:
            self._configure_posix_tty()

        # Start non-blocking background stream reader for IDE ConPTY pipes
        t = threading.Thread(target=self._stream_reader_worker, daemon=True)
        t.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self._stop.set()
        if self._is_win and self._old_win_in_mode is not None:
            try:
                kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
                in_h = kernel32.GetStdHandle(-10)
                kernel32.SetConsoleMode(in_h, self._old_win_in_mode)
            except Exception:
                pass
        elif not self._is_win and self._fd is not None and self._old_term is not None:
            try:
                import termios
                termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old_term)
            except Exception:
                pass
            if self._opened_fd:
                try:
                    os.close(self._fd)
                except Exception:
                    pass

    def _configure_win_console(self) -> None:
        try:
            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            out_h = kernel32.GetStdHandle(-11)
            mode = ctypes.c_ulong()
            if kernel32.GetConsoleMode(out_h, ctypes.byref(mode)):
                kernel32.SetConsoleMode(out_h, mode.value | 0x0004)

            in_h = kernel32.GetStdHandle(-10)
            if kernel32.GetConsoleMode(in_h, ctypes.byref(mode)):
                self._old_win_in_mode = mode.value
                # Clear LINE_INPUT (0x02), ECHO_INPUT (0x04), QUICK_EDIT (0x40)
                clean = (mode.value & ~(0x0002 | 0x0004 | 0x0040)) | 0x0080
                kernel32.SetConsoleMode(in_h, clean)
        except Exception:
            pass

    def _configure_posix_tty(self) -> None:
        try:
            import termios
            import tty
            if sys.stdin.isatty():
                self._fd = sys.stdin.fileno()
                self._opened_fd = False
            else:
                self._fd = os.open("/dev/tty", os.O_RDONLY | os.O_NONBLOCK)
                self._opened_fd = True
            self._old_term = termios.tcgetattr(self._fd)
            tty.setcbreak(self._fd)
        except Exception:
            self._fd = None

    def _stream_reader_worker(self) -> None:
        # Hybrid reader: Win32 ReadConsoleInput (works in ConPTY + native console)
        # with POSIX select/read fallback for Linux/macOS.
        if self._is_win:
            self._win32_input_loop()
        else:
            self._posix_input_loop()

    def _win32_input_loop(self) -> None:
        """Read keyboard input via Win32 API -- reliable in ConPTY and native console."""
        try:
            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        except Exception:
            self._msvcrt_input_loop()
            return

        KEY_EVENT = 0x0001
        WAIT_OBJECT_0 = 0x00000000
        WAIT_TIMEOUT = 0x00000102

        class KEY_EVENT_RECORD(ctypes.Structure):
            _fields_ = [
                ("bKeyDown", wintypes.BOOL),
                ("wRepeatCount", wintypes.WORD),
                ("wVirtualKeyCode", wintypes.WORD),
                ("wVirtualScanCode", wintypes.WORD),
                ("uChar", wintypes.WCHAR),
                ("dwControlKeyState", wintypes.DWORD),
            ]

        class INPUT_RECORD_UNION(ctypes.Union):
            _fields_ = [
                ("KeyEvent", KEY_EVENT_RECORD),
                ("_pad", ctypes.c_byte * 16),
            ]

        class INPUT_RECORD(ctypes.Structure):
            _fields_ = [
                ("EventType", wintypes.WORD),
                ("_pad0", wintypes.WORD),
                ("Event", INPUT_RECORD_UNION),
            ]

        h_in = kernel32.GetStdHandle(wintypes.DWORD(-10 & 0xFFFFFFFF))
        if not h_in or h_in == wintypes.HANDLE(-1).value:
            self._msvcrt_input_loop()
            return

        rec = INPUT_RECORD()
        read_count = wintypes.DWORD(0)

        while not self._stop.is_set():
            try:
                # Wait up to 50 ms for console input -- avoids busy-wait spin
                rc = kernel32.WaitForSingleObject(
                    wintypes.HANDLE(h_in), wintypes.DWORD(50)
                )
                if rc == WAIT_TIMEOUT:
                    continue
                if rc != WAIT_OBJECT_0:
                    time.sleep(0.05)
                    continue

                if not kernel32.ReadConsoleInputW(
                    wintypes.HANDLE(h_in),
                    ctypes.byref(rec),
                    wintypes.DWORD(1),
                    ctypes.byref(read_count),
                ):
                    time.sleep(0.05)
                    continue

                if read_count.value == 0:
                    continue
                if rec.EventType != KEY_EVENT:
                    continue

                ke = rec.Event.KeyEvent
                if not ke.bKeyDown:
                    continue

                ch = ke.uChar
                if not ch or ch in ("\x00", "\xe0"):
                    continue

                # Ctrl+C comes through as '\x03'
                if ch == "\x03":
                    self._queue.put("q")
                elif 32 <= ord(ch) <= 126:
                    self._queue.put(ch.lower())
            except Exception:
                time.sleep(0.1)

    def _msvcrt_input_loop(self) -> None:
        """Legacy msvcrt fallback -- only used when Win32 console handle is unavailable."""
        import msvcrt
        while not self._stop.is_set():
            try:
                if msvcrt.kbhit():
                    ch = msvcrt.getwch()
                    if ch in ("\x00", "\xe0"):
                        if msvcrt.kbhit():
                            msvcrt.getwch()
                        time.sleep(0.03)
                        continue
                    self._queue.put(ch.lower())
                else:
                    time.sleep(0.03)
            except Exception:
                time.sleep(0.1)

    def _posix_input_loop(self) -> None:
        """POSIX select-based input reader for Linux/macOS."""
        import select
        fd = self._fd if self._fd is not None else sys.stdin.fileno()
        while not self._stop.is_set():
            try:
                r, _, _ = select.select([fd], [], [], 0.05)
                if r:
                    data = os.read(fd, 16)
                    if data:
                        for b in data:
                            if b == 3:  # Ctrl+C
                                self._queue.put("q")
                            elif 32 <= b <= 126:
                                self._queue.put(chr(b).lower())
                    else:
                        time.sleep(0.05)
            except Exception:
                time.sleep(0.1)

    def poll_key(self) -> Optional[str]:
        # Drain queue and return most recent command character
        last: Optional[str] = None
        while not self._queue.empty():
            try:
                ch = self._queue.get_nowait()
                if ch in ("\r", "\n", " "):
                    continue
                last = ch
            except queue.Empty:
                break
        return last


class AsyncGpuProbe:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._snapshot = GpuSnapshot(
            available=False,
            name="Scanning PCIe Bus...",
            load_pct=0.0,
            vram_used_mb=0.0,
            vram_total_mb=0.0,
            vram_pct=0.0,
            temp_c=None,
            power_w=None,
            backend="Init",
        )
        self._stop_event = threading.Event()
        self._nvidia_smi = shutil.which("nvidia-smi")
        if not self._nvidia_smi and os.name == "nt":
            candidate = r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe"
            if os.path.isfile(candidate):
                self._nvidia_smi = candidate

        self._wmi_static_cache: Optional[Tuple[str, float]] = None
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def get_snapshot(self) -> GpuSnapshot:
        with self._lock:
            return self._snapshot

    def _worker(self) -> None:
        while not self._stop_event.is_set():
            snap = (
                self._probe_nvidia()
                or self._probe_linux_sysfs()
                or self._probe_windows_fallback()
                or GpuSnapshot(
                    available=False,
                    name="Integrated / Generic Display",
                    load_pct=0.0,
                    vram_used_mb=0.0,
                    vram_total_mb=0.0,
                    vram_pct=0.0,
                    temp_c=None,
                    power_w=None,
                    backend="Standard",
                )
            )
            with self._lock:
                self._snapshot = snap
            self._stop_event.wait(1.5)

    def _probe_nvidia(self) -> Optional[GpuSnapshot]:
        if not self._nvidia_smi:
            return None
        try:
            flags = 0x08000000 if os.name == "nt" else 0
            proc = subprocess.run(
                [
                    self._nvidia_smi,
                    "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=1.2,
                creationflags=flags,
                check=False,
            )
            if proc.returncode != 0 or not proc.stdout.strip():
                return None
            first_line = proc.stdout.strip().splitlines()[0]
            parts = [p.strip() for p in first_line.split(",")]
            if len(parts) < 4:
                return None

            def _flt(val: str) -> Optional[float]:
                try:
                    return float(val)
                except ValueError:
                    return None

            name = parts[0][:26]
            load = _flt(parts[1]) or 0.0
            used_mb = _flt(parts[2]) or 0.0
            total_mb = max(1.0, _flt(parts[3]) or 1.0)
            temp = _flt(parts[4]) if len(parts) > 4 else None
            power = _flt(parts[5]) if len(parts) > 5 else None
            vram_pct = min(100.0, (used_mb / total_mb) * 100.0)

            return GpuSnapshot(
                available=True,
                name=name,
                load_pct=load,
                vram_used_mb=used_mb,
                vram_total_mb=total_mb,
                vram_pct=vram_pct,
                temp_c=temp,
                power_w=power,
                backend="NVML",
            )
        except Exception:
            return None

    def _probe_linux_sysfs(self) -> Optional[GpuSnapshot]:
        if os.name == "nt":
            return None
        try:
            for card_dir in sorted(glob.glob("/sys/class/drm/card[0-9]/device")):
                busy_path = os.path.join(card_dir, "gpu_busy_percent")
                if not os.path.isfile(busy_path):
                    continue
                with open(busy_path, "r", encoding="utf-8") as f:
                    load = float(f.read().strip())

                used_mb, total_mb = 0.0, 0.0
                v_used = os.path.join(card_dir, "mem_info_vram_used")
                v_tot = os.path.join(card_dir, "mem_info_vram_total")
                if os.path.isfile(v_used) and os.path.isfile(v_tot):
                    with open(v_used, "r", encoding="utf-8") as fu, open(v_tot, "r", encoding="utf-8") as ft:
                        used_mb = int(fu.read().strip()) / (1024 * 1024)
                        total_mb = int(ft.read().strip()) / (1024 * 1024)

                temp_c: Optional[float] = None
                for t_path in glob.glob(os.path.join(card_dir, "hwmon/hwmon*/temp1_input")):
                    try:
                        with open(t_path, "r", encoding="utf-8") as ft:
                            temp_c = int(ft.read().strip()) / 1000.0
                            break
                    except Exception:
                        pass

                vram_pct = (used_mb / total_mb * 100.0) if total_mb > 0 else 0.0
                return GpuSnapshot(
                    available=True,
                    name="Linux DRM Accelerator",
                    load_pct=load,
                    vram_used_mb=used_mb,
                    vram_total_mb=total_mb,
                    vram_pct=vram_pct,
                    temp_c=temp_c,
                    power_w=None,
                    backend="sysfs",
                )
        except Exception:
            pass
        return None

    def _probe_windows_fallback(self) -> Optional[GpuSnapshot]:
        if os.name != "nt":
            return None
        try:
            if self._wmi_static_cache is None:
                flags = 0x08000000
                cmd = [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Get-CimInstance Win32_VideoController | Select-Object -First 1 Name,AdapterRAM | ConvertTo-Json -Compress",
                ]
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=2.0, creationflags=flags, check=False)
                if proc.returncode == 0 and proc.stdout.strip():
                    data = json.loads(proc.stdout.strip())
                    if isinstance(data, list):
                        data = data[0]
                    name = str(data.get("Name") or "Windows Display Adapter")[:26]
                    ram_bytes = float(data.get("AdapterRAM") or 0.0)
                    self._wmi_static_cache = (name, ram_bytes / (1024 * 1024))
                else:
                    self._wmi_static_cache = ("Windows GPU", 0.0)

            name, total_mb = self._wmi_static_cache
            return GpuSnapshot(
                available=True,
                name=name,
                load_pct=0.0,
                vram_used_mb=0.0,
                vram_total_mb=total_mb,
                vram_pct=0.0,
                temp_c=None,
                power_w=None,
                backend="WMI",
            )
        except Exception:
            return None


def format_bytes_rate(bytes_per_sec: float) -> str:
    if bytes_per_sec < 1024.0:
        return f"{bytes_per_sec:5.0f} B/s"
    kb = bytes_per_sec / 1024.0
    if kb < 1024.0:
        return f"{kb:5.1f} KB/s"
    mb = kb / 1024.0
    if mb < 1024.0:
        return f"{mb:5.2f} MB/s"
    return f"{mb / 1024.0:5.2f} GB/s"


def visible_len(text: str) -> int:
    return len(ANSI_ESCAPE_RE.sub("", text))


def fit_ansi(text: str, target_width: int) -> str:
    if target_width <= 0:
        return ""
    vis = visible_len(text)
    if vis == target_width:
        return text
    if vis < target_width:
        return text + (" " * (target_width - vis))

    out: List[str] = []
    count = 0
    idx = 0
    n = len(text)
    while idx < n and count < target_width:
        if text[idx] == "\x1b":
            match = ANSI_ESCAPE_RE.match(text, idx)
            if match:
                out.append(match.group(0))
                idx = match.end()
                continue
        out.append(text[idx])
        count += 1
        idx += 1
    out.append(RESET)
    if count < target_width:
        out.append(" " * (target_width - count))
    return "".join(out)


class TelemetryCollector:
    def __init__(self, threshold: float, gpu_probe: AsyncGpuProbe, history_len: int = 28) -> None:
        self.threshold = threshold
        self.gpu_probe = gpu_probe
        self.root_mount = os.path.abspath(os.sep)
        self.username = os.environ.get("USERNAME") or os.environ.get("USER") or "user"
        self.hostname = platform.node() or "localhost"
        self.os_label = f"{platform.system()} {platform.release()}"
        self.kernel_ver = platform.version()[:28]
        self.arch = platform.machine() or "x86_64"
        self.shell_name = self._detect_shell()
        self.terminal_name = self._detect_terminal()
        self.cpu_model = self._detect_cpu_model()
        self.phys_cores = psutil.cpu_count(logical=False) or 1
        self.log_cores = psutil.cpu_count(logical=True) or 1

        self.cpu_history: Deque[float] = deque([0.0] * history_len, maxlen=history_len)
        self.mem_history: Deque[float] = deque([0.0] * history_len, maxlen=history_len)
        self.net_history: Deque[float] = deque([0.0] * history_len, maxlen=history_len)
        self.cpu_peak: float = 0.0

        self._proc_cache: Dict[int, psutil.Process] = {}
        self._last_time = time.monotonic()
        self._last_net = psutil.net_io_counters()
        self._last_cpu_stats = psutil.cpu_stats()
        try:
            self._last_disk_io = psutil.disk_io_counters()
        except Exception:
            self._last_disk_io = None

        self._primary_ip = self._resolve_primary_ip()
        self._last_prefetch_scan = 0.0
        self._cached_prefetch_info: Tuple[str, str] = ("Scanning...", "")

        psutil.cpu_percent(interval=None)
        psutil.cpu_percent(interval=None, percpu=True)
        self._prime_processes()

    def _detect_shell(self) -> str:
        if os.name == "nt":
            if "PSModulePath" in os.environ:
                return "PowerShell"
            return os.path.basename(os.environ.get("COMSPEC", "cmd.exe"))
        return os.path.basename(os.environ.get("SHELL", "bash"))

    def _detect_terminal(self) -> str:
        term_prog = os.environ.get("TERM_PROGRAM")
        if term_prog:
            return term_prog[:20]
        if "WT_SESSION" in os.environ:
            return "Windows Terminal"
        return os.environ.get("TERM", "ConPTY / TTY")[:20]

    def _detect_cpu_model(self) -> str:
        if os.name != "nt":
            try:
                with open("/proc/cpuinfo", "r", encoding="utf-8") as f:
                    for line in f:
                        lower = line.lower()
                        if any(lower.startswith(k) for k in ("model name", "hardware", "model")):
                            return line.split(":", 1)[1].strip()[:32]
            except Exception:
                pass
        raw = platform.processor() or "Generic Processor"
        return raw[:32]

    def _resolve_primary_ip(self) -> str:
        try:
            for iface, snics in psutil.net_if_addrs().items():
                if "loopback" in iface.lower() or iface.lower().startswith("lo"):
                    continue
                for snic in snics:
                    if snic.family == socket.AF_INET and not snic.address.startswith("127."):
                        return f"{snic.address} ({iface[:10]})"
        except Exception:
            pass
        return "127.0.0.1 (lo)"

    def _prime_processes(self) -> None:
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                pid = proc.info["pid"]
                name = (proc.info.get("name") or "").strip().lower()
                if pid == 0 or name in IGNORED_PROCESS_NAMES:
                    continue
                proc.cpu_percent(interval=None)
                self._proc_cache[pid] = proc
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

    def _read_cache_and_prefetch(self, vmem) -> CachePrefetchStat:
        now = time.monotonic()
        if os.name == "nt":
            cache_gb = 0.0
            paged_gb = 0.0
            nonpaged_gb = 0.0
            commit_used_gb = 0.0
            commit_limit_gb = 0.0
            try:
                perf = PERFORMANCE_INFORMATION()
                perf.cb = ctypes.sizeof(PERFORMANCE_INFORMATION)
                if ctypes.windll.psapi.GetPerformanceInfo(ctypes.byref(perf), perf.cb):  # type: ignore[attr-defined]
                    psize = perf.PageSize
                    cache_gb = (perf.SystemCache * psize) / (1024**3)
                    paged_gb = (perf.KernelPaged * psize) / (1024**3)
                    nonpaged_gb = (perf.KernelNonpaged * psize) / (1024**3)
                    commit_used_gb = (perf.CommitTotal * psize) / (1024**3)
                    commit_limit_gb = (perf.CommitLimit * psize) / (1024**3)
            except Exception:
                pass

            if now - self._last_prefetch_scan > 10.0:
                self._last_prefetch_scan = now
                pf_dir = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "Prefetch")
                try:
                    entries = [e for e in os.scandir(pf_dir) if e.name.lower().endswith(".pf")]
                    total_mb = sum(e.stat().st_size for e in entries) / (1024 * 1024)
                    self._cached_prefetch_info = ("Win Prefetch", f"{len(entries)} .pf files ({total_mb:.1f} MB)")
                except PermissionError:
                    self._cached_prefetch_info = ("Win Prefetch", "SysMain Active (Admin locked)")
                except Exception:
                    self._cached_prefetch_info = ("Win Prefetch", "Standby Superfetch Enabled")

            return CachePrefetchStat(
                cache_gb=cache_gb,
                buffers_or_paged_gb=paged_gb,
                slab_or_nonpaged_gb=nonpaged_gb,
                commit_used_gb=commit_used_gb,
                commit_limit_gb=commit_limit_gb,
                prefetch_label=self._cached_prefetch_info[0],
                prefetch_detail=self._cached_prefetch_info[1],
            )
        else:
            cache_gb = getattr(vmem, "cached", 0) / (1024**3)
            buffers_gb = getattr(vmem, "buffers", 0) / (1024**3)
            slab_gb = getattr(vmem, "slab", 0) / (1024**3)
            dirty_mb = 0.0
            swappiness = "60"
            try:
                with open("/proc/meminfo", "r", encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("Dirty:"):
                            dirty_mb = float(line.split()[1]) / 1024.0
                        elif line.startswith("SReclaimable:") and slab_gb == 0.0:
                            slab_gb = float(line.split()[1]) / (1024**2)
                with open("/proc/sys/vm/swappiness", "r", encoding="utf-8") as fs:
                    swappiness = fs.read().strip()
            except Exception:
                pass

            return CachePrefetchStat(
                cache_gb=cache_gb,
                buffers_or_paged_gb=buffers_gb,
                slab_or_nonpaged_gb=slab_gb,
                commit_used_gb=vmem.used / (1024**3),
                commit_limit_gb=vmem.total / (1024**3),
                prefetch_label="PageCache/VM",
                prefetch_detail=f"Dirty: {dirty_mb:.1f}MB | Swapness: {swappiness}",
            )

    def _read_temperature(self) -> Optional[float]:
        try:
            if hasattr(psutil, "sensors_temperatures"):
                temps = psutil.sensors_temperatures()
                if temps:
                    for entries in temps.values():
                        if entries:
                            return float(entries[0].current)
        except Exception:
            pass
        return None

    def _read_power(self) -> str:
        try:
            if hasattr(psutil, "sensors_battery"):
                bat = psutil.sensors_battery()
                if bat is not None:
                    state = "AC" if bat.power_plugged else "BAT"
                    return f"{bat.percent:3.0f}% ({state})"
        except Exception:
            pass
        return "AC ONLINE (Desktop)"

    def _read_partitions(self) -> List[PartitionStat]:
        stats: List[PartitionStat] = []
        seen_mounts: Set[str] = set()
        try:
            parts = psutil.disk_partitions(all=False)
        except Exception:
            parts = []

        for part in parts:
            if not part.mountpoint or part.mountpoint in seen_mounts:
                continue
            if "loop" in part.device or part.fstype.lower() in ("squashfs", "tmpfs", "devtmpfs"):
                continue
            try:
                du = psutil.disk_usage(part.mountpoint)
                if du.total <= 0:
                    continue
                seen_mounts.add(part.mountpoint)
                stats.append(
                    PartitionStat(
                        mount=part.mountpoint[:10],
                        fstype=(part.fstype or "fs")[:5],
                        pct=du.percent,
                        used_gb=du.used / (1024**3),
                        total_gb=du.total / (1024**3),
                    )
                )
            except OSError:
                continue

        if not stats:
            try:
                du = psutil.disk_usage(self.root_mount)
                stats.append(
                    PartitionStat(
                        mount=self.root_mount[:10],
                        fstype="root",
                        pct=du.percent,
                        used_gb=du.used / (1024**3),
                        total_gb=du.total / (1024**3),
                    )
                )
            except OSError:
                pass
        return stats[:2]

    def collect(self, sort_key: str = "cpu", reverse_sort: bool = True) -> SystemSnapshot:
        now = time.monotonic()
        dt = max(now - self._last_time, 1e-3)
        self._last_time = now

        cpu_cores = psutil.cpu_percent(interval=None, percpu=True)
        cpu_total = (
            sum(cpu_cores) / len(cpu_cores)
            if cpu_cores
            else psutil.cpu_percent(interval=None)
        )
        self.cpu_history.append(cpu_total)
        self.cpu_peak = max(self.cpu_peak, cpu_total)
        active_hist = [v for v in self.cpu_history if v > 0.0]
        cpu_avg = sum(active_hist) / len(active_hist) if active_hist else cpu_total

        cpu_freq_cur, cpu_freq_max = 0.0, 0.0
        try:
            freq = psutil.cpu_freq()
            if freq is not None:
                cpu_freq_cur = freq.current
                cpu_freq_max = freq.max or freq.current
        except Exception:
            pass

        try:
            load_avg = psutil.getloadavg()
        except Exception:
            load_avg = (0.0, 0.0, 0.0)

        ctx_rate, irq_rate = 0.0, 0.0
        try:
            curr_stats = psutil.cpu_stats()
            ctx_rate = max(0.0, (curr_stats.ctx_switches - self._last_cpu_stats.ctx_switches) / dt)
            irq_rate = max(0.0, (curr_stats.interrupts - self._last_cpu_stats.interrupts) / dt)
            self._last_cpu_stats = curr_stats
        except Exception:
            pass

        vmem = psutil.virtual_memory()
        try:
            swap = psutil.swap_memory()
        except Exception:
            from collections import namedtuple
            _Swap = namedtuple("_Swap", ["total", "used", "free", "percent", "sin", "sout"])
            swap = _Swap(total=0, used=0, free=0, percent=0.0, sin=0, sout=0)
        self.mem_history.append(vmem.percent)
        cache_stats = self._read_cache_and_prefetch(vmem)

        partitions = self._read_partitions()
        disk_read_rate, disk_write_rate = 0.0, 0.0
        disk_read_iops, disk_write_iops = 0.0, 0.0
        try:
            curr_dio = psutil.disk_io_counters()
            if curr_dio and self._last_disk_io:
                disk_read_rate = max(0.0, (curr_dio.read_bytes - self._last_disk_io.read_bytes) / dt)
                disk_write_rate = max(0.0, (curr_dio.write_bytes - self._last_disk_io.write_bytes) / dt)
                disk_read_iops = max(0.0, (curr_dio.read_count - self._last_disk_io.read_count) / dt)
                disk_write_iops = max(0.0, (curr_dio.write_count - self._last_disk_io.write_count) / dt)
            self._last_disk_io = curr_dio
        except Exception:
            pass

        net_rx_rate, net_tx_rate = 0.0, 0.0
        net_rx_total_gb, net_tx_total_gb = 0.0, 0.0
        try:
            curr_net = psutil.net_io_counters()
            if curr_net:
                net_rx_total_gb = curr_net.bytes_recv / (1024**3)
                net_tx_total_gb = curr_net.bytes_sent / (1024**3)
                if self._last_net:
                    net_rx_rate = max(0.0, (curr_net.bytes_recv - self._last_net.bytes_recv) / dt)
                    net_tx_rate = max(0.0, (curr_net.bytes_sent - self._last_net.bytes_sent) / dt)
            self._last_net = curr_net
        except Exception:
            pass

        combined_net_pct = min(100.0, ((net_rx_rate + net_tx_rate) / (10 * 1024 * 1024)) * 100.0)
        self.net_history.append(combined_net_pct)

        tcp_est, tcp_listen = 0, 0
        try:
            for conn in psutil.net_connections(kind="tcp"):
                if conn.status == psutil.CONN_ESTABLISHED:
                    tcp_est += 1
                elif conn.status == psutil.CONN_LISTEN:
                    tcp_listen += 1
        except Exception:
            pass

        uptime_sec = max(0, int(time.time() - psutil.boot_time()))
        uptime_str = str(timedelta(seconds=uptime_sec))

        procs: List[ProcessStat] = []
        active_pids: Set[int] = set()
        total_threads = 0

        for p in psutil.process_iter(["pid", "name", "status", "num_threads", "memory_percent", "memory_info"]):
            try:
                pid = p.info["pid"]
                raw_name = (p.info.get("name") or "unknown").strip()
                if pid == 0 or raw_name.lower() in IGNORED_PROCESS_NAMES:
                    continue

                active_pids.add(pid)
                cached_proc = self._proc_cache.get(pid)
                if cached_proc is None:
                    p.cpu_percent(interval=None)
                    self._proc_cache[pid] = p
                    raw_cpu = 0.0
                else:
                    raw_cpu = cached_proc.cpu_percent(interval=None) or 0.0

                norm_cpu = max(0.0, min(100.0, raw_cpu / self.log_cores))
                mem_p = p.info.get("memory_percent") or 0.0
                mem_info = p.info.get("memory_info")
                mem_mb = (mem_info.rss / (1024 * 1024)) if mem_info else 0.0
                p_threads = p.info.get("num_threads") or 1
                total_threads += p_threads
                status_str = (p.info.get("status") or "run")[:4].upper()

                procs.append(
                    ProcessStat(
                        pid=pid,
                        name=raw_name[:22],
                        status=status_str,
                        threads=p_threads,
                        cpu_pct=norm_cpu,
                        mem_pct=mem_p,
                        mem_mb=mem_mb,
                    )
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        stale_pids = set(self._proc_cache.keys()) - active_pids
        for stale_pid in stale_pids:
            self._proc_cache.pop(stale_pid, None)

        if sort_key == "mem":
            procs.sort(key=lambda item: (item.mem_pct, item.cpu_pct), reverse=reverse_sort)
        elif sort_key == "pid":
            procs.sort(key=lambda item: item.pid, reverse=not reverse_sort)
        elif sort_key == "thr":
            procs.sort(key=lambda item: (item.threads, item.cpu_pct), reverse=reverse_sort)
        else:
            procs.sort(key=lambda item: (item.cpu_pct, item.mem_pct), reverse=reverse_sort)

        root_disk_pct = partitions[0].pct if partitions else 0.0
        gpu_snap = self.gpu_probe.get_snapshot()

        breach = (
            cpu_total >= self.threshold
            or vmem.percent >= self.threshold
            or root_disk_pct >= self.threshold
        )

        return SystemSnapshot(
            username=self.username,
            hostname=self.hostname,
            os_label=self.os_label,
            kernel_ver=self.kernel_ver,
            arch=self.arch,
            shell_name=self.shell_name,
            terminal_name=self.terminal_name,
            uptime_str=uptime_str,
            power_label=self._read_power(),
            cpu_model=self.cpu_model,
            cpu_total=cpu_total,
            cpu_peak=self.cpu_peak,
            cpu_avg=cpu_avg,
            cpu_cores=cpu_cores,
            cpu_phys_cores=self.phys_cores,
            cpu_log_cores=self.log_cores,
            cpu_freq_cur=cpu_freq_cur,
            cpu_freq_max=cpu_freq_max,
            load_avg=(load_avg[0], load_avg[1], load_avg[2]),
            ctx_switches_sec=ctx_rate,
            interrupts_sec=irq_rate,
            cpu_temp_c=self._read_temperature(),
            mem_pct=vmem.percent,
            mem_used_gb=vmem.used / (1024**3),
            mem_avail_gb=vmem.available / (1024**3),
            mem_total_gb=vmem.total / (1024**3),
            swap_pct=swap.percent,
            swap_used_gb=swap.used / (1024**3),
            swap_total_gb=swap.total / (1024**3),
            cache_stats=cache_stats,
            gpu=gpu_snap,
            partitions=partitions,
            disk_read_rate=disk_read_rate,
            disk_write_rate=disk_write_rate,
            disk_read_iops=disk_read_iops,
            disk_write_iops=disk_write_iops,
            net_ip=self._primary_ip,
            net_rx_rate=net_rx_rate,
            net_tx_rate=net_tx_rate,
            net_rx_total_gb=net_rx_total_gb,
            net_tx_total_gb=net_tx_total_gb,
            tcp_established=tcp_est,
            tcp_listen=tcp_listen,
            total_procs=len(active_pids),
            total_threads=total_threads,
            top_processes=procs[:15],
            breach=breach,
        )


class TerminalRenderer:
    def __init__(self, threshold: float) -> None:
        self.threshold = threshold

    def _color_for(self, pct: float) -> str:
        if pct >= self.threshold:
            return FG_RED
        if pct >= self.threshold * 0.75:
            return FG_AMBER
        return FG_GREEN

    def _bar(self, pct: float, width: int = 14) -> str:
        clamped = max(0.0, min(100.0, pct))
        filled = int(round((clamped / 100.0) * width))
        empty = max(0, width - filled)
        color = self._color_for(clamped)
        return f"{color}{'█' * filled}{FG_MUTED}{'░' * empty}{RESET}"

    def _sparkline(self, series: Deque[float], color: str, width: int = 20) -> str:
        items = list(series)[-width:]
        chars = []
        for val in items:
            idx = min(7, max(0, int((val / 100.0) * 7)))
            chars.append(SPARK_CHARS[idx])
        return f"{color}{''.join(chars)}{RESET}"

    def _build_os_logo(self) -> List[str]:
        # Iconic 4-Square Microsoft Windows emblem on Windows; Tux emblem on Linux
        if os.name == "nt":
            return [
                f"  {MS_RED}██████████{RESET}  {MS_GREEN}██████████{RESET}  ",
                f"  {MS_RED}██████████{RESET}  {MS_GREEN}██████████{RESET}  ",
                f"  {MS_RED}██████████{RESET}  {MS_GREEN}██████████{RESET}  ",
                f"  {MS_RED}██████████{RESET}  {MS_GREEN}██████████{RESET}  ",
                f"                          ",
                f"  {MS_BLUE}██████████{RESET}  {MS_YELLOW}██████████{RESET}  ",
                f"  {MS_BLUE}██████████{RESET}  {MS_YELLOW}██████████{RESET}  ",
                f"  {MS_BLUE}██████████{RESET}  {MS_YELLOW}██████████{RESET}  ",
                f"  {MS_BLUE}██████████{RESET}  {MS_YELLOW}██████████{RESET}  ",
            ]
        return [
            f"        {FG_SLATE}.---.{RESET}         ",
            f"       {FG_SLATE}/     \\{RESET}        ",
            f"      {FG_SLATE}| {FG_WHITE}() (){FG_SLATE} |{RESET}       ",
            f"       {FG_AMBER}\\  ^  /{RESET}        ",
            f"      {FG_SLATE} /|||||\\{RESET}        ",
            f"     {FG_SLATE} / |   | \\{RESET}       ",
            f"     {FG_SLATE}|  |   |  |{RESET}      ",
            f"      {FG_SLATE}\\ |   | /{RESET}       ",
            f"     {FG_AMBER}==={FG_SLATE}-----{FG_AMBER}==={RESET}      ",
        ]

    def _build_syspulse_banner(self, snap: SystemSnapshot, width: int) -> List[str]:
        logo = self._build_os_logo()
        status_pill = (
            f"{FG_RED}{BOLD}[THRESHOLD BREACH]{RESET}"
            if snap.breach
            else f"{FG_GREEN}{BOLD}[SYSTEM NOMINAL]{RESET}"
        )
        palette_dots = (
            f"{MS_RED}███{MS_GREEN}███{MS_BLUE}███{MS_YELLOW}███"
            f"{FG_MAGENTA}███{FG_CYAN}███{FG_WHITE}███{FG_SLATE}███{RESET}"
        )
        user_host = f"{BOLD}{FG_CYAN}{snap.username}{FG_WHITE}@{FG_GREEN}{snap.hostname}{RESET}"
        sep_len = len(snap.username) + 1 + len(snap.hostname)

        info_rows = [
            f"{user_host}   {status_pill}",
            f"{FG_MUTED}{'─' * sep_len}{RESET}",
            f"{BOLD}{FG_BLUE}OS      {RESET}{FG_SLATE}│{RESET} {FG_WHITE}{snap.os_label} ({snap.arch}){RESET}  {FG_MUTED}[Kernel {snap.kernel_ver}]{RESET}",
            f"{BOLD}{FG_BLUE}Uptime  {RESET}{FG_SLATE}│{RESET} {FG_WHITE}{snap.uptime_str}{RESET}   {BOLD}{FG_BLUE}Power:{RESET} {FG_WHITE}{snap.power_label}{RESET}",
            f"{BOLD}{FG_BLUE}Shell   {RESET}{FG_SLATE}│{RESET} {FG_WHITE}{snap.shell_name}{RESET}   {BOLD}{FG_BLUE}Term:{RESET} {FG_WHITE}{snap.terminal_name}{RESET}",
            f"{BOLD}{FG_BLUE}CPU     {RESET}{FG_SLATE}│{RESET} {FG_WHITE}{snap.cpu_model} ({snap.cpu_phys_cores}P/{snap.cpu_log_cores}L) @ {snap.cpu_freq_cur:.0f}MHz{RESET}",
            f"{BOLD}{FG_BLUE}GPU     {RESET}{FG_SLATE}│{RESET} {FG_CYAN}{snap.gpu.name}{RESET} {FG_MUTED}[{snap.gpu.backend}]{RESET}",
            f"{BOLD}{FG_BLUE}Memory  {RESET}{FG_SLATE}│{RESET} {FG_WHITE}{snap.mem_used_gb:.2f} GiB / {snap.mem_total_gb:.2f} GiB ({snap.mem_pct:.1f}%){RESET}  {BOLD}{FG_BLUE}Cache:{RESET} {FG_CYAN}{snap.cache_stats.cache_gb:.2f} GiB{RESET}",
            f"{BOLD}{FG_BLUE}Colors  {RESET}{FG_SLATE}│{RESET} {palette_dots}",
        ]

        combined: List[str] = []
        for i in range(len(logo)):
            combined.append(f"{logo[i]}   {info_rows[i]}")
        return self._make_box("SYSPULSE-CLI SYSTEM IDENTITY", combined, width)

    def _make_box(self, title: str, body_lines: List[str], width: int) -> List[str]:
        inner = max(10, width - 4)
        title_str = f" {title} "
        dashes = max(0, width - 3 - len(title_str))
        top = f"{FG_BORDER}╭─{BOLD}{FG_CYAN}{title_str}{RESET}{FG_BORDER}{'─' * dashes}╮{RESET}"
        bot = f"{FG_BORDER}╰{'─' * (width - 2)}╯{RESET}"
        framed = [top]
        for line in body_lines:
            fitted = fit_ansi(line, inner)
            framed.append(f"{FG_BORDER}│{RESET} {fitted} {FG_BORDER}│{RESET}")
        framed.append(bot)
        return framed

    def _join_boxes_horizontal(self, left: List[str], right: List[str], left_w: int, right_w: int) -> List[str]:
        max_h = max(len(left), len(right))
        combined: List[str] = []
        for i in range(max_h):
            l_line = left[i] if i < len(left) else (" " * left_w)
            r_line = right[i] if i < len(right) else (" " * right_w)
            combined.append(f"{l_line}  {r_line}")
        return combined

    def render(
        self,
        snap: SystemSnapshot,
        cpu_hist: Deque[float],
        mem_hist: Deque[float],
        net_hist: Deque[float],
        sort_key: str,
        reverse_sort: bool,
        last_key_info: str,
        interval: float,
    ) -> str:
        cols, rows = shutil.get_terminal_size(fallback=(114, 38))
        total_w = min(max(cols - 2, 76), 142)
        dual_column = total_w >= 100

        if dual_column:
            col_w = (total_w - 2) // 2
            right_w = total_w - 2 - col_w
        else:
            col_w = total_w
            right_w = total_w

        output_lines: List[str] = []
        output_lines.extend(self._build_syspulse_banner(snap, total_w))

        # Panel 1: Compute Engine
        cpu_col = self._color_for(snap.cpu_total)
        freq_str = f"{snap.cpu_freq_cur:4.0f}MHz" if snap.cpu_freq_cur > 0 else "N/A"
        temp_str = f"{snap.cpu_temp_c:4.1f}°C" if snap.cpu_temp_c is not None else "N/A"

        core_cells: List[str] = []
        for idx, c_val in enumerate(snap.cpu_cores[:8]):
            c_col = self._color_for(c_val)
            b_idx = min(7, max(0, int((c_val / 100.0) * 7)))
            core_cells.append(f"{FG_SLATE}C{idx}{RESET}{c_col}{SPARK_CHARS[b_idx]}{c_val:3.0f}%{RESET}")

        cpu_lines = [
            f"{BOLD}{FG_WHITE}Load {RESET}{self._bar(snap.cpu_total, 14)} "
            f"{cpu_col}{BOLD}{snap.cpu_total:5.1f}%{RESET} "
            f"{FG_SLATE}Pk:{RESET}{FG_WHITE}{snap.cpu_peak:4.0f}%{RESET} "
            f"{FG_SLATE}Av:{RESET}{FG_WHITE}{snap.cpu_avg:4.0f}%{RESET}",
            f"{FG_SLATE}Wave {RESET}{self._sparkline(cpu_hist, cpu_col, max(10, col_w - 11))}",
            f"{FG_SLATE}Ctx/s:{RESET} {FG_WHITE}{snap.ctx_switches_sec:6.0f}{RESET}  "
            f"{FG_SLATE}IRQ/s:{RESET} {FG_WHITE}{snap.interrupts_sec:5.0f}{RESET}  "
            f"{FG_SLATE}Tmp:{RESET} {FG_WHITE}{temp_str}{RESET}",
            " ".join(core_cells[:4]) if core_cells else "",
            " ".join(core_cells[4:8]) if len(core_cells) > 4 else "",
        ]
        cpu_lines = [l for l in cpu_lines if l]

        # Panel 2: Memory, Standby Cache & Prefetch
        mem_col = self._color_for(snap.mem_pct)
        swap_col = self._color_for(snap.swap_pct)
        cs = snap.cache_stats
        pool_lbl = "Paged/NP:" if os.name == "nt" else "Buf/Slab:"

        mem_lines = [
            f"{BOLD}{FG_WHITE}RAM  {RESET}{self._bar(snap.mem_pct, 14)} "
            f"{mem_col}{BOLD}{snap.mem_pct:5.1f}%{RESET} "
            f"{FG_WHITE}{snap.mem_used_gb:4.1f}{FG_SLATE}/{snap.mem_total_gb:4.1f} GiB{RESET}",
            f"{FG_SLATE}Wave {RESET}{self._sparkline(mem_hist, mem_col, max(10, right_w - 11))}",
            f"{FG_SLATE}Standby/Cache:{RESET} {FG_CYAN}{cs.cache_gb:4.2f}G{RESET}  "
            f"{FG_SLATE}{pool_lbl}{RESET} {FG_WHITE}{cs.buffers_or_paged_gb:4.2f}/{cs.slab_or_nonpaged_gb:4.2f}G{RESET}",
            f"{FG_SLATE}{cs.prefetch_label}:{RESET} {FG_AMBER}{cs.prefetch_detail}{RESET}",
            f"{BOLD}{FG_WHITE}SWAP {RESET}{self._bar(snap.swap_pct, 14)} "
            f"{swap_col}{BOLD}{snap.swap_pct:5.1f}%{RESET} "
            f"{FG_WHITE}{snap.swap_used_gb:4.1f}{FG_SLATE}/{snap.swap_total_gb:4.1f} GiB{RESET}",
        ]
        while len(cpu_lines) < len(mem_lines):
            cpu_lines.append("")
        while len(mem_lines) < len(cpu_lines):
            mem_lines.append("")

        cpu_box = self._make_box("COMPUTE TELEMETRY", cpu_lines, col_w)
        mem_box = self._make_box("MEMORY, CACHE & PREFETCH", mem_lines, right_w)

        # Panel 3: GPU Accelerator
        g = snap.gpu
        gpu_col = self._color_for(g.load_pct)
        vram_col = self._color_for(g.vram_pct)
        g_temp = f"{g.temp_c:.0f}°C" if g.temp_c is not None else "N/A"
        g_pwr = f"{g.power_w:.0f}W" if g.power_w is not None else "N/A"

        gpu_lines = [
            f"{BOLD}{FG_WHITE}Core {RESET}{self._bar(g.load_pct, 14)} "
            f"{gpu_col}{BOLD}{g.load_pct:5.1f}%{RESET}  "
            f"{FG_SLATE}Temp:{RESET} {FG_WHITE}{g_temp}{RESET}  "
            f"{FG_SLATE}Pwr:{RESET} {FG_WHITE}{g_pwr}{RESET}",
            f"{BOLD}{FG_WHITE}VRAM {RESET}{self._bar(g.vram_pct, 14)} "
            f"{vram_col}{BOLD}{g.vram_pct:5.1f}%{RESET}  "
            f"{FG_WHITE}{g.vram_used_mb:4.0f}{FG_SLATE}/{g.vram_total_mb:4.0f} MiB{RESET}",
        ]

        # Panel 4: Network & Storage IOPS
        p_info = ""
        if snap.partitions:
            p0 = snap.partitions[0]
            p_info = f"{FG_SLATE}Disk ({p0.mount}):{RESET} {FG_WHITE}{p0.used_gb:.0f}/{p0.total_gb:.0f}G ({p0.pct:.0f}%){RESET}"

        io_lines = [
            f"{BOLD}{FG_WHITE}NET  {RESET}{FG_SLATE}RX↓{RESET} {FG_GREEN}{format_bytes_rate(snap.net_rx_rate)}{RESET} "
            f"{FG_SLATE}TX↑{RESET} {FG_BLUE}{format_bytes_rate(snap.net_tx_rate)}{RESET} "
            f"{FG_SLATE}IP:{RESET} {FG_CYAN}{snap.net_ip[:15]}{RESET}",
            f"{BOLD}{FG_WHITE}IOPS {RESET}{FG_SLATE}R:{RESET} {FG_WHITE}{format_bytes_rate(snap.disk_read_rate)}{RESET} "
            f"{FG_SLATE}W:{RESET} {FG_WHITE}{format_bytes_rate(snap.disk_write_rate)}{RESET}  {p_info}",
        ]
        while len(io_lines) < len(gpu_lines):
            io_lines.append("")

        gpu_box = self._make_box("GPU ACCELERATOR", gpu_lines, col_w)
        io_box = self._make_box("NETWORK & STORAGE IOPS", io_lines, right_w)

        if dual_column:
            output_lines.extend(self._join_boxes_horizontal(cpu_box, mem_box, col_w, right_w))
            output_lines.extend(self._join_boxes_horizontal(gpu_box, io_box, col_w, right_w))
        else:
            output_lines.extend(cpu_box)
            output_lines.extend(mem_box)
            output_lines.extend(gpu_box)
            output_lines.extend(io_box)

        # Panel 5: Process Table
        remaining_rows = max(4, rows - len(output_lines) - 4)
        proc_count = min(8, max(2, remaining_rows - 1))
        arrow = "↓" if reverse_sort else "↑"

        def _col_hdr(key: str, label: str, width: int, align_right: bool = False) -> str:
            lbl = f"{label}{arrow}" if sort_key == key else label
            pad = f"{lbl:>{width}}" if align_right else f"{lbl:<{width}}"
            if sort_key == key:
                return f"{MS_YELLOW}{BOLD}{pad}{RESET}"
            return f"{FG_SLATE}{pad}{RESET}"

        proc_lines: List[str] = [
            f"{BOLD}{_col_hdr('pid', '[P]ID', 8)} "
            f"{FG_SLATE}{'PROCESS':<22} {'STATE':<6}{RESET} "
            f"{_col_hdr('thr', '[T]HR', 6, True)} "
            f"{FG_SLATE}{'RSS MB':>9}{RESET} "
            f"{_col_hdr('mem', '[M]EM%', 9, True)} "
            f"{_col_hdr('cpu', '[C]PU%', 9, True)}   "
            f"{FG_SLATE}LOAD{RESET}"
        ]

        for proc in snap.top_processes[:proc_count]:
            p_col = self._color_for(proc.cpu_pct)
            m_col = self._color_for(proc.mem_pct)
            mini_bar = self._bar(proc.cpu_pct, 10)
            proc_lines.append(
                f"{FG_SLATE}{proc.pid:<8}{RESET} "
                f"{FG_WHITE}{proc.name:<22}{RESET} "
                f"{FG_SLATE}{proc.status:<6}{RESET} "
                f"{FG_SLATE}{proc.threads:>6}{RESET} "
                f"{FG_WHITE}{proc.mem_mb:>8.1f}M{RESET} "
                f"{m_col}{proc.mem_pct:>8.1f}%{RESET} "
                f"{p_col}{BOLD}{proc.cpu_pct:>8.1f}%{RESET}   "
                f"{mini_bar}"
            )

        proc_title = f"ACTIVE PROCESSES ({snap.total_procs} Tasks, {snap.total_threads} Threads) | Status: {last_key_info}"
        proc_box = self._make_box(proc_title, proc_lines, total_w)
        output_lines.extend(proc_box)

        footer = (
            f"{BOLD}{FG_CYAN}HOTKEYS:{RESET} "
            f"{FG_WHITE}[C]{RESET}{DIM} CPU  "
            f"{FG_WHITE}[M]{RESET}{DIM} RAM  "
            f"{FG_WHITE}[P]{RESET}{DIM} PID  "
            f"{FG_WHITE}[T]{RESET}{DIM} Threads  "
            f"{FG_WHITE}[R]{RESET}{DIM} Reverse  "
            f"{FG_WHITE}[Q / Ctrl+C]{RESET}{DIM} Exit  "
            f"{FG_MUTED}(Click terminal pane first to focus){RESET}"
        )
        output_lines.append(fit_ansi(footer, total_w))

        visible = output_lines[: max(1, rows - 1)]
        framed = "".join(f"{line}{CLEAR_LINE}\n" for line in visible)
        return f"{CURSOR_HOME}{framed}{CLEAR_EOS}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="syspulse-cli",
        description="Fastfetch-inspired cross-platform system telemetry monitor.",
    )
    parser.add_argument(
        "-i", "--interval",
        type=float,
        default=1.0,
        help="Refresh interval in seconds (default: 1.0, minimum: 0.25)",
    )
    parser.add_argument(
        "-t", "--threshold",
        type=float,
        default=90.0,
        help="Alert threshold percentage for exit code 1 (default: 90.0)",
    )
    parser.add_argument(
        "-s", "--sort",
        choices=["cpu", "mem", "pid", "thr"],
        default="cpu",
        help="Initial process sort column (default: cpu)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Emit a single JSON snapshot and exit with status 0 (ok) or 1 (breach)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    interval = max(0.25, min(args.interval, 60.0))
    threshold = max(1.0, min(args.threshold, 100.0))
    sort_key = args.sort
    reverse_sort = True
    last_key_info = "Listening for C / M / P / T / R / Q"

    gpu_probe = AsyncGpuProbe()
    collector = TelemetryCollector(threshold=threshold, gpu_probe=gpu_probe)

    if args.once:
        time.sleep(0.35)
        snap = collector.collect(sort_key=sort_key, reverse_sort=reverse_sort)
        gpu_probe.stop()
        payload: Dict[str, object] = {
            "user": f"{snap.username}@{snap.hostname}",
            "os": snap.os_label,
            "cpu_model": snap.cpu_model,
            "cpu_percent": round(snap.cpu_total, 2),
            "memory_percent": round(snap.mem_pct, 2),
            "cache_standby_gb": round(snap.cache_stats.cache_gb, 2),
            "prefetch": snap.cache_stats.prefetch_detail,
            "gpu_name": snap.gpu.name,
            "gpu_load_percent": round(snap.gpu.load_pct, 2),
            "breach": snap.breach,
        }
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
        sys.stdout.flush()
        return 1 if snap.breach else 0

    renderer = TerminalRenderer(threshold=threshold)

    sys.stdout.write(f"{ALT_BUFFER_ON}{CURSOR_HIDE}")
    sys.stdout.flush()

    try:
        with InputEngine() as engine:
            while True:
                loop_start = time.monotonic()
                snap = collector.collect(sort_key=sort_key, reverse_sort=reverse_sort)
                frame = renderer.render(
                    snap,
                    collector.cpu_history,
                    collector.mem_history,
                    collector.net_history,
                    sort_key,
                    reverse_sort,
                    last_key_info,
                    interval,
                )
                sys.stdout.write(frame)
                sys.stdout.flush()

                while (time.monotonic() - loop_start) < interval:
                    key = engine.poll_key()
                    if key is not None:
                        if key in ("q", "\x1b", "\x03"):
                            return 0
                        if key in ("c", "1"):
                            sort_key = "cpu"
                            last_key_info = "Sorted by CPU%"
                            break
                        if key in ("m", "2"):
                            sort_key = "mem"
                            last_key_info = "Sorted by RAM%"
                            break
                        if key in ("p", "3"):
                            sort_key = "pid"
                            last_key_info = "Sorted by PID"
                            break
                        if key in ("t", "4"):
                            sort_key = "thr"
                            last_key_info = "Sorted by Threads"
                            break
                        if key == "r":
                            reverse_sort = not reverse_sort
                            order_lbl = "DESC" if reverse_sort else "ASC"
                            last_key_info = f"Order -> {order_lbl}"
                            break
                    time.sleep(0.025)
    except KeyboardInterrupt:
        return 0
    finally:
        gpu_probe.stop()
        sys.stdout.write(f"{CURSOR_SHOW}{ALT_BUFFER_OFF}{RESET}")
        sys.stdout.flush()


if __name__ == "__main__":
    sys.exit(main())