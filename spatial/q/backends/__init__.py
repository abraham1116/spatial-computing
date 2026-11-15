"""SPATIAL Q backends. A backend either really executes a circuit or raises
BackendUnavailable with the reason; it never returns invented results."""
from __future__ import annotations

from ..ir import Circuit
from .. import sim


class BackendUnavailable(RuntimeError):
    pass


class Backend:
    name = "?"
    kind = "qsim"       # qsim | qpu | export

    def sample(self, c: Circuit, shots: int, seed: int | None = None) -> dict[str, int]:
        raise NotImplementedError

    def expectation(self, c: Circuit, pauli: str) -> float:
        raise BackendUnavailable(f"{self.name} does not provide exact expectation values")


class StateVectorBackend(Backend):
    """Built-in NumPy simulator."""
    name = "statevector"

    def sample(self, c, shots, seed=None):
        return sim.sample(c, shots, seed)

    def expectation(self, c, pauli):
        return sim.expectation(c, pauli)


def to_qiskit(c: Circuit, measure_all: bool = True):
    from qiskit import ClassicalRegister, QuantumCircuit, QuantumRegister
    q = QuantumRegister(c.n_qubits, "q")
    regs = [q]
    m = None
    if c.n_cbits:
        m = ClassicalRegister(c.n_cbits, "m")
        regs.append(m)
    qc = QuantumCircuit(*regs)

    def emit(o):
        if o.name == "measure":
            qc.measure(q[o.qubits[0]], m[o.cbit])
        elif o.name == "reset":
            qc.reset(q[o.qubits[0]])
        else:
            getattr(qc, o.name)(*o.params, *[q[i] for i in o.qubits])

    for o in c.ops:
        if o.cond:
            def nest(conds):
                if not conds:
                    emit(o)
                    return
                b, v = conds[0]
                with qc.if_test((m[b], v)):
                    nest(conds[1:])
            nest(list(o.cond))
        else:
            emit(o)
    if measure_all:
        cr = ClassicalRegister(c.n_qubits, "c")
        qc.add_register(cr)
        qc.measure(q, cr)
    return qc


class AerBackend(Backend):
    """Qiskit Aer simulator (independent implementation used as the reference)."""
    name = "aer"

    def __init__(self):
        try:
            from qiskit_aer import AerSimulator
        except Exception as e:
            raise BackendUnavailable(f"qiskit-aer not importable: {e}")
        self._sim = AerSimulator()

    def sample(self, c, shots, seed=None):
        qc = to_qiskit(c)
        res = self._sim.run(qc, shots=shots, seed_simulator=seed).result()
        counts: dict[str, int] = {}
        for k, v in res.get_counts().items():
            key = k.split()[0]          # registers print as "c m"; keep the final read-out
            counts[key] = counts.get(key, 0) + v
        return counts

    def expectation(self, c, pauli):
        from qiskit.quantum_info import Pauli, Statevector
        return float(Statevector(to_qiskit(c, measure_all=False)).expectation_value(Pauli(pauli)).real)


class Qasm3Export(Backend):
    """Not an executor: produces the OpenQASM 3 program a provider would receive."""
    name = "qasm3"
    kind = "export"

    def sample(self, c, shots, seed=None):
        raise BackendUnavailable("qasm3 is an export target; use Circuit.to_qasm3()")


class QpuBackend(Backend):
    """Real quantum hardware. No provider credentials are configured in this prototype, so
    this backend refuses to run instead of silently falling back to a simulator."""
    name = "qpu"
    kind = "qpu"

    def sample(self, c, shots, seed=None):
        raise BackendUnavailable(
            "no QPU provider configured (needs an account/API token with IBM Quantum, IonQ, "
            "Quantinuum, AWS Braket...). The circuit can be exported with to_qasm3().")


def get(name: str) -> Backend:
    table = {"statevector": StateVectorBackend, "aer": AerBackend, "qasm3": Qasm3Export, "qpu": QpuBackend}
    if name not in table:
        raise BackendUnavailable(f"unknown backend '{name}'")
    return table[name]()
