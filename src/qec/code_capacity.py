"""Own NumPy implementation: no Stim, PyMatching, or other quantum library here."""

from math import comb

import numpy as np

from qec.statistics import rate_record


def validate_distance(distance: int) -> None:
    if type(distance) is not int or distance < 3 or distance % 2 == 0:
        raise ValueError("Repetition distance must be odd and at least 3")


def syndrome(bits: np.ndarray) -> np.ndarray:
    values = np.asarray(bits, dtype=np.uint8)
    if values.ndim < 1 or values.shape[-1] < 2 or np.any(values > 1):
        raise ValueError("Expected binary arrays with a data-bit final axis")
    return values[..., :-1] ^ values[..., 1:]


def majority_decode(bits: np.ndarray) -> np.ndarray:
    values = np.asarray(bits, dtype=np.uint8)
    validate_distance(values.shape[-1])
    if np.any(values > 1):
        raise ValueError("Expected binary data")
    return (values.sum(axis=-1) > values.shape[-1] // 2).astype(np.uint8)


def lookup_table(distance: int) -> np.ndarray:
    """Each syndrome has two complementary error patterns; retain the lighter one."""
    validate_distance(distance)
    indices = np.arange(1 << (distance - 1), dtype=np.uint32)
    checks = ((indices[:, None] >> np.arange(distance - 1)) & 1).astype(np.uint8)
    errors = np.zeros((len(indices), distance), dtype=np.uint8)
    errors[:, 1:] = np.bitwise_xor.accumulate(checks, axis=1)
    complement_is_lighter = errors.sum(axis=1) > distance // 2
    errors[complement_is_lighter] ^= 1
    return errors


def lookup_decode(checks: np.ndarray) -> np.ndarray:
    values = np.asarray(checks, dtype=np.uint8)
    if values.ndim < 1 or np.any(values > 1):
        raise ValueError("Expected binary syndromes")
    distance = values.shape[-1] + 1
    index = values @ (1 << np.arange(distance - 1, dtype=np.uint32))
    return lookup_table(distance)[index]


def exact_logical_error(distance: int, p: float) -> float:
    validate_distance(distance)
    if not 0 <= p <= 1:
        raise ValueError("Noise must be between 0 and 1")
    return sum(
        comb(distance, k) * p**k * (1 - p) ** (distance - k)
        for k in range(distance // 2 + 1, distance + 1)
    )


def simulate(distance: int, p: float, shots: int, seed: int) -> dict:
    validate_distance(distance)
    if not 0 <= p <= 1 or shots <= 0:
        raise ValueError("Invalid noise or shots")
    errors = (np.random.default_rng(seed).random((shots, distance)) < p).astype(np.uint8)
    majority = majority_decode(errors)
    corrected = errors ^ lookup_decode(syndrome(errors))
    return {
        "distance": distance,
        "physical_error_rate": p,
        "seed": seed,
        "majority": rate_record(int(majority.sum()), shots),
        "lookup": rate_record(int(corrected[:, 0].sum()), shots),
        "unencoded": rate_record(int(errors[:, 0].sum()), shots),
        "exact_logical_error_rate": exact_logical_error(distance, p),
    }


def viterbi_correction(
    history: np.ndarray, final_checks: np.ndarray, p: float, q: float
) -> np.ndarray:
    """Most-likely hidden *path* using exact finite-state dynamic programming.

    Clear O(rounds * 4**d) reference implementation; exponential cost limits this
    educational decoder to d<=9. It is not a scalable surface-code decoder.
    """
    history = np.asarray(history, dtype=np.uint8)
    final_checks = np.asarray(final_checks, dtype=np.uint8)
    if (
        history.ndim != 2
        or final_checks.shape != history.shape[1:]
        or np.any(history > 1)
        or np.any(final_checks > 1)
    ):
        raise ValueError("Expected rounds by checks and a final syndrome")
    distance = history.shape[1] + 1
    validate_distance(distance)
    if distance > 9 or not 0 <= p < 0.5 or not 0 <= q < 0.5:
        raise ValueError("Use d<=9, 0<=p<0.5 and 0<=q<0.5")
    states = ((np.arange(1 << distance)[:, None] >> np.arange(distance)) & 1).astype(np.uint8)
    state_checks = syndrome(states)
    hamming = (states[:, None, :] != states[None, :, :]).sum(axis=2)
    if p == 0:
        transitions = np.where(hamming == 0, 0.0, np.inf)
    else:
        transitions = -hamming * np.log(p) - (distance - hamming) * np.log1p(-p)
    costs = np.full(len(states), np.inf)
    costs[0] = 0.0
    for observed in history:
        costs = (costs[:, None] + transitions).min(axis=0)
        wrong_checks = (state_checks != observed).sum(axis=1)
        if q == 0:
            costs[wrong_checks != 0] = np.inf
        else:
            costs += -wrong_checks * np.log(q) - (distance - 1 - wrong_checks) * np.log1p(-q)
    costs[np.any(state_checks != final_checks, axis=1)] = np.inf
    if not np.any(np.isfinite(costs)):
        raise ValueError("No history path is consistent with this zero-noise model")
    return states[int(np.argmin(costs))]


def simulate_phenomenological(
    distance: int, p: float, q: float, rounds: int, shots: int, seed: int
) -> dict:
    validate_distance(distance)
    if distance > 9 or rounds < 1 or shots < 1 or not 0 <= p < 0.5 or not 0 <= q < 0.5:
        raise ValueError("Invalid phenomenological parameters")
    rng = np.random.default_rng(seed)
    increments = (rng.random((shots, rounds, distance)) < p).astype(np.uint8)
    states = np.bitwise_xor.accumulate(increments, axis=1)
    noisy_checks = syndrome(states) ^ (rng.random((shots, rounds, distance - 1)) < q).astype(
        np.uint8
    )
    final = states[:, -1, :]
    corrections = np.array(
        [viterbi_correction(h, s, p, q) for h, s in zip(noisy_checks, syndrome(final), strict=True)]
    )
    history_failures = int((final[:, 0] ^ corrections[:, 0]).sum())
    last = lookup_decode(noisy_checks[:, -1, :])
    return {
        "distance": distance,
        "physical_error_rate_per_round": p,
        "measurement_error_rate": q,
        "rounds": rounds,
        "seed": seed,
        "final_readout": "perfect",
        "viterbi": rate_record(history_failures, shots),
        "last_noisy_syndrome": rate_record(int((final[:, 0] ^ last[:, 0]).sum()), shots),
        "final_majority": rate_record(int(majority_decode(final).sum()), shots),
    }
