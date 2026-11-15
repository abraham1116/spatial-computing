"""Spatial AI Engine: first components in the public repository.

kvcache.py: a toy NumPy transformer with a real key/value cache, used to measure recompute
versus restore through the tiered memory store (CPU, toy sizes: says nothing about GPUs).

The model-placement planner (layers over heterogeneous nodes, memory, network, availability)
lives in the private `spatial_pro` package. When that package is installed, `plan_pipeline`
and friends are re-exported here; otherwise they are None and nothing pretends to work.
No real language model is executed by this repository.
"""
try:  # pragma: no cover - depends on a private package
    from spatial_pro.placement import ModelSpec, NodeSpec, plan_pipeline  # noqa: F401
    HAVE_PLANNER = True
except ImportError:
    ModelSpec = NodeSpec = plan_pipeline = None
    HAVE_PLANNER = False

from .kvcache import ToyTransformer, measure_restore_vs_recompute  # noqa: E402,F401
