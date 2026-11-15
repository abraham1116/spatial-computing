"""Artifact inspection: identify executable format, target OS and CPU from file headers."""
from __future__ import annotations

import struct
from dataclasses import dataclass

_MACHO_CPU = {0x01000007: "x86_64", 0x0100000C: "arm64", 7: "i386", 12: "arm"}
_ELF_MACHINE = {0x3E: "x86_64", 0xB7: "aarch64", 0x03: "i386", 0x28: "arm", 0xF3: "riscv"}
_PE_MACHINE = {0x8664: "x86_64", 0xAA64: "aarch64", 0x014C: "i386"}


@dataclass
class Artifact:
    path: str
    format: str            # macho | elf | pe | wasm | script | unknown
    os: str | None         # macos | linux | windows | any
    arch: list[str]
    detail: str = ""


def inspect(path: str) -> Artifact:
    with open(path, "rb") as f:
        head = f.read(4096)
    if len(head) >= 8 and head[:4] in (b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe"):
        cpu = struct.unpack("<I", head[4:8])[0]
        return Artifact(path, "macho", "macos", [_MACHO_CPU.get(cpu, hex(cpu))])
    if head[:4] in (b"\xca\xfe\xba\xbe", b"\xca\xfe\xba\xbf"):
        n = struct.unpack(">I", head[4:8])[0]
        if n < 20:   # fat Mach-O (a Java class file has a large "count" here)
            archs = [_MACHO_CPU.get(struct.unpack(">I", head[8 + 20 * i:12 + 20 * i])[0], "?") for i in range(n)]
            return Artifact(path, "macho", "macos", archs, "universal binary")
    if head[:4] == b"\x7fELF":
        little = head[5] == 1
        mach = struct.unpack("<H" if little else ">H", head[18:20])[0]
        osabi = head[7]
        return Artifact(path, "elf", "linux" if osabi in (0, 3) else f"elf-osabi-{osabi}",
                        [_ELF_MACHINE.get(mach, hex(mach))], "64-bit" if head[4] == 2 else "32-bit")
    if head[:2] == b"MZ" and len(head) >= 0x40:
        off = struct.unpack("<I", head[0x3C:0x40])[0]
        if off + 6 <= len(head) and head[off:off + 4] == b"PE\0\0":
            mach = struct.unpack("<H", head[off + 4:off + 6])[0]
            return Artifact(path, "pe", "windows", [_PE_MACHINE.get(mach, hex(mach))])
        return Artifact(path, "pe", "windows", ["?"], "DOS/unknown PE")
    if head[:4] == b"\0asm":
        return Artifact(path, "wasm", "any", ["wasm32"], f"version {struct.unpack('<I', head[4:8])[0]}")
    if head[:2] == b"#!":
        return Artifact(path, "script", "any", ["any"], head.split(b"\n", 1)[0][2:].decode(errors="replace").strip())
    return Artifact(path, "unknown", None, [])
