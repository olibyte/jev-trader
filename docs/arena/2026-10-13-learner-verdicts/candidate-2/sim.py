"""Candidate 2: ONE RULE'S PAIRS. Synthetic win rates, honesty, and cost.

A learner rule's verdict uses a simultaneous 95% interval over its own pairs with the 8
catalog entries in its market. Every number this script prints is measured on synthetic data.

Model (shared setup): daily excess return r_i = mu_i + s * (sqrt(rho) f + sqrt(1 - rho) e_i),
s = 1 (Sharpe is scale-free), mu_i = S_i / sqrt(252). Catalog: 8 entries, all with true excess
Sharpe 0.6 (buy and hold, M7 measured 0.61). A null learner rule also has 0.6. A rule with a
true advantage d has 0.6 + d.

The verdict uses the Gaussian max-|z| equivalent of catalog.critical_value: z = (S_L - S_c) / SE
per pair, with SE from the delta method on the estimated correlation, and a win when |z| exceeds
the 95th percentile of max |z| over the rule's 8 pairs. section 5 spot-checks this against the
real evaluate.block_bootstrap and catalog.critical_value.

Run: uv run python sim.py  (about 10 minutes)
"""

import sys
import time

import numpy as np

np.seterr(invalid="ignore", divide="ignore")

YEAR = 252
BLOCK = 20
FIRST = 3 * BLOCK  # "Too early" below 3 blocks
HORIZONS = {"1y": 252, "3y": 756, "5y": 1260}
H = 1260
N_CAT = 8
BASE = 0.6
DS = [0.0, 0.3, 0.5, 1.0]
RHOS = [0.75, 0.25]


# ---------------------------------------------------------------- 1. critical values


