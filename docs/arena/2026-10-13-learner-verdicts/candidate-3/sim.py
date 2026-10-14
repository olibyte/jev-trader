"""Candidate 3: one learner's rules. Synthetic measurements for proposal.md.

A learner rule's verdict uses a simultaneous 95% interval over the pairs (rule i, catalog c)
for every rule i that the same account has saved and every catalog entry c (8 entries).

Model (shared setup): r_i = mu_i + s * (sqrt(rho) f + sqrt(1 - rho) e_i). Under this model the
excess Sharpe difference of a pair over T sessions is Gaussian with
SE = sqrt(2 (1 - rho) / (T / 252)), and z_ic = (U_i - V_c) / sqrt(2 T) where U, V are cumulative
sums of the idiosyncratic shocks. The correlation between pair z's does not depend on rho, so
the critical value and every null rate are the same at rho 0.75 and 0.25. rho changes power.

Run: uv run python sim.py
"""

import math
import sys
import time

import numpy as np

YEAR, BLOCK, LOOK0 = 252, 20, 60  # 3 blocks of 20 sessions before any verdict
CAT = 8
LEVEL = 0.95
RHOS = (0.75, 0.25)
HORIZONS = (1, 3, 5)
KS = (1, 5, 50)
DS = (0.3, 0.5, 1.0)


