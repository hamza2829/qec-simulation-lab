import argparse
from pathlib import Path

from qec.experiments import ExperimentConfig, run_experiments


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CPU-only QEC memory experiments")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run")
    run.add_argument(
        "--quick", action="store_true", help="Few-shot smoke run, not a threshold reproduction"
    )
    run.add_argument("--output", type=Path, default=Path("results"))
    args = parser.parse_args(argv)
    config = ExperimentConfig.quick() if args.quick else ExperimentConfig()
    data = run_experiments(args.output, config)
    print("\nFinite-size surface crossings (not asymptotic thresholds):")
    for pair, record in data["thresholds"]["pairs"].items():
        print(
            f"  d={pair}: {record['estimate']} ; conditional CI95={record['conditional_ci95']} ; no-cross fraction={record['bootstrap_no_crossing_fraction']:.3f}"
        )
    print(
        f"Suppression per +2 distance: {data['scaling']['suppression_factor_per_distance_plus_2']:.5g}; CI95={data['scaling']['suppression_ci95']}"
    )
    print("Simplified resources: physical_p target_block_rate distance physical_qubits rounds")
    for record in data["resources"]:
        print(
            f"  {record['physical_error_rate']:.0e} {record['target_per_d_round_memory_block']:.0e} {record['distance']} {record['physical_qubits']} {record['rounds']}"
        )
    for result in data["ml"]:
        print(f"ML comparison: {result['code']}")
        for record in result["evaluation"]:
            print(
                f"  p={record['physical_error_rate']}: ML {record['ml']['failures']}/{record['ml']['shots']}, MWPM {record['pymatching']['failures']}, lookup {record['lookup']['failures']}; vs MWPM {record['ml_vs_pymatching']['observed']}, vs lookup {record['ml_vs_lookup']['observed']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
