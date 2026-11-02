# Verification history

The first repository commit wrote `docs/concepts.md` and froze `docs/experiment-plan.md` before committing implementation or running the full sweep. The scientific settings are unchanged from that plan.

- Initial CPU-Torch installation failed because the CPU-only package index lacked a transitive dependency's build backend (`flit_core`). Installing the pinned Torch CPU wheel with `--no-deps`, then resolving normal dependencies from PyPI, succeeded. Torch reports `2.10.0+cpu`, with no CUDA build.
- An initial few-shot smoke run completed and exposed an estimator issue: touching/equal sampled rates could be called a crossing without a sign change. The estimator now requires opposite signs on either side, including across exact-equality points. A zero-count plateau or tangent does not manufacture a threshold. A regression test covers this. The sweep grid and seeds were not altered.
- First pytest run: **71 passed, 0 failed, 0 errors, 0 skipped**. Tests include exhaustive protected-channel repetition patterns through half distance, all single initial surface-data X faults at d=3/5, seeded noise/decoder checks, confidence intervals/crossings/scaling, resource formulas, CPU MLP save/load/predict, and five plot files from actual small experiments.
- Ruff initially identified import ordering, multi-statement formatting and a loop-variable closure in report formatting. These were fixed before committing source.

Full-run measured results and CI evidence are recorded below. Quick-profile crossings and fits are explicitly smoke results, not the full experiment's scientific conclusions.

Visual review of the first full-run plots caught a presentation error: the unencoded y=p reference joined only its endpoints on a log-y plot, drawing the wrong intervening curve. The reference is now sampled densely, and the plot integration test checks its rendered geometry at p=0.1. Raw error counts, decoders and scientific settings were unchanged. The full command is rerun after this plotting correction; the report also explicitly discusses the distance-pair threshold spread and physical-p extrapolation in all resource rows.

## Full local execution

Final reviewed tests: **71 passed, 0 failed/errors/skipped**, Python 3.11.0. Ruff check/format passed. No pytest failure was suppressed. The full `python -m qec run` completed in **52.53 seconds on the recorded CPU** after the plotting correction; all raw counts and numerical fit/ML results reproduced the first full run in the same environment. Both committed CPU model checkpoints were reloaded and predicted successfully. All five PNGs were inspected visually, including the corrected reference curve.

Measured surface pair crossings, 100,000 shots per point, 1,000 bootstrap resamples:

| Pair | Finite-size crossing | Conditional 95% bootstrap interval |
|---|---:|---:|
| 3–5 | 0.598083% | 0.565905–0.633677% |
| 5–7, primary | 0.721768% | 0.692075–0.741320% |
| 3–7 | 0.667636% | 0.650500–0.693568% |

Every bootstrap replicate found a crossing in the fixed grid. Pair dependence is a warning about finite-size bias, excluded from these sampling intervals. Separate calibration used 500,000 shots at p=0.002 per distance, with 1,517 / 547 / 153 failures for d=3/5/7. Fitted suppression per +2 distance: **4.727831 [4.429870, 5.052460]**, 95% bootstrap CI. Full JSON preserves more digits; printed precision is not a claim of systematic accuracy.

ML test counts, 40,000 independent held-out shots per row:

| Code | p | MLP failures | PyMatching failures | Lookup failures |
|---|---:|---:|---:|---:|
| Repetition | 0.01 | 16 | 16 | 16 |
| Repetition | 0.05 | 272 | 272 | 272 |
| Repetition | 0.10 | 1,164 | 1,164 | 1,164 |
| Surface | 0.003 | 375 | 265 | 358 |
| Surface | 0.010 | 3,194 | 2,333 | 3,564 |
| Surface | 0.020 | 8,593 | 6,986 | 9,590 |

Surface MLP was worse than MWPM at all three p values, supported by paired approximate intervals. It was better than the empirical lookup at p=0.01/0.02; its observed worse result at p=0.003 versus lookup is statistically inconclusive. Repetition predictions had identical error outcomes. These are small model/data experiments, not an ML superiority claim.

## CI and the merged setup PR

[PR #1](https://github.com/hamza2829/qec-simulation-lab/pull/1) was merged on 3 November 2026 (Europe/Berlin; GitHub UTC timestamp 2026-11-02T23:17:42Z) after [its CI run](https://github.com/hamza2829/qec-simulation-lab/actions/runs/41544017792) passed both Python versions. The post-merge [main-branch run 41544300363](https://github.com/hamza2829/qec-simulation-lab/actions/runs/41544300363) **completed successfully** for commit `9b6f56dfec49132f4a06e1b56ea704a818e2f922`. Later README/docs-only commits save this evidence without changing tested source or the measured experiment.

| Environment | Tests | Passed | Failed | Errors | Skipped |
|---|---:|---:|---:|---:|---:|
| Local Python 3.11 | 71 | 71 | 0 | 0 | 0 |
| CI Python 3.10 | 71 | 71 | 0 | 0 | 0 |
| CI Python 3.12 | 71 | 71 | 0 | 0 | 0 |

The CI counts were calculated from downloaded original JUnit XML, not source annotations. These are 71 distinct tests exercised in three environments; the two CI matrix jobs total 142 executions. Both CI runs in this build passed; no CI or pytest failure was hidden. Setup, estimator and plotting corrections remain described above.

Both matrix jobs passed Ruff lint/format, pytest and the reduced command `python -m qec run --quick --output artifacts/quick`. Each uploaded exactly five PNG plots plus JSON, trained model checkpoints, `report.md`, and test XML. The job checked that committed full `results/` files were unchanged. Downloaded run metadata confirms `torch=2.10.0+cpu`, `device=cpu`, and `torch_cuda_build=null` on both versions. No Docker, accelerator, quantum hardware, or quantum-cloud account was used.

Original [XML and quick-run CPU metadata](ci-evidence/) are committed alongside a [machine-counted summary](ci-results.json). The [main run's artifacts](https://github.com/hamza2829/qec-simulation-lab/actions/runs/41544300363#artifacts) contain the quick plots/reports. They use 1,000 surface shots per point, 100 bootstrap replicates, and much smaller ML datasets; they are functionality checks, not validation of the full statistical conclusions. Full local JSON, plots and uncertainty remain under `results/`.
