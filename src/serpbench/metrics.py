"""Statistics and helpers. Pure functions, no I/O, easy to test.

Everything here is deliberately small and dependency-free so that a reader can
verify each formula against its textbook definition.
"""
from __future__ import annotations

import math
import random
import statistics
from collections.abc import Callable, Iterable, Sequence
from urllib.parse import urlsplit

from .providers import NormalizedResult

NAN = float("nan")


def percentile(values: Sequence[float], q: float) -> float:
    """Percentile with linear interpolation between closest ranks (q in 0..100).

    Same definition as numpy's default ("linear") method.
    """
    if not values:
        return NAN
    s = sorted(values)
    if len(s) == 1:
        return float(s[0])
    k = (len(s) - 1) * q / 100.0
    lo, hi = math.floor(k), math.ceil(k)
    if lo == hi:
        return float(s[int(k)])
    return float(s[lo] + (s[hi] - s[lo]) * (k - lo))


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion (95% by default).

    Preferred over the normal approximation because it behaves sensibly for
    small n and for proportions near 0 or 1, which is exactly where API
    success rates live.
    """
    if n <= 0:
        return (NAN, NAN)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def bootstrap_ci(
    values: Sequence[float],
    stat: Callable[[Sequence[float]], float] = statistics.median,
    n_boot: int = 2000,
    alpha: float = 0.05,
    seed: int = 0,
) -> tuple[float, float]:
    """Percentile bootstrap confidence interval for `stat` (seeded, reproducible)."""
    if not values:
        return (NAN, NAN)
    if len(values) == 1:
        return (float(values[0]), float(values[0]))
    rng = random.Random(seed)
    n = len(values)
    stats = sorted(stat([values[rng.randrange(n)] for _ in range(n)]) for _ in range(n_boot))
    lo = stats[int((alpha / 2) * n_boot)]
    hi = stats[min(n_boot - 1, int((1 - alpha / 2) * n_boot))]
    return (float(lo), float(hi))


def normalize_url(url: str) -> str:
    """Canonical form used for cross-provider overlap.

    Lower-cases the host, drops `www.`, the scheme, the fragment, a trailing
    slash and tracking parameters (utm_*, gclid, fbclid). Everything else is
    kept: two different paths are two different results.
    """
    try:
        p = urlsplit(url.strip())
    except ValueError:
        return url.strip().lower()
    host = (p.hostname or "").lower()
    host = host.removeprefix("www.")
    path = p.path.rstrip("/")
    params = sorted(
        kv for kv in p.query.split("&")
        if kv and not kv.lower().startswith(("utm_", "gclid", "fbclid"))
    )
    return host + path + (("?" + "&".join(params)) if params else "")


def jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return NAN
    return len(sa & sb) / len(sa | sb)


def completeness(results: Sequence[NormalizedResult]) -> dict[str, float]:
    """Share of organic results that carry a non-empty title, link and snippet."""
    n = len(results)
    if n == 0:
        return {"title": 0.0, "link": 0.0, "snippet": 0.0, "overall": 0.0}
    title = sum(1 for r in results if r.title.strip()) / n
    link = sum(1 for r in results if r.link.strip()) / n
    snippet = sum(1 for r in results if r.snippet.strip()) / n
    return {
        "title": title,
        "link": link,
        "snippet": snippet,
        "overall": (title + link + snippet) / 3,
    }


def clean(x: float | None, ndigits: int = 4) -> float | None:
    """NaN -> None so that JSON stays standards-compliant."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    return round(x, ndigits)
