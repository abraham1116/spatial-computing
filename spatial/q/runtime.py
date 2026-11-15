"""SPATIAL Q runtime + orchestrator.

Executes `main` (classical control), dispatches:
  * classical tasks  -> local CPU or a compute worker (SWP/0), per `on` clause / load;
  * quantum kernels  -> compiled to SQIR, optimised, sent to a backend chosen from the
                        circuit's ResourceEstimate (or the explicit `on <backend>`).
Every dispatch is appended to `trace` (what ran where, why, how long).
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import psutil

from ..compute import workloads
from . import backends
from .compiler import CONSTS, FUNCS, SQCompileError, compile_kernel, div
from .parser import Program, parse


class SQRuntimeError(Exception):
    pass


class _Return(Exception):
    def __init__(self, v):
        self.v = v


class Runtime:
    def __init__(self, program: Program, worker_client=None, seed: int | None = None,
                 ram_fraction: float = 0.5, out=print, default_backend: str = "statevector",
                 noise: float = 0.0):
        self.noise = noise
        self.p = program
        self.worker = worker_client
        self.seed = seed
        self.ram_fraction = ram_fraction
        self.out = out
        self.default_backend = default_backend
        self.trace: list[dict] = []
        self._cache: dict = {}
        self._backends: dict[str, backends.Backend] = {}

    # ---- quantum dispatch
    def _circuit(self, name: str, args: list):
        if name not in self.p.kernels:
            raise SQRuntimeError(f"unknown quantum kernel '{name}'")
        key = (name, repr(args))
        if key not in self._cache:
            t0 = time.perf_counter()
            c, info = compile_kernel(self.p.kernels[name], args, kernels=self.p.kernels)
            info["compile_s"] = time.perf_counter() - t0
            self._cache[key] = (c, info)
        return self._cache[key]

    def _backend(self, requested: str, est) -> backends.Backend:
        name = requested
        reason = "explicit"
        if requested == "auto":
            avail = psutil.virtual_memory().available
            if est.statevector_bytes > self.ram_fraction * avail:
                raise SQRuntimeError(
                    f"{est.qubits} qubits need {est.statevector_bytes / 2**30:.1f} GiB for an exact "
                    f"state vector; only {avail / 2**30:.1f} GiB available. Not simulable here: needs "
                    "a QPU, a larger machine or an approximate simulator.")
            name = self.default_backend
            reason = f"auto: state vector {est.statevector_bytes} B fits in RAM"
        if name not in self._backends:
            self._backends[name] = backends.get(name)
        self._last_reason = reason
        return self._backends[name]

    def _sample(self, name, args, shots, backend):
        c, info = self._circuit(name, args)
        est = c.estimate()
        b = self._backend(backend, est)
        t0 = time.perf_counter()
        if self.noise and b.name != "statevector":
            raise SQRuntimeError(f"the noise option is only implemented for the built-in statevector backend, not '{b.name}'")
        counts = b.sample(c, shots, self.seed, noise=self.noise) if self.noise else b.sample(c, shots, self.seed)
        self.trace.append({"op": "sample", "kernel": name, "backend": b.name, "why": self._last_reason,
                           "shots": shots, "wall_s": time.perf_counter() - t0, "resources": est.to_dict(),
                           "optimizer": info, **({"noise": self.noise} if self.noise else {}),
                           **({"qpu_job": b.last_job} if getattr(b, "last_job", None) else {})})
        return counts

    def _expect(self, pauli, name, args, backend):
        c, info = self._circuit(name, args)
        est = c.estimate()
        b = self._backend(backend, est)
        t0 = time.perf_counter()
        v = b.expectation(c, pauli)
        self.trace.append({"op": "expect", "kernel": name, "backend": b.name, "pauli": pauli,
                           "wall_s": time.perf_counter() - t0, "qubits": est.qubits})
        return v

    # ---- classical dispatch
    def _workload(self, wname: str, kwargs: dict, target: str):
        where, why = "cpu", "task target"
        if target == "worker" or (target == "any" and self.worker is not None
                                  and psutil.cpu_percent(interval=0.05) > 75):
            if self.worker is None:
                raise SQRuntimeError("task targets a worker but none is attached to the runtime")
            where = "worker"
            why = "task target" if target == "worker" else "local CPU busy > 75%"
        elif target == "any":
            why = "local CPU has headroom" if self.worker is not None else "no worker attached"
        t0 = time.perf_counter()
        if where == "worker":
            rh, _ = self.worker.call({"op": "run", "workload": wname, "params": kwargs})
            r = rh["result"]
        else:
            r = workloads.run(wname, **kwargs)
        self.trace.append({"op": "workload", "workload": wname, "where": where, "why": why,
                           "wall_s": time.perf_counter() - t0})
        return r

    def _call_task(self, name: str, args: list):
        t = self.p.tasks[name]
        if len(args) != len(t.params):
            raise SQRuntimeError(f"task {name} expects {len(t.params)} argument(s)")
        env = dict(zip(t.params, args))
        try:
            self._block(t.body, env, t.target)
        except _Return as r:
            return r.v
        return None

    # ---- evaluation
    def ev(self, e, env: dict, target: str = "cpu"):
        k = e[0]
        if k in ("num", "str"):
            return e[1]
        if k == "var":
            if e[1] in env:
                return env[e[1]]
            if e[1] in CONSTS:
                return CONSTS[e[1]]
            raise SQRuntimeError(f"line {e[2]}: unknown name '{e[1]}'")
        if k == "neg":
            return -self.ev(e[1], env, target)
        if k == "not":
            return not self.ev(e[1], env, target)
        if k == "list":
            return [self.ev(x, env, target) for x in e[1]]
        if k == "index":
            return self.ev(e[1], env, target)[self.ev(e[2], env, target)]
        if k == "bin":
            op = e[1]
            a = self.ev(e[2], env, target)
            if op == "and":
                return a and self.ev(e[3], env, target)
            if op == "or":
                return a or self.ev(e[3], env, target)
            b = self.ev(e[3], env, target)
            return {"+": lambda: a + b, "-": lambda: a - b, "*": lambda: a * b, "/": lambda: div(a, b),
                    "%": lambda: a % b, "==": lambda: a == b, "!=": lambda: a != b, "<": lambda: a < b,
                    "<=": lambda: a <= b, ">": lambda: a > b, ">=": lambda: a >= b}[op]()
        if k == "call":
            args = [self.ev(a, env, target) for a in e[2]]
            if e[1] in self.p.tasks:
                return self._call_task(e[1], args)
            if e[1] in FUNCS:
                return FUNCS[e[1]](*args)
            if e[1] in self.p.kernels:
                raise SQRuntimeError(f"line {e[3]}: quantum kernel '{e[1]}' must be used with 'sample' or 'expect'")
            raise SQRuntimeError(f"line {e[3]}: unknown function '{e[1]}'")
        if k == "sample":
            return self._sample(e[1], [self.ev(a, env, target) for a in e[2]],
                                int(self.ev(e[3], env, target)), e[4])
        if k == "expect":
            return self._expect(e[1], e[2], [self.ev(a, env, target) for a in e[3]], e[4])
        if k == "workload":
            return self._workload(e[1], {kk: self.ev(v, env, target) for kk, v in e[2].items()}, target)
        if k == "measure":
            raise SQRuntimeError(f"line {e[2]}: 'measure' is only valid inside a quantum kernel")
        raise SQRuntimeError(f"cannot evaluate {k}")

    def _block(self, stmts, env: dict, target: str = "cpu"):
        for s in stmts:
            k = s[0]
            if k == "let" or k == "assign":
                if k == "assign" and s[1] not in env:
                    raise SQRuntimeError(f"line {s[3]}: assignment to undeclared variable '{s[1]}'")
                env[s[1]] = self.ev(s[2], env, target)
            elif k == "print":
                self.out(*[self.ev(x, env, target) for x in s[1]])
            elif k == "for":
                for i in range(self.ev(s[2], env, target), self.ev(s[3], env, target)):
                    env[s[1]] = i
                    self._block(s[4], env, target)
            elif k == "while":
                while self.ev(s[1], env, target):
                    self._block(s[2], env, target)
            elif k == "if":
                self._block(s[2] if self.ev(s[1], env, target) else s[3], env, target)
            elif k == "return":
                raise _Return(self.ev(s[1], env, target))
            elif k == "expr":
                self.ev(s[1], env, target)
            elif k == "parallel":
                lets = [x for x in s[1] if x[0] in ("let", "assign")]
                if len(lets) != len(s[1]):
                    raise SQRuntimeError(f"line {s[2]}: a parallel block may only contain let/assignment statements")
                t0 = time.perf_counter()
                with ThreadPoolExecutor(len(lets)) as ex:
                    futs = [ex.submit(self.ev, x[2], dict(env), target) for x in lets]
                    for x, f in zip(lets, futs):
                        env[x[1]] = f.result()
                self.trace.append({"op": "parallel", "branches": len(lets), "wall_s": time.perf_counter() - t0})
            else:
                raise SQRuntimeError(f"line {s[-1]}: statement '{k}' not allowed here")

    def run(self, compiled: bool = False) -> dict:
        """compiled=True runs the classical part through generated Python (see codegen.py)
        instead of the tree-walking interpreter; results are identical."""
        if compiled:
            from .codegen import run_compiled
            return run_compiled(self)
        env: dict = {}
        try:
            self._block(self.p.main, env)
        except _Return:
            pass
        return env


def run_source(src: str, compiled: bool = False, **kw) -> tuple[dict, Runtime]:
    rt = Runtime(parse(src), **kw)
    return rt.run(compiled=compiled), rt


def main():
    import argparse
    import json
    ap = argparse.ArgumentParser(prog="spatialq", description="SPATIAL Q compiler/runtime")
    ap.add_argument("cmd", choices=["run", "check", "qasm", "qasm2", "ir", "qir"])
    ap.add_argument("file")
    ap.add_argument("--kernel", help="kernel name for qasm/ir")
    ap.add_argument("--args", default="[]", help="JSON list of kernel arguments")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--trace", action="store_true")
    ap.add_argument("--compiled", action="store_true", help="compile the classical part to Python bytecode")
    ap.add_argument("--noise", type=float, default=0.0, help="depolarising error probability per gate and qubit")
    a = ap.parse_args()
    src = open(a.file).read()
    prog = parse(src)
    if a.cmd == "check":
        print(f"ok: {len(prog.kernels)} kernel(s), {len(prog.tasks)} task(s)")
        return
    if a.cmd in ("qasm", "qasm2", "ir", "qir"):
        name = a.kernel or next(k for k, v in prog.kernels.items() if "qubit" not in v.ptypes)
        c, info = compile_kernel(prog.kernels[name], json.loads(a.args), kernels=prog.kernels)
        if a.cmd == "qir":
            from .qir import to_qir
            print(to_qir(c))
        elif a.cmd == "qasm2":
            print(c.to_qasm2())
        else:
            print(c.to_qasm3() if a.cmd == "qasm" else c.to_json())
        return
    rt = Runtime(prog, seed=a.seed, noise=a.noise)
    rt.run(compiled=a.compiled)
    if a.trace:
        for t in rt.trace:
            print("TRACE", json.dumps(t, default=str))


if __name__ == "__main__":
    try:
        main()
    except (SyntaxError, SQCompileError, SQRuntimeError, backends.BackendUnavailable) as e:
        raise SystemExit(f"spatialq: {e}")
