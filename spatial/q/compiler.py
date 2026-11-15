"""SPATIAL Q compiler: kernel AST + classical arguments -> SQIR Circuit, then optimisation.

Kernels are specialised at call time (like a JIT): classical expressions and loops are
evaluated at compile time; measurement results are run-time values that may only be used
as `if` conditions (feed-forward).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .ir import Circuit, Op
from .parser import GATES, Kernel


class SQCompileError(Exception):
    pass


@dataclass(frozen=True)
class MeasRef:
    """Run-time measurement outcome (classical bit index, expected value)."""
    cbit: int
    value: int = 1


CONSTS = {"pi": math.pi, "tau": math.tau, "e": math.e}
FUNCS = {"sin": math.sin, "cos": math.cos, "sqrt": math.sqrt, "abs": abs, "min": min, "max": max,
         "floor": math.floor, "acos": math.acos, "asin": math.asin, "exp": math.exp, "log": math.log,
         "len": len, "float": float, "int": int, "pow": pow}


def div(a, b):
    """`/` keeps integers when the division is exact (so `n / 2` can index or size things)."""
    if isinstance(a, int) and isinstance(b, int) and not isinstance(a, bool) and b != 0 and a % b == 0:
        return a // b
    return a / b


def eval_const(e, env: dict):
    """Evaluate a classical expression (shared with the runtime for pure expressions)."""
    k = e[0]
    if k in ("num", "str"):
        return e[1]
    if k == "var":
        if e[1] in env:
            return env[e[1]]
        if e[1] in CONSTS:
            return CONSTS[e[1]]
        raise SQCompileError(f"line {e[2]}: unknown name '{e[1]}'")
    if k == "neg":
        return -eval_const(e[1], env)
    if k == "not":
        v = eval_const(e[1], env)
        return MeasRef(v.cbit, 1 - v.value) if isinstance(v, MeasRef) else (not v)
    if k == "list":
        return [eval_const(x, env) for x in e[1]]
    if k == "index":
        return eval_const(e[1], env)[eval_const(e[2], env)]
    if k == "bin":
        op = e[1]
        a = eval_const(e[2], env)
        if op == "and":
            return a and eval_const(e[3], env)
        if op == "or":
            return a or eval_const(e[3], env)
        b = eval_const(e[3], env)
        return {"+": lambda: a + b, "-": lambda: a - b, "*": lambda: a * b, "/": lambda: div(a, b),
                "%": lambda: a % b, "==": lambda: a == b, "!=": lambda: a != b, "<": lambda: a < b,
                "<=": lambda: a <= b, ">": lambda: a > b, ">=": lambda: a >= b}[op]()
    if k == "call" and e[1] in FUNCS:
        return FUNCS[e[1]](*[eval_const(a, env) for a in e[2]])
    raise SQCompileError(f"expression kind '{k}' is not allowed here")


MAX_CALL_DEPTH = 32


class KernelCompiler:
    def __init__(self, kernel: Kernel, args: list, kernels: dict | None = None):
        if any(t == "qubit" for t in kernel.ptypes):
            raise SQCompileError(f"kernel {kernel.name} takes qubit parameters: it can only be called from another kernel")
        if len(args) != len(kernel.params):
            raise SQCompileError(f"kernel {kernel.name} expects {len(kernel.params)} argument(s), got {len(args)}")
        self.k = kernel
        self.kernels = kernels or {}
        self.env = dict(zip(kernel.params, args))
        self.regs: dict[str, list[int]] = {}          # register name -> qubit indices
        self.c = Circuit(kernel.name)
        self.cond: tuple[tuple[int, int], ...] = ()
        self.depth = 0

    def _qubits_from_expr(self, e, line) -> list[int]:
        if e[0] == "var":
            return self.qubits((e[1], None), line)
        if e[0] == "index" and e[1][0] == "var":
            return self.qubits((e[1][1], e[2]), line)
        raise SQCompileError(f"line {line}: a qubit argument must be a register or a register element")

    def _call(self, name: str, args: list, line: int):
        """Inline a sub-kernel: its gates are appended to this circuit on the qubits passed in."""
        callee = self.kernels.get(name)
        if callee is None:
            raise SQCompileError(f"line {line}: unknown kernel '{name}'")
        if len(args) != len(callee.params):
            raise SQCompileError(f"line {line}: kernel {name} expects {len(callee.params)} argument(s), got {len(args)}")
        if self.depth >= MAX_CALL_DEPTH:
            raise SQCompileError(f"line {line}: kernel calls nested deeper than {MAX_CALL_DEPTH} (recursion?)")
        child = object.__new__(KernelCompiler)
        child.k, child.kernels, child.c, child.cond, child.depth = callee, self.kernels, self.c, self.cond, self.depth + 1
        child.env, child.regs = {}, {}
        ptypes = callee.ptypes or [None] * len(callee.params)
        for pname, ptype, a in zip(callee.params, ptypes, args):
            if ptype == "qubit":
                child.regs[pname] = self._qubits_from_expr(a, line)
            else:
                child.env[pname] = eval_const(a, self.env)
        child.body(callee.body)

    def qubits(self, qa, line) -> list[int]:
        name, idx = qa
        if name not in self.regs:
            raise SQCompileError(f"line {line}: unknown qubit register '{name}'")
        qs = self.regs[name]
        size = len(qs)
        if idx is None:
            return list(qs)
        i = eval_const(idx, self.env)
        if not isinstance(i, int) or not 0 <= i < size:
            raise SQCompileError(f"line {line}: index {i!r} out of range for {name}[{size}]")
        return [qs[i]]

    def one(self, qa, line) -> int:
        qs = self.qubits(qa, line)
        if len(qs) != 1:
            raise SQCompileError(f"line {line}: a single qubit is required here (use {qa[0]}[i])")
        return qs[0]

    def body(self, stmts):
        for s in stmts:
            kind = s[0]
            if kind == "qubit":
                size = eval_const(s[2], self.env)
                if not isinstance(size, int) or size < 1:
                    raise SQCompileError(f"line {s[3]}: register size must be a positive integer")
                self.regs[s[1]] = list(range(self.c.n_qubits, self.c.n_qubits + size))
                self.c.n_qubits += size
            elif kind == "kcall":
                self._call(s[1], s[2], s[3])
            elif kind == "gate":
                _, name, params, qargs, line = s
                ps = tuple(float(eval_const(p, self.env)) for p in params)
                if GATES[name][1] == 1 and qargs[0][1] is None:      # broadcast: `h q;`
                    for q in self.qubits(qargs[0], line):
                        self.c.ops.append(Op(name, (q,), ps, cond=self.cond))
                else:
                    qs = tuple(self.one(qa, line) for qa in qargs)
                    if len(set(qs)) != len(qs):
                        raise SQCompileError(f"line {line}: gate {name} applied twice to the same qubit")
                    self.c.ops.append(Op(name, qs, ps, cond=self.cond))
            elif kind == "reset":
                for q in self.qubits(s[1], s[2]):
                    self.c.ops.append(Op("reset", (q,), cond=self.cond))
            elif kind in ("let", "assign"):
                e = s[2]
                if e[0] == "measure":
                    q = self.one(e[1], e[2])
                    self.c.ops.append(Op("measure", (q,), cbit=self.c.n_cbits, cond=self.cond))
                    self.env[s[1]] = MeasRef(self.c.n_cbits)
                    self.c.n_cbits += 1
                else:
                    self.env[s[1]] = eval_const(e, self.env)
            elif kind == "for":
                lo, hi = eval_const(s[2], self.env), eval_const(s[3], self.env)
                for i in range(lo, hi):
                    self.env[s[1]] = i
                    self.body(s[4])
            elif kind == "if":
                c = eval_const(s[1], self.env)
                if isinstance(c, MeasRef):
                    saved = self.cond
                    self.cond = saved + ((c.cbit, c.value),)
                    self.body(s[2])
                    self.cond = saved + ((c.cbit, 1 - c.value),)
                    self.body(s[3])
                    self.cond = saved
                else:
                    self.body(s[2] if c else s[3])
            elif kind == "expr" and s[1][0] == "measure":
                q = self.one(s[1][1], s[1][2])
                self.c.ops.append(Op("measure", (q,), cbit=self.c.n_cbits, cond=self.cond))
                self.c.n_cbits += 1
            else:
                raise SQCompileError(f"line {s[-1]}: statement '{kind}' is not allowed in a quantum kernel")

    def compile(self) -> Circuit:
        self.body(self.k.body)
        if self.c.n_qubits == 0:
            raise SQCompileError(f"kernel {self.k.name} declares no qubits")
        return self.c


# ------------------------------------------------------------------ optimiser
_SELF_INVERSE = {"h", "x", "y", "z", "cx", "cz", "swap", "ccx"}
_INVERSE_PAIR = {("s", "sdg"), ("sdg", "s"), ("t", "tdg"), ("tdg", "t")}
_ROT = {"rx", "ry", "rz", "p", "cp", "crz"}
_SYMMETRIC = {"cz", "swap", "cp"}


def _key(o: Op):
    return tuple(sorted(o.qubits)) if o.name in _SYMMETRIC else o.qubits


_DIAG_1Q = {"z", "s", "sdg", "t", "tdg", "rz", "p"}
_DIAG_ANY = _DIAG_1Q | {"cz", "cp", "crz"}
_X_1Q = {"x", "rx"}


def _commutes(g: Op, o: Op, q: int) -> bool:
    """Does single-qubit gate `g` (acting on q) commute with `o`, which also touches q?"""
    if o.cond or o.name in ("measure", "reset"):
        return False
    if g.name in _DIAG_1Q:                       # diagonal: commutes with diagonal gates and with controls
        if o.name in _DIAG_ANY:
            return True
        if o.name == "cx":
            return o.qubits[0] == q              # control
        if o.name == "ccx":
            return q in o.qubits[:2]
        return False
    if g.name in _X_1Q:                          # X-type: commutes with X-type and with a CX/CCX target
        if o.name in _X_1Q:
            return True
        if o.name == "cx":
            return o.qubits[1] == q
        if o.name == "ccx":
            return o.qubits[2] == q
    return False


def _merge(prev: Op, g: Op):
    """Result of applying prev then g on the same qubit: Op, None (cancel) or "no" (not mergeable)."""
    if prev.cond or prev.qubits != g.qubits:
        return "no"
    if prev.name == g.name and g.name in _SELF_INVERSE:
        return None
    if (prev.name, g.name) in _INVERSE_PAIR:
        return None
    if prev.name == g.name and g.name in ("rz", "rx", "p"):
        return Op(g.name, g.qubits, (prev.params[0] + g.params[0],))
    return "no"


def _commute_pass(ops: list) -> tuple[list, bool]:
    """Move single-qubit gates backwards across gates they commute with, to meet and merge with
    an earlier gate of the same kind (e.g. rz a; cx q0,q1; rz b  ->  rz (a+b); cx q0,q1)."""
    ops, changed = list(ops), False
    for i, g in enumerate(ops):
        if g is None or g.cond or len(g.qubits) != 1 or g.name not in (_DIAG_1Q | _X_1Q):
            continue
        q = g.qubits[0]
        for j in range(i - 1, -1, -1):
            o = ops[j]
            if o is None or q not in o.qubits:
                continue
            m = _merge(o, g) if len(o.qubits) == 1 else "no"
            if m != "no":
                ops[j] = m
                ops[i] = None
                changed = True
                break
            if not _commutes(g, o, q):
                break
    return [o for o in ops if o is not None], changed


def optimize(c: Circuit) -> tuple[Circuit, dict]:
    """Peephole passes to a fixed point: cancel adjacent inverse pairs, merge same-axis
    rotations, drop identity rotations. 'Adjacent' = no other op touches those qubits in
    between. Measurements, resets and conditional ops are barriers."""
    ops = list(c.ops)
    before = len(ops)
    passes = 0
    changed = True
    while changed:
        changed = False
        passes += 1
        out: list[Op | None] = []
        last: dict[int, int] = {}          # qubit -> index in `out` of the last op touching it
        for o in ops:
            barrier = o.name in ("measure", "reset") or bool(o.cond)
            prev_i = None
            if not barrier:
                idxs = {last.get(q) for q in o.qubits}
                if len(idxs) == 1 and None not in idxs:
                    prev_i = idxs.pop()
            prev = out[prev_i] if prev_i is not None else None
            if prev is not None and not prev.cond and prev.name not in ("measure", "reset") \
                    and _key(prev) == _key(o) and len(prev.qubits) == len(o.qubits):
                if (prev.name == o.name and o.name in _SELF_INVERSE) or (prev.name, o.name) in _INVERSE_PAIR:
                    out[prev_i] = None
                    for q in o.qubits:
                        last.pop(q, None)
                    # restore `last` for these qubits from earlier ops
                    for j in range(prev_i - 1, -1, -1):
                        if out[j] is not None:
                            for q in out[j].qubits:
                                if q in o.qubits and q not in last:
                                    last[q] = j
                    changed = True
                    continue
                if prev.name == o.name and o.name in _ROT:
                    out[prev_i] = Op(o.name, prev.qubits, (prev.params[0] + o.params[0],))
                    changed = True
                    continue
            out.append(o)
            for q in o.qubits:
                last[q] = len(out) - 1
        ops = []
        for o in out:
            if o is None:
                continue
            if o.name in _ROT and not o.cond:
                period = 2 * math.pi if o.name in ("p", "cp") else 4 * math.pi
                a = math.fmod(o.params[0], period)
                if abs(a) < 1e-12 or abs(abs(a) - period) < 1e-12:
                    changed = True
                    continue
            ops.append(o)
        ops, moved = _commute_pass(ops)
        changed = changed or moved
    oc = Circuit(c.name, c.n_qubits, c.n_cbits, ops)
    return oc, {"ops_before": before, "ops_after": len(ops), "passes": passes}


def compile_kernel(kernel: Kernel, args: list, opt: bool = True, kernels: dict | None = None) -> tuple[Circuit, dict]:
    """`kernels` is the program's kernel table, needed when the kernel calls sub-kernels."""
    c = KernelCompiler(kernel, args, kernels).compile()
    if opt:
        return optimize(c)
    return c, {"ops_before": len(c.ops), "ops_after": len(c.ops), "passes": 0}
