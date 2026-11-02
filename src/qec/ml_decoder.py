"""Small supervised logical-observable classifiers, always on CPU."""

import time
from pathlib import Path

import numpy as np
import stim
import torch
from torch import nn

from qec.code_capacity import lookup_decode
from qec.statistics import rate_record
from qec.surface_code import matching_decoder, memory_circuit, sample_memory


def repetition_circuit(p: float) -> stim.Circuit:
    """Prepared logical 0, independent X noise, perfect final checks/readout.

    The detector bits are adjacent data parities. Observable 0 is the first
    physical bit, so predicting its flip is equivalent to applying a correction.
    """
    if not 0 <= p <= 0.5:
        raise ValueError("Use 0<=p<=0.5")
    return stim.Circuit(f"""
        R 0 1 2
        X_ERROR({p}) 0 1 2
        M 0 1 2
        DETECTOR rec[-3] rec[-2]
        DETECTOR rec[-2] rec[-1]
        OBSERVABLE_INCLUDE(0) rec[-3]
    """)


def make_network(input_dim: int) -> nn.Sequential:
    return nn.Sequential(
        nn.Linear(input_dim, 32), nn.ReLU(), nn.Linear(32, 16), nn.ReLU(), nn.Linear(16, 1)
    )


class MLPDecoder:
    def __init__(self, input_dim: int, threshold: float = 0.5) -> None:
        if input_dim < 1 or not 0 < threshold < 1:
            raise ValueError("Invalid input dimension or threshold")
        self.input_dim = input_dim
        self.threshold = threshold
        self.model = make_network(input_dim).cpu()

    def probabilities(self, detectors: np.ndarray) -> np.ndarray:
        values = np.asarray(detectors)
        if (
            values.ndim != 2
            or values.shape[1] != self.input_dim
            or np.any((values != 0) & (values != 1))
        ):
            raise ValueError("Expected binary shots by detector features")
        self.model.eval()
        with torch.no_grad():
            return (
                torch.sigmoid(self.model(torch.tensor(values, dtype=torch.float32, device="cpu")))
                .squeeze(1)
                .numpy()
            )

    def predict(self, detectors: np.ndarray) -> np.ndarray:
        return (self.probabilities(detectors) >= self.threshold).astype(np.uint8)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "schema_version": 1,
                "input_dim": self.input_dim,
                "threshold": self.threshold,
                "state_dict": self.model.state_dict(),
            },
            path,
        )

    @classmethod
    def load(cls, path: Path) -> "MLPDecoder":
        data = torch.load(path, map_location="cpu", weights_only=True)
        if data["schema_version"] != 1:
            raise ValueError("Unsupported checkpoint schema")
        decoder = cls(data["input_dim"], data["threshold"])
        decoder.model.load_state_dict(data["state_dict"])
        decoder.model.eval()
        return decoder


def train_mlp(
    train_x: np.ndarray,
    train_y: np.ndarray,
    val_x: np.ndarray,
    val_y: np.ndarray,
    epochs: int,
    seed: int,
) -> tuple[MLPDecoder, dict]:
    if (
        epochs < 1
        or len(train_x) != len(train_y)
        or len(val_x) != len(val_y)
        or not len(train_x)
        or not len(val_x)
    ):
        raise ValueError("Need nonempty matched training/validation samples and positive epochs")
    torch.set_num_threads(1)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)
    decoder = MLPDecoder(train_x.shape[1])
    x = torch.tensor(train_x, dtype=torch.float32, device="cpu")
    y = torch.tensor(train_y, dtype=torch.float32, device="cpu").reshape(-1, 1)
    optimizer = torch.optim.Adam(decoder.model.parameters(), lr=0.003)
    loss_function = nn.BCEWithLogitsLoss()
    generator = torch.Generator(device="cpu").manual_seed(seed)
    losses = []
    start = time.perf_counter()
    for _ in range(epochs):
        decoder.model.train()
        order = torch.randperm(len(x), generator=generator)
        total_loss = 0.0
        for indices in order.split(1024):
            optimizer.zero_grad()
            loss = loss_function(decoder.model(x[indices]), y[indices])
            loss.backward()
            optimizer.step()
            total_loss += float(loss.detach()) * len(indices)
        losses.append(total_loss / len(x))
    probabilities = decoder.probabilities(val_x)
    candidates = np.arange(0.05, 1.0, 0.05)
    best = min(
        candidates,
        key=lambda threshold: (
            int(np.count_nonzero((probabilities >= threshold) != val_y)),
            abs(threshold - 0.5),
            threshold,
        ),
    )
    decoder.threshold = float(best)
    return decoder, {
        "seed": seed,
        "epochs": epochs,
        "batch_size": 1024,
        "learning_rate": 0.003,
        "hidden_units": [32, 16],
        "device": "cpu",
        "training_shots": len(train_x),
        "validation_shots": len(val_x),
        "training_positive_fraction": float(np.mean(train_y)),
        "validation_selected_threshold": float(best),
        "validation_failures_after_selection": int(
            np.count_nonzero(decoder.predict(val_x) != val_y)
        ),
        "parameter_count": sum(parameter.numel() for parameter in decoder.model.parameters()),
        "epoch_mean_bce": losses,
        "elapsed_seconds": time.perf_counter() - start,
    }


