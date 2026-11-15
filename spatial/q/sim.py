"""Built-in exact state-vector simulator (NumPy).

Conventions (same as Qiskit, to make cross-checks direct):
  * qubit 0 is the least-significant bit of the basis-state index;
  * printed bitstrings show qubit n-1 on the left, qubit 0 on the right;
  * multi-qubit gate matrices list their first qubit argument as the most significant.
Memory: 16 bytes x 2^n. This is a classical simulation: it shows correctness, not speed-up.
"""
from __future__ import annotations

import math

import numpy as np

from .ir import Circuit

_S2 = 1 / math.sqrt(2)
I2 = np.eye(2, dtype=complex)
FIXED = {
    "h": np.array([[_S2, _S2], [_S2, -_S2]], dtype=complex),
    "x": np.array([[0, 1], [1, 0]], dtype=complex),
    "y": np.array([[0, -1j], [1j, 0]], dtype=complex),
    "z": np.array([[1, 0], [0, -1]], dtype=complex),
    "s": np.array([[1, 0], [0, 1j]], dtype=complex),
    "sdg": np.array([[1, 0], [0, -1j]], dtype=complex),
    "t": np.array([[1, 0], [0, np.exp(1j * math.pi / 4)]], dtype=complex),
    "tdg": np.array([[1, 0], [0, np.exp(-1j * math.pi / 4)]], dtype=complex),
    "sx": 0.5 * np.array([[1 + 1j, 1 - 1j], [1 - 1j, 1 + 1j]], dtype=complex),
    "cx": np.array([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 1], [0, 0, 1, 0]], dtype=complex),
    "cz": np.diag([1, 1, 1, -1]).astype(complex),
    "swap": np.array([[1, 0, 0, 0], [0, 0, 1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], dtype=complex),
}
_ccx = np.eye(8, dtype=complex)
_ccx[6:, 6:] = [[0, 1], [1, 0]]
FIXED["ccx"] = _ccx


def matrix(name: str, params: tuple) -> np.ndarray:
    if name in FIXED:
        return FIXED[name]
    t = params[0]
    c, s = math.cos(t / 2), math.sin(t / 2)
    if name == "rx":
        return np.array([[c, -1j * s], [-1j * s, c]], dtype=complex)
    if name == "ry":
        return np.array([[c, -s], [s, c]], dtype=complex)
    if name == "rz":
        return np.array([[np.exp(-1j * t / 2), 0], [0, np.exp(1j * t / 2)]], dtype=complex)
    if name == "p":
        return np.array([[1, 0], [0, np.exp(1j * t)]], dtype=complex)
    if name == "cp":
        return np.diag([1, 1, 1, np.exp(1j * t)]).astype(complex)
    if name == "crz":
        return np.diag([1, 1, np.exp(-1j * t / 2), np.exp(1j * t / 2)]).astype(complex)
    raise KeyError(f"unknown gate {name}")


class State:
    def __init__(self, n: int):
        self.n = n
        self.psi = np.zeros((2,) * n, dtype=complex)
        self.psi[(0,) * n] = 1.0

    def apply(self, U: np.ndarray, qubits: tuple[int, ...]):
        k = len(qubits)
        axes = [self.n - 1 - q for q in qubits]
        self.psi = np.moveaxis(
            np.tensordot(U.reshape((2,) * (2 * k)), self.psi, axes=(list(range(k, 2 * k)), axes)),
            list(range(k)), axes)

    def prob1(self, q: int) -> float:
        ax = self.n - 1 - q
        return float(np.sum(np.abs(np.take(self.psi, 1, axis=ax)) ** 2))

    def measure(self, q: int, rng) -> int:
        p1 = self.prob1(q)
        r = int(rng.random() < p1)
        ax = self.n - 1 - q
        sl = [slice(None)] * self.n
        sl[ax] = 1 - r
        self.psi[tuple(sl)] = 0
        self.psi /= math.sqrt(p1 if r else 1 - p1)
        return r

    def reset(self, q: int, rng):
        if self.measure(q, rng):
            self.apply(FIXED["x"], (q,))

    def probs(self) -> np.ndarray:
        return np.abs(self.psi.reshape(-1)) ** 2

    def vector(self) -> np.ndarray:
        return self.psi.reshape(-1)


