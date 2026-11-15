"""Compiles the CLASSICAL part of a SPATIAL Q program (main + tasks) to Python source, which
CPython then compiles to bytecode. Quantum kernels keep going through the SQIR compiler;
this replaces the tree-walking interpreter for control flow and arithmetic.

Semantics are the interpreter's: same dispatch (`sample`, `expect`, `workload`, tasks,
`parallel`), same integer-preserving division, same errors for undeclared assignment.
`compile_program()` returns the generated source so it can be inspected or cached.
"""
from __future__ import annotations

from .compiler import CONSTS, FUNCS, div
from .parser import Program


class SQCodegenError(Exception):
    pass


_BIN = {"and": "and", "or": "or", "==": "==", "!=": "!=", "<": "<", "<=": "<=", ">": ">", ">=": ">=",
        "+": "+", "-": "-", "*": "*", "%": "%"}


class _Gen:
    def __init__(self, prog: Program):
        self.p = prog
        self.lines: list[str] = []

    def emit(self, depth: int, s: str):
        self.lines.append("    " * depth + s)

    def expr(self, e, scope: set, target: str) -> str:
        k = e[0]
        if k == "num":
            return repr(e[1])
        if k == "str":
            return repr(e[1])
        if k == "var":
            if e[1] in scope:
                return "v_" + e[1]
            if e[1] in CONSTS:
                return repr(CONSTS[e[1]])
            raise SQCodegenError(f"line {e[2]}: unknown name '{e[1]}'")
        if k == "neg":
            return f"(-{self.expr(e[1], scope, target)})"
        if k == "not":
            return f"(not {self.expr(e[1], scope, target)})"
        if k == "list":
            return "[" + ", ".join(self.expr(x, scope, target) for x in e[1]) + "]"
        if k == "index":
            return f"{self.expr(e[1], scope, target)}[{self.expr(e[2], scope, target)}]"
        if k == "bin":
            a, b = self.expr(e[2], scope, target), self.expr(e[3], scope, target)
            return f"_div({a}, {b})" if e[1] == "/" else f"({a} {_BIN[e[1]]} {b})"
        if k == "call":
            args = ", ".join(self.expr(a, scope, target) for a in e[2])
            if e[1] in self.p.tasks:
                return f"t_{e[1]}({args})"
            if e[1] in FUNCS:
                return f"_F[{e[1]!r}]({args})"
            if e[1] in self.p.kernels:
                raise SQCodegenError(f"line {e[3]}: quantum kernel '{e[1]}' must be used with 'sample' or 'expect'")
            raise SQCodegenError(f"line {e[3]}: unknown function '{e[1]}'")
        if k == "sample":
            args = ", ".join(self.expr(a, scope, target) for a in e[2])
            return f"_rt._sample({e[1]!r}, [{args}], int({self.expr(e[3], scope, target)}), {e[4]!r})"
        if k == "expect":
            args = ", ".join(self.expr(a, scope, target) for a in e[3])
            return f"_rt._expect({e[1]!r}, {e[2]!r}, [{args}], {e[4]!r})"
        if k == "workload":
            kw = ", ".join(f"{kk!r}: {self.expr(v, scope, target)}" for kk, v in e[2].items())
            return f"_rt._workload({e[1]!r}, {{{kw}}}, {target!r})"
        if k == "measure":
            raise SQCodegenError(f"line {e[2]}: 'measure' is only valid inside a quantum kernel")
        raise SQCodegenError(f"cannot compile expression {k}")

    def block(self, stmts, scope: set, depth: int, target: str):
        if not stmts:
            self.emit(depth, "pass")
        for s in stmts:
            k = s[0]
            if k == "let":
                rhs = self.expr(s[2], scope, target)
                scope.add(s[1])
                self.emit(depth, f"v_{s[1]} = {rhs}")
            elif k == "assign":
                if s[1] not in scope:
                    raise SQCodegenError(f"line {s[3]}: assignment to undeclared variable '{s[1]}'")
                self.emit(depth, f"v_{s[1]} = {self.expr(s[2], scope, target)}")
            elif k == "print":
                self.emit(depth, f"_rt.out({', '.join(self.expr(x, scope, target) for x in s[1])})")
            elif k == "for":
                lo, hi = self.expr(s[2], scope, target), self.expr(s[3], scope, target)
                scope.add(s[1])
                self.emit(depth, f"for v_{s[1]} in range({lo}, {hi}):")
                self.block(s[4], scope, depth + 1, target)
            elif k == "while":
                self.emit(depth, f"while {self.expr(s[1], scope, target)}:")
                self.block(s[2], scope, depth + 1, target)
            elif k == "if":
                self.emit(depth, f"if {self.expr(s[1], scope, target)}:")
                self.block(s[2], scope, depth + 1, target)
                if s[3]:
                    self.emit(depth, "else:")
                    self.block(s[3], scope, depth + 1, target)
            elif k == "return":
                self.emit(depth, f"return {self.expr(s[1], scope, target)}")
            elif k == "expr":
                self.emit(depth, self.expr(s[1], scope, target))
            elif k == "parallel":
                lets = [x for x in s[1] if x[0] in ("let", "assign")]
                if len(lets) != len(s[1]):
                    raise SQCodegenError(f"line {s[2]}: a parallel block may only contain let/assignment statements")
                thunks = ", ".join(f"lambda: {self.expr(x[2], scope, target)}" for x in lets)
                names = ", ".join(f"v_{x[1]}" for x in lets)
                for x in lets:
                    scope.add(x[1])
                self.emit(depth, f"{names}{',' if len(lets) == 1 else ''} = _par([{thunks}])")
            else:
                raise SQCodegenError(f"line {s[-1]}: statement '{k}' not allowed here")

    def program(self) -> str:
        for t in self.p.tasks.values():
            self.emit(0, f"def t_{t.name}({', '.join('v_' + a for a in t.params)}):")
            self.block(t.body, set(t.params), 1, t.target)
            self.emit(0, "")
        self.emit(0, "def _main():")
        scope: set = set()
        self.block(self.p.main, scope, 1, "cpu")
        self.emit(1, "return {k[2:]: v for k, v in locals().items() if k.startswith('v_')}")
        return "\n".join(self.lines) + "\n"


def compile_program(prog: Program) -> str:
    """Python source for the classical part of `prog`."""
    return _Gen(prog).program()


def run_compiled(rt) -> dict:
    """Execute a Runtime's program through the compiled classical path. Returns main's variables."""
    import time
    from concurrent.futures import ThreadPoolExecutor

    def _par(thunks):
        t0 = time.perf_counter()
        with ThreadPoolExecutor(len(thunks)) as ex:
            out = [f.result() for f in [ex.submit(t) for t in thunks]]
        rt.trace.append({"op": "parallel", "branches": len(thunks), "wall_s": time.perf_counter() - t0})
        return out

    src = compile_program(rt.p)
    ns = {"_rt": rt, "_F": FUNCS, "_div": div, "_par": _par}
    exec(compile(src, "<spatialq-compiled>", "exec"), ns)      # source generated by this module, never user-supplied Python
    return ns["_main"]()
