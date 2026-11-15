"""Linux micro-VM runner (QEMU). Boots a kernel + generated initramfs containing a static
Linux ELF, runs it, captures its output from the serial console, powers off.

accel="hvf" : hardware virtualization (same ISA as host)  -> near-native CPU speed
accel="tcg" : full software emulation                      -> the cost of cross-ISA execution

No network device, no disk, no host folder is attached to the guest: it only sees the
files packed in its initramfs. Guest RAM is a hard cap (-m).
"""
from __future__ import annotations

import gzip
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

VENDOR = Path(__file__).resolve().parents[2] / "vendor"
KERNEL = VENDOR / "vmlinuz-virt"
BUSYBOX = VENDOR / "busybox-x86_64"


def _cpio_entry(name: str, mode: int, data: bytes = b"", rdev: tuple[int, int] = (0, 0), ino: int = 0) -> bytes:
    n = name.encode() + b"\0"
    hdr = "070701" + "".join(f"{v:08X}" for v in (
        ino, mode, 0, 0, 1, 0, len(data), 0, 0, rdev[0], rdev[1], len(n), 0))
    out = hdr.encode() + n
    out += b"\0" * (-len(out) % 4)
    out += data + b"\0" * (-len(data) % 4)
    return out


def build_initramfs(app: bytes, args: list[str], out_path: str) -> int:
    """newc cpio archive written directly (no root needed for the device node)."""
    init = "\n".join([
        "#!/bin/sh",
        "/bin/busybox mount -t devtmpfs dev /dev 2>/dev/null",
        "/bin/busybox mount -t proc proc /proc 2>/dev/null",
        "echo SPATIAL_BEGIN",
        "/app " + " ".join(args),
        "echo SPATIAL_EXIT $?",
        "/bin/busybox poweroff -f",
        ""]).encode()
    S_DIR, S_REG, S_CHR, S_LNK = 0o040755, 0o100755, 0o020600, 0o120777
    parts = [
        _cpio_entry("bin", S_DIR, ino=1), _cpio_entry("dev", S_DIR, ino=2), _cpio_entry("proc", S_DIR, ino=3),
        _cpio_entry("dev/console", S_CHR, rdev=(5, 1), ino=4),
        _cpio_entry("bin/busybox", S_REG, BUSYBOX.read_bytes(), ino=5),
        _cpio_entry("bin/sh", S_LNK, b"busybox", ino=6),
        _cpio_entry("init", S_REG, init, ino=7),
        _cpio_entry("app", S_REG, app, ino=8),
        _cpio_entry("TRAILER!!!", 0),
    ]
    blob = gzip.compress(b"".join(parts), compresslevel=1)
    Path(out_path).write_bytes(blob)
    return len(blob)


@dataclass
class VmResult:
    ok: bool
    accel: str
    stdout: str          # what the app printed
    exit_code: int | None
    total_wall_s: float  # QEMU start -> QEMU exit (boot + app + shutdown)
    boot_s: float | None # QEMU start -> app start marker
    raw_tail: str = ""


def available() -> dict:
    return {"qemu": shutil.which("qemu-system-x86_64"), "kernel": KERNEL.exists(), "busybox": BUSYBOX.exists()}


def run_elf(elf_path: str, args: list[str] | None = None, accel: str = "hvf", mem_mb: int = 256,
            cpus: int = 1, timeout_s: float = 180.0) -> VmResult:
    qemu = shutil.which("qemu-system-x86_64")
    if not (qemu and KERNEL.exists() and BUSYBOX.exists()):
        raise RuntimeError(f"micro-VM prerequisites missing: {available()}")
    with tempfile.TemporaryDirectory(prefix="spatial-vm-") as td:
        initrd = os.path.join(td, "initramfs.cpio.gz")
        build_initramfs(Path(elf_path).read_bytes(), args or [], initrd)
        cmd = [qemu, "-accel", accel, "-cpu", "host" if accel == "hvf" else "max",
               "-m", str(mem_mb), "-smp", str(cpus), "-kernel", str(KERNEL), "-initrd", initrd,
               "-append", "console=ttyS0 quiet panic=-1 rdinit=/init",
               "-nodefaults", "-no-reboot", "-display", "none", "-serial", "stdio"]
        t0 = time.perf_counter()
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, text=True,
                             errors="replace")
        lines, boot_s, code, capture, app_out = [], None, None, False, []
        try:
            for line in p.stdout:
                line = line.rstrip("\r\n")
                lines.append(line)
                if line.strip() == "SPATIAL_BEGIN":
                    boot_s = time.perf_counter() - t0
                    capture = True
                elif line.startswith("SPATIAL_EXIT"):
                    code = int(line.split()[1])
                    capture = False
                elif capture:
                    app_out.append(line)
                if time.perf_counter() - t0 > timeout_s:
                    break
            p.wait(timeout=max(1.0, timeout_s - (time.perf_counter() - t0)))
        except subprocess.TimeoutExpired:
            pass
        finally:
            if p.poll() is None:
                p.kill()
                p.wait()
        total = time.perf_counter() - t0
    return VmResult(ok=code == 0, accel=accel, stdout="\n".join(app_out), exit_code=code,
                    total_wall_s=total, boot_s=boot_s, raw_tail="\n".join(lines[-15:]))
