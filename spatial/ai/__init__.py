"""Spatial AI Engine: interface only in the public repository.

The model-placement planner (layers over heterogeneous nodes, memory, network, availability)
lives in the private `spatial_pro` package. When that package is installed, `plan_pipeline`
and friends are re-exported here; otherwise they are None and nothing pretends to work.
No model inference is executed by this repository.
"""
try:  # pragma: no cover - depends on a private package
    from spatial_pro.placement import ModelSpec, NodeSpec, plan_pipeline  # noqa: F401
    HAVE_PLANNER = True
except ImportError:
    ModelSpec = NodeSpec = plan_pipeline = None
    HAVE_PLANNER = False
