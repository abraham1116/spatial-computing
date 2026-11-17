"""The one place that maps `platform.machine()` to the architecture names used everywhere else in this
package (matching `inspect.py`'s ELF/Mach-O/PE architecture names: x86_64, aarch64, i386, arm). A separate
module so `planner.py`, `microvm.py` and `runner.py` can all import it without a circular import."""
from __future__ import annotations

import platform

_MACHINE = {"AMD64": "x86_64", "arm64": "aarch64"}


def host_arch() -> str:
    return _MACHINE.get(platform.machine(), platform.machine())
