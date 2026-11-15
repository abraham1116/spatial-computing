"""Portable kernel language: write a per-pixel kernel ONCE in a small, typed subset of Python and run
it on the CPU (Numba), a Metal GPU (generated Metal Shading Language) or an NVIDIA GPU (generated
CUDA C, never compiled or run here).

This is not a translator of CUDA and uses nothing from NVIDIA: the source language is ours, the
back ends are generated from its AST. Same idea as Triton or SYCL at a much smaller scale.

Kernel shape:   def k(i: int, j: int, n: int, <params>) -> int      (i, j = row, column; n = grid size)
Params          annotated int or float; floats are float32, ints are 32-bit on every back end
                (the CPU wraps ints at each assignment, so it matches the GPU's overflow behaviour;
                intermediate values inside one expression are not wrapped before the assignment)
Statements      assignment, +=, while, if/else, for k in range(a), one final `return <expr>`
Expressions     + - * / % // (ints for % and //), comparisons, and/or/not, int(x), float(x),
                sqrt sin cos exp log floor abs min max
Output          the returned value, cast to uint32, stored at out[i, j] (it must be >= 0)
"""
from __future__ import annotations

import ast
import inspect
import textwrap
from dataclasses import dataclass, field

MATH_F = {"sqrt", "sin", "cos", "exp", "log", "floor"}
OTHER = {"abs", "min", "max", "int", "float"}


class KernelError(Exception):
    pass


