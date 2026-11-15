"""Spatial Intelligence Engine — FIRST COMPONENTS ONLY.

A power-law runtime predictor fitted on ledger measurements, so the scheduler can
estimate a strategy's time before running it. No learned world model is claimed.
"""
from .predictor import PowerLawPredictor  # noqa: F401
