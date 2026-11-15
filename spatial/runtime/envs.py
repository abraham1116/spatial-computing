"""Environment detection and isolated Python environments (dependency management).

Isolation level: separate interpreter + site-packages (venv). It protects the host's
packages; it is NOT a security sandbox (same user, same filesystem)."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def detect_interpreters() -> list[dict]:
    """Language runtimes actually present on the host."""
    out = []
    probes = {"python3": ["--version"], "python3.14": ["--version"], "node": ["--version"],
              "swift": ["--version"], "clang": ["--version"], "java": ["-version"], "go": ["version"],
              "rustc": ["--version"], "ruby": ["--version"], "perl": ["-e", "print $^V"]}
    for exe, flag in probes.items():
        p = shutil.which(exe) or (f"/opt/local/bin/{exe}" if Path(f"/opt/local/bin/{exe}").exists() else None)
        if not p:
            out.append({"runtime": exe, "present": False})
            continue
        try:
            r = subprocess.run([p, *flag], capture_output=True, text=True, timeout=15)
            ver = (r.stdout or r.stderr).strip().splitlines()[0] if (r.stdout or r.stderr).strip() else ""
            out.append({"runtime": exe, "present": r.returncode == 0, "path": p, "version": ver})
        except Exception as e:
            out.append({"runtime": exe, "present": False, "error": str(e)})
    return out


def check_requirements(python: str, requirements: list[str]) -> dict[str, str | None]:
    """Which requirement names are missing/incompatible in `python` (installed version or None)."""
    code = ("import importlib.metadata as m,json,sys;"
            "print(json.dumps({n:(m.version(n) if any(d.metadata['Name'].lower()==n.lower() "
            "for d in m.distributions()) else None) for n in sys.argv[1:]}))")
    import json
    names = [r.split("==")[0].split(">=")[0].strip() for r in requirements]
    r = subprocess.run([python, "-c", code, *names], capture_output=True, text=True, timeout=60)
    return json.loads(r.stdout)


class IsolatedEnv:
    def __init__(self, path: str, python: str | None = None):
        self.path = Path(path)
        self.python_src = python

    @property
    def python(self) -> str:
        return str(self.path / "bin" / "python")

    def create(self, requirements: list[str] | None = None) -> float:
        import time
        t0 = time.perf_counter()
        uv = shutil.which("uv")
        if uv:
            cmd = [uv, "venv", str(self.path)] + (["--python", self.python_src] if self.python_src else [])
            subprocess.run(cmd, check=True, capture_output=True, timeout=300)
            if requirements:
                subprocess.run([uv, "pip", "install", "--python", self.python, *requirements],
                               check=True, capture_output=True, timeout=600)
        else:
            import sys
            subprocess.run([self.python_src or sys.executable, "-m", "venv", str(self.path)], check=True, timeout=300)
            if requirements:
                subprocess.run([self.python, "-m", "pip", "install", *requirements], check=True,
                               capture_output=True, timeout=600)
        return time.perf_counter() - t0

    def run(self, code: str, timeout: float = 120) -> subprocess.CompletedProcess:
        return subprocess.run([self.python, "-c", code], capture_output=True, text=True, timeout=timeout)

    def destroy(self):
        shutil.rmtree(self.path, ignore_errors=True)
