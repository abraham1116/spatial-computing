"""SQIR — SPATIAL Q Intermediate Representation (quantum part).

A Circuit is a flat list of Ops on numbered qubits and classical bits, plus a
ResourceEstimate that the orchestrator uses to pick a backend. Serialisable to
JSON (`to_json`) and to OpenQASM 3 (`to_qasm3`), the interoperability target.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Op:
    name: str                       # gate name | "measure" | "reset"
    qubits: tuple[int, ...]
    params: tuple[float, ...] = ()
    cbit: int | None = None         # target classical bit for "measure"
    cond: tuple[tuple[int, int], ...] = ()   # all (cbit, value) pairs must hold


@dataclass
class ResourceEstimate:
    qubits: int
    ops: int
    two_qubit_ops: int
    depth: int
    mid_circuit_measurements: int
    statevector_bytes: int          # 16 * 2^n: RAM needed by an exact state-vector simulation
    dynamic: bool                   # needs feed-forward (conditional ops)

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class Circuit:
    name: str
    n_qubits: int = 0
    n_cbits: int = 0
    ops: list[Op] = field(default_factory=list)

    def estimate(self) -> ResourceEstimate:
        level = [0] * max(self.n_qubits, 1)
        two = mid = 0
        dyn = False
        for o in self.ops:
            d = max(level[q] for q in o.qubits) + 1
            for q in o.qubits:
                level[q] = d
            if len(o.qubits) >= 2:
                two += 1
            if o.name == "measure":
                mid += 1
            if o.cond:
                dyn = True
        return ResourceEstimate(self.n_qubits, len(self.ops), two, max(level) if self.ops else 0,
                                mid, 16 * (1 << self.n_qubits), dyn)

    def to_json(self) -> str:
        return json.dumps({
            "sqir": "0.1", "name": self.name, "qubits": self.n_qubits, "cbits": self.n_cbits,
            "ops": [{"g": o.name, "q": list(o.qubits), **({"p": list(o.params)} if o.params else {}),
                     **({"c": o.cbit} if o.cbit is not None else {}),
                     **({"if": [list(c) for c in o.cond]} if o.cond else {})} for o in self.ops],
            "resources": self.estimate().to_dict()}, indent=1)

    @staticmethod
    def from_json(text: str) -> "Circuit":
        d = json.loads(text)
        c = Circuit(d["name"], d["qubits"], d["cbits"])
        for o in d["ops"]:
            c.ops.append(Op(o["g"], tuple(o["q"]), tuple(o.get("p", ())), o.get("c"),
                            tuple(tuple(x) for x in o.get("if", ()))))
        return c

    def to_qasm3(self) -> str:
        """OpenQASM 3 text. A final `c = measure q;` reads out every qubit."""
        L = ["OPENQASM 3.0;", 'include "stdgates.inc";', f"qubit[{self.n_qubits}] q;"]
        if self.n_cbits:
            L.append(f"bit[{self.n_cbits}] m;")
        L.append(f"bit[{self.n_qubits}] c;")
        for o in self.ops:
            qs = ", ".join(f"q[{q}]" for q in o.qubits)
            if o.name == "measure":
                s = f"m[{o.cbit}] = measure {qs};"
            elif o.name == "reset":
                s = f"reset {qs};"
            else:
                p = "(" + ", ".join(repr(float(x)) for x in o.params) + ")" if o.params else ""
                s = f"{o.name}{p} {qs};"
            if o.cond:
                cond = " && ".join(f"m[{b}] == {v}" for b, v in o.cond)
                s = f"if ({cond}) {{ {s} }}"
            L.append(s)
        L.append("c = measure q;")
        return "\n".join(L) + "\n"