def phi(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def crit(k: int, n: int = 400_000, seed: int = 1) -> float:
    """Gaussian max-|z| critical value for k rules x CAT catalog pairs on one shared window."""
    rng = np.random.default_rng(seed)
    out = np.empty(n)
    step = max(1, 2_000_000 // (k + CAT))
    for a in range(0, n, step):
        m = min(step, n - a)
        u = rng.standard_normal((m, k), dtype=np.float32)
        v = rng.standard_normal((m, CAT), dtype=np.float32)
        out[a : a + m] = np.maximum(u.max(1) - v.min(1), v.max(1) - u.min(1)) / math.sqrt(2)
    return float(np.quantile(out, LEVEL))


def crit_catalog(n_strat: int, n: int = 400_000, seed: int = 2) -> float:
    """Gaussian max-|z| critical value over all pairs among n_strat strategies."""
    v = np.random.default_rng(seed).standard_normal((n, n_strat))
    return float(np.quantile((v.max(1) - v.min(1)) / math.sqrt(2), LEVEL))


def null_paths(k: int, c: float, reps: int, seed: int) -> dict:
    """All-null learner with k rules saved on one day. Nightly looks from session 60 to 5 years.

    Returns per horizon: single look at the horizon and ever at any nightly look, for
    'any' (any of the 8k verdicts is not Too close to call) and 'win' (some rule shows A wins),
    plus the per-rule rate of showing a win at the horizon.
    """
    T = 5 * YEAR
    rng = np.random.default_rng(seed)
    t = np.arange(1, T + 1, dtype=np.float32)
    sq = np.sqrt(2 * t)
    res = {h: dict(any1=0, win1=0, anyE=0, winE=0, rule1=0) for h in HORIZONS}
    chunk = max(20, 6_000_000 // ((k + CAT) * T))
    done = 0
    while done < reps:
        m = min(chunk, reps - done)
        U = np.cumsum(rng.standard_normal((m, k, T), dtype=np.float32), axis=2)
        V = np.cumsum(rng.standard_normal((m, CAT, T), dtype=np.float32), axis=2)
        up = (U.max(1) - V.min(1)) / sq  # largest "rule ahead" z each night
        dn = (V.max(1) - U.min(1)) / sq  # largest "catalog ahead" z each night
        anyz = np.maximum(up, dn)
        for h in HORIZONS:
            e = h * YEAR
            res[h]["any1"] += int((anyz[:, e - 1] > c).sum())
            res[h]["win1"] += int((up[:, e - 1] > c).sum())
            res[h]["anyE"] += int((anyz[:, LOOK0 - 1 : e] > c).any(1).sum())
            res[h]["winE"] += int((up[:, LOOK0 - 1 : e] > c).any(1).sum())
            zr = (U[:, :, e - 1] - V[:, :, e - 1].min(1)[:, None]) / sq[e - 1]
            res[h]["rule1"] += int((zr > c).sum())
        done += m
    for h in HORIZONS:
        for key in ("any1", "win1", "anyE", "winE"):
            res[h][key] /= reps
        res[h]["rule1"] /= reps * k
    return res


def power(k: int, c: float, d: float, rho: float, years: int, reps: int, seed: int) -> float:
    """P(the edge rule's interval against buy and hold lies above zero) at the horizon.

    The learner has k rules: one with true advantage d over every catalog entry, k - 1 null.
    Only the edge rule's pair with buy and hold matters, so the other rules enter through c.
    """
    rng = np.random.default_rng(seed)
    se = math.sqrt(2 * (1 - rho) / years)
    z = (rng.standard_normal(reps) - rng.standard_normal(reps)) / math.sqrt(2) + d / se
    return float((z > c).mean())


def sequential(kmax: int, crits: dict, reps: int, seed: int, one_account: bool) -> float:
    """A person saves a new null rule every 20 sessions, up to kmax, and stops saving at the
    first night any rule shows "A wins". Returns P(some rule ever shows a win within 5 years).

    one_account: every rule shares one account, so the family grows with each save. The
    critical value uses the equal-window value for the current family size, which is slightly
    below the exact value for staggered windows, so this overstates the gamer's success.
    Otherwise each rule sits in its own account with the k = 1 critical value.
    """
    T = 5 * YEAR
    rng = np.random.default_rng(seed)
    hits = 0
    chunk = 40
    done = 0
    days = np.arange(T)
    while done < reps:
        m = min(chunk, reps - done)
        E = rng.standard_normal((m, kmax, T), dtype=np.float32)
        V = np.cumsum(rng.standard_normal((m, CAT, T), dtype=np.float32), axis=2)
        best = np.full((m, T), -np.inf, dtype=np.float32)  # max over rules of z - crit
        for j in range(kmax):
            s = j * BLOCK
            if s + LOOK0 > T:
                break
            Uj = np.zeros((m, T), dtype=np.float32)
            Uj[:, s:] = np.cumsum(E[:, j, s:], axis=1)
            base = V[:, :, s - 1] if s > 0 else np.zeros((m, CAT), dtype=np.float32)
            Vmin = (V - base[:, :, None]).min(1)
            n = (days - s + 1).astype(np.float32)
            z = np.full((m, T), -np.inf, dtype=np.float32)
            ok = n >= LOOK0
            z[:, ok] = (Uj[:, ok] - Vmin[:, ok]) / np.sqrt(2 * n[ok])
            best = np.maximum(best, z - (0 if one_account else crits[1]))
        if one_account:
            fam = np.minimum(days // BLOCK + 1, kmax)
            cvec = np.array([crits[f] for f in fam], dtype=np.float32)
            best = best - cvec
        # Stopping saving after a win only removes later rules, so "ever" is unchanged up to
        # the first win, and the first-win event is what we count.
        hits += int((best > 0).any(1).sum())
        done += m
    return hits / reps


def bootstrap_spot_check(k: int, years: int, rho: float, seeds: range) -> list[float]:
    """Critical value from the real block bootstrap (jevtrader code) on synthetic daily returns."""
    from jevtrader.catalog import critical_value
    from jevtrader.evaluate import block_bootstrap, sharpe

    out = []
    for sd in seeds:
        rng = np.random.default_rng(100 + sd)
        T = years * YEAR
        s = 0.01
        f = rng.standard_normal(T)
        r = 0.0003 + s * (
            math.sqrt(rho) * f + math.sqrt(1 - rho) * rng.standard_normal((k + CAT, T))
        )
        dates = np.arange(T)
        draws, points = [], []
        for i in range(k):
            for c in range(k, k + CAT):
                a, b = r[i], r[c]
                points.append(sharpe(a) - sharpe(b))
                draws.append(block_bootstrap(dates, lambda w, a=a, b=b: sharpe(a, w) - sharpe(b, w)))
        out.append(critical_value(np.array(draws), np.array(points)))
    return out


def nightly_cost(M: int, years: int = 5, reps: int = 2000, seed: int = 3) -> float:
    """Seconds for one night's bootstrap of M learner rules x 8 catalog pairs, vectorised.

    Rules have staggered save blocks. Each pair reads the shared block draw on its own window.
    Returns wall time for the draws of every pair (critical values per account are a groupby
    max on top and cost little).
    """
    rng = np.random.default_rng(seed)
    T = years * YEAR
    B = T // BLOCK
    x = (0.0003 + 0.01 * rng.standard_normal((M + CAT, B * BLOCK))).reshape(M + CAT, B, BLOCK)
    start = rng.integers(0, B - 3, size=M)
    S1 = x.sum(2).T  # B x N
    S2 = (x**2).sum(2).T
    for i in range(M):  # a rule has no returns before its save block
        S1[: start[i], i] = 0
        S2[: start[i], i] = 0
    t0 = time.perf_counter()
    W = np.zeros((reps, B))
    draw = rng.integers(B, size=(reps, B))
    for r in range(reps):
        W[r] = np.bincount(draw[r], minlength=B)
    W *= 1.0  # block weights on the shared calendar
    nb = np.zeros((B, M))
    for i in range(M):
        nb[start[i] :, i] = BLOCK

    def sh(a1, a2, n):
        mean = a1 / n
        return mean / np.sqrt((a2 - a1 * mean) / (n - 1)) * math.sqrt(YEAR)

    rule = sh(W @ S1[:, :M], W @ S2[:, :M], W @ nb)  # reps x M
    zmax = np.empty((reps, M), dtype=np.float32)
    for s in np.unique(start):
        idx = np.flatnonzero(start == s)
        Wm = W[:, s:]
        n = Wm.sum(1, keepdims=True) * BLOCK
        cat = sh(Wm @ S1[s:, M:], Wm @ S2[s:, M:], n)  # reps x CAT
        diff = rule[:, idx, None] - cat[:, None, :]  # reps x |idx| x CAT
        dev = np.abs(diff - diff.mean(0)) / diff.std(0, ddof=1)
        zmax[:, idx] = dev.max(2)
    _ = np.quantile(zmax, LEVEL, axis=0)  # stands in for the per-account max and quantile
    return time.perf_counter() - t0


def main() -> None:
    t0 = time.perf_counter()
    print("# Critical values (Gaussian max-|z|, 400k draws)")
    c4 = crit_catalog(4)
    c8 = crit_catalog(8)
    print(f"catalog 4 entries, 6 pairs: {c4:.3f}  (milestone 7 bootstrap: 2.53)")
    print(f"catalog 8 entries, 28 pairs: {c8:.3f}")
    crits = {k: crit(k) for k in range(1, 51)}
    for k in (1, 5, 50):
        print(f"learner with {k} rules, {8 * k} pairs: {crits[k]:.3f}")
    site = {M: crit(M, n=20_000) for M in (10, 100, 1000, 10_000)}
    for M, c in site.items():
        print(f"site-wide family, {M} rules, {8 * M} pairs: {c:.3f}")

    print("\n# Bootstrap spot check (jevtrader block_bootstrap + critical_value, 2000 reps)")
    for k, yrs in ((1, 3), (5, 3)):
        got = bootstrap_spot_check(k, yrs, 0.75, range(5))
        print(f"k={k}, {yrs}y, rho 0.75, 5 datasets: " + ", ".join(f"{g:.3f}" for g in got)
              + f"; mean {np.mean(got):.3f} vs Gaussian {crits[k]:.3f}")

    print("\n# Null learner, all k rules saved on one day (rates are the same for both rho)")
    print("k | horizon | any verdict, single | rule wins, single | per-rule win, single "
          "| any verdict, ever nightly | rule wins, ever nightly")
    nulls = {}
    for k in KS:
        nulls[k] = null_paths(k, crits[k], reps=6000, seed=10 + k)
        for h in HORIZONS:
            q = nulls[k][h]
            print(f"{k} | {h}y | {q['any1']:.3f} | {q['win1']:.3f} | {q['rule1']:.4f} "
                  f"| {q['anyE']:.3f} | {q['winE']:.3f}")

    print("\n# Power: P(edge rule shows A wins vs buy and hold), single look at the horizon")
    pw = {}
    for rho in RHOS:
        for k in KS:
            for d in DS:
                for h in HORIZONS:
                    pw[rho, k, d, h] = power(k, crits[k], d, rho, h, 200_000, seed=7)
        print(f"rho {rho}")
        print("k | d | 1y | 3y | 5y")
        for k in KS:
            for d in DS:
                print(f"{k} | {d} | " + " | ".join(f"{pw[rho, k, d, h]:.2f}" for h in HORIZONS))

    print("\n# Alternative for contrast: site-wide family, power at d=1.0, 3y (Phi(d/SE - c))")
    for rho in RHOS:
        se = math.sqrt(2 * (1 - rho) / 3)
        print(f"rho {rho}: " + ", ".join(f"M={M}: {phi(1.0 / se - c):.3f}" for M, c in site.items()))

    print("\n# Site grid. Learner mix (guess): 60% save 1 rule, 30% save 5, 10% save 50.")
    mix = {1: 0.6, 5: 0.3, 50: 0.1}
    per = sum(mix[k] * k for k in KS)
    print(f"mean rules per account {per:.2f}")
    print("M | accounts | expected null rules showing a win, single 3y | accounts ever "
          "showing a null win by 3y")
    for M in (10, 100, 1000, 10_000):
        A = M / per
        fp = sum(A * mix[k] * k * nulls[k][3]["rule1"] for k in KS)
        ever = sum(A * mix[k] * nulls[k][3]["winE"] for k in KS)
        print(f"{M} | {A:.0f} | {fp:.1f} | {ever:.1f}")

    print("\n# Chance a shown win is luck, at 3 years, single look, by share pi of rules with an "
          "edge d (pi is a guess)")
    print("rho | k | d | pi=0.01 | pi=0.10")
    for rho in RHOS:
        for k in KS:
            for d in DS:
                fp = nulls[k][3]["rule1"]
                row = []
                for pi in (0.01, 0.10):
                    tp = pi * pw[rho, k, d, 3]
                    row.append((1 - pi) * fp / ((1 - pi) * fp + tp))
                print(f"{rho} | {k} | {d} | {row[0]:.2f} | {row[1]:.2f}")

    print("\n# Gaming. One person, null rules, saves one rule every 20 sessions up to 50, "
          "P(some rule ever shows A wins within 5 years)")
    seq1 = sequential(50, crits, reps=1200, seed=21, one_account=True)
    seqA = sequential(50, crits, reps=1200, seed=22, one_account=False)
    print(f"one account (family grows): {seq1:.3f}")
    print(f"50 accounts, one rule each: {seqA:.3f}")
    print(f"one account, 50 saved at once (ever, 5y): {nulls[50][5]['winE']:.3f}")
    p1 = nulls[1][3]["win1"]
    for A in (1, 5, 50):
        print(f"{A} accounts x 1 rule, single look 3y: P(>=1 win) = {1 - (1 - p1) ** A:.3f}")

    print("\n# Nightly compute (vectorised bootstrap, 2000 reps, 5 years of live data)")
    for M in (100, 1000, 10_000):
        print(f"M={M}: {nightly_cost(M):.1f} s")
    print(f"\ntotal runtime {time.perf_counter() - t0:.0f} s")


if __name__ == "__main__":
    main()
