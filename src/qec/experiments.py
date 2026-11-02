import json
import platform
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

import torch

from qec.code_capacity import simulate, simulate_phenomenological
from qec.compile_notes import toy_gate_cost
from qec.ml_decoder import run_ml_experiments
from qec.plots import write_plots
from qec.reporting import build_report
from qec.resources import resource_table
from qec.surface_code import experiment, fit_scaling, threshold_estimates

REPETITION_P = (0.01, 0.03, 0.05, 0.10, 0.15, 0.20, 0.30, 0.40, 0.50)
SURFACE_P = (0.001, 0.002, 0.003, 0.004, 0.005, 0.006, 0.007, 0.008, 0.009, 0.010, 0.012, 0.015)


@dataclass(frozen=True)
class ExperimentConfig:
    profile: str = "full"
    seed: int = 20261102
    repetition_shots: int = 100_000
    phenomenological_shots: int = 3_000
    surface_shots: int = 100_000
    calibration_shots: int = 500_000
    bootstrap_replicates: int = 1_000
    ml_train: int = 60_000
    ml_validation: int = 12_000
    ml_test: int = 40_000
    ml_epochs: int = 25

    @classmethod
    def quick(cls) -> "ExperimentConfig":
        return cls(
            profile="quick",
            repetition_shots=2_000,
            phenomenological_shots=128,
            surface_shots=1_000,
            calibration_shots=3_000,
            bootstrap_replicates=100,
            ml_train=1_024,
            ml_validation=256,
            ml_test=512,
            ml_epochs=2,
        )


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def run_experiments(output: Path, config: ExperimentConfig) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    for key, value in asdict(config).items():
        if key not in {"profile", "seed"} and (type(value) is not int or value < 1):
            raise ValueError("Shot, bootstrap and epoch counts must be positive integers")
    start = time.perf_counter()
    environment = {
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "processor": platform.processor(),
        "packages": {
            name: version(name)
            for name in ("numpy", "scipy", "stim", "pymatching", "matplotlib", "torch")
        },
        "device": "cpu",
        "torch_cuda_build": torch.version.cuda,
        "seed_caution": "Stim SIMD/platform and package versions can change exact samples despite the same seed",
    }
    data = {"config": asdict(config), "environment": environment}
    write_json(output / "config.json", data["config"])
    print(f"Profile {config.profile}; CPU only; seed {config.seed}", flush=True)

    data["repetition"] = []
    for d in (3, 5, 7, 9):
        for p in REPETITION_P:
            data["repetition"].append(
                simulate(d, p, config.repetition_shots, config.seed + len(data["repetition"]))
            )
    write_json(output / "repetition.json", data["repetition"])
    print("Completed NumPy code-capacity sweep.", flush=True)

    data["phenomenological"] = []
    for d in (3, 5):
        for rounds in (3, 5):
            for q in (0.0, 0.02, 0.05):
                data["phenomenological"].append(
                    simulate_phenomenological(
                        d,
                        0.02,
                        q,
                        rounds,
                        config.phenomenological_shots,
                        config.seed + 1000 + len(data["phenomenological"]),
                    )
                )
    write_json(output / "phenomenological.json", data["phenomenological"])
    print("Completed noisy-check histories.", flush=True)

    data["surface"] = []
    for d in (3, 5, 7):
        for p in SURFACE_P:
            row = experiment(d, p, config.surface_shots, config.seed + 2000 + len(data["surface"]))
            data["surface"].append(row)
            print(f"Surface d={d} p={p}: {row['failures']}/{row['shots']}", flush=True)
    write_json(output / "surface_code.json", data["surface"])
    data["thresholds"] = threshold_estimates(
        data["surface"], config.bootstrap_replicates, config.seed + 3000
    )
    write_json(output / "thresholds.json", data["thresholds"])

    data["scaling_calibration"] = [
        experiment(d, 0.002, config.calibration_shots, config.seed + 4000 + d) for d in (3, 5, 7)
    ]
    write_json(output / "scaling_calibration.json", data["scaling_calibration"])
    data["scaling"] = fit_scaling(
        data["scaling_calibration"], config.bootstrap_replicates, config.seed + 5000
    )
    primary = data["thresholds"]["pairs"]["5-7"]["estimate"]
    data["scaling"]["calibration_below_primary_crossing"] = (
        None if primary is None else 0.002 < primary
    )
    write_json(output / "scaling.json", data["scaling"])
    data["resources"] = resource_table(data["scaling"])
    write_json(output / "resources.json", data["resources"])
    print("Completed crossings, scaling calibration and resource extrapolation.", flush=True)

    data["ml"] = run_ml_experiments(
        output,
        config.ml_train,
        config.ml_validation,
        config.ml_test,
        config.ml_epochs,
        config.seed + 6000,
    )
    write_json(output / "ml_decoder.json", data["ml"])
    print("Completed held-out MLP/MWPM/lookup comparisons.", flush=True)
    data["compilation_toy"] = [
        {"name": name, **toy_gate_cost(gates, 3)}
        for name, gates in (
            ("Bell preparation (hand-written)", ["H", "CX"]),
            ("Single T sandwich (hand-written)", ["H", "T", "H"]),
            ("Small phase sequence (hand-written)", ["H", "T", "CX", "S", "TDG", "H"]),
        )
    ]
    write_json(output / "compile_notes.json", data["compilation_toy"])
    plots = write_plots(data, output / "plots")
    (output / "report.md").write_text(build_report(data), encoding="utf-8")
    environment["elapsed_seconds"] = time.perf_counter() - start
    environment["torch_threads"] = torch.get_num_threads()
    write_json(output / "environment.json", environment)
    summary = {
        "profile": config.profile,
        "thresholds": data["thresholds"]["pairs"],
        "suppression_factor": data["scaling"]["suppression_factor_per_distance_plus_2"],
        "suppression_ci95": data["scaling"]["suppression_ci95"],
        "resources": data["resources"],
        "ml_comparison": [
            {"code": item["code"], "evaluation": item["evaluation"]} for item in data["ml"]
        ],
        "plots": plots,
        "elapsed_seconds": environment["elapsed_seconds"],
    }
    write_json(output / "summary.json", summary)
    print(f"Wrote JSON, report.md, models and {len(plots)} PNGs to {output}", flush=True)
    return data
