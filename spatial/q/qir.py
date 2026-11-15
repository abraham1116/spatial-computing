"""QIR export (base profile) for static SQIR circuits.

Gates outside the common QIS set are lowered first (exact up to a global phase):
  sx -> rx(pi/2)      p(t) -> rz(t)
  cp(t) a,b  -> rz(t/2) a; cx a,b; rz(-t/2) b; cx a,b; rz(t/2) b
  crz(t) c,t -> rz(t/2) t; cx c,t; rz(-t/2) t; cx c,t
Dynamic circuits (mid-circuit measurement, feed-forward) need the adaptive profile and
are refused rather than exported incorrectly.
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
    """Rewrite the circuit with gates of the QIS set only."""
    out: list[Op] = []
    for o in c.ops:
        if o.name in ("measure", "reset") or o.cond:
            raise QirExportError("dynamic circuits are not supported by the base-profile exporter")
        if o.name == "sx":
            out.append(Op("rx", o.qubits, (math.pi / 2,)))
        elif o.name == "p":
            out.append(Op("rz", o.qubits, o.params))
        elif o.name == "cp":
            (t,), (a, b) = o.params, o.qubits
            out += [Op("rz", (a,), (t / 2,)), Op("cx", (a, b)), Op("rz", (b,), (-t / 2,)),
                    Op("cx", (a, b)), Op("rz", (b,), (t / 2,))]
        elif o.name == "crz":
            (t,), (a, b) = o.params, o.qubits
            out += [Op("rz", (b,), (t / 2,)), Op("cx", (a, b)), Op("rz", (b,), (-t / 2,)), Op("cx", (a, b))]
        elif o.name in _QIS:
            out.append(o)
        else:
            raise QirExportError(f"gate {o.name} has no QIR lowering")
    return Circuit(c.name, c.n_qubits, 0, out)


def _q(i: int) -> str:
    return "ptr null" if i == 0 else f"ptr inttoptr (i64 {i} to ptr)"


def _dbl(x: float) -> str:
    return "double 0x" + struct.pack(">d", float(x)).hex().upper()     # exact IEEE-754 literal


def to_qir(c: Circuit) -> str:
    """LLVM IR text (opaque pointers), QIR base profile: gates, then measure every qubit."""
    low = lower(c)
    body, decls = [], set()
    for o in low.ops:
        fn = f"__quantum__qis__{_QIS[o.name]}__body"
        args = [_dbl(p) for p in o.params] + [_q(q) for q in o.qubits]
        body.append(f"  call void @{fn}({', '.join(args)})")
        decls.add(f"declare void @{fn}({', '.join(['double'] * len(o.params) + ['ptr'] * len(o.qubits))})")
    n = c.n_qubits
    for i in range(n):
        body.append(f"  call void @__quantum__qis__mz__body({_q(i)}, {_q(i)})")
    body.append(f"  call void @__quantum__rt__array_record_output(i64 {n}, ptr null)")
    for i in range(n):
        body.append(f"  call void @__quantum__rt__result_record_output({_q(i)}, ptr null)")
    decls |= {"declare void @__quantum__qis__mz__body(ptr, ptr writeonly) #1",
              "declare void @__quantum__rt__array_record_output(i64, ptr)",
              "declare void @__quantum__rt__result_record_output(ptr, ptr)"}
    return "\n".join([
        f"; SPATIAL Q kernel '{c.name}' exported to QIR (base profile)",
        "define void @main() #0 {", "entry:", *body, "  ret void", "}", "", *sorted(decls), "",
        f'attributes #0 = {{ "entry_point" "output_labeling_schema" "qir_profiles"="base_profile" '
        f'"required_num_qubits"="{n}" "required_num_results"="{n}" }}',
        'attributes #1 = { "irreversible" }', "",
        "!llvm.module.flags = !{!0, !1, !2, !3}",
        '!0 = !{i32 1, !"qir_major_version", i32 1}',
        '!1 = !{i32 7, !"qir_minor_version", i32 0}',
        '!2 = !{i32 1, !"dynamic_qubit_management", i1 false}',
        '!3 = !{i32 1, !"dynamic_result_management", i1 false}', ""])
