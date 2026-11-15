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

    def sample(self, c, shots, seed=None, noise: float = 0.0):
        return sim.sample(c, shots, seed, noise=noise)

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


def _ibm_token() -> str | None:
    import os
    from pathlib import Path
    tok = os.environ.get("IBM_QUANTUM_TOKEN")
    if tok:
        return tok
    f = Path.home() / ".spatial" / "secrets.env"
    if f.exists():
        for line in f.read_text().splitlines():
            if line.startswith("IBM_QUANTUM_TOKEN="):
                return line.split("=", 1)[1].strip() or None
    return None


class QpuBackend(Backend):
    """Real quantum hardware through IBM Quantum (qiskit-ibm-runtime, SamplerV2).

    Needs: the `qiskit-ibm-runtime` package, a token in IBM_QUANTUM_TOKEN (or
    ~/.spatial/secrets.env) and an IBM Quantum instance on the account. When any of these is
    missing it raises BackendUnavailable with the real reason; it never falls back to a
    simulator. Jobs wait in the provider's queue: a call can block for a long time.
    """
    name = "qpu"
    kind = "qpu"

    def __init__(self):
        self.last_job: dict | None = None

    def _service(self):
        try:
            from qiskit_ibm_runtime import QiskitRuntimeService
        except ImportError:
            raise BackendUnavailable("qiskit-ibm-runtime is not installed (pip install qiskit-ibm-runtime)")
        tok = _ibm_token()
        if not tok:
            raise BackendUnavailable(
                "no QPU provider configured: set IBM_QUANTUM_TOKEN or add it to ~/.spatial/secrets.env. "
                "The circuit can be exported with to_qasm3() or to_qir().")
        try:
            return QiskitRuntimeService(channel="ibm_quantum_platform", token=tok)
        except Exception as e:
            raise BackendUnavailable(f"IBM Quantum refused the account: {type(e).__name__}: {str(e)[:200]}")

    def sample(self, c, shots, seed=None):
        from qiskit import transpile
        from qiskit_ibm_runtime import SamplerV2
        svc = self._service()
        try:
            backend = svc.least_busy(operational=True, simulator=False, min_num_qubits=c.n_qubits)
        except Exception as e:
            raise BackendUnavailable(f"no real backend available for {c.n_qubits} qubits: {str(e)[:200]}")
        qc = transpile(to_qiskit(c), backend, optimization_level=1)
        job = SamplerV2(mode=backend).run([qc], shots=shots)
        res = job.result()[0]
        counts = res.data.c.get_counts()
        self.last_job = {"backend": backend.name, "job_id": job.job_id(), "shots": shots,
                         "physical_qubits": backend.num_qubits}
        return {k: int(v) for k, v in counts.items()}


def get(name: str) -> Backend:
    table = {"statevector": StateVectorBackend, "aer": AerBackend, "qasm3": Qasm3Export, "qpu": QpuBackend}
    if name not in table:
        raise BackendUnavailable(f"unknown backend '{name}'")
    return table[name]()
