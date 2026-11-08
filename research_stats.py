"""Uncertainty for the research tools: how sure a share or a difference is, from the numbers alone.

Standard library only, deterministic (bootstrap draws come from a seeded generator), and small on purpose:

- wilson(k, n): a 95% interval for a share k/n that stays sensible at 0/n, n/n and small n;
- share(k, n): the share with its interval, as the reports write it;
- bootstrap(values, statistic): an interval for a mean, median or any statistic of per-round values;
- bootstrap_difference(a, b, statistic): the same for the difference between two groups of rounds;
- mcnemar(b, c): an exact two-sided p for paired yes/no outcomes (the same moments asked two ways), where b and c
  count the moments that changed one way and the other;
- paired(first, second): b, c and that p from two lists of yes/no outcomes on the same moments;
- per_arm_rounds(p1, p2): how many moments or rounds per arm find a difference between two shares.

Reports state the interval next to the share, so a share from 5 moments reads as what it is.
"""
from __future__ import annotations
import math
import random
from statistics import NormalDist, mean, median

Z95 = NormalDist().inv_cdf(.975)


def wilson(k, n, z=Z95):
    """The Wilson score interval for k successes in n, rounded to 3 places; None for n == 0."""
    if not n:
        return None
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(max(0., centre - half), 3), round(min(1., centre + half), 3)]


def share(k, n):
    """{'k', 'n', 'share', 'ci95'}: a share as the reports write it (share and ci95 None for n == 0)."""
    return {'k': k, 'n': n, 'share': round(k / n, 3) if n else None, 'ci95': wilson(k, n)}


def _percentile(sorted_values, q):
    """The q-quantile (0..1) of sorted values, by linear interpolation."""
    position = (len(sorted_values) - 1) * q
    low, high = math.floor(position), math.ceil(position)
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (position - low)


def bootstrap(values, statistic=mean, draws=2000, seed=0, level=.95):
    """A percentile bootstrap interval for statistic(values), rounded to 3 places; None for no values."""
    values = list(values)
    if not values:
        return None
    rng = random.Random(seed)
    stats = sorted(statistic(rng.choices(values, k=len(values))) for _ in range(draws))
    tail = (1 - level) / 2
    return [round(_percentile(stats, tail), 3), round(_percentile(stats, 1 - tail), 3)]


def bootstrap_difference(a, b, statistic=mean, draws=2000, seed=0, level=.95):
    """A percentile bootstrap interval for statistic(b) - statistic(a), each group resampled on its own."""
    a, b = list(a), list(b)
    if not a or not b:
        return None
    rng = random.Random(seed)
    stats = sorted(statistic(rng.choices(b, k=len(b))) - statistic(rng.choices(a, k=len(a))) for _ in range(draws))
    tail = (1 - level) / 2
    return [round(_percentile(stats, tail), 3), round(_percentile(stats, 1 - tail), 3)]


def mcnemar(b, c):
    """The exact two-sided McNemar p for b moments that went no -> yes and c that went yes -> no (binomial, p = 1/2)."""
    n = b + c
    if not n:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n
    return round(min(1.0, 2 * tail), 4)


def paired(first, second):
    """Yes/no outcomes of the same moments under two arms (None where either has no answer): counts and McNemar p."""
    both = [(x, y) for x, y in zip(first, second) if x is not None and y is not None]
    b = sum(1 for x, y in both if not x and y)
    c = sum(1 for x, y in both if x and not y)
    return {'moments': len(both), 'only_second': b, 'only_first': c,
            'difference': round((b - c) / len(both), 3) if both else None, 'mcnemar_p': mcnemar(b, c)}


def per_arm_rounds(p1, p2, alpha=.05, power=.8):
    """Moments or rounds per arm to tell share p1 from p2 (two-sided, normal approximation); None if they are equal."""
    if p1 == p2:
        return None
    za, zb = NormalDist().inv_cdf(1 - alpha / 2), NormalDist().inv_cdf(power)
    p = (p1 + p2) / 2
    n = (za * math.sqrt(2 * p * (1 - p)) + zb * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2 / (p1 - p2) ** 2
    return math.ceil(n)


STATISTICS = {'mean': mean, 'median': median}
