"""Redundant-execution verification. See spatial.verify.consensus."""

from .consensus import Consensus, VerificationError, consensus, verify_kernel

__all__ = ["Consensus", "VerificationError", "consensus", "verify_kernel"]
