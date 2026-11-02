"""Optional toy Clifford/T accounting; not a quantum compiler or scheduler."""


def toy_gate_cost(
    gates: list[str], distance: int, distillation_qubits: int = 100, distillation_rounds: int = 10
) -> dict:
    cliffords = {"H", "S", "SDG", "X", "Y", "Z", "CX", "CZ", "SWAP"}
    if distance < 3 or distance % 2 == 0 or distillation_qubits <= 0 or distillation_rounds <= 0:
        raise ValueError("Invalid toy resource parameters")
    if any(gate not in cliffords | {"T", "TDG"} for gate in gates):
        raise ValueError("Only listed hand-written Clifford/T gate names are supported")
    t_count = sum(gate in {"T", "TDG"} for gate in gates)
    clifford_count = len(gates) - t_count
    patch = 2 * distance * distance - 1
    return {
        "T_gates": t_count,
        "Clifford_gates": clifford_count,
        "assumed_distance": distance,
        "toy_sequential_qubit_rounds": clifford_count * patch * distance
        + t_count * distillation_qubits * distillation_rounds,
        "assumptions": "Each Clifford costs one patch for d rounds; each T consumes an arbitrary 100-qubit/10-round factory product; no parallel scheduling, fidelity or real distillation protocol",
        "toy_only": True,
    }
