def _prob(value):
    return "not identified" if value is None else f"{value:.6g}"


def _percent_ci(estimate, ci):
    return (
        "not identified in fixed grid"
        if estimate is None
        else f"{100 * estimate:.4f}% [{100 * ci[0]:.4f}%, {100 * ci[1]:.4f}%]"
        if ci
        else f"{100 * estimate:.4f}% (no bootstrap interval)"
    )


def build_report(data: dict) -> str:
    config = data["config"]
    lines = [
        "# QEC simulation lab: measured CPU results",
        "",
        f"Profile: **{config['profile']}**. UTC execution date: {data['environment']['started_utc']}. Base seed: {config['seed']}.",
        "",
        "Simulation only. Independent Pauli/depolarizing noise; no hardware or cloud account. Rates below are per complete memory experiment unless explicitly marked otherwise. All proportion intervals are 95% Wilson intervals.",
        "",
    ]
    if config["profile"] == "quick":
        lines += [
            "**SMOKE RUN ONLY: few-shot crossings, zero-count fits, resources and ML scores are not scientific conclusions.**",
            "",
        ]
    lines += [
        "## Repetition code capacity",
        "",
        f"{config['repetition_shots']:,} shots for each distance/noise point. Majority and syndrome lookup see identical shots. The nontrivial analytical break-even with unencoded p is **p=0.5** for this ideal X-only, perfect-check model; it is not a circuit threshold.",
        "",
        "| d | p | Majority failures / shots | Logical error [95% CI] | Lookup failures | Unencoded failures | Exact binomial tail |",
        "|---:|---:|---:|---|---:|---:|---:|",
    ]
    for row in data["repetition"]:
        if row["physical_error_rate"] in (0.1, 0.5):
            stat = row["majority"]
            lines.append(
                f"| {row['distance']} | {row['physical_error_rate']} | {stat['failures']} / {stat['shots']} | {_prob(stat['logical_error_rate'])} [{_prob(stat['ci95'][0])}, {_prob(stat['ci95'][1])}] | {row['lookup']['failures']} | {row['unencoded']['failures']} | {_prob(row['exact_logical_error_rate'])} |"
            )
    lines += [
        "",
        "![Repetition code](plots/repetition.png)",
        "",
        "## Noisy measurements and multiple rounds",
        "",
        "Data p=0.02 per round, perfect final data readout. Viterbi finds a most-likely history path, not the optimal logical-class posterior. Last-check decoding deliberately trusts a noisy final check; final-majority uses the perfect final readout but no history.",
        "",
        "| d | Rounds | Measurement q | Viterbi failures / shots | Last-noisy-check failures | Final-majority failures |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for row in data["phenomenological"]:
        stat = row["viterbi"]
        lines.append(
            f"| {row['distance']} | {row['rounds']} | {row['measurement_error_rate']} | {stat['failures']} / {stat['shots']} | {row['last_noisy_syndrome']['failures']} | {row['final_majority']['failures']} |"
        )
    lines += [
        "",
        "![Phenomenological repetition](plots/phenomenological.png)",
        "",
        "## Circuit-level rotated surface code",
        "",
        f"Task: rotated_memory_z; distances 3,5,7; rounds=d; **{config['surface_shots']:,} shots per point**. All four Stim noise arguments equal p: after-Clifford depolarization, before-round data depolarization, measurement flips, reset flips. Only one logical Z-memory observable is tested. Default uncorrelated PyMatching MWPM uses a decomposed graphlike detector error model.",
        "",
        "| d | Rounds | Active qubits | p | Failures / shots | Logical error [95% CI] |",
        "|---:|---:|---:|---:|---:|---|",
    ]
    for row in data["surface"]:
        lines.append(
            f"| {row['distance']} | {row['rounds']} | {row['active_qubits']} | {row['physical_error_rate']} | {row['failures']} / {row['shots']} | {_prob(row['logical_error_rate'])} [{_prob(row['ci95'][0])}, {_prob(row['ci95'][1])}] |"
        )
    lines += [
        "",
        "![Surface code](plots/surface_code.png)",
        "",
        "### Finite-size crossing estimates",
        "",
        "The primary estimate is d=5 versus d=7. Linear interpolation in physical p; bootstrap intervals are conditional on finding a root. The first nontrivial root is used by the predeclared rule; all roots remain in JSON. These are finite-size crossings, not an asymptotic threshold determination.",
        "",
        "| Pair | Crossing and conditional 95% bootstrap CI | Bootstrap with no crossing |",
        "|---|---|---:|",
    ]
    for pair, result in data["thresholds"]["pairs"].items():
        lines.append(
            f"| {pair} | {_percent_ci(result['estimate'], result['conditional_ci95'])} | {100 * result['bootstrap_no_crossing_fraction']:.1f}% |"
        )
    estimates = [
        result["estimate"]
        for result in data["thresholds"]["pairs"].values()
        if result["estimate"] is not None
    ]
    if len(estimates) > 1:
        lines += [
            "",
            f"Distance-pair estimates range from **{100 * min(estimates):.4f}% to {100 * max(estimates):.4f}%**. This pair dependence is a finite-size warning, not extra independent measurements of one universal threshold. A single pair's sampling interval does not capture this systematic spread.",
        ]
    primary = data["thresholds"]["pairs"]["5-7"]["estimate"]
    comparison = (
        "not identified, so no numerical comparison is justified"
        if primary is None
        else "inside"
        if 0.005 <= primary <= 0.01
        else "outside"
    )
    lines += [
        "",
        f"The primary crossing is **{comparison}** the commonly quoted roughly 0.5–1% circuit-noise context. [Stephens (2014)](https://arxiv.org/abs/1311.5003) reports 0.502–1.140% across specific assumptions; neither its circuit nor its noise convention is identical to this small experiment. No sweep was moved to force agreement. Statistical intervals omit finite-size, grid/interpolation, decoder-approximation and noise-model biases.",
        "",
        "## Below-threshold distance scaling",
        "",
    ]
    fit = data["scaling"]
    lines += [
        f"Independent calibration at p_ref={fit['reference_p']}, **{config['calibration_shots']:,} shots per distance**. Fit log(P_block/d) against (d+1)/2 at d=3,5,7. WLS weights sqrt(k+0.5), using (k+0.5)/(N+1) for log-fit stabilization only; raw rates are unchanged.",
        "",
        "| d | Failures / shots | Whole-memory rate [95% CI] | P_block/d proxy |",
        "|---:|---:|---|---:|",
    ]
    for row in data["scaling_calibration"]:
        lines.append(
            f"| {row['distance']} | {row['failures']} / {row['shots']} | {_prob(row['logical_error_rate'])} [{_prob(row['ci95'][0])}, {_prob(row['ci95'][1])}] | {_prob(row['per_round_small_error_proxy'])} |"
        )
    lines += [
        "",
        f"**Suppression Lambda_ref={fit['suppression_factor_per_distance_plus_2']:.4f} per +2 distance; 95% bootstrap CI [{fit['suppression_ci95'][0]:.4f}, {fit['suppression_ci95'][1]:.4f}].** A={fit['A']:.6g}. Fitted noise scale p_ref×Lambda={fit['fitted_noise_scale_not_crossing_threshold']:.6g}; this is a scaling parameter, **not another measured threshold**.",
        "",
        f"Calibration below the measured primary crossing: {fit['calibration_below_primary_crossing']}. Zero-count distances: {fit['raw_zero_count_distances']}. Only three distances constrain two fit parameters; interval reflects count noise, not extrapolation error.",
        "",
        "![Scaling](plots/scaling.png)",
        "",
        "## Simplified resource illustration",
        "",
        "Assume Lambda(p)=Lambda_ref×p_ref/p and P_block≈d×A/Lambda(p)^((d+1)/2). Target is **failure per d-round memory block**, not an algorithm lifetime. Choose the smallest odd d>=3; qubits=2d²−1; rounds=d. The additional p-power law is assumed, not independently fitted. Counts omit routing, spares, magic-state factories, logical gates and control hardware.",
        "",
        "| Physical p | Target per block | Needed d [bootstrap interval] | Physical qubits / logical memory | Rounds | Predicted block failure | Beyond fitted d? |",
        "|---:|---:|---|---:|---:|---:|---|",
    ]
    for row in data["resources"]:
        lines.append(
            f"| {row['physical_error_rate']} | {row['target_per_d_round_memory_block']:.0e} | {row['distance']} {row['distance_bootstrap_ci95']} | {row['physical_qubits']} | {row['rounds']} | {_prob(row['predicted_block_error'])} | {row['beyond_fitted_distances']} |"
        )
    lines += [
        "",
        "Bootstrap distance intervals omit model bias and are conditional on solvable bootstrap fits; unresolved fractions are in resources.json. All four rows extrapolate in physical p, even when the chosen distance lies inside d=3,5,7. A narrow or single-integer bootstrap interval does not imply model certainty. These very small target rates are **extrapolated, not directly observed or validated**.",
        "",
        "## Small PyTorch MLP decoder experiment",
        "",
        "CPU only. A 32→16 hidden-unit ReLU MLP predicts the logical observable bit. Independent training/validation/test sampler seeds; validation alone chooses the output threshold. Matching knows each test p; MLP and surface lookup train at one fixed p. This difference and out-of-training-p distribution shifts matter. Surface lookup is empirical and defaults to 0 for unseen/tied syndromes; repetition lookup is exact minimum weight.",
        "",
    ]
    for experiment in data["ml"]:
        train = experiment["training"]
        lines += [
            f"### {experiment['code']} d=3",
            "",
            f"Train p={experiment['training_physical_p']}; {train['training_shots']:,} training, {train['validation_shots']:,} validation; {train['epochs']} epochs; {train['parameter_count']} parameters; threshold={train['validation_selected_threshold']:.2f}; training observable-flip fraction={train['training_positive_fraction']:.4f}. Checkpoint: `{experiment['checkpoint']}`.",
            "",
            "| Test p | MLP failures / shots [95% CI] | MWPM failures | Lookup failures | Unseen lookup syndromes | MLP vs MWPM | MLP vs lookup |",
            "|---:|---|---:|---:|---:|---|---|",
        ]
        for row in experiment["evaluation"]:
            ml = row["ml"]

            def comparison_text(key, row=row):
                value = row[key]
                support = (
                    "CI supports difference"
                    if value["difference_supported_by_approx_ci"]
                    else "inconclusive/equal, not an equivalence claim"
                )
                return f"{value['observed']}; delta={value['ml_minus_baseline_error_rate']:.5g} [{value['paired_approx_ci95'][0]:.5g}, {value['paired_approx_ci95'][1]:.5g}]; {support}"

            lines.append(
                f"| {row['physical_error_rate']} | {ml['failures']} / {ml['shots']} [{ml['ci95'][0]:.5g}, {ml['ci95'][1]:.5g}] | {row['pymatching']['failures']} | {row['lookup']['failures']} | {100 * row['lookup_unseen_fraction']:.2f}% | {comparison_text('ml_vs_pymatching')} | {comparison_text('ml_vs_lookup')} |"
            )
    lines += [
        "",
        "![ML comparison](plots/ml_comparison.png)",
        "",
        "Paired intervals are approximate normal intervals for differences on common shots; sparse discordances are inconclusive. No hyperparameters were selected on test shots. One architecture/training seed is not a decoder research result or evidence of general ML superiority.",
        "",
        "## Optional hand-written gate-count toy",
        "",
        "| Circuit | Clifford gates | T gates | Toy sequential qubit-rounds |",
        "|---|---:|---:|---:|",
    ]
    for row in data["compilation_toy"]:
        lines.append(
            f"| {row['name']} | {row['Clifford_gates']} | {row['T_gates']} | {row['toy_sequential_qubit_rounds']} |"
        )
    lines += [
        "",
        "Stim does not simulate T gates here. These are hand-written gate lists and arbitrary factory-cost formulas, **not a fault-tolerant compiler, protocol, or scheduling result**.",
        "",
        "## Reproducibility and limits",
        "",
        "See ../docs/experiment-plan.md for the preregistered grid, seeds, shot budgets and estimators, and ../docs/concepts.md for the worked examples. environment.json records library versions, CPU-only mode and elapsed time. Fixed seeds are version/platform dependent, especially Stim SIMD sampling. CI's quick sweep is a smoke check and does not reproduce the full statistical precision.",
        "",
        "Simulation only; independent standard noise, one surface-memory basis, small distances, no quantum hardware, coherent/correlated errors, leakage, crosstalk or cloud service. Per-round division, p-scaling, required distances and toy factory costs are simplified. No claimed implementation of a general fault-tolerant quantum computer or compiler.",
        "",
    ]
    return "\n".join(lines)
