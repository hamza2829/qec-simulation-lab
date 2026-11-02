import itertools

import numpy as np
import pytest

from qec.code_capacity import (
    exact_logical_error,
    lookup_decode,
    lookup_table,
    majority_decode,
    simulate,
    simulate_phenomenological,
    syndrome,
    validate_distance,
    viterbi_correction,
)


@pytest.mark.parametrize(
    "bits,expected",
    [
        ([0, 0, 0], [0, 0]),
        ([1, 0, 0], [1, 0]),
        ([0, 1, 0], [1, 1]),
        ([0, 0, 1], [0, 1]),
        ([1, 1, 1], [0, 0]),
        ([1, 1, 0], [0, 1]),
    ],
)
def test_known_syndromes(bits, expected):
    np.testing.assert_array_equal(syndrome(np.array(bits)), expected)


@pytest.mark.parametrize("distance", [3, 5, 7, 9])
def test_decoders_correct_every_pattern_up_to_half_distance(distance):
    errors = np.array(
        [bits for bits in itertools.product((0, 1), repeat=distance) if sum(bits) <= distance // 2],
        dtype=np.uint8,
    )
    assert not np.any(majority_decode(errors))
    np.testing.assert_array_equal(errors ^ lookup_decode(syndrome(errors)), np.zeros_like(errors))


@pytest.mark.parametrize("distance", [3, 5, 7, 9])
def test_lookup_and_majority_agree_on_all_error_patterns(distance):
    errors = np.array(list(itertools.product((0, 1), repeat=distance)), dtype=np.uint8)
    corrections = lookup_decode(syndrome(errors))
    np.testing.assert_array_equal((errors ^ corrections)[:, 0], majority_decode(errors))
    np.testing.assert_array_equal(syndrome(corrections), syndrome(errors))


@pytest.mark.parametrize("distance", [3, 5, 7, 9])
def test_lookup_table_covers_every_syndrome_once(distance):
    table = lookup_table(distance)
    assert table.shape == (2 ** (distance - 1), distance)
    assert np.unique(syndrome(table), axis=0).shape[0] == len(table)


@pytest.mark.parametrize("distance", [3, 5, 7, 9])
def test_exact_break_even_and_zero_noise(distance):
    assert exact_logical_error(distance, 0) == 0
    assert exact_logical_error(distance, 0.5) == pytest.approx(0.5)
    assert exact_logical_error(distance, 0.1) < 0.1


def test_three_bit_worked_example():
    assert exact_logical_error(3, 0.1) == pytest.approx(0.028)
    np.testing.assert_array_equal(lookup_decode(np.array([0, 1])), [0, 0, 1])
    assert majority_decode(np.array([1, 1, 0])) == 1


@pytest.mark.parametrize("distance", [3, 5, 7, 9])
def test_seeded_monte_carlo_is_monotonic_with_coupled_physical_noise(distance):
    # Reusing the same uniforms couples the X-only error samples monotonically in p.
    failures = [
        simulate(distance, p, 2000, 55)["majority"]["failures"] for p in (0.02, 0.08, 0.15, 0.3)
    ]
    assert failures == sorted(failures)


def test_seeded_monte_carlo_matches_exact_binomial_within_sampling_tolerance():
    result = simulate(3, 0.1, 30_000, 123)
    assert abs(result["majority"]["logical_error_rate"] - 0.028) < 0.005
    assert result == simulate(3, 0.1, 30_000, 123)
    assert result["majority"]["failures"] == result["lookup"]["failures"]


@pytest.mark.parametrize("distance", [0, 1, 2, 4, -3])
def test_invalid_distance_is_rejected(distance):
    with pytest.raises(ValueError):
        validate_distance(distance)


def test_measurement_fault_is_not_automatically_a_data_fault():
    correction = viterbi_correction(np.array([[0, 0], [1, 0], [0, 0]]), np.array([0, 0]), 0.01, 0.1)
    np.testing.assert_array_equal(correction, [0, 0, 0])


def test_history_can_recover_two_separated_data_faults_that_final_majority_cannot():
    correction = viterbi_correction(np.array([[1, 0], [0, 1]]), np.array([0, 1]), 0.01, 0)
    np.testing.assert_array_equal(correction, [1, 1, 0])


def test_no_data_noise_with_noisy_checks_keeps_logical_memory_safe():
    result = simulate_phenomenological(3, 0, 0.1, 3, 32, 71)
    assert result["viterbi"]["failures"] == 0
    assert result["final_majority"]["failures"] == 0


def test_noisy_measurement_experiment_is_seeded_and_records_per_round_parameters():
    result = simulate_phenomenological(3, 0.02, 0.05, 3, 64, 72)
    assert result == simulate_phenomenological(3, 0.02, 0.05, 3, 64, 72)
    assert result["viterbi"]["shots"] == 64
    assert result["final_readout"] == "perfect"
