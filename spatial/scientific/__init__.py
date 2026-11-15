"""Spatial Scientific & Industrial Engine — FIRST COMPONENTS ONLY.

A JobSpec describes a numerical job with a validation target; the engine runs it and
checks the answer against an independent reference. One reference job is implemented
(Monte Carlo option pricing vs Black-Scholes) plus an RK4 ODE job checked against its
analytic solution. No industrial solver is claimed.
"""
from .jobs import JobSpec, run_job, european_call_mc, black_scholes_call, harmonic_rk4  # noqa: F401