@dataclass
class Kernel:
    name: str
    params: list                       # [(name, "int"|"float")] after i, j
    body: list                         # statements before the return
    ret: ast.expr
    types: dict = field(default_factory=dict)    # local variable -> "int" | "float"
    source: str = ""

    # ------------------------------------------------------------------ analysis
    def _err(self, node, msg):
        raise KernelError(f"{self.name}, line {getattr(node, 'lineno', '?')}: {msg}")

    def type_of(self, e: ast.expr, env: dict) -> str:
        if isinstance(e, ast.Constant):
            if isinstance(e.value, bool) or not isinstance(e.value, (int, float)):
                self._err(e, f"unsupported constant {e.value!r}")
            return "float" if isinstance(e.value, float) else "int"
        if isinstance(e, ast.Name):
            if e.id not in env:
                self._err(e, f"unknown name '{e.id}'")
            return env[e.id]
        if isinstance(e, ast.UnaryOp):
            if isinstance(e.op, ast.Not):
                return "int"
            if isinstance(e.op, (ast.USub, ast.UAdd)):
                return self.type_of(e.operand, env)
            self._err(e, "unsupported unary operator")
        if isinstance(e, ast.BinOp):
            a, b = self.type_of(e.left, env), self.type_of(e.right, env)
            if isinstance(e.op, ast.Div):
                return "float"
            if isinstance(e.op, (ast.Mod, ast.FloorDiv)):
                if a != "int" or b != "int":
                    self._err(e, "% and // are only defined for ints")
                return "int"
            if isinstance(e.op, (ast.Add, ast.Sub, ast.Mult)):
                return "float" if "float" in (a, b) else "int"
            self._err(e, "unsupported operator")
        if isinstance(e, ast.Compare):
            if len(e.ops) != 1 or not isinstance(e.ops[0], (ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Eq, ast.NotEq)):
                self._err(e, "only single comparisons with < <= > >= == != are supported")
            self.type_of(e.left, env)
            self.type_of(e.comparators[0], env)
            return "int"
        if isinstance(e, ast.BoolOp):
            for v in e.values:
                self.type_of(v, env)
            return "int"
        if isinstance(e, ast.Call):
            if not isinstance(e.func, ast.Name) or e.keywords:
                self._err(e, "only plain calls to built-in math functions are supported")
            f, args = e.func.id, [self.type_of(a, env) for a in e.args]
            if f in MATH_F:
                if len(args) != 1:
                    self._err(e, f"{f} takes one argument")
                return "float"
            if f in ("int", "float"):
                if len(args) != 1:
                    self._err(e, f"{f} takes one argument")
                return f
            if f == "abs":
                return args[0]
            if f in ("min", "max"):
                if len(args) != 2:
                    self._err(e, f"{f} takes two arguments")
                return "float" if "float" in args else "int"
            self._err(e, f"unknown function '{f}'")
        self._err(e, f"unsupported expression ({type(e).__name__})")

    RESERVED = {"out", "partial", "gid", "lid", "tgid", "ngroups", "blockIdx", "blockDim", "threadIdx", "gridDim", "total"}

    def _check_names(self, names) -> None:
        for nm in names:
            if nm in self.RESERVED or nm.startswith("_sp_") or nm.startswith("__"):
                raise KernelError(f"{self.name}: '{nm}' is reserved by the generated code; rename it")

    def analyse(self) -> None:
        self._check_names([p for p, _ in self.params])
        env = {"i": "int", "j": "int", "n": "int", **dict(self.params)}
        for _ in range(2):                                    # second pass: a variable later assigned a float becomes float
            self._walk(self.body, env)
        self.type_of(self.ret, env)
        self.types = {k: v for k, v in env.items() if k not in ("i", "j", "n") and k not in dict(self.params)}

    def _walk(self, stmts, env):
        for s in stmts:
            if isinstance(s, ast.Assign):
                if len(s.targets) != 1 or not isinstance(s.targets[0], ast.Name):
                    self._err(s, "assign to a single name")
                name, t = s.targets[0].id, self.type_of(s.value, env)
                self._check_names([name])
                if name in ("i", "j", "n") or name in dict(self.params):
                    self._err(s, f"'{name}' is an input and cannot be assigned")
                env[name] = "float" if "float" in (env.get(name), t) else t
            elif isinstance(s, ast.AugAssign):
                if not isinstance(s.target, ast.Name) or s.target.id not in env or not isinstance(s.op, (ast.Add, ast.Sub, ast.Mult)):
                    self._err(s, "+=, -=, *= on an existing variable only")
                if s.target.id in ("i", "j", "n") or s.target.id in dict(self.params):
                    self._err(s, f"'{s.target.id}' is an input and cannot be assigned")
                t = self.type_of(s.value, env)
                if t == "float":
                    env[s.target.id] = "float"
            elif isinstance(s, ast.While):
                self.type_of(s.test, env)
                self._walk(s.body, env)
                if s.orelse:
                    self._err(s, "while/else is not supported")
            elif isinstance(s, ast.If):
                self.type_of(s.test, env)
                self._walk(s.body, env)
                self._walk(s.orelse, env)
            elif isinstance(s, ast.For):
                if not (isinstance(s.target, ast.Name) and isinstance(s.iter, ast.Call) and isinstance(s.iter.func, ast.Name)
                        and s.iter.func.id == "range" and len(s.iter.args) == 1):
                    self._err(s, "only `for k in range(a)` is supported")
                if self.type_of(s.iter.args[0], env) != "int":
                    self._err(s, "range bound must be an int")
                env[s.target.id] = "int"
                self._walk(s.body, env)
            elif isinstance(s, ast.Return):
                self._err(s, "a single `return` is allowed, and it must be the last statement")
            else:
                self._err(s, f"unsupported statement ({type(s).__name__})")

    # ------------------------------------------------------------------ code generation
    def _expr_c(self, e, env, cuda: bool) -> str:
        t = lambda x: self.type_of(x, env)
        f32 = (lambda s: s) if not cuda else (lambda s: s)
        rec = lambda x: self._expr_c(x, env, cuda)
        tof = lambda x: rec(x) if t(x) == "float" else f"((float)({rec(x)}))"
        if isinstance(e, ast.Constant):
            return repr(float(e.value)) + "f" if isinstance(e.value, float) else str(e.value)
        if isinstance(e, ast.Name):
            return e.id
        if isinstance(e, ast.UnaryOp):
            return f"(!{rec(e.operand)})" if isinstance(e.op, ast.Not) else f"(-{rec(e.operand)})" if isinstance(e.op, ast.USub) else rec(e.operand)
        if isinstance(e, ast.BinOp):
            a, b = e.left, e.right
            if isinstance(e.op, ast.Div):
                return f"({tof(a)} / {tof(b)})"
            if isinstance(e.op, ast.FloorDiv):
                return f"({rec(a)} / {rec(b)})"                 # ints: C division truncates; Python floors (differs for negatives)
            op = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Mod: "%"}[type(e.op)]
            if t(e) == "float":
                return f"({tof(a)} {op} {tof(b)})"
            return f"({rec(a)} {op} {rec(b)})"
        if isinstance(e, ast.Compare):
            op = {ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=", ast.Eq: "==", ast.NotEq: "!="}[type(e.ops[0])]
            a, b = e.left, e.comparators[0]
            if "float" in (t(a), t(b)):
                return f"({tof(a)} {op} {tof(b)})"
            return f"({rec(a)} {op} {rec(b)})"
        if isinstance(e, ast.BoolOp):
            return "(" + (" && " if isinstance(e.op, ast.And) else " || ").join(rec(v) for v in e.values) + ")"
        if isinstance(e, ast.Call):
            fn, args = e.func.id, e.args
            if fn in MATH_F:
                return f"{fn}{'f' if cuda else ''}({tof(args[0])})"
            if fn == "int":
                return f"((int)({rec(args[0])}))"
            if fn == "float":
                return f"((float)({rec(args[0])}))"
            if fn == "abs":
                return (f"fabs{'f' if cuda else ''}({rec(args[0])})" if t(args[0]) == "float" else f"abs({rec(args[0])})")
            if fn in ("min", "max"):
                if t(e) == "float":
                    return (f"f{fn}f(" if cuda else f"{fn}(") + f"{tof(args[0])}, {tof(args[1])})"
                return f"{fn}({rec(args[0])}, {rec(args[1])})"
        raise KernelError("internal: unsupported expression in code generation")

    def _stmts_c(self, stmts, env, cuda: bool, ind: str) -> list[str]:
        out = []
        for s in stmts:
            if isinstance(s, ast.Assign):
                out.append(f"{ind}{s.targets[0].id} = {self._cast_assign(s.targets[0].id, s.value, env, cuda)};")
            elif isinstance(s, ast.AugAssign):
                op = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*"}[type(s.op)]
                out.append(f"{ind}{s.target.id} = {s.target.id} {op} {self._cast_assign(s.target.id, s.value, env, cuda)};")
            elif isinstance(s, ast.While):
                out.append(f"{ind}while ({self._expr_c(s.test, env, cuda)}) {{")
                out += self._stmts_c(s.body, env, cuda, ind + "    ")
                out.append(f"{ind}}}")
            elif isinstance(s, ast.If):
                out.append(f"{ind}if ({self._expr_c(s.test, env, cuda)}) {{")
                out += self._stmts_c(s.body, env, cuda, ind + "    ")
                if s.orelse:
                    out.append(f"{ind}}} else {{")
                    out += self._stmts_c(s.orelse, env, cuda, ind + "    ")
                out.append(f"{ind}}}")
            elif isinstance(s, ast.For):
                v = s.target.id
                out.append(f"{ind}for ({v} = 0; {v} < {self._expr_c(s.iter.args[0], env, cuda)}; {v}++) {{")
                out += self._stmts_c(s.body, env, cuda, ind + "    ")
                out.append(f"{ind}}}")
        return out

    def _cast_assign(self, name, value, env, cuda):
        e = self._expr_c(value, env, cuda)
        return e if self.type_of(value, env) == env[name] else f"(({'float' if env[name] == 'float' else 'int'})({e}))"

    def _env(self):
        return {"i": "int", "j": "int", "n": "int", **dict(self.params), **self.types}

    def to_c(self, cuda: bool, reduce: bool = False, hip: bool = False) -> str:
        env = self._env()
        decls = [f"    {t} {v};" for v, t in self.types.items()]
        body = "\n".join(self._stmts_c(self.body, env, cuda, "        " if reduce else "    "))
        ret = f"(unsigned int)({self._expr_c(self.ret, env, cuda)})"
        if cuda:
            name = self.name + ("_sum" if reduce else "")
            first = "unsigned long long *partial" if reduce else "unsigned int *out"
            sig = ", ".join([first, "int n"] + [f"{t} {p}" for p, t in self.params])
            head = f'extern "C" __global__ void {name}({sig}) {{\n    int j = blockIdx.x * blockDim.x + threadIdx.x;\n    int i = blockIdx.y * blockDim.y + threadIdx.y;'
            pre = "#include <hip/hip_runtime.h>\n" if hip else ""
        else:
            name = self.name + ("_sum" if reduce else "")
            args = ["device ulong *partial [[buffer(0)]]" if reduce else "device uint *out [[buffer(0)]]", "constant int &n [[buffer(1)]]"]
            args += [f"constant {t} &{p} [[buffer({k + 2})]]" for k, (p, t) in enumerate(self.params)]
            args.append("uint2 gid [[thread_position_in_grid]]")
            if reduce:
                args += ["uint lid [[thread_index_in_threadgroup]]", "uint2 tgid [[threadgroup_position_in_grid]]", "uint2 ngroups [[threadgroups_per_grid]]"]
            head = f"kernel void {name}({', '.join(args)}) {{\n    int j = (int)gid.x;\n    int i = (int)gid.y;"
            pre = "#include <metal_stdlib>\nusing namespace metal;\n"
        d = "\n".join(decls) + ("\n" if decls else "")
        if not reduce:
            return (f"{pre}{head}\n    if (i >= n || j >= n) return;\n" + d + (body + "\n" if body else "") + f"    out[i * n + j] = {ret};\n}}\n")
        # Reduction: 16 x 16 threads per block share a 256-entry array and add pairwise; every thread must reach the
        # barriers, so there is no early return. One partial sum per block; the host adds the partials.
        ull = "unsigned long long" if cuda else "ulong"
        shared = f"    __shared__ {ull} _sp_sh[256];" if cuda else f"    threadgroup {ull} _sp_sh[256];"
        t = "int _sp_t = threadIdx.y * blockDim.x + threadIdx.x;" if cuda else "int _sp_t = (int)lid;"
        bar = "__syncthreads();" if cuda else "threadgroup_barrier(mem_flags::mem_threadgroup);"
        gid = "blockIdx.y * gridDim.x + blockIdx.x" if cuda else "tgid.y * ngroups.x + tgid.x"
        return (f"{pre}{head}\n{shared}\n    {t}\n" + d + f"    {ull} _sp_v = 0;\n    if (i < n && j < n) {{\n" + (body + "\n" if body else "")
                + f"        _sp_v = ({ull}){ret};\n    }}\n    _sp_sh[_sp_t] = _sp_v;\n    {bar}\n    for (int _sp_s = 128; _sp_s > 0; _sp_s >>= 1) {{\n"
                f"        if (_sp_t < _sp_s) _sp_sh[_sp_t] += _sp_sh[_sp_t + _sp_s];\n        {bar}\n    }}\n    if (_sp_t == 0) partial[{gid}] = _sp_sh[0];\n}}\n")

    def to_metal(self, reduce: bool = False) -> str:
        return self.to_c(cuda=False, reduce=reduce)

    def to_cuda_c(self, reduce: bool = False) -> str:
        """CUDA C source for NVRTC/nvcc. Generated, never compiled or run: no NVIDIA toolchain here."""
        return self.to_c(cuda=True, reduce=reduce)

    def to_hip(self, reduce: bool = False) -> str:
        """HIP source for AMD GPUs (hipcc). Same syntax tree, the CUDA-style kernel dialect that HIP accepts.
        Generated only: no AMD GPU, no ROCm here, so it has never been compiled or run."""
        return self.to_c(cuda=True, reduce=reduce, hip=True)

    def _expr_py(self, e, env) -> str:
        t = lambda x: self.type_of(x, env)
        rec = lambda x: self._expr_py(x, env)
        tof = lambda x: rec(x) if t(x) == "float" else f"np.float32({rec(x)})"
        if isinstance(e, ast.Constant):
            return f"np.float32({e.value!r})" if isinstance(e.value, float) else str(e.value)
        if isinstance(e, ast.Name):
            return e.id
        if isinstance(e, ast.UnaryOp):
            return f"(not {rec(e.operand)})" if isinstance(e.op, ast.Not) else f"(-{rec(e.operand)})" if isinstance(e.op, ast.USub) else rec(e.operand)
        if isinstance(e, ast.BinOp):
            a, b = e.left, e.right
            if isinstance(e.op, ast.Div):
                return f"({tof(a)} / {tof(b)})"
            if isinstance(e.op, ast.FloorDiv):
                return f"int({rec(a)} / {rec(b)})"             # truncating, to match the C back ends
            if isinstance(e.op, ast.Mod):
                return f"_cmod({rec(a)}, {rec(b)})"
            op = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*"}[type(e.op)]
            return f"({tof(a)} {op} {tof(b)})" if t(e) == "float" else f"({rec(a)} {op} {rec(b)})"
        if isinstance(e, ast.Compare):
            op = {ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=", ast.Eq: "==", ast.NotEq: "!="}[type(e.ops[0])]
            a, b = e.left, e.comparators[0]
            return f"({tof(a)} {op} {tof(b)})" if "float" in (t(a), t(b)) else f"({rec(a)} {op} {rec(b)})"
        if isinstance(e, ast.BoolOp):
            return "(" + (" and " if isinstance(e.op, ast.And) else " or ").join(rec(v) for v in e.values) + ")"
        fn, args = e.func.id, e.args
        if fn in MATH_F:
            return f"np.{fn}({tof(args[0])})"
        if fn == "int":
            return f"_cint({rec(args[0])})"
        if fn == "float":
            return f"np.float32({rec(args[0])})"
        if fn == "abs":
            return f"abs({rec(args[0])})"
        if t(e) == "float":
            return f"{fn}({tof(args[0])}, {tof(args[1])})"
        return f"{fn}({rec(args[0])}, {rec(args[1])})"

    def _stmts_py(self, stmts, env, ind) -> list[str]:
        out = []
        cast = lambda name, v: (lambda e: e if self.type_of(v, env) == env[name] else (f"np.float32({e})" if env[name] == "float" else f"_w32({e})"))(self._expr_py(v, env))
        for s in stmts:
            if isinstance(s, ast.Assign):
                t0, e0 = s.targets[0].id, cast(s.targets[0].id, s.value)
                out.append(f"{ind}{t0} = " + (e0 if env[t0] == "float" or e0.startswith("_w32(") else f"_w32({e0})"))
            elif isinstance(s, ast.AugAssign):
                op = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*"}[type(s.op)]
                v = s.target.id
                rhs = cast(v, s.value)
                out.append(f"{ind}{v} = {'np.float32(' + v + ' ' + op + ' ' + rhs + ')' if env[v] == 'float' else '_w32(' + v + ' ' + op + ' ' + rhs + ')'}")
            elif isinstance(s, ast.While):
                out.append(f"{ind}while {self._expr_py(s.test, env)}:")
                out += self._stmts_py(s.body, env, ind + "    ") or [ind + "    pass"]
            elif isinstance(s, ast.If):
                out.append(f"{ind}if {self._expr_py(s.test, env)}:")
                out += self._stmts_py(s.body, env, ind + "    ") or [ind + "    pass"]
                if s.orelse:
                    out.append(f"{ind}else:")
                    out += self._stmts_py(s.orelse, env, ind + "    ")
            elif isinstance(s, ast.For):
                out.append(f"{ind}for {s.target.id} in range({self._expr_py(s.iter.args[0], env)}):")
                out += self._stmts_py(s.body, env, ind + "    ") or [ind + "    pass"]
        return out

    def to_python(self, reduce: bool = False) -> str:
        """Numba-compilable source with explicit float32 arithmetic (matches the GPU back ends)."""
        env = self._env()
        inits = [f"        {v} = np.float32(0.0)" if t == "float" else f"        {v} = 0" for v, t in self.types.items()]
        sig = ", ".join(([] if reduce else ["out"]) + ["n"] + [p for p, _ in self.params])
        body = "\n".join(self._stmts_py(self.body, env, "        "))
        ret = self._expr_py(self.ret, env)
        ret = f"_w32({ret}) & 0xFFFFFFFF" if self.type_of(self.ret, env) == "int" else ret
        if reduce:
            return ("def _kernel(" + sig + "):\n    total = np.uint64(0)\n    for i in prange(n):\n      for j in range(n):\n" + "\n".join(inits)
                    + ("\n" if inits else "") + (body + "\n" if body else "") + f"        total += np.uint64({ret})\n    return total\n")
        return ("def _kernel(" + sig + "):\n    for i in prange(n):\n      for j in range(n):\n" + "\n".join(inits)
                + ("\n" if inits else "") + (body + "\n" if body else "") + f"        out[i, j] = {ret}\n")

    # ------------------------------------------------------------------ execution
    def reduce(self, device: str, n: int, **params) -> int:
        """Sum of the kernel's output over the whole n x n grid, as an int (uint64 accumulation). On Metal this
        uses threadgroup shared memory and barriers; on the CPU a Numba parallel reduction."""
        for p, t in self.params:
            if p not in params:
                raise KernelError(f"{self.name}: missing parameter '{p}'")
        if device == "cpu":
            return self._run_cpu(n, params, reduce=True)
        if device == "metal":
            from ..fabric import metal
            return metal.run_kernel(self, n, params, reduce=True)
        if device in ("cuda", "hip"):
            raise KernelError(f"the {device} back end only generates source; it has never been run on that hardware")
        raise KernelError(f"unknown device '{device}'")

    def run(self, device: str, n: int, **params):
        """Run on `device` ("cpu" or "metal"); returns an (n, n) uint32 array."""
        import numpy as np
        for p, t in self.params:
            if p not in params:
                raise KernelError(f"{self.name}: missing parameter '{p}'")
        if device == "cpu":
            return self._run_cpu(n, params)
        if device == "metal":
            from ..fabric import metal
            return metal.run_kernel(self, n, params)
        if device == "cuda":
            raise KernelError("the CUDA back end only generates source (to_cuda_c); it has never been run on NVIDIA hardware")
        raise KernelError(f"unknown device '{device}'")

    def _run_cpu(self, n, params, reduce: bool = False):
        import numpy as np
        from numba import njit, prange
        attr = "_cpu_sum" if reduce else "_cpu"
        if not hasattr(self, attr):
            ns = {"np": np, "prange": prange, "_cint": njit(_cint), "_cmod": njit(_cmod), "_w32": njit(_w32)}
            exec(compile(self.to_python(reduce=reduce), f"<kernel {self.name}>", "exec"), ns)      # generated from OUR restricted AST only
            setattr(self, attr, njit(parallel=True)(ns["_kernel"]))
        if reduce:
            return int(getattr(self, attr)(n, *[np.float32(params[p]) if t == "float" else int(params[p]) for p, t in self.params]))
        out = np.zeros((n, n), dtype=np.uint32)
        args = [np.float32(params[p]) if t == "float" else int(params[p]) for p, t in self.params]
        self._cpu(out, n, *args)
        return out


def _cint(x):
    return int(x)


def _w32(x):                          # ints are 32-bit on the GPU back ends: wrap the same way on the CPU
    return ((x + 2147483648) & 4294967295) - 2147483648


def _cmod(a, b):                      # C semantics: the sign follows the dividend
    r = abs(a) % abs(b)
    return -r if a < 0 else r


def kernel(fn) -> Kernel:
    """Decorator: parse and type-check `fn` as a portable kernel."""
    src = textwrap.dedent(inspect.getsource(fn))
    tree = ast.parse(src).body[0]
    name = tree.name
    a = [x.arg for x in tree.args.args]
    if a[:3] != ["i", "j", "n"]:
        raise KernelError(f"{name}: the first three parameters must be i, j, n")
    params = []
    for x in tree.args.args[3:]:
        ann = x.annotation.id if isinstance(x.annotation, ast.Name) else None
        if ann not in ("int", "float"):
            raise KernelError(f"{name}: parameter '{x.arg}' needs an `int` or `float` annotation")
        params.append((x.arg, ann))
    body = [s for s in tree.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]   # skip the docstring
    if not body or not isinstance(body[-1], ast.Return):
        raise KernelError(f"{name}: the kernel must end with a single `return <expr>`")
    k = Kernel(name, params, body[:-1], body[-1].value, source=src)
    k.analyse()
    return k
