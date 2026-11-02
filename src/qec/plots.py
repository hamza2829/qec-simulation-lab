from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def _finish(fig, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=170, bbox_inches="tight")
    plt.close(fig)


def _rate_curve(ax, x, records, label, **kwargs):
    rates = np.array([row["logical_error_rate"] for row in records])
    lower = np.array([row["ci95"][0] for row in records])
    upper = np.array([row["ci95"][1] for row in records])
    positive = rates > 0
    error = np.maximum(0, np.array([rates - lower, upper - rates]))
    line = ax.errorbar(
        np.asarray(x)[positive],
        rates[positive],
        yerr=error[:, positive],
        label=label,
        marker="o",
        capsize=2,
        **kwargs,
    )
    if np.any(~positive):
        ax.scatter(
            np.asarray(x)[~positive],
            upper[~positive],
            marker="v",
            facecolors="none",
            edgecolors=line.lines[0].get_color(),
        )


def write_plots(data: dict, directory: Path) -> list[str]:
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    names = []
    fig, ax = plt.subplots(figsize=(8, 5))
    for distance in (3, 5, 7, 9):
        rows = [row for row in data["repetition"] if row["distance"] == distance]
        _rate_curve(
            ax,
            [row["physical_error_rate"] for row in rows],
            [row["majority"] for row in rows],
            f"d={distance}; majority=lookup",
        )
    # On a log-y axis, joining only two endpoints would draw an exponential,
    # not the intended unencoded probability y=p. Sample the reference densely.
    reference = np.linspace(0.005, 0.5, 300)
    ax.plot(reference, reference, "--", color="black", label="Unencoded: p")
    ax.axvline(0.5, linestyle=":", color="gray", label="Analytical break-even p=0.5")
    ax.set(
        yscale="log",
        xlabel="Physical bit-flip probability p",
        ylabel="Logical failure per memory trial",
        title="Repetition code capacity · perfect checks",
    )
    ax.legend(fontsize=8)
    ax.grid(alpha=0.2)
    fig.text(
        0.01,
        -0.015,
        "95% Wilson bars; hollow triangles show upper limits when zero failures were observed.",
        fontsize=8,
    )
    name = "repetition.png"
    _finish(fig, directory / name)
    names.append(name)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4), sharey=True)
    for ax, distance in zip(axes, (3, 5), strict=True):
        rows = [
            row
            for row in data["phenomenological"]
            if row["distance"] == distance and row["rounds"] == 5
        ]
        for key, label in (
            ("viterbi", "Full noisy history (Viterbi path)"),
            ("last_noisy_syndrome", "Trust last noisy syndrome"),
            ("final_majority", "Perfect-final-readout majority"),
        ):
            _rate_curve(
                ax,
                [row["measurement_error_rate"] for row in rows],
                [row[key] for row in rows],
                label,
            )
        ax.set(
            xlabel="Measurement-error probability per check",
            title=f"d={distance}, 5 rounds, data p=0.02",
        )
        ax.grid(alpha=0.2)
    axes[0].set_ylabel("Logical failure per full experiment")
    axes[1].legend(fontsize=8)
    fig.suptitle("NumPy phenomenological noise · perfect final data readout")
    fig.text(
        0.01,
        -0.03,
        "95% Wilson bars; hollow triangles are upper limits for zero observed failures.",
        fontsize=8,
    )
    name = "phenomenological.png"
    _finish(fig, directory / name)
    names.append(name)

    fig, ax = plt.subplots(figsize=(8, 5))
    for distance in (3, 5, 7):
        rows = [row for row in data["surface"] if row["distance"] == distance]
        _rate_curve(
            ax,
            [100 * row["physical_error_rate"] for row in rows],
            rows,
            f"d={distance}, rounds={distance}",
        )
    primary = data["thresholds"]["pairs"]["5-7"]
    if primary["estimate"] is not None:
        ax.axvline(
            100 * primary["estimate"],
            linestyle=":",
            color="black",
            label="Finite-size d=5/7 crossing",
        )
    if primary["conditional_ci95"]:
        low, high = primary["conditional_ci95"]
        ax.axvspan(100 * low, 100 * high, alpha=0.15, color="black")
    ax.set(
        yscale="log",
        xlabel="Circuit noise parameter p (%)",
        ylabel="Logical failure per d-round memory",
        title="Rotated surface-code Z memory · MWPM",
    )
    ax.grid(alpha=0.2)
    ax.legend(fontsize=8)
    fig.text(
        0.01,
        -0.015,
        "95% Wilson bars; crossing band is a statistical bootstrap interval, excluding finite-size/model bias.",
        fontsize=8,
    )
    name = "surface_code.png"
    _finish(fig, directory / name)
    names.append(name)

    fig, ax = plt.subplots(figsize=(7, 4.5))
    calibration = data["scaling_calibration"]
    per_round = [
        {
            "logical_error_rate": row["logical_error_rate"] / row["rounds"],
            "ci95": [value / row["rounds"] for value in row["ci95"]],
        }
        for row in calibration
    ]
    _rate_curve(
        ax,
        [row["distance"] for row in calibration],
        per_round,
        "Measured per-round small-error proxy",
        linestyle="none",
    )
    fit = data["scaling"]
    d = np.linspace(3, 7, 100)
    ax.plot(
        d,
        fit["A"] / fit["suppression_factor_per_distance_plus_2"] ** ((d + 1) / 2),
        label=f"Log fit: suppression {fit['suppression_factor_per_distance_plus_2']:.2f} per +2 distance",
    )
    ax.set(
        yscale="log",
        xlabel="Code distance d",
        ylabel="P_block / rounds",
        title=f"Below-threshold calibration · p={fit['reference_p']}",
        xticks=[3, 5, 7],
    )
    ax.legend(fontsize=8)
    ax.grid(alpha=0.2)
    name = "scaling.png"
    _finish(fig, directory / name)
    names.append(name)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    for ax, result in zip(axes, data["ml"], strict=True):
        x = np.arange(len(result["evaluation"]))
        for offset, key in enumerate(("ml", "pymatching", "lookup")):
            records = [row[key] for row in result["evaluation"]]
            rates = np.array([row["logical_error_rate"] for row in records])
            yerr = np.maximum(
                0,
                np.array(
                    [
                        [rate - row["ci95"][0] for rate, row in zip(rates, records, strict=True)],
                        [row["ci95"][1] - rate for rate, row in zip(rates, records, strict=True)],
                    ]
                ),
            )
            ax.bar(x + (offset - 1) * 0.25, rates, width=0.23, yerr=yerr, capsize=2, label=key)
        ax.set(
            xticks=x,
            xticklabels=[str(row["physical_error_rate"]) for row in result["evaluation"]],
            xlabel="Physical p on held-out test shots",
            ylabel="Logical error per experiment",
            title=f"{result['code']} d=3; train p={result['training_physical_p']}",
        )
        ax.grid(axis="y", alpha=0.2)
    axes[1].legend(fontsize=8)
    fig.suptitle("Small CPU MLP experiment · same test shots for all decoders")
    name = "ml_comparison.png"
    _finish(fig, directory / name)
    names.append(name)
    return names
