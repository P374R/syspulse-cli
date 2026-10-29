#!/usr/bin/env python3
"""
Cross-platform Debian (.deb) package builder for syspulse-cli.
Builds a production-ready Debian package on any OS (Windows, Linux, macOS)
using only Python's standard library.
"""
from __future__ import annotations

import io
import os
import sys
import tarfile
import time
from pathlib import Path

PACKAGE_NAME = "syspulse-cli"
VERSION = "1.0.0"
MAINTAINER = "P374R <https://github.com/P374R>"
DESCRIPTION = "Industrial cross-platform system telemetry and process monitor"
HOMEPAGE = "https://github.com/P374R/syspulse-cli"


def create_ar_header(name: str, size: int, mode: int = 0o100644, mtime: int = 0) -> bytes:
    name_field = f"{name:<16}".encode("ascii")
    mtime_field = f"{mtime:<12}".encode("ascii")
    owner_field = f"{0:<6}".encode("ascii")
    group_field = f"{0:<6}".encode("ascii")
    mode_field = f"{mode:<8o}".encode("ascii")
    size_field = f"{size:<10}".encode("ascii")
    fmag = b"`\n"
    return name_field + mtime_field + owner_field + group_field + mode_field + size_field + fmag


def build_control_tar() -> bytes:
    control_text = f"""Package: {PACKAGE_NAME}
Version: {VERSION}
Architecture: all
Maintainer: {MAINTAINER}
Depends: python3 (>= 3.8), python3-psutil
Section: utils
Priority: optional
Homepage: {HOMEPAGE}
Description: {DESCRIPTION}
 SysPulse is a fast, terminal-based hardware and process telemetry monitor
 inspired by fastfetch and industrial telemetry consoles.
"""
    control_bytes = control_text.encode("utf-8")
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w:gz", format=tarfile.GNU_FORMAT) as tar:
        ti = tarfile.TarInfo(name="./control")
        ti.size = len(control_bytes)
        ti.mode = 0o644
        ti.mtime = int(time.time())
        ti.uname = "root"
        ti.gname = "root"
        tar.addfile(ti, io.BytesIO(control_bytes))
    return out.getvalue()


def build_data_tar(main_py_path: Path) -> bytes:
    with open(main_py_path, "r", encoding="utf-8") as f:
        code = f.read()

    # Prepend shebang for standalone execution on Linux
    if not code.startswith("#!"):
        code = "#!/usr/bin/env python3\n" + code

    bin_bytes = code.encode("utf-8")
    now = int(time.time())
    out = io.BytesIO()

    with tarfile.open(fileobj=out, mode="w:gz", format=tarfile.GNU_FORMAT) as tar:
        # Directories
        for dir_name in ["./usr", "./usr/bin", "./usr/share", f"./usr/share/doc/{PACKAGE_NAME}"]:
            ti = tarfile.TarInfo(name=dir_name)
            ti.type = tarfile.DIRTYPE
            ti.mode = 0o755
            ti.mtime = now
            ti.uname = "root"
            ti.gname = "root"
            tar.addfile(ti)

        # /usr/bin/syspulse
        ti_bin = tarfile.TarInfo(name="./usr/bin/syspulse")
        ti_bin.size = len(bin_bytes)
        ti_bin.mode = 0o755
        ti_bin.mtime = now
        ti_bin.uname = "root"
        ti_bin.gname = "root"
        tar.addfile(ti_bin, io.BytesIO(bin_bytes))

        # /usr/bin/syspulse-cli symlink
        ti_link = tarfile.TarInfo(name="./usr/bin/syspulse-cli")
        ti_link.type = tarfile.SYMTYPE
        ti_link.linkname = "syspulse"
        ti_link.mode = 0o777
        ti_link.mtime = now
        ti_link.uname = "root"
        ti_link.gname = "root"
        tar.addfile(ti_link)

        # /usr/bin/syspulse_cli symlink (alias)
        ti_link2 = tarfile.TarInfo(name="./usr/bin/syspulse_cli")
        ti_link2.type = tarfile.SYMTYPE
        ti_link2.linkname = "syspulse"
        ti_link2.mode = 0o777
        ti_link2.mtime = now
        ti_link2.uname = "root"
        ti_link2.gname = "root"
        tar.addfile(ti_link2)

    return out.getvalue()


def build_deb(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    deb_filename = f"{PACKAGE_NAME}_{VERSION}_all.deb"
    deb_path = output_dir / deb_filename

    root_dir = Path(__file__).resolve().parent
    main_py = root_dir / "main.py"

    debian_binary = b"2.0\n"
    control_tar = build_control_tar()
    data_tar = build_data_tar(main_py)

    with open(deb_path, "wb") as f:
        # AR Magic Header
        f.write(b"!<arch>\n")

        # 1. debian-binary
        f.write(create_ar_header("debian-binary", len(debian_binary)))
        f.write(debian_binary)
        if len(debian_binary) % 2 != 0:
            f.write(b"\n")

        # 2. control.tar.gz
        f.write(create_ar_header("control.tar.gz", len(control_tar)))
        f.write(control_tar)
        if len(control_tar) % 2 != 0:
            f.write(b"\n")

        # 3. data.tar.gz
        f.write(create_ar_header("data.tar.gz", len(data_tar)))
        f.write(data_tar)
        if len(data_tar) % 2 != 0:
            f.write(b"\n")

    print(f"[OK] Successfully built Debian package: {deb_path} ({deb_path.stat().st_size:,} bytes)")
    return deb_path


if __name__ == "__main__":
    out_dir = Path(__file__).resolve().parent / "dist"
    build_deb(out_dir)
