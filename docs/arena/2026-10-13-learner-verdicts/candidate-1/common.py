"""Shared helpers for the "every saved rule" simulations.

Units: every strategy's daily excess return is r_i = mu_i + s * (sqrt(rho) f + sqrt(1 - rho) e_i).
The common factor f cancels in a difference, so a pair's daily difference in units of
s * sqrt(1 - rho) is x = Delta + e_j - e_k, with Delta = d / (sqrt(252) * sqrt(1 - rho)) for a
true excess Sharpe advantage d. A null pair's z does not depend on rho; power does.
"""

import math

import numpy as np

YEAR = 252
BLOCK = 20
MIN_SESSIONS = 3 * BLOCK
LEVEL = 0.95
N_CATALOG = 8
MS = (10, 100, 1_000, 10_000)
HORIZONS = (1, 3, 5)
DS = (0.3, 0.5, 1.0)
RHOS = (0.75, 0.25)


def delta(d: float, rho: float) -> float:
    return d / (math.sqrt(YEAR) * math.sqrt(1 - rho))


def norm_sf(z: float) -> float:
    return 0.5 * math.erfc(z / math.sqrt(2))


def norm_cdf(z: float) -> float:
    return 1 - norm_sf(z)


def _betacf(a: float, b: float, x: float) -> float:
    tiny = 1e-300
    c, d = 1.0, 1.0 - (a + b) * x / (a + 1)
    d = 1 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 500):
        m2 = 2 * m
        aa = m * (b - m) * x / ((a + m2 - 1) * (a + m2))
        d = 1 + aa * d
        d = 1 / (d if abs(d) > tiny else tiny)
        c = 1 + aa / c
        c = c if abs(c) > tiny else tiny
        h *= d * c
        aa = -(a + m) * (a + b + m) * x / ((a + m2) * (a + m2 + 1))
        d = 1 + aa * d
        d = 1 / (d if abs(d) > tiny else tiny)
        c = 1 + aa / c
        c = c if abs(c) > tiny else tiny
        delta_ = d * c
        h *= delta_
        if abs(delta_ - 1) < 1e-15:
            break
    return h


def betainc(a: float, b: float, x: float) -> float:
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lbt = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x)
    if x < (a + 1) / (a + b + 2):
        return math.exp(lbt) * _betacf(a, b, x) / a
    return 1 - math.exp(lbt) * _betacf(b, a, 1 - x) / b


def t_sf(t: float, df: float) -> float:
    """P(T > t) for t >= 0."""
    return 0.5 * betainc(df / 2, 0.5, df / (df + t * t))


def t_isf(p: float, df: float) -> float:
    """t with P(T > t) = p, by bisection in log space."""
    lo, hi = 0.0, 1e7
    for _ in range(200):
        mid = 0.5 * (lo + hi) if hi < 10 else math.sqrt(max(lo, 1e-9) * hi)
        if t_sf(mid, df) > p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def t_cutoff(c_gauss: float, blocks: int) -> float:
    """The small-sample cutoff for a pair with `blocks` complete blocks.

    It has the same two-sided tail probability under the pair's own reference distribution,
    t with blocks - 1 degrees of freedom scaled by sqrt(blocks / (blocks - 1)) (the bootstrap sd
    divides by blocks, not blocks - 1), as c_gauss has under the normal.
    """
    p = norm_sf(c_gauss)
    return math.sqrt(blocks / (blocks - 1)) * t_isf(p, blocks - 1)


def crit_table_lookup(table: dict[int, float], m: int) -> float:
    """Interpolate a critical value by log family size. table maps rules -> critical value."""
    if m <= 0:
        return 0.0
    keys = sorted(table)
    if m <= keys[0]:
        return table[keys[0]]
    if m >= keys[-1]:
        return table[keys[-1]]
    lx = [math.log(k) for k in keys]
    return float(np.interp(math.log(m), lx, [table[k] for k in keys]))
