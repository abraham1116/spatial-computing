"""QIR export for SQIR circuits (base and adaptive profiles).

Gates outside the common QIS set are lowered first (exact up to a global phase):
  sx -> rx(pi/2)      p(t) -> rz(t)
  cp(t) a,b  -> rz(t/2) a; cx a,b; rz(-t/2) b; cx a,b; rz(t/2) b
  crz(t) c,t -> rz(t/2) t; cx c,t; rz(-t/2) t; cx c,t
Static circuits are exported in the base profile; circuits with mid-circuit measurement
or feed-forward in the adaptive profile.
"""
from __future__ import annotations

import math
import struct

from .ir import Circuit, Op

_QIS = {"h": "h", "x": "x", "y": "y", "z": "z", "s": "s", "sdg": "s__adj", "t": "t", "tdg": "t__adj",
        "rx": "rx", "ry": "ry", "rz": "rz", "cx": "cnot", "cz": "cz", "swap": "swap", "ccx": "ccx"}


class QirExportError(Exception):
    pass


def lower(c: Circuit) -> Circuit:
    """Rewrite the circuit with gates of the QIS set only (measure/reset/conditions kept)."""
    out: list[Op] = []
    for o in c.ops:
        k = o.cond
        if o.name in ("measure", "reset"):
            out.append(o)
        elif o.name == "sx":
            out.append(Op("rx", o.qubits, (math.pi / 2,), cond=k))
        elif o.name == "p":
            out.append(Op("rz", o.qubits, o.params, cond=k))
        elif o.name == "cp":
            (t,), (a, b) = o.params, o.qubits
            out += [Op("rz", (a,), (t / 2,), cond=k), Op("cx", (a, b), cond=k), Op("rz", (b,), (-t / 2,), cond=k),
                    Op("cx", (a, b), cond=k), Op("rz", (b,), (t / 2,), cond=k)]
        elif o.name == "crz":
            (t,), (a, b) = o.params, o.qubits
            out += [Op("rz", (b,), (t / 2,), cond=k), Op("cx", (a, b), cond=k), Op("rz", (b,), (-t / 2,), cond=k),
                    Op("cx", (a, b), cond=k)]
        elif o.name in _QIS:
            out.append(o)
        else:
            raise QirExportError(f"gate {o.name} has no QIR lowering")
    return Circuit(c.name, c.n_qubits, c.n_cbits, out)


def _q(i: int) -> str:
    return "ptr null" if i == 0 else f"ptr inttoptr (i64 {i} to ptr)"


def _dbl(x: float) -> str:
    return "double 0x" + struct.pack(">d", float(x)).hex().upper()     # exact IEEE-754 literal


def to_qir(c: Circuit) -> str:
    """LLVM IR text (opaque pointers). Static circuits use the QIR base profile; circuits with
    mid-circuit measurement or feed-forward use the adaptive profile (results read back with
    read_result and conditional branches). Every qubit is measured at the end."""
    low = lower(c)
    dynamic = any(o.name in ("measure", "reset") or o.cond for o in low.ops)
    body, decls, tmp, blk = [], set(), 0, 0
    n, m = c.n_qubits, c.n_cbits

    def gate(o: Op) -> str:
        if o.name == "measure":
            decls.add("declare void @__quantum__qis__mz__body(ptr, ptr writeonly) #1")
            return f"  call void @__quantum__qis__mz__body({_q(o.qubits[0])}, {_q(o.cbit)})"
        if o.name == "reset":
            decls.add("declare void @__quantum__qis__reset__body(ptr) #1")
            return f"  call void @__quantum__qis__reset__body({_q(o.qubits[0])})"
        fn = f"__quantum__qis__{_QIS[o.name]}__body"
        decls.add(f"declare void @{fn}({', '.join(['double'] * len(o.params) + ['ptr'] * len(o.qubits))})")
        return f"  call void @{fn}({', '.join([_dbl(p) for p in o.params] + [_q(q) for q in o.qubits])})"

    i = 0
    while i < len(low.ops):
        o = low.ops[i]
        if not o.cond:
            body.append(gate(o))
            i += 1
            continue
        j = i                                   # consecutive ops under the same condition share one branch
        while j < len(low.ops) and low.ops[j].cond == o.cond:
            j += 1
        decls.add("declare i1 @__quantum__qis__read_result__body(ptr)")
        acc = None
        for bit, val in o.cond:
            body.append(f"  %t{tmp} = call i1 @__quantum__qis__read_result__body({_q(bit)})")
            cur = f"%t{tmp}"
            tmp += 1
            if val == 0:
                body.append(f"  %t{tmp} = xor i1 {cur}, true")
                cur = f"%t{tmp}"
                tmp += 1
            if acc is not None:
                body.append(f"  %t{tmp} = and i1 {acc}, {cur}")
                cur = f"%t{tmp}"
                tmp += 1
            acc = cur
        body += [f"  br i1 {acc}, label %then{blk}, label %cont{blk}", f"then{blk}:"]
        body += [gate(x) for x in low.ops[i:j]]
        body += [f"  br label %cont{blk}", f"cont{blk}:"]
        blk += 1
        i = j
    for q in range(n):                          # final read-out uses result ids after the mid-circuit ones
        body.append(f"  call void @__quantum__qis__mz__body({_q(q)}, {_q(m + q)})")
    body.append(f"  call void @__quantum__rt__array_record_output(i64 {n}, ptr null)")
    for q in range(n):
        body.append(f"  call void @__quantum__rt__result_record_output({_q(m + q)}, ptr null)")
    decls |= {"declare void @__quantum__qis__mz__body(ptr, ptr writeonly) #1",
              "declare void @__quantum__rt__array_record_output(i64, ptr)",
              "declare void @__quantum__rt__result_record_output(ptr, ptr)"}
    profile = "adaptive_profile" if dynamic else "base_profile"
    return "\n".join([
        f"; SPATIAL Q kernel '{c.name}' exported to QIR ({profile})",
        "define void @main() #0 {", "entry:", *body, "  ret void", "}", "", *sorted(decls), "",
        f'attributes #0 = {{ "entry_point" "output_labeling_schema" "qir_profiles"="{profile}" '
        f'"required_num_qubits"="{n}" "required_num_results"="{m + n}" }}',
        'attributes #1 = { "irreversible" }', "",
        "!llvm.module.flags = !{!0, !1, !2, !3}",
        '!0 = !{i32 1, !"qir_major_version", i32 1}',
        '!1 = !{i32 7, !"qir_minor_version", i32 0}',
        '!2 = !{i32 1, !"dynamic_qubit_management", i1 false}',
        '!3 = !{i32 1, !"dynamic_result_management", i1 false}', ""])
