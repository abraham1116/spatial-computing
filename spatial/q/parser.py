"""SPATIAL Q recursive-descent parser. AST nodes are tuples: (kind, ..., line).

See docs/07_SPATIAL_Q_SPEC.md for the grammar.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .lexer import SQSyntaxError, Tok, lex

GATES = {  # name -> (n_params, n_qubits)
    "h": (0, 1), "x": (0, 1), "y": (0, 1), "z": (0, 1), "s": (0, 1), "sdg": (0, 1),
    "t": (0, 1), "tdg": (0, 1), "sx": (0, 1),
    "rx": (1, 1), "ry": (1, 1), "rz": (1, 1), "p": (1, 1),
    "cx": (0, 2), "cz": (0, 2), "swap": (0, 2), "cp": (1, 2), "crz": (1, 2),
    "ccx": (0, 3),
}


@dataclass
class Kernel:
    name: str
    params: list[str]
    body: list
    line: int


@dataclass
class TaskDef:
    name: str
    params: list[str]
    target: str        # cpu | worker | any
    body: list
    line: int


@dataclass
class Program:
    kernels: dict[str, Kernel] = field(default_factory=dict)
    tasks: dict[str, TaskDef] = field(default_factory=dict)
    main: list | None = None


class Parser:
    def __init__(self, src: str):
        self.t = lex(src)
        self.i = 0

    # ---- token helpers
    @property
    def cur(self) -> Tok:
        return self.t[self.i]

    def err(self, msg: str):
        raise SQSyntaxError(f"line {self.cur.line}:{self.cur.col}: {msg} (found {self.cur.val!r})")

    def at(self, kind: str, val=None) -> bool:
        return self.cur.kind == kind and (val is None or self.cur.val == val)

    def eat(self, kind: str, val=None) -> Tok:
        if not self.at(kind, val):
            self.err(f"expected {val or kind}")
        self.i += 1
        return self.t[self.i - 1]

    def opt(self, kind: str, val=None) -> bool:
        if self.at(kind, val):
            self.i += 1
            return True
        return False

    # ---- declarations
    def program(self) -> Program:
        p = Program()
        while not self.at("eof"):
            if self.at("kw", "quantum"):
                line = self.eat("kw").line
                name = self.eat("id").val
                params = self.params()
                p.kernels[name] = Kernel(name, params, self.block(True), line)
            elif self.at("kw", "task"):
                line = self.eat("kw").line
                name = self.eat("id").val
                params = self.params()
                target = self.eat("id").val if self.opt("kw", "on") else "cpu"
                if target not in ("cpu", "worker", "any"):
                    self.err("task target must be cpu, worker or any")
                p.tasks[name] = TaskDef(name, params, target, self.block(False), line)
            elif self.at("kw", "main"):
                self.eat("kw")
                if p.main is not None:
                    self.err("duplicate main")
                p.main = self.block(False)
            else:
                self.err("expected 'quantum', 'task' or 'main'")
        if p.main is None:
            raise SQSyntaxError("program has no main block")
        return p

    def params(self) -> list[str]:
        self.eat("op", "(")
        out = []
        while not self.at("op", ")"):
            out.append(self.eat("id").val)
            if self.opt("op", ":"):
                self.eat("id")           # type annotation: parsed, informative in v0
            if not self.opt("op", ","):
                break
        self.eat("op", ")")
        return out

    def block(self, q: bool) -> list:
        self.eat("op", "{")
        out = []
        while not self.at("op", "}"):
            out.append(self.stmt(q))
        self.eat("op", "}")
        return out

    # ---- statements
    def stmt(self, q: bool):
        c = self.cur
        if c.kind == "kw":
            if c.val == "qubit":
                if not q:
                    self.err("'qubit' is only allowed inside a quantum kernel")
                self.eat("kw")
                name = self.eat("id").val
                self.eat("op", "[")
                size = self.expr()
                self.eat("op", "]")
                self.eat("op", ";")
                return ("qubit", name, size, c.line)
            if c.val == "let":
                self.eat("kw")
                name = self.eat("id").val
                self.eat("op", "=")
                e = self.expr()
                self.eat("op", ";")
                return ("let", name, e, c.line)
            if c.val == "for":
                self.eat("kw")
                var = self.eat("id").val
                self.eat("kw", "in")
                lo = self.expr()
                self.eat("op", "..")
                hi = self.expr()
                return ("for", var, lo, hi, self.block(q), c.line)
            if c.val == "while":
                self.eat("kw")
                cond = self.expr()
                return ("while", cond, self.block(q), c.line)
            if c.val == "if":
                self.eat("kw")
                cond = self.expr()
                then = self.block(q)
                els = self.block(q) if self.opt("kw", "else") else []
                return ("if", cond, then, els, c.line)
            if c.val == "return":
                self.eat("kw")
                e = self.expr()
                self.eat("op", ";")
                return ("return", e, c.line)
            if c.val == "print":
                self.eat("kw")
                es = [self.expr()]
                while self.opt("op", ","):
                    es.append(self.expr())
                self.eat("op", ";")
                return ("print", es, c.line)
            if c.val == "parallel":
                if q:
                    self.err("'parallel' is not allowed inside a quantum kernel")
                self.eat("kw")
                return ("parallel", self.block(False), c.line)
            if c.val == "reset" and q:
                self.eat("kw")
                qa = self.qarg()
                self.eat("op", ";")
                return ("reset", qa, c.line)
        if q and c.kind == "id" and c.val in GATES:
            self.eat("id")
            params = []
            if self.opt("op", "("):
                while not self.at("op", ")"):
                    params.append(self.expr())
                    if not self.opt("op", ","):
                        break
                self.eat("op", ")")
            qargs = [self.qarg()]
            while self.opt("op", ","):
                qargs.append(self.qarg())
            self.eat("op", ";")
            np_, nq = GATES[c.val]
            if len(params) != np_:
                raise SQSyntaxError(f"line {c.line}: gate {c.val} takes {np_} parameter(s), got {len(params)}")
            if len(qargs) != nq:
                raise SQSyntaxError(f"line {c.line}: gate {c.val} acts on {nq} qubit(s), got {len(qargs)}")
            return ("gate", c.val, params, qargs, c.line)
        if c.kind == "id" and self.t[self.i + 1].kind == "op" and self.t[self.i + 1].val == "=":
            name = self.eat("id").val
            self.eat("op", "=")
            e = self.expr()
            self.eat("op", ";")
            return ("assign", name, e, c.line)
        e = self.expr()
        self.eat("op", ";")
        return ("expr", e, c.line)

    def qarg(self):
        name = self.eat("id").val
        idx = None
        if self.opt("op", "["):
            idx = self.expr()
            self.eat("op", "]")
        return (name, idx)

    # ---- expressions (precedence climbing)
    _BIN = [("or",), ("and",), ("==", "!=", "<", "<=", ">", ">="), ("+", "-"), ("*", "/", "%")]

    def expr(self, level: int = 0):
        if level == len(self._BIN):
            return self.unary()
        left = self.expr(level + 1)
        while self.cur.kind in ("op", "kw") and self.cur.val in self._BIN[level]:
            op = self.cur.val
            self.i += 1
            left = ("bin", op, left, self.expr(level + 1))
        return left

    def unary(self):
        if self.opt("op", "-"):
            return ("neg", self.unary())
        if self.opt("op", "!") or self.opt("kw", "not"):
            return ("not", self.unary())
        return self.postfix()

    def postfix(self):
        e = self.primary()
        while self.opt("op", "["):
            idx = self.expr()
            self.eat("op", "]")
            e = ("index", e, idx)
        return e

    def call_args(self) -> list:
        self.eat("op", "(")
        args = []
        while not self.at("op", ")"):
            args.append(self.expr())
            if not self.opt("op", ","):
                break
        self.eat("op", ")")
        return args

    def primary(self):
        c = self.cur
        if c.kind == "num":
            self.i += 1
            return ("num", c.val)
        if c.kind == "str":
            self.i += 1
            return ("str", c.val)
        if c.kind == "kw":
            if c.val in ("true", "false"):
                self.i += 1
                return ("num", c.val == "true")
            if c.val == "measure":
                self.i += 1
                return ("measure", self.qarg(), c.line)
            if c.val == "sample":
                self.i += 1
                name = self.eat("id").val
                args = self.call_args()
                shots = self.expr(3) if self.opt("kw", "shots") else ("num", 1024)
                backend = self.eat("id").val if self.opt("kw", "on") else "auto"
                return ("sample", name, args, shots, backend, c.line)
            if c.val == "expect":
                self.i += 1
                pauli = self.eat("str").val
                self.eat("kw", "of")
                name = self.eat("id").val
                args = self.call_args()
                backend = self.eat("id").val if self.opt("kw", "on") else "auto"
                return ("expect", pauli, name, args, backend, c.line)
            if c.val == "workload":
                self.i += 1
                self.eat("op", "(")
                wname = self.eat("str").val
                kwargs = {}
                while self.opt("op", ","):
                    k = self.eat("id").val
                    self.eat("op", "=")
                    kwargs[k] = self.expr()
                self.eat("op", ")")
                return ("workload", wname, kwargs, c.line)
        if c.kind == "id":
            self.i += 1
            if self.at("op", "("):
                return ("call", c.val, self.call_args(), c.line)
            return ("var", c.val, c.line)
        if self.opt("op", "("):
            e = self.expr()
            self.eat("op", ")")
            return e
        if self.opt("op", "["):
            items = []
            while not self.at("op", "]"):
                items.append(self.expr())
                if not self.opt("op", ","):
                    break
            self.eat("op", "]")
            return ("list", items)
        self.err("expected an expression")


def parse(src: str) -> Program:
    return Parser(src).program()