def max_abs_z(n_cat: int, n_learn: int, draws: int, rng, catalog_pairs: bool) -> np.ndarray:
    """Max |z| over a family of pairs whose differences are (e_i - e_j) / sqrt(2).

    The family is every (learner, catalog) pair, plus every catalog pair when catalog_pairs.
    Pairs that share an entry correlate 0.5, as in the synthetic model.
    """
    out = np.empty(draws)
    step = max(1, 2_000_000 // max(1, n_cat + n_learn))
    for a in range(0, draws, step):
        b = min(draws, a + step)
        c = rng.standard_normal((b - a, n_cat))
        lo, hi = c.min(1), c.max(1)
        m = (hi - lo) if catalog_pairs else np.zeros(b - a)
        for k in range(0, n_learn, 2000):
            e = rng.standard_normal((b - a, min(2000, n_learn - k)))
            m = np.maximum(m, np.maximum(e - lo[:, None], hi[:, None] - e).max(1))
        out[a:b] = m / np.sqrt(2)
    return out


def critical(n_cat, n_learn, catalog_pairs, draws=400_000, seed=1):
    return float(np.quantile(max_abs_z(n_cat, n_learn, draws, np.random.default_rng(seed),
                                       catalog_pairs), 0.95))


# ---------------------------------------------------------------- 2. nightly path simulation


def paths(rho, learner_S, reps, chunk, cv, seed, horizon=H):
    """Nightly verdicts from session 60 to `horizon` for learner rules that share a catalog.

    Returns per-rep booleans keyed by horizon: snapshot and ever (from session 60) for
    'any' (any of the rule's 8 pairs reads a win either way), 'fav' (the rule wins over at
    least one entry), and 'bh' (the rule wins over buy and hold, pair 0). Also the mean
    snapshot and ever curves of 'any' and 'fav' over n.
    """
    rng = np.random.default_rng(seed)
    S = np.r_[np.full(N_CAT, BASE), BASE + np.asarray(learner_S, float)]
    K = len(learner_S)
    mu = S / np.sqrt(YEAR)
    n = np.arange(1, horizon + 1, dtype=float)[FIRST - 1 :]
    res = {h: {k: [] for k in ("snap_any", "snap_fav", "snap_bh", "ever_any", "ever_fav",
                               "ever_bh")} for h in HORIZONS if HORIZONS[h] <= horizon}
    curve = {k: np.zeros((K, len(n))) for k in ("snap_any", "snap_fav", "ever_any", "ever_fav")}
    for a in range(0, reps, chunk):
        B = min(chunk, reps - a)
        f = rng.standard_normal((B, 1, horizon))
        e = rng.standard_normal((B, N_CAT + K, horizon))
        r = mu[None, :, None] + np.sqrt(rho) * f + np.sqrt(1 - rho) * e
        c1 = np.cumsum(r, -1)[..., FIRST - 1 :]
        c2 = np.cumsum(r * r, -1)[..., FIRST - 1 :]
        cp = np.cumsum(r[:, N_CAT:, None, :] * r[:, None, :N_CAT, :], -1)[..., FIRST - 1 :]
        m = c1 / n
        sd = np.sqrt((c2 - n * m * m) / (n - 1))
        sh = m / sd  # daily Sharpe, (B, 8+K, N)
        mL, mC = m[:, N_CAT:, None], m[:, None, :N_CAT]
        sL, sC = sd[:, N_CAT:, None], sd[:, None, :N_CAT]
        hL, hC = sh[:, N_CAT:, None], sh[:, None, :N_CAT]
        rh = (cp - n * mL * mC) / (n - 1) / (sL * sC)
        var = (2 - 2 * rh + 0.5 * (hL**2 + hC**2 - 2 * hL * hC * rh**2)) / n
        z = (hL - hC) / np.sqrt(var)  # (B, K, 8, N)
        win_any = (np.abs(z) > cv).any(2)
        win_fav = (z > cv).any(2)
        win_bh = z[:, :, 0, :] > cv
        ev_any = np.logical_or.accumulate(win_any, -1)
        ev_fav = np.logical_or.accumulate(win_fav, -1)
        ev_bh = np.logical_or.accumulate(win_bh, -1)
        curve["snap_any"] += win_any.sum(0)
        curve["snap_fav"] += win_fav.sum(0)
        curve["ever_any"] += ev_any.sum(0)
        curve["ever_fav"] += ev_fav.sum(0)
        for h in res:
            i = HORIZONS[h] - FIRST
            for k, arr in (("snap_any", win_any), ("snap_fav", win_fav), ("snap_bh", win_bh),
                           ("ever_any", ev_any), ("ever_fav", ev_fav), ("ever_bh", ev_bh)):
                res[h][k].append(arr[..., i])
    for h in res:
        for k in res[h]:
            res[h][k] = np.concatenate(res[h][k])  # (reps, K)
    for k in curve:
        curve[k] /= reps
    return res, curve


# ---------------------------------------------------------------- 3. site-wide snapshot


def site(rho, M, reps, cv, seed, starts="staggered", horizon=H):
    """Counts of null learner rules that show a win on one night, sharing one catalog.

    staggered: each rule is saved on a uniform session in [0, horizon) and the site is read
    at `horizon`. cohort: every rule is saved on session 0. Rules under 60 sessions read
    "Too early" and count in neither.
    """
    rng = np.random.default_rng(seed)
    mu = BASE / np.sqrt(YEAR)
    played, fav, anyw = [], [], []
    for _ in range(reps):
        f = rng.standard_normal(horizon)
        rc = mu + np.sqrt(rho) * f + np.sqrt(1 - rho) * rng.standard_normal((N_CAT, horizon))
        suf1 = np.cumsum(rc[:, ::-1], 1)[:, ::-1]
        suf2 = np.cumsum((rc * rc)[:, ::-1], 1)[:, ::-1]
        t0 = rng.integers(0, horizon, M) if starts == "staggered" else np.zeros(M, int)
        cf = ca = cpl = 0
        for a in range(0, M, 2000):
            tt = t0[a : a + 2000]
            nn = (horizon - tt).astype(float)
            mask = np.arange(horizon)[None, :] >= tt[:, None]
            rl = (mu + np.sqrt(rho) * f + np.sqrt(1 - rho)
                  * rng.standard_normal((len(tt), horizon))) * mask
            mL = rl.sum(1) / nn
            sL = np.sqrt(((rl * rl).sum(1) - nn * mL**2) / (nn - 1))
            mC = suf1[:, tt].T / nn[:, None]
            sC = np.sqrt((suf2[:, tt].T - nn[:, None] * mC**2) / (nn[:, None] - 1))
            rh = ((rl @ rc.T) - nn[:, None] * mL[:, None] * mC) / (nn[:, None] - 1) / (
                sL[:, None] * sC)
            hL, hC = (mL / sL)[:, None], mC / sC
            var = (2 - 2 * rh + 0.5 * (hL**2 + hC**2 - 2 * hL * hC * rh**2)) / nn[:, None]
            z = (hL - hC) / np.sqrt(var)
            ok = nn >= FIRST
            cpl += ok.sum()
            cf += ((z > cv).any(1) & ok).sum()
            ca += ((np.abs(z) > cv).any(1) & ok).sum()
        played.append(cpl)
        fav.append(cf)
        anyw.append(ca)
    return np.array(played), np.array(fav), np.array(anyw)


# ---------------------------------------------------------------- 4. bootstrap spot check


def spot_check(n_days, datasets, cv8, seed):
    """Real evaluate.block_bootstrap + catalog.critical_value against the Gaussian rule."""
    from jevtrader.catalog import critical_value
    from jevtrader.evaluate import block_bootstrap, sharpe

    rng = np.random.default_rng(seed)
    rho = 0.75
    mu = BASE / np.sqrt(YEAR)
    dates = np.arange(n_days)
    boot_win = gauss_win = 0
    cvs, ratios = [], []
    for _ in range(datasets):
        r = mu + np.sqrt(rho) * rng.standard_normal(n_days) + np.sqrt(1 - rho) * \
            rng.standard_normal((N_CAT + 1, n_days))
        xL = r[N_CAT]
        draws = np.array([
            block_bootstrap(dates, lambda w, xc=r[c]: sharpe(xL, w) - sharpe(xc, w))
            for c in range(N_CAT)])
        points = np.array([sharpe(xL) - sharpe(r[c]) for c in range(N_CAT)])
        cv = critical_value(draws, points)
        sdb = draws.std(axis=1, ddof=1)
        boot_win += bool((np.abs(points) > cv * sdb).any())
        # Gaussian rule on the same data
        hL = xL.mean() / xL.std(ddof=1)
        g = False
        for c in range(N_CAT):
            xc = r[c]
            hC = xc.mean() / xc.std(ddof=1)
            rh = np.corrcoef(xL, xc)[0, 1]
            se = np.sqrt(YEAR * (2 - 2 * rh + 0.5 * (hL**2 + hC**2 - 2 * hL * hC * rh**2))
                         / n_days)
            g |= abs(points[c]) > cv8 * se
            ratios.append(sdb[c] / se)
        gauss_win += g
        cvs.append(cv)
    return boot_win / datasets, gauss_win / datasets, float(np.mean(cvs)), float(
        np.median(ratios))


# ---------------------------------------------------------------- 5. nightly cost


def fast_draws(n_days, X, reps=2000, seed=0):
    """block_bootstrap's draws for every column of X at once: same RNG sequence, one matmul."""
    blocks = np.arange(n_days) // BLOCK
    count = int(blocks.max()) + 1
    rng = np.random.default_rng(seed)
    W = np.empty((reps, count))
    for i in range(reps):
        W[i] = np.bincount(rng.integers(count, size=count), minlength=count)
    Wd = W[:, blocks]
    nw = Wd.sum(1, keepdims=True)
    m = Wd @ X / nw
    var = (Wd @ (X * X) - nw * m * m) / (nw - 1)
    return m / np.sqrt(var) * np.sqrt(YEAR)


def cost(M, seed=3):
    """Seconds for one night's bootstrap draws for M rules saved on staggered days.

    Rules saved on the same day share a block grid, so one weight matrix serves them and the
    8 catalog entries. Up to 1,260 save days over 5 years.
    """
    rng = np.random.default_rng(seed)
    groups = min(M, H)
    sizes = np.bincount(rng.integers(groups, size=M), minlength=groups)
    t = time.perf_counter()
    for g, k in enumerate(sizes):
        n_days = int(H - g * H // groups)
        if n_days < FIRST or k == 0:
            continue
        X = rng.standard_normal((n_days, k + N_CAT)) * 0.01 + 0.0003
        fast_draws(n_days, X)
    return time.perf_counter() - t


def main():
    t_all = time.perf_counter()
    out = []

    def p(s=""):
        print(s)
        out.append(s)
        sys.stdout.flush()

    # 1. critical values
    cv8 = critical(N_CAT, 1, False)
    cv14 = float(np.quantile(np.maximum(
        max_abs_z(8, 1, 400_000, np.random.default_rng(2), False),
        max_abs_z(6, 1, 400_000, np.random.default_rng(3), False)), 0.95))
    cv28 = critical(N_CAT, 0, True)
    p("## 1. Critical values (Gaussian max-|z|, 400,000 draws)")
    p(f"- One learner rule, 8 pairs, one market: {cv8:.3f}")
    p(f"- One learner rule, 14 pairs, two independent markets (8 + 6): {cv14:.3f}")
    p(f"- Catalog only, 28 pairs: {cv28:.3f}")
    p("- Every saved rule in one family (28 + 8M pairs), the rejected alternative:")
    for M in (10, 100, 1000, 10000):
        p(f"  - M = {M}: {critical(N_CAT, M, True, draws=20_000 if M >= 1000 else 100_000):.3f}")
    p()

    # 2. per-rule rates, nightly looks
    REPS = int(__import__('os').environ.get('REPS', 20_000))
    curves = {}
    p("## 2. Per-rule rates (20,000 synthetic runs per rho)")
    for rho in RHOS:
        res, curve = paths(rho, DS, REPS, 250, cv8, seed=10 + int(rho * 100))
        curves[rho] = curve
        p(f"\n### rho = {rho}")
        p("\nNull rule (true excess Sharpe equal to buy and hold). Percent of rules.\n")
        p("| Horizon | Any win, single look | Rule wins, single look | Any win, ever (nightly) "
          "| Rule wins, ever (nightly) |")
        p("|---|---|---|---|---|")
        for h in res:
            d = res[h]
            p(f"| {h} | {100*d['snap_any'][:,0].mean():.1f} | {100*d['snap_fav'][:,0].mean():.1f}"
              f" | {100*d['ever_any'][:,0].mean():.1f} | {100*d['ever_fav'][:,0].mean():.1f} |")
        p("\nPower: percent of rules with a true advantage d that read 'A wins' over buy and "
          "hold. Single look at the horizon (ever, at any nightly look).\n")
        p("| d | 1y | 3y | 5y |")
        p("|---|---|---|---|")
        for j, dd in enumerate(DS[1:], 1):
            cells = [f"{100*res[h]['snap_bh'][:,j].mean():.1f} ({100*res[h]['ever_bh'][:,j].mean():.1f})"
                     for h in res]
            p(f"| {dd} | " + " | ".join(cells) + " |")
        p("\nRule wins over at least one catalog entry, single look:\n")
        p("| d | 1y | 3y | 5y |")
        p("|---|---|---|---|")
        for j, dd in enumerate(DS):
            p(f"| {dd} | " + " | ".join(f"{100*res[h]['snap_fav'][:,j].mean():.1f}"
                                         for h in res) + " |")
        sn = curve["snap_any"][0]
        p(f"\nNull snapshot rate 'any win' across nights 60..1260: min {100*sn.min():.1f}%, "
          f"max {100*sn.max():.1f}%, at night 60 {100*sn[0]:.1f}%, at 1260 {100*sn[-1]:.1f}%.")
        globals()[f"RES_{int(rho*100)}"] = res
    p()

    # 3. luck share of a shown win (arithmetic from measured rates and guessed priors)
    p("## 3. Chance that a shown 'rule wins' verdict is luck, at a 3-year single look")
    p("Arithmetic: pi0*a / (pi0*a + pi1*power). a and power are measured above. "
      "pi1, the share of rules with a real edge, is a guess.\n")
    p("| rho | pi1 | d = 0.5 | d = 1.0 |")
    p("|---|---|---|---|")
    for rho in RHOS:
        res = globals()[f"RES_{int(rho*100)}"]["3y"]
        a = res["snap_fav"][:, 0].mean()
        for pi1 in (0.01, 0.05, 0.20):
            cells = []
            for j in (2, 3):
                pw = res["snap_fav"][:, j].mean()
                cells.append(f"{100*(1-pi1)*a/((1-pi1)*a+pi1*pw):.0f}%")
            p(f"| {rho} | {pi1:.0%} | " + " | ".join(cells) + " |")
    p()

    # 4. site-wide counts, all rules null
    p("## 4. Site-wide counts on one night, every learner rule null")
    p("Rules saved on uniform days over 5 years, read at the end of year 5 (staggered), or all "
      "saved on one day and read 1 year later (cohort). 'Played' = rules with at least 3 "
      "blocks. Counts are of rules that show 'rule wins' over at least one catalog entry.\n")
    p("| rho | starts | M | played (mean) | expected luck wins, 2.5% x played | mean wins "
      "| 95th pct wins | P(>= 1 win) |")
    p("|---|---|---|---|---|---|---|---|")
    for rho in RHOS:
        for starts, hz in (("staggered", H), ("cohort", 252)):
            for M in (10, 100, 1000, 10000):
                reps = 1000 if M <= 100 else (300 if M <= 1000 else 60)
                pl_, fv, _ = site(rho, M, reps, cv8, seed=M + int(rho * 7), starts=starts,
                                  horizon=hz)
                p(f"| {rho} | {starts} | {M} | {pl_.mean():.0f} | {0.025*pl_.mean():.1f} | "
                  f"{fv.mean():.1f} | {np.quantile(fv, 0.95):.0f} | {100*(fv>0).mean():.0f}% |")
    p()
    p("Expected 'ever showed a win' for staggered null rules (arithmetic: mean of the measured "
      "per-rule ever curve over uniform live lengths):")
    for rho in RHOS:
        c = curves[rho]["ever_fav"][0]
        lens = np.arange(FIRST, H + 1)
        p(f"- rho {rho}: {100*c[lens - FIRST].sum()/H:.1f}% of all saved rules "
          f"(snapshot: {100*curves[rho]['snap_fav'][0][lens-FIRST].sum()/H:.1f}%)")
    p()

    # 5. one person, many accounts: K null rules saved on one day
    p("## 5. One person saves K null rules on one day (many accounts)")
    p("Percent of runs where at least one of the K rules shows 'rule wins'. 1,000 runs (400 for "
      "K = 100). Independent-rule arithmetic in brackets: 1 - (1 - a)^K.\n")
    p("| rho | K | 1y single look | 1y ever (nightly) | 5y ever (nightly) |")
    p("|---|---|---|---|---|")
    for rho in RHOS:
        for K in (1, 10, 20, 100):
            reps = 400 if K == 100 else 1000
            chunk = max(1, 2000 // K)
            res, _ = paths(rho, [0.0] * K, reps, chunk, cv8, seed=50 + K)
            a1 = res["1y"]["snap_fav"].mean()
            s1 = res["1y"]["snap_fav"].any(1).mean()
            e1 = res["1y"]["ever_fav"].any(1).mean()
            e5 = res["5y"]["ever_fav"].any(1).mean()
            p(f"| {rho} | {K} | {100*s1:.0f}% [{100*(1-(1-a1)**K):.0f}%] | {100*e1:.0f}% | "
              f"{100*e5:.0f}% |")
    p()

    # 6. bootstrap spot check
    p("## 6. Spot check: real block_bootstrap + critical_value vs the Gaussian rule")
    p("rho 0.75, null rule, 8 pairs, 2,000 reps, seed 0, 200 datasets each. Same data for "
      "both rules.\n")
    p("| Sessions | Blocks | Bootstrap any-win rate | Gaussian any-win rate | Mean bootstrap "
      "critical value | Median bootstrap SD / delta SE |")
    p("|---|---|---|---|---|---|")
    for n_days in (60, 252, 1260):
        ds = 200 if n_days < 1260 else 100
        b, g, cvm, ratio = spot_check(n_days, ds, cv8, seed=n_days)
        p(f"| {n_days} | {int(np.ceil(n_days/BLOCK))} | {100*b:.1f}% | {100*g:.1f}% | {cvm:.2f} "
          f"| {ratio:.2f} |")
    p(f"(Gaussian critical value {cv8:.2f}.)")
    p()

    # 7. cost
    from jevtrader.evaluate import block_bootstrap, sharpe

    xa, xb = np.random.default_rng(0).standard_normal((2, 630)) * 0.01
    ref = block_bootstrap(np.arange(630), lambda w: sharpe(xa, w) - sharpe(xb, w))
    fd = fast_draws(630, np.c_[xa, xb])
    p("## 7. Nightly compute")
    p(f"- fast_draws equals block_bootstrap: max abs diff "
      f"{np.abs((fd[:,0]-fd[:,1]) - ref).max():.1e}")
    t = time.perf_counter()
    block_bootstrap(np.arange(630), lambda w: sharpe(xa, w) - sharpe(xb, w))
    one = time.perf_counter() - t
    p(f"- Today's per-pair block_bootstrap, 630 sessions: {one:.2f} s per pair, so "
      f"{one*8:.1f} s per rule (8 pairs)")
    for M in (10, 100, 1000, 10000):
        p(f"- Shared-weights matmul, M = {M} rules: {cost(M):.1f} s per night "
          f"(per-pair loop would take about {one*8*M/60:.0f} min)")
    p()
    p(f"Total run time {time.perf_counter() - t_all:.0f} s.")
    with open(__file__.replace("sim.py", "results.md"), "w") as fh:
        fh.write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
