# Verification history

The first repository commit wrote `docs/concepts.md` and froze `docs/experiment-plan.md` before committing implementation or running the full sweep. The scientific settings are unchanged from that plan.

- Initial CPU-Torch installation failed because the CPU-only package index lacked a transitive dependency's build backend (`flit_core`). Installing the pinned Torch CPU wheel with `--no-deps`, then resolving normal dependencies from PyPI, succeeded. Torch reports `2.10.0+cpu`, with no CUDA build.
- An initial few-shot smoke run completed and exposed an estimator issue: touching/equal sampled rates could be called a crossing without a sign change. The estimator now requires opposite signs on either side, including across exact-equality points. A zero-count plateau or tangent does not manufacture a threshold. A regression test covers this. The sweep grid and seeds were not altered.
- First pytest run: **71 passed, 0 failed, 0 errors, 0 skipped**. Tests include exhaustive protected-channel repetition patterns through half distance, all single initial surface-data X faults at d=3/5, seeded noise/decoder checks, confidence intervals/crossings/scaling, resource formulas, CPU MLP save/load/predict, and five plot files from actual small experiments.
- Ruff initially identified import ordering, multi-statement formatting and a loop-variable closure in report formatting. These were fixed before committing source.

Full-run measured results and CI evidence will be appended after execution. Quick-profile crossings and fits are explicitly smoke results, not the full experiment's scientific conclusions.
