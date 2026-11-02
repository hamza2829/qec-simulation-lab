from dataclasses import replace

import numpy as np
import pytest

from qec.compile_notes import toy_gate_cost
from qec.experiments import ExperimentConfig, run_experiments
from qec.ml_decoder import (
    MLPDecoder,
    empirical_lookup,
    lookup_predict,
    paired_comparison,
    repetition_circuit,
    train_mlp,
)
from qec.resources import block_error_estimate, required_distance, resource_table
from qec.surface_code import sample_memory


@pytest.mark.parametrize("distance", [3, 5, 7, 9])
def test_resource_formula_uses_patch_qubits_and_d_round_blocks(distance):
    assert block_error_estimate(distance, 0.001, 0.1, 10, 0.001) == pytest.approx(
        distance * 0.1 / 10 ** ((distance + 1) / 2)
    )


def test_resource_distance_is_the_smallest_odd_distance_meeting_the_target():
    d = required_distance(1e-6, 0.001, 0.1, 10, 0.001)
    assert d == 13
    assert block_error_estimate(d, 0.001, 0.1, 10, 0.001) <= 1e-6
    assert block_error_estimate(d - 2, 0.001, 0.1, 10, 0.001) > 1e-6


def test_resource_table_has_all_four_required_combinations():
    fit = {
        "A": 0.1,
        "suppression_factor_per_distance_plus_2": 10,
        "reference_p": 0.001,
        "distances": [3, 5, 7],
        "bootstrap_parameters": [[0.1, 10], [0.1, 10]],
    }
    rows = resource_table(fit)
    assert len(rows) == 4
    for row in rows:
        d = row["distance"]
        assert row["physical_qubits"] == 2 * d**2 - 1
        assert row["rounds"] == d
        assert row["qubit_rounds"] == row["physical_qubits"] * d
        assert row["simplified_estimate"] is True


def test_non_suppressing_parameters_do_not_invent_a_solution():
    assert required_distance(1e-6, 0.01, 0.1, 1, 0.001) is None


@pytest.mark.parametrize("p", [0, -0.1, float("nan")])
def test_invalid_resource_probability_is_rejected(p):
    with pytest.raises(ValueError):
        required_distance(1e-6, p, 0.1, 10, 0.001)


def test_toy_gate_accounting_counts_t_separately_from_cliffords():
    result = toy_gate_cost(["H", "T", "CX", "TDG"], 3)
    assert result["T_gates"] == result["Clifford_gates"] == 2
    assert result["toy_sequential_qubit_rounds"] == 2 * 17 * 3 + 2 * 100 * 10
    assert result["toy_only"]


def test_small_mlp_trains_saves_loads_and_predicts_on_cpu(tmp_path):
    train_x, train_y = sample_memory(repetition_circuit(0.1), 256, 18)
    val_x, val_y = sample_memory(repetition_circuit(0.1), 64, 19)
    decoder, metadata = train_mlp(train_x, train_y, val_x, val_y, 2, 20)
    path = tmp_path / "decoder.pt"
    decoder.save(path)
    loaded = MLPDecoder.load(path)
    np.testing.assert_array_equal(decoder.predict(val_x), loaded.predict(val_x))
    assert set(loaded.predict(val_x)) <= {0, 1}
    assert next(loaded.model.parameters()).device.type == "cpu"
    assert metadata["training_shots"] == 256


def test_empirical_lookup_ties_and_unseen_syndromes_default_to_zero():
    table = empirical_lookup(np.array([[0, 0], [0, 0], [1, 0]]), np.array([0, 1, 1]))
    predicted, unseen = lookup_predict(table, np.array([[0, 0], [1, 0], [1, 1]]))
    np.testing.assert_array_equal(predicted, [0, 1, 0])
    assert unseen == pytest.approx(1 / 3)


def test_paired_comparison_distinguishes_direction_from_equality():
    ml, matching = np.zeros(100, dtype=bool), np.ones(100, dtype=bool)
    assert paired_comparison(ml, matching)["observed"] == "better"
    assert paired_comparison(matching, ml)["observed"] == "worse"
    assert paired_comparison(ml, ml)["identical_error_outcomes"]


def test_plots_json_models_and_report_are_written_from_real_small_experiments(tmp_path):
    config = replace(
        ExperimentConfig.quick(),
        repetition_shots=128,
        phenomenological_shots=8,
        surface_shots=64,
        calibration_shots=128,
        bootstrap_replicates=10,
        ml_train=128,
        ml_validation=32,
        ml_test=64,
        ml_epochs=1,
    )
    data = run_experiments(tmp_path, config)
    assert len(data["surface"]) == 36
    assert len(data["repetition"]) == 36
    assert len(list((tmp_path / "plots").glob("*.png"))) == 5
    assert all(path.stat().st_size > 1000 for path in (tmp_path / "plots").glob("*.png"))
    assert (tmp_path / "models/surface_d3.pt").exists()
    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "SMOKE RUN ONLY" in report
    assert "conditional 95%" in report
    assert "not directly observed" in report
    assert (tmp_path / "thresholds.json").exists()
