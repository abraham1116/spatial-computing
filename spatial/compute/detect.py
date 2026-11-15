"""Hardware detection (macOS first; degrades gracefully elsewhere). Nothing is assumed."""
from __future__ import annotations

import json
import platform
import shutil
import subprocess
import uuid

import psutil

from ..core.model import Node, Resource, ResourceKind


def _sysctl(key: str) -> str | None:
    try:
        r = subprocess.run(["sysctl", "-n", key], capture_output=True, text=True, timeout=5)
        return r.stdout.strip() or None
    except Exception:
        return None


def _os_name() -> str:
    if platform.system() == "Darwin":
        try:   # platform.mac_ver() can report a compatibility version (10.16)
            v = subprocess.run(["sw_vers", "-productVersion"], capture_output=True, text=True, timeout=5).stdout.strip()
            return f"macOS {v}"
        except Exception:
            pass
    return f"{platform.system()} {platform.release()}"


def _gpus() -> list[dict]:
    try:
        out = subprocess.run(["system_profiler", "SPDisplaysDataType", "-json"],
                             capture_output=True, text=True, timeout=30).stdout
        return json.loads(out).get("SPDisplaysDataType", [])
    except Exception:
        return []


def parse_nvidia_smi(csv: str) -> list[dict]:
    """Parse `nvidia-smi --query-gpu=name,memory.total,memory.used,utilization.gpu --format=csv,noheader,nounits`."""
    out = []
    for line in csv.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 4:
            continue
        name, total, used, util = parts
        try:
            out.append({"name": name, "vram_bytes": int(float(total)) * 2**20,
                        "vram_used_bytes": int(float(used)) * 2**20, "utilization_percent": float(util)})
        except ValueError:
            continue
    return out


def _nvidia_gpus() -> list[dict]:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return []
    try:
        r = subprocess.run([exe, "--query-gpu=name,memory.total,memory.used,utilization.gpu",
                            "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=20)
        return parse_nvidia_smi(r.stdout) if r.returncode == 0 else []
    except Exception:
        return []


def virtualization() -> dict:
    """What can actually run guests here."""
    info = {"hvf": _sysctl("kern.hv_support") == "1"}
    for tool in ("qemu-system-x86_64", "qemu-system-aarch64", "docker", "podman", "limactl",
                 "wine", "wine64", "node", "wasmtime"):
        info[tool] = shutil.which(tool)
    return info


def detect_node() -> Node:
    vm = psutil.virtual_memory()
    arch = platform.machine()
    node = Node(node_id=uuid.uuid5(uuid.NAMESPACE_DNS, platform.node()).hex[:12],
                hostname="local", os=_os_name(),
                arch=arch)
    node.attrs["model"] = _sysctl("hw.model")
    node.attrs["cpu_brand"] = _sysctl("machdep.cpu.brand_string")
    node.attrs["virtualization"] = virtualization()
    feats = (_sysctl("machdep.cpu.features") or "") + " " + (_sysctl("machdep.cpu.leaf7_features") or "")
    simd = [f for f in ("SSE4.2", "AVX1.0", "AVX2", "AVX512F", "FMA") if f in feats.split()]
    node.resources.append(Resource(
        ResourceKind.CPU, node.attrs["cpu_brand"] or "cpu",
        capacity=psutil.cpu_count(logical=False) or 1, unit="physical cores",
        attrs={"logical": psutil.cpu_count(logical=True), "simd": simd,
               "l2_bytes": int(_sysctl("hw.l2cachesize") or 0),
               "l3_bytes": int(_sysctl("hw.l3cachesize") or 0)}))
    node.resources.append(Resource(ResourceKind.RAM, "physical RAM", capacity=vm.total,
                                   unit="bytes", available=vm.available))
    sw = psutil.swap_memory()
    node.resources.append(Resource(
        ResourceKind.FAR_MEMORY, "OS swap (SSD-backed, NOT RAM)", capacity=sw.total, unit="bytes",
        available=sw.free, attrs={"compressor_mode": _sysctl("vm.compressor_mode")}))
    for g in _gpus():
        node.resources.append(Resource(
            ResourceKind.GPU, g.get("sppci_model", "gpu"), capacity=1, unit="device",
            attrs={"vram": g.get("spdisplays_vram_shared") or g.get("spdisplays_vram") or g.get("_spdisplays_vram"),
                   "metal": g.get("spdisplays_mtlgpufamilysupport"),
                   "vendor": g.get("spdisplays_vendor"), "integrated": "builtin" in str(g.get("sppci_bus", "")).lower().replace("-", "")}))
    for g in _nvidia_gpus():
        node.resources.append(Resource(
            ResourceKind.GPU, g["name"], capacity=g["vram_bytes"], unit="bytes",
            available=g["vram_bytes"] - g["vram_used_bytes"],
            attrs={"vendor": "NVIDIA", "cuda": True, "integrated": False,
                   "utilization_percent": g["utilization_percent"]}))
    du = psutil.disk_usage("/System/Volumes/Data" if platform.system() == "Darwin" else "/")
    node.resources.append(Resource(ResourceKind.STORAGE, "system volume", capacity=du.total,
                                   unit="bytes", available=du.free))
    return node


def limitations(node: Node) -> list[str]:
    """Hard limits derived from what was detected (used by the scheduler and the audit)."""
    out = []
    cpu = node.by_kind(ResourceKind.CPU)[0]
    if cpu.capacity <= 2:
        out.append(f"Only {int(cpu.capacity)} physical cores: parallel speed-up is bounded near 2x "
                   "(hyper-threads add little for compute-bound code).")
    if "AVX512F" not in cpu.attrs.get("simd", []):
        out.append("No AVX-512; SIMD width limited to AVX2 (256-bit).")
    if node.arch == "x86_64":
        out.append("Intel Mac: no Apple Neural Engine/NPU, no MLX, no Apple Virtualization.framework "
                   "Rosetta-for-Linux; ARM guests run under slow TCG emulation only.")
    for g in node.by_kind(ResourceKind.GPU):
        if g.attrs.get("integrated"):
            out.append(f"GPU {g.name} is integrated: shares system RAM, no CUDA, low compute throughput.")
    if not node.attrs["virtualization"].get("wine") and not node.attrs["virtualization"].get("wine64"):
        out.append("No Wine installed: Windows PE binaries cannot be executed locally.")
    if not node.attrs["virtualization"].get("docker"):
        out.append("No Docker/Podman: OCI containers unavailable; QEMU micro-VM is the Linux path.")
    return out
