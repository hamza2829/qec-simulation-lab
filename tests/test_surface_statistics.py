import numpy as np
import pytest
import stim

from qec.statistics import rate_record, wilson_interval
from qec.surface_code import (
    crossing_roots,
    experiment,
    fit_scaling,
    matching_decoder,
    memory_circuit,
    sample_memory,
    threshold_estimates,
)


@pytest.mark.parametrize("distance", [3, 5, 7])
def test_rotated_patch_active_qubit_and_detector_counts(distance):
    circuit = memory_circuit(distance, 0.001)
    assert len(circuit.get_final_qubit_coordinates()) == 2 * distance**2 - 1
    assert circuit.num_detectors == (distance**2 - 1) * distance
    assert circuit.num_observables == 1


def test_noiseless_memory_has_no_logical_errors():
    result = experiment(3, 0, 256, 10)
    assert result["failures"] == 0
    assert result["ci95"][1] > 0


@pytest.mark.parametrize("distance", [3, 5])
def test_matching_corrects_each_single_initial_data_x_fault(distance):
    noiseless = memory_circuit(distance, 0)
    matcher = matching_decoder(memory_circuit(distance, 0.001))
    data_qubits = [
        q
        for q, (x, y) in noiseless.get_final_qubit_coordinates().items()
        if int(x) % 2 == 1 and int(y) % 2 == 1
    ]
    assert len(data_qubits) == distance**2
    first_tick = next(i for i, instruction in enumerate(noiseless) if instruction.name == "TICK")
    for q in data_qubits:
        faulty = noiseless.copy()
        faulty.insert(first_tick, stim.CircuitInstruction("X", [q]))
        detectors, actual = sample_memory(faulty, 1, 11)
        assert matcher.decode_batch(detectors)[0, 0] == actual[0]


def test_circuit_logical_error_grows_across_widely_separated_noise_levels():
    low, high = experiment(3, 0.001, 2000, 12), experiment(3, 0.03, 2000, 13)
    assert low["ci95"][1] < high["ci95"][0]


def test_stim_sampler_is_repeatable_in_the_same_environment():
    circuit = memory_circuit(3, 0.01)
    first, second = sample_memory(circuit, 256, 14), sample_memory(circuit, 256, 14)
    np.testing.assert_array_equal(first[0], second[0])
    np.testing.assert_array_equal(first[1], second[1])


@pytest.mark.parametrize("failures,shots", [(0, 100), (1, 100), (50, 100), (100, 100)])
def test_wilson_interval_contains_observed_rate_and_stays_bounded(failures, shots):
    low, high = wilson_interval(failures, shots)
    assert 0 <= low <= failures / shots <= high <= 1


def test_zero_counts_are_upper_limits_not_zero_risk():
    low, high = wilson_interval(0, 1000)
    assert low == 0
    assert 0.003 < high < 0.004


def test_crossing_is_interpolated_without_a_literature_prior():
    assert crossing_roots(
        np.array([0.001, 0.003]), np.array([0.1, 0.3]), np.array([0.2, 0.2])
    ) == pytest.approx([0.002])


def test_equal_curves_touching_and_zero_plateaus_do_not_manufacture_crossings():
    x = np.array([0.001, 0.002, 0.003])
    assert not crossing_roots(x, np.zeros(3), np.zeros(3))
    assert not crossing_roots(x, np.array([0.2, 0.1, 0.2]), np.array([0.1, 0.1, 0.1]))


def test_multiple_sign_changes_are_retained():
    roots = crossing_roots(np.array([1, 2, 3, 4]), np.array([0.2, 0.1, 0.2, 0.1]), np.full(4, 0.15))
    assert roots == pytest.approx([1.5, 2.5, 3.5])


def test_threshold_bootstrap_reports_missing_crossings():
    rows = [
        {"distance": d, "physical_error_rate": p, **rate_record(0, 100)}
        for d in (3, 5, 7)
        for p in (0.001, 0.01)
    ]
    result = threshold_estimates(rows, 20, 15)
    assert result["pairs"]["5-7"]["estimate"] is None
    assert result["pairs"]["5-7"]["bootstrap_no_crossing_fraction"] == 1


def test_scaling_fit_recovers_a_known_synthetic_suppression_law():
    records = [
        {
            "distance": d,
            "rounds": d,
            "physical_error_rate": 0.002,
            **rate_record(round(10_000_000 * d * 0.1 / 10 ** ((d + 1) / 2)), 10_000_000),
        }
        for d in (3, 5, 7)
    ]
    fit = fit_scaling(records, 30, 16)
    assert fit["suppression_factor_per_distance_plus_2"] == pytest.approx(10, rel=0.01)
    assert fit["A"] == pytest.approx(0.1, rel=0.01)
    assert len(fit["bootstrap_parameters"]) == 30


def test_zero_count_calibration_is_flagged_and_fit_remains_finite():
    records = [
        {"distance": d, "rounds": d, "physical_error_rate": 0.002, **rate_record(0, 100)}
        for d in (3, 5, 7)
    ]
    fit = fit_scaling(records, 10, 17)
    assert fit["raw_zero_count_distances"] == [3, 5, 7]
    assert np.isfinite(fit["suppression_factor_per_distance_plus_2"])