def syndrome_keys(detectors: np.ndarray) -> list[bytes]:
    return [row.tobytes() for row in np.packbits(detectors, axis=1, bitorder="little")]


def empirical_lookup(train_x: np.ndarray, train_y: np.ndarray) -> dict[bytes, int]:
    counts: dict[bytes, list[int]] = {}
    for key, label in zip(syndrome_keys(train_x), train_y, strict=True):
        pair = counts.setdefault(key, [0, 0])
        pair[int(label)] += 1
    return {key: int(ones > zeros) for key, (zeros, ones) in counts.items()}


def lookup_predict(table: dict[bytes, int], detectors: np.ndarray) -> tuple[np.ndarray, float]:
    keys = syndrome_keys(detectors)
    predicted = np.array([table.get(key, 0) for key in keys], dtype=np.uint8)
    return predicted, sum(key not in table for key in keys) / len(keys)


def paired_comparison(ml_errors: np.ndarray, baseline_errors: np.ndarray) -> dict:
    delta = ml_errors.astype(float) - baseline_errors.astype(float)
    mean = float(delta.mean())
    variance = max(0.0, float(np.mean(delta * delta) - mean * mean))
    radius = 1.959963984540054 * np.sqrt(variance / len(delta))
    ci = [float(max(-1.0, mean - radius)), float(min(1.0, mean + radius))]
    discordant = int(np.count_nonzero(delta))
    observed = "better" if mean < 0 else "worse" if mean > 0 else "equal observed rate"
    return {
        "observed": observed,
        "ml_minus_baseline_error_rate": mean,
        "paired_approx_ci95": ci,
        "ml_only_failures": int(np.count_nonzero(delta > 0)),
        "baseline_only_failures": int(np.count_nonzero(delta < 0)),
        "identical_error_outcomes": discordant == 0,
        "difference_supported_by_approx_ci": bool(discordant >= 25 and (ci[0] > 0 or ci[1] < 0)),
        "caution": "Normal paired interval; sparse discordances are inconclusive; equality is not an equivalence test",
    }


def run_ml_experiments(
    output: Path, train_shots: int, val_shots: int, test_shots: int, epochs: int, seed: int
) -> list[dict]:
    results = []
    for code_index, code in enumerate(("repetition", "surface")):
        base = seed + 1000 * code_index
        train_p = 0.10 if code == "repetition" else 0.01
        generate = repetition_circuit if code == "repetition" else lambda p: memory_circuit(3, p, 3)
        circuit = generate(train_p)
        train_x, train_y = sample_memory(circuit, train_shots, base + 1)
        val_x, val_y = sample_memory(circuit, val_shots, base + 2)
        decoder, training = train_mlp(train_x, train_y, val_x, val_y, epochs, base + 3)
        model_path = output / "models" / f"{code}_d3.pt"
        decoder.save(model_path)
        table = empirical_lookup(train_x, train_y)
        evaluation = []
        probabilities = (0.01, 0.05, 0.10) if code == "repetition" else (0.003, 0.01, 0.02)
        for i, p in enumerate(probabilities):
            test_circuit = generate(p)
            test_x, actual = sample_memory(test_circuit, test_shots, base + 10 + i)
            ml = decoder.predict(test_x)
            matching = matching_decoder(test_circuit).decode_batch(test_x)[:, 0]
            if code == "repetition":
                lookup = lookup_decode(test_x)[:, 0]
                unseen = 0.0
            else:
                lookup, unseen = lookup_predict(table, test_x)
            ml_errors, matching_errors, lookup_errors = (
                ml != actual,
                matching != actual,
                lookup != actual,
            )
            evaluation.append(
                {
                    "physical_error_rate": p,
                    "test_seed": base + 10 + i,
                    "actual_observable_flip_fraction": float(actual.mean()),
                    "ml": rate_record(int(ml_errors.sum()), test_shots),
                    "pymatching": rate_record(int(matching_errors.sum()), test_shots),
                    "lookup": rate_record(int(lookup_errors.sum()), test_shots),
                    "lookup_unseen_fraction": unseen,
                    "ml_vs_pymatching": paired_comparison(ml_errors, matching_errors),
                    "ml_vs_lookup": paired_comparison(ml_errors, lookup_errors),
                }
            )
        results.append(
            {
                "code": code,
                "distance": 3,
                "training_physical_p": train_p,
                "train_sampler_seed": base + 1,
                "validation_sampler_seed": base + 2,
                "lookup_type": "exact minimum weight"
                if code == "repetition"
                else "training-only empirical table; ties/unseen=0",
                "detector_features": circuit.num_detectors,
                "training": training,
                "checkpoint": (Path("models") / model_path.name).as_posix(),
                "evaluation": evaluation,
            }
        )
    return results
