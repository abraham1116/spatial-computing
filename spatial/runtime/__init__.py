"""Spatial Runtime Engine: inspect artifacts, plan an execution route, run it."""
from .inspect import inspect, Artifact  # noqa: F401
from .planner import plan, execute, host_caps  # noqa: F401
