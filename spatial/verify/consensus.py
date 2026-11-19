"""Redundant-execution verification: trust a result only if an independent second execution
agrees. The same comparison this project already made ad hoc between CPU and Metal kernel
output (tests/test_kernel.py), made into a reusable, documented primitive instead of a
one-off test.

Not cryptographic proof: no zkML, no TEE attestation. It is the cheap, economical check 2026
production systems actually use for decentralized/untrusted GPU markets -- redundant execution
or spot-check agreement, not a proof of correct floating-point GPU execution (see
docs/VERIFY.md for what this does and does not prove, and why).

No network calls here, no rented hardware, no money spent: this module only compares results
you already have. Actually renting two independent untrusted providers (e.g. two different
Vast.ai listings) and running a job on each is a separate, later, money-spending step that
needs explicit go-ahead each time -- same boundary as spatial.market's read-only pricing.
"""

from dataclasses import dataclass

import numpy as np


class VerificationError(Exception):
    pass


@dataclass(frozen=True)
class Consensus:
    agreed: bool
    max_abs_diff: float
    n_results: int
    reason: str


def consensus(results, *, tolerance: float = 0.0, exact: bool = False) -> Consensus:
    """Compare 2+ independent results for the same job.

    exact=True: every value must match bit-for-bit (integer/deterministic kernels); tolerance
    is ignored. exact=False: the largest absolute difference across all pairs must be <=
    tolerance (float kernels, which legitimately differ in the last bits between devices).

    Raises VerificationError for fewer than 2 results or results of different shapes -- there
    is nothing to verify by redundancy with only one result."""
    if len(results) < 2:
        raise VerificationError("need at least 2 independent results to verify by redundancy")
    arrays = [np.asarray(r) for r in results]
    shape = arrays[0].shape
    for a in arrays[1:]:
        if a.shape != shape:
            raise VerificationError(f"shape mismatch: {shape} vs {a.shape}")
    ref = arrays[0]
    max_diff = 0.0
    for a in arrays[1:]:
        if exact:
            if not np.array_equal(ref, a):
                diff = np.abs(ref.astype(np.int64) - a.astype(np.int64))
                return Consensus(False, float(diff.max()), len(results), "exact match required, results differ")
        else:
            diff = np.abs(ref.astype(np.float64) - a.astype(np.float64))
            d = float(diff.max())
            max_diff = max(max_diff, d)
            if d > tolerance:
                return Consensus(False, d, len(results), f"max absolute difference {d:g} exceeds tolerance {tolerance:g}")
    return Consensus(True, max_diff, len(results), "bit-exact match" if exact else "agreement within tolerance")


def verify_kernel(kernel, devices, n: int, *, tolerance: float = 0.0, exact: bool = False, **params) -> Consensus:
    """Run the same portable kernel on 2+ devices (e.g. ("cpu", "metal")) and check the results
    agree. This is what redundant-execution verification looks like when the two independent
    executions are two of this project's own devices rather than two rented, untrusted ones --
    the only thing actually measurable here (no second machine to rent)."""
    results = [kernel.run(d, n, **params) for d in devices]
    return consensus(results, tolerance=tolerance, exact=exact)
