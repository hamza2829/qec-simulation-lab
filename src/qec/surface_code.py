"""Stim memory experiments; the decoder predicts a logical observable flip."""

import time

import numpy as np
import pymatching
import stim

from qec.statistics import rate_record


def memory_circuit(distance: int, p: float, rounds: int | None = None) -> stim.Circuit:
    if type(distance) is not int or distance < 3 or distance % 2 == 0 or not 0 <= p <= 0.1:
        raise ValueError("Use odd d>=3 and 0<=p<=0.1")
    rounds = distance if rounds is None else rounds
    if rounds < 1:
        raise ValueError("Need at least one round")
    return stim.Circuit.generated(
        "surface_code:rotated_memory_z",
        distance=distance,
        rounds=rounds,
        after_clifford_depolarization=p,
        before_round_data_depolarization=p,
        before_measure_flip_probability=p,
        after_reset_flip_probability=p,
    )


def matching_decoder(circuit: stim.Circuit) -> pymatching.Matching:
    return pymatching.Matching.from_detector_error_model(
        circuit.detector_error_model(decompose_errors=True)
    )


def sample_memory(circuit: stim.Circuit, shots: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    if shots <= 0:
        raise ValueError("Need positive shots")
    detectors, observables = circuit.compile_detector_sampler(seed=seed).sample(
        shots, separate_observables=True
    )
    if observables.shape[1] != 1:
        raise ValueError("This lab expects one logical observable")
    return detectors.astype(np.uint8), observables[:, 0].astype(np.uint8)


def experiment(distance: int, p: float, shots: int, seed: int, rounds: int | None = None) -> dict:
    start = time.perf_counter()
    rounds = distance if rounds is None else rounds
    circuit = memory_circuit(distance, p, rounds)
    detectors, actual = sample_memory(circuit, shots, seed)
    predicted = matching_decoder(circuit).decode_batch(detectors)[:, 0]
    errors = int(np.count_nonzero(predicted != actual))
    return {
        "distance": distance,
        "physical_error_rate": p,
        "rounds": rounds,
        "seed": seed,
        "task": "surface_code:rotated_memory_z",
        "noise": {
            "after_clifford_depolarization": p,
            "before_round_data_depolarization": p,
            "before_measure_flip_probability": p,
            "after_reset_flip_probability": p,
        },
        "active_qubits": len(circuit.get_final_qubit_coordinates()),
        "detectors": circuit.num_detectors,
        "num_observables": circuit.num_observables,
        "decoder": "PyMatching default uncorrelated MWPM; decomposed DEM",
        "elapsed_seconds": time.perf_counter() - start,
        **rate_record(errors, shots),
        "per_round_small_error_proxy": errors / shots / rounds,
    }


def crossing_roots(probabilities: np.ndarray, first: np.ndarray, second: np.ndarray) -> list[float]:
    """All nontrivial sign-change roots, linearly interpolated in physical p."""
    x, a, b = map(lambda values: np.asarray(values, dtype=float), (probabilities, first, second))
    if (
        x.ndim != 1
        or len(x) < 2
        or a.shape != x.shape
        or b.shape != x.shape
        or np.any(np.diff(x) <= 0)
    ):
        raise ValueError("Need equal-length curves on a strictly increasing grid")
    difference = a - b
    roots = []
    nonzero = np.flatnonzero(difference)
    for left, right in zip(nonzero[:-1], nonzero[1:], strict=True):
        if difference[left] * difference[right] < 0:
            if right > left + 1:
                # Equal-rate points only count when opposite signs bracket them.
                # A mere touch, zero-count plateau or boundary equality is not a crossing.
                root = x[left + 1]
            else:
                root = x[left] - difference[left] * (x[right] - x[left]) / (
                    difference[right] - difference[left]
                )
            roots.append(float(root))
    return sorted(set(roots))


def threshold_estimates(records: list[dict], bootstrap: int, seed: int) -> dict:
    if bootstrap < 1:
        raise ValueError("Need bootstrap replicates")
    rng = np.random.default_rng(seed)
    by_distance = {
        d: sorted(
            [row for row in records if row["distance"] == d],
            key=lambda row: row["physical_error_rate"],
        )
        for d in (3, 5, 7)
    }
    output = {
        "method": "First nontrivial pairwise linear crossing; conditional binomial-bootstrap CI",
        "primary_pair": "5-7",
        "bootstrap_replicates": bootstrap,
        "bootstrap_seed": seed,
        "ci_excludes": ["finite-size bias", "grid/interpolation bias", "noise-model error"],
        "pairs": {},
    }
    for first_d, second_d in ((3, 5), (5, 7), (3, 7)):
        first, second = by_distance[first_d], by_distance[second_d]
        p = np.array([row["physical_error_rate"] for row in first])
        if not len(first) or [row["physical_error_rate"] for row in second] != p.tolist():
            raise ValueError("Distance curves must use the same grid")
        rates_a = np.array([row["logical_error_rate"] for row in first])
        rates_b = np.array([row["logical_error_rate"] for row in second])
        roots = crossing_roots(p, rates_a, rates_b)
        resampled_roots = []
        for _ in range(bootstrap):
            # Unsmooth empirical binomial bootstrap for crossings. Zero counts remain zero.
            a = np.array(
                [
                    rng.binomial(row["shots"], row["logical_error_rate"]) / row["shots"]
                    for row in first
                ]
            )
            b = np.array(
                [
                    rng.binomial(row["shots"], row["logical_error_rate"]) / row["shots"]
                    for row in second
                ]
            )
            sample_roots = crossing_roots(p, a, b)
            if sample_roots:
                resampled_roots.append(sample_roots[0])
        fraction = len(resampled_roots) / bootstrap
        output["pairs"][f"{first_d}-{second_d}"] = {
            "estimate": roots[0] if roots else None,
            "all_roots": roots,
            "conditional_ci95": np.quantile(resampled_roots, [0.025, 0.975]).tolist()
            if resampled_roots
            else None,
            "bootstrap_crossing_fraction": fraction,
            "bootstrap_no_crossing_fraction": 1 - fraction,
            "well_identified_in_grid": bool(roots) and fraction >= 0.8,
            "shots_per_point": sorted({row["shots"] for row in first + second}),
            "sweep_interval": [float(p[0]), float(p[-1])],
        }
    return output


def _fit_log_scaling(records: list[dict], counts: np.ndarray) -> tuple[float, float]:
    x = np.array([(row["distance"] + 1) / 2 for row in records])
    shots = np.array([row["shots"] for row in records])
    rounds = np.array([row["rounds"] for row in records])
    stabilized_rates = (counts + 0.5) / (shots + 1) / rounds
    slope, intercept = np.polyfit(x, np.log(stabilized_rates), 1, w=np.sqrt(counts + 0.5))
    return float(np.exp(intercept)), float(np.exp(-slope))


def fit_scaling(records: list[dict], bootstrap: int, seed: int) -> dict:
    if bootstrap < 1:
        raise ValueError("Need positive bootstrap replicates")
    if len(records) < 3 or len({row["distance"] for row in records}) != len(records):
        raise ValueError("Need at least three distinct distances")
    if len({row["physical_error_rate"] for row in records}) != 1:
        raise ValueError("Scaling calibration must use one fixed physical p")
    counts = np.array([row["failures"] for row in records])
    a, suppression = _fit_log_scaling(records, counts)
    rng = np.random.default_rng(seed)
    samples = []
    for _ in range(bootstrap):
        bootstrap_counts = np.array(
            [
                rng.binomial(row["shots"], (row["failures"] + 0.5) / (row["shots"] + 1))
                for row in records
            ]
        )
        samples.append(_fit_log_scaling(records, bootstrap_counts))
    reference_p = records[0]["physical_error_rate"]
    return {
        "reference_p": reference_p,
        "A": a,
        "suppression_factor_per_distance_plus_2": suppression,
        "A_ci95": np.quantile(np.array(samples)[:, 0], [0.025, 0.975]).tolist(),
        "suppression_ci95": np.quantile(np.array(samples)[:, 1], [0.025, 0.975]).tolist(),
        "suppresses_with_distance": suppression > 1,
        "fitted_noise_scale_not_crossing_threshold": reference_p * suppression,
        "distances": [row["distance"] for row in records],
        "bootstrap_seed": seed,
        "bootstrap_replicates": bootstrap,
        "bootstrap_parameters": [list(pair) for pair in samples],
        "fit": "WLS log(P_block/rounds) vs (d+1)/2, weights sqrt(k+0.5), Jeffreys half-count stabilization",
        "raw_zero_count_distances": [row["distance"] for row in records if row["failures"] == 0],
    }
