import math

from serpbench.metrics import (
    bootstrap_ci,
    completeness,
    jaccard,
    normalize_url,
    percentile,
    wilson_interval,
)
from serpbench.providers import NormalizedResult


def test_percentile_matches_linear_interpolation():
    v = [10, 20, 30, 40, 50]
    assert percentile(v, 0) == 10
    assert percentile(v, 50) == 30
    assert percentile(v, 100) == 50
    assert percentile(v, 25) == 20
    assert math.isclose(percentile([1, 2], 50), 1.5)
    assert math.isnan(percentile([], 50))


def test_wilson_known_value():
    lo, hi = wilson_interval(95, 100)
    assert math.isclose(lo, 0.8883, abs_tol=1e-3)
    assert math.isclose(hi, 0.9785, abs_tol=1e-3)
    assert wilson_interval(0, 10)[0] == 0.0
    assert wilson_interval(10, 10)[1] == 1.0


def test_bootstrap_is_seeded_and_brackets_median():
    data = [float(x) for x in range(1, 101)]
    a = bootstrap_ci(data, seed=7)
    assert a == bootstrap_ci(data, seed=7)
    assert a[0] <= 50.5 <= a[1]


def test_normalize_url():
    assert normalize_url("https://www.Example.com/path/?utm_source=x&b=1&a=2#frag") == \
        "example.com/path?a=2&b=1"
    assert normalize_url("http://example.com/path") == normalize_url("https://www.example.com/path/")


def test_jaccard():
    assert jaccard(["a", "b"], ["b", "c"]) == 1 / 3
    assert math.isnan(jaccard([], []))


def test_completeness():
    rs = [NormalizedResult(1, "t", "l", "s"), NormalizedResult(2, "t", "l", "")]
    c = completeness(rs)
    assert c["snippet"] == 0.5 and c["title"] == 1.0
