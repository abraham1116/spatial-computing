"""Remote desktop: run a graphical Linux application in a container and use it from a browser (noVNC).

    from spatial.runtime.desktop import start, stop
    d = start("xterm")          # d.url opens the desktop in a browser; d.stop() removes it

Several people can connect at once (shared session). `clipboard=False` disables copy and paste both ways; `view_only_link=True` adds a second
password that can watch but not type or click. Not provided: audio, file transfer.

Security: the port is published on 127.0.0.1 only, a random one-time password is required, the container has no
capabilities, a read-only root and 512 MiB. To use it from another machine, tunnel it (ssh -L); do not publish it.
"""
from __future__ import annotations

import os
import secrets
import subprocess
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from ..planner import find_oci

HERE = Path(__file__).parent
IMAGE = "spatial-desktop:1"
APPS = {"xterm": ["xterm"], "xclock": ["xclock"], "mousepad": ["mousepad"]}      # an allow-list: no arbitrary command from the caller


class DesktopError(Exception):
    pass


@dataclass
class Desktop:
    container: str
    port: int
    password: str
    runtime: str
    exe: str
    env: dict
    view_password: str | None = None
    clipboard: bool = True

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/vnc.html?autoconnect=1&resize=scale&password={self.password}"

    @property
    def view_url(self) -> str | None:
        """A link whose password can watch but not type or click (give this one to people who only need to look)."""
        return None if not self.view_password else f"http://127.0.0.1:{self.port}/vnc.html?autoconnect=1&resize=scale&view_only=1&password={self.view_password}"

    def stop(self) -> None:
        subprocess.run([self.exe, "rm", "-f", self.container], capture_output=True, timeout=60, env=self.env)


def build_image(force: bool = False) -> str:
    oci = find_oci()
    if oci is None:
        raise DesktopError("no container daemon reachable (Docker via Colima, or Podman)")
    name, exe, env = oci
    have = subprocess.run([exe, "image", "inspect", IMAGE], capture_output=True, env=env).returncode == 0
    if not have or force:
        r = subprocess.run([exe, "build", "-t", IMAGE, str(HERE)], capture_output=True, text=True, timeout=1800, env=env)
        if r.returncode != 0:
            raise DesktopError("image build failed: " + r.stderr[-400:])
    return IMAGE


def start(app: str = "xterm", port: int = 0, wait_s: float = 60.0, resolution: str = "1024x640x24", clipboard: bool = True, view_only_link: bool = False) -> Desktop:
    """clipboard=False turns the clipboard off in both directions; view_only_link=True also creates a second password that can only watch."""
    if app not in APPS:
        raise DesktopError(f"application must be one of {', '.join(APPS)}")
    build_image()
    name, exe, env = find_oci()
    password = secrets.token_urlsafe(9)
    view_password = secrets.token_urlsafe(9) if view_only_link else None
    cname = f"spatial-desktop-{secrets.token_hex(4)}"
    publish = f"127.0.0.1:{port}:6080" if port else "127.0.0.1::6080"                # loopback only, by construction
    r = subprocess.run([exe, "run", "-d", "--name", cname, "-p", publish, "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                        "--read-only", "--tmpfs", "/tmp:rw,mode=1777,size=64m", "--tmpfs", "/home/desk:rw,uid=10001,mode=0700,size=64m",
                        "--memory", "512m", "--pids-limit", "128", "-e", f"VNC_PASSWORD={password}", "-e", f"RESOLUTION={resolution}", "-e", f"CLIPBOARD={1 if clipboard else 0}",
                        *(["-e", f"VIEW_PASSWORD={view_password}"] if view_password else []), IMAGE, *APPS[app]], capture_output=True, text=True, timeout=120, env=env)
    if r.returncode != 0:
        raise DesktopError("could not start the desktop: " + r.stderr[-300:])
    p = subprocess.run([exe, "port", cname, "6080/tcp"], capture_output=True, text=True, timeout=30, env=env).stdout.strip().splitlines()[0]
    d = Desktop(cname, int(p.rsplit(":", 1)[1]), password, name, exe, env, view_password, clipboard)
    deadline = time.time() + wait_s
    while time.time() < deadline:
        try:
            if urllib.request.urlopen(f"http://127.0.0.1:{d.port}/vnc.html", timeout=3).status == 200:
                return d
        except Exception:
            time.sleep(0.5)
    logs = subprocess.run([exe, "logs", "--tail", "20", cname], capture_output=True, text=True, env=env).stdout[-400:]
    d.stop()
    raise DesktopError("the desktop did not come up: " + logs)