def run_static(c: Circuit) -> State:
    """Circuit without mid-circuit measurement / feed-forward."""
    s = State(c.n_qubits)
    for o in c.ops:
        s.apply(matrix(o.name, o.params), o.qubits)
    return s


def is_static(c: Circuit) -> bool:
    return all(o.name not in ("measure", "reset") and not o.cond for o in c.ops)


def run_shot(c: Circuit, rng) -> State:
    s = State(c.n_qubits)
    bits = [0] * c.n_cbits
    for o in c.ops:
        if o.cond and any(bits[b] != v for b, v in o.cond):
            continue
        if o.name == "measure":
            bits[o.cbit] = s.measure(o.qubits[0], rng)
        elif o.name == "reset":
            s.reset(o.qubits[0], rng)
        else:
            s.apply(matrix(o.name, o.params), o.qubits)
    return s


def branch_distribution(c: Circuit, max_branches: int = 4096) -> np.ndarray | None:
    """Exact output distribution of a dynamic circuit by enumerating measurement branches
    (each mid-circuit measurement splits the state in two, weighted by its probability).
    Returns None when the branch count would exceed `max_branches`."""
    n = c.n_qubits
    total = np.zeros(1 << n)
    stack = [(1.0, State(n), [0] * c.n_cbits, 0)]
    leaves = 0
    while stack:
        w, s, bits, pc = stack.pop()
        while pc < len(c.ops):
            o = c.ops[pc]
            pc += 1
            if o.cond and any(bits[b] != v for b, v in o.cond):
                continue
            if o.name in ("measure", "reset"):
                q = o.qubits[0]
                p1 = s.prob1(q)
                ax = n - 1 - q
                for r, pr in ((0, 1 - p1), (1, p1)):
                    if pr < 1e-15:
                        continue
                    s2 = State(n)
                    s2.psi = s.psi.copy()
                    sl = [slice(None)] * n
                    sl[ax] = 1 - r
                    s2.psi[tuple(sl)] = 0
                    s2.psi /= math.sqrt(pr)
                    b2 = list(bits)
                    if o.name == "measure":
                        b2[o.cbit] = r
                    elif r:
                        s2.apply(FIXED["x"], (q,))
                    stack.append((w * pr, s2, b2, pc))
                if len(stack) + leaves > max_branches:
                    return None
                break
            s.apply(matrix(o.name, o.params), o.qubits)
        else:
            total += w * s.probs()
            leaves += 1
    return total


def sample(c: Circuit, shots: int, seed: int | None = None, dynamic: str = "branch") -> dict[str, int]:
    """dynamic="branch": exact branch enumeration then one multinomial draw (fast);
       dynamic="shots" : one full simulation per shot (reference implementation)."""
    rng = np.random.default_rng(seed)
    n = c.n_qubits
    p = None
    if is_static(c):
        p = run_static(c).probs()
    elif dynamic == "branch":
        p = branch_distribution(c)
    if p is not None:
        p = p / p.sum()
        draws = rng.multinomial(shots, p)
        return {format(i, f"0{n}b"): int(k) for i, k in enumerate(draws) if k}
    counts: dict[str, int] = {}
    for _ in range(shots):
        p = run_shot(c, rng).probs()
        i = int(rng.choice(len(p), p=p / p.sum()))
        key = format(i, f"0{n}b")
        counts[key] = counts.get(key, 0) + 1
    return counts


_PAULI = {"I": I2, "X": FIXED["x"], "Y": FIXED["y"], "Z": FIXED["z"]}


def expectation(c: Circuit, pauli: str) -> float:
    """Exact <psi|P|psi>. `pauli` is written like a bitstring: leftmost char acts on qubit n-1."""
    if not is_static(c):
        raise ValueError("expect needs a kernel without mid-circuit measurement")
    if len(pauli) != c.n_qubits or any(ch not in _PAULI for ch in pauli):
        raise ValueError(f"Pauli string must have {c.n_qubits} characters from IXYZ")
    s = run_static(c)
    psi0 = s.psi.copy()
    for pos, ch in enumerate(pauli):
        if ch != "I":
            s.apply(_PAULI[ch], (c.n_qubits - 1 - pos,))
    return float(np.real(np.vdot(psi0.reshape(-1), s.psi.reshape(-1))))
