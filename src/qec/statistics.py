from math import sqrt


def wilson_interval(failures: int, shots: int) -> list[float]:
    """Two-sided 95% Wilson score interval; zero counts keep a nonzero upper bound."""
    if type(shots) is not int or shots <= 0 or not 0 <= failures <= shots:
        raise ValueError("Need 0 <= failures <= positive shots")
    z = 1.959963984540054
    p = failures / shots
    denominator = 1 + z * z / shots
    center = (p + z * z / (2 * shots)) / denominator
    radius = z * sqrt(p * (1 - p) / shots + z * z / (4 * shots * shots)) / denominator
    return [
        0.0 if failures == 0 else max(0.0, center - radius),
        1.0 if failures == shots else min(1.0, center + radius),
    ]


def rate_record(failures: int, shots: int) -> dict:
    return {
        "failures": int(failures),
        "shots": int(shots),
        "logical_error_rate": failures / shots,
        "ci95": wilson_interval(int(failures), int(shots)),
    }
