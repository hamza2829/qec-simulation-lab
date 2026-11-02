"""Simplified extrapolation from a fitted distance-suppression law."""

import math

import numpy as np


def block_error_estimate(
    distance: int, physical_p: float, a: float, suppression: float, reference_p: float
) -> float:
    if (
        distance < 3
        or distance % 2 == 0
        or not all(
            math.isfinite(value) and value > 0
            for value in (physical_p, a, suppression, reference_p)
        )
    ):
        raise ValueError("Use odd d>=3 and positive finite model parameters")
    effective_suppression = suppression * reference_p / physical_p
    return distance * a / effective_suppression ** ((distance + 1) / 2)


def required_distance(
    target: float,
    physical_p: float,
    a: float,
    suppression: float,
    reference_p: float,
    max_distance: int = 199,
) -> int | None:
    if not 0 < target < 1:
        raise ValueError("Target must be a probability between 0 and 1")
    block_error_estimate(3, physical_p, a, suppression, reference_p)  # Validate before dividing.
    if suppression * reference_p / physical_p <= 1:
        return None
    for distance in range(3, max_distance + 1, 2):
        if block_error_estimate(distance, physical_p, a, suppression, reference_p) <= target:
            return distance
    return None


def resource_table(fit: dict) -> list[dict]:
    rows = []
    for physical_p in (1e-3, 1e-4):
        for target in (1e-6, 1e-9):
            d = required_distance(
                target,
                physical_p,
                fit["A"],
                fit["suppression_factor_per_distance_plus_2"],
                fit["reference_p"],
            )
            bootstrap_distances = [
                required_distance(target, physical_p, a, suppression, fit["reference_p"])
                for a, suppression in fit["bootstrap_parameters"]
            ]
            valid = [value for value in bootstrap_distances if value is not None]
            rows.append(
                {
                    "physical_error_rate": physical_p,
                    "target_per_d_round_memory_block": target,
                    "distance": d,
                    "physical_qubits": 2 * d * d - 1 if d else None,
                    "rounds": d,
                    "qubit_rounds": (2 * d * d - 1) * d if d else None,
                    "predicted_block_error": block_error_estimate(
                        d,
                        physical_p,
                        fit["A"],
                        fit["suppression_factor_per_distance_plus_2"],
                        fit["reference_p"],
                    )
                    if d
                    else None,
                    "distance_bootstrap_ci95": np.quantile(valid, [0.025, 0.975], method="nearest")
                    .astype(int)
                    .tolist()
                    if valid
                    else None,
                    "bootstrap_unresolved_fraction": 1 - len(valid) / len(bootstrap_distances),
                    "beyond_fitted_distances": d is not None and d > max(fit["distances"]),
                    "simplified_estimate": True,
                }
            )
    return rows
