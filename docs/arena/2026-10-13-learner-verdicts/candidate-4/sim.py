"""Candidate 4: false-discovery control across all learner rules.

Gaussian model of the shared setup. Rule j and catalog entry k have daily excess returns
r = mu + s * (sqrt(rho) f + sqrt(1 - rho) e). The common factor f cancels in every
difference, so the z statistic of pair (j, k) after t sessions is

    z_jk(t) = (S_j(t) - S_k(t)) / sqrt(2 t) + d_j * sqrt(t / 252) / sqrt(2 (1 - rho))

where S is a cumulative sum of standard normals and d_j is rule j's true excess Sharpe
advantage over buy and hold. Every catalog entry is null (true excess Sharpe equal to buy
and hold). Within one rule, the 8 pair statistics have correlation 0.5. Across rules, pairs
with the same catalog entry share S_k, so the cohort's p-values are dependent.

All M rules form one cohort saved on the same day (the worst case for that dependence).
The site looks every night from session 60 (3 blocks) to the horizon.

Methods (a "win" is a rule-ahead verdict on at least one of its 8 pairs):
  own95   own 8 pairs, two-sided simultaneous 95% interval (current critical_value rule)
  bh      PROPOSAL: one-sided "rule ahead" max-T p per rule, BH at q = 0.025 over all M
  by      the same with Benjamini-Yekutieli, q = 0.025 / H_M
  bh2     two-sided max-|T| p per rule, BH at q = 0.05 (shown to fail the loser flood)
  all95   every saved rule's pairs in one family, Sidak approximation of the max over 8M
"""

import math
import sys
import time

import numpy as np

PAIRS = 8
YEAR = 252
LOOK0 = 60
HORIZONS = {1: 252, 3: 756, 5: 1260}
Q1 = 0.025  # one-sided, per direction
Q2 = 0.05


# ---------- exact tail of the max over 8 equicorrelated (0.5) standard normals ----------
def erfc(x):
    """Numerical Recipes erfcc, relative error < 1.2e-7 everywhere."""
    z = np.abs(x)
    t = 1.0 / (1.0 + 0.5 * z)
    poly = -z * z - 1.26551223 + t * (1.00002368 + t * (0.37409196 + t * (0.09678418 + t * (
        -0.18628806 + t * (0.27886807 + t * (-1.13520398 + t * (1.48851587 + t * (
            -0.82215223 + t * 0.17087277))))))))
    ans = t * np.exp(poly)
    return np.where(x >= 0, ans, 2.0 - ans)


def sf(x):
    return 0.5 * erfc(x / math.sqrt(2.0))


A = np.linspace(-9, 9, 3601)
WA = np.exp(-A * A / 2) / math.sqrt(2 * math.pi) * (A[1] - A[0])
MGRID = np.linspace(0.0, 9.0, 9001)


def _tail(m, two_sided):
    # z_k = (a - b_k) / sqrt 2 with a, b_k iid N(0,1). Condition on a.
    u = math.sqrt(2.0) * m[:, None] - A[None, :]
    s_up = sf(u)  # P(z_k > m | a)
    s = s_up + (sf(math.sqrt(2.0) * m[:, None] + A[None, :]) if two_sided else 0.0)
    s = np.minimum(s, 1.0)
    one_minus = -np.expm1(PAIRS * np.log1p(-np.minimum(s, 1 - 1e-16)))
    return np.maximum((one_minus * WA[None, :]).sum(axis=1), 1e-300)


LOGP1 = np.log(np.concatenate([_tail(MGRID[i : i + 1000], False) for i in range(0, 9001, 1000)]))
LOGP2 = np.log(np.concatenate([_tail(MGRID[i : i + 1000], True) for i in range(0, 9001, 1000)]))


def logp(m, table):
    return np.interp(m, MGRID, table).astype(np.float32)


def crit(alpha, table):
    """m such that P(max >= m) = alpha."""
    return float(np.interp(math.log(alpha), table[::-1], MGRID[::-1]))


# ---------- one cohort replicate ----------
def bh_level(lp, q):
    """lp: (nights, M) log p. Returns log alpha_t per night (or -inf when R = 0)."""
    n, m = lp.shape
    srt = np.sort(lp, axis=1)
    thr = np.log(np.arange(1, m + 1) * q / m).astype(np.float32)
    ok = srt <= thr[None, :]
    any_ok = ok.any(axis=1)
    r = m - np.argmax(ok[:, ::-1], axis=1)
    r = np.where(any_ok, r, 0)
    with np.errstate(divide="ignore"):
        return np.log(r * q / m), r


def replicate(rng, drift_sharpe, path_of, rho, T):
    """drift_sharpe: (M,) true advantage d_j. path_of: (M,) index into unique noise paths."""
    n_paths = int(path_of.max()) + 1
    t = np.arange(1, T + 1, dtype=np.float64)
    looks = np.arange(LOOK0, T + 1)  # session counts at which the site looks
    tl = t[looks - 1]
    s_cat = np.cumsum(rng.standard_normal((PAIRS, T)), axis=1)[:, looks - 1]
    s_rule = np.cumsum(rng.standard_normal((n_paths, T)).astype(np.float32), axis=1)[:, looks - 1]
    s_rule = s_rule[path_of]
    scale = (1.0 / np.sqrt(2 * tl)).astype(np.float32)
    drift = (drift_sharpe[:, None] * np.sqrt(tl / YEAR)[None, :] / math.sqrt(2 * (1 - rho))).astype(
        np.float32
    )
    zmax = np.full(s_rule.shape, -np.inf, dtype=np.float32)
    zabs = np.zeros(s_rule.shape, dtype=np.float32)
    z0 = None
    for k in range(PAIRS):
        z = (s_rule - s_cat[k].astype(np.float32)[None, :]) * scale[None, :] + drift
        if k == 0:
            z0 = z.copy()  # pair with buy and hold
        np.maximum(zmax, z, out=zmax)
        np.maximum(zabs, np.abs(z), out=zabs)
    return looks, zmax, zabs, z0


def run(M, rho, frac_true=0.0, d=0.0, reps=10, seed=0, extra=None, T=1260):
    """Returns per-method arrays of metrics. extra: dict for attack scenarios."""
    rng = np.random.default_rng(seed)
    c2_95 = crit(0.05, LOGP2)
    out = {}
    for rep in range(reps):
        true = rng.random(M) < frac_true
        drifts = np.where(true, d, 0.0)
        path_of = np.arange(M)
        honest = np.ones(M, bool)
        if extra:
            k = extra["k"]
            kind = extra["kind"]
            if kind == "nulls":
                add_d = np.zeros(k)
                add_path = np.arange(M, M + k)
            elif kind == "losers":
                add_d = np.full(k, extra["d"])
                add_path = np.arange(M, M + k)
            elif kind == "clones":  # k copies of one real edge, plus k null rules
                add_d = np.concatenate([np.full(k, extra["d"]), np.zeros(k)])
                add_path = np.concatenate([np.full(k, M), np.arange(M + 1, M + 1 + k)])
            drifts = np.concatenate([drifts, add_d])
            path_of = np.concatenate([path_of, add_path])
            true = np.concatenate([true, add_d > 0])
            honest = np.concatenate([honest, np.zeros(len(add_d), bool)])
        n = len(drifts)
        looks, zmax, zabs, z0 = replicate(rng, drifts, path_of, rho, T)
        lp1 = logp(zmax, LOGP1)
        lp2 = logp(zabs, LOGP2)
        h_n = float(np.sum(1.0 / np.arange(1, n + 1)))
        wins = {}
        win_bh_pair = {}
        # own95: rule ahead on some pair beyond the two-sided 95% simultaneous critical value
        wins["own95"] = zmax > c2_95
        win_bh_pair["own95"] = z0 > c2_95
        for name, table, lp, q in (
            ("bh", LOGP1, lp1, Q1),
            ("by", LOGP1, lp1, Q1 / h_n),
            ("bh2", LOGP2, lp2, Q2),
        ):
            la, r = bh_level(lp.T, q)
            # critical value at the night's level alpha_t = R q / n; R = 0 means no win
            cvec = np.where(
                np.isfinite(la), np.interp(la, table[::-1], MGRID[::-1]), np.inf
            ).astype(np.float32)
            wins[name] = zmax > cvec[None, :]
            win_bh_pair[name] = z0 > cvec[None, :]
        sid = 1 - 0.95 ** (1 / n)
        c_all = crit(sid, LOGP2)
        wins["all95"] = zmax > c_all
        win_bh_pair["all95"] = z0 > c_all
        for name, w in wins.items():
            rec = out.setdefault(name, {})
            for hy, H in HORIZONS.items():
                if H > T:
                    continue
                i = H - LOOK0
                at = w[:, i]
                ever = w[:, : i + 1].any(axis=1)
                nul = ~true
                V = int((at & nul).sum())
                R = int(at.sum())
                Ve = int((ever & nul).sum())
                Re = int(ever.sum())
                row = dict(
                    V=V,
                    R=R,
                    fdp=V / R if R else 0.0,
                    Ve=Ve,
                    Re=Re,
                    fdp_ever=Ve / Re if Re else 0.0,
                    n_null=int(nul.sum()),
                    n_true=int(true.sum()),
                    tp=int((at & true).sum()),
                    tp_ever=int((ever & true).sum()),
                    tp_pair=int((win_bh_pair[name][:, i] & true).sum()),
                    hon_null=int((~true & honest).sum()),
                    hon_V=int((at & ~true & honest).sum()),
                    att_V=int((at & ~true & ~honest).sum()),
                    hon_true=int((true & honest).sum()),
                    hon_tp=int((at & true & honest).sum()),
                    any_wins=int((at & true).sum() + V),
                )
                if name == "bh" and R:
                    # luck share among marginal wins (p in the upper half of the allowed range)
                    la_i = math.log(max(R, 1) * Q1 / n)
                    marg = at & (lp1[:, i] > la_i + math.log(0.5))
                    row["marg_R"] = int(marg.sum())
                    row["marg_V"] = int((marg & nul).sum())
                rec.setdefault(hy, []).append(row)
    return out


def summarize(out):
    res = {}
    for name, rec in out.items():
        for hy, rows in rec.items():
            tot = lambda k: sum(r.get(k, 0) for r in rows)  # noqa: E731
            reps = len(rows)
            res[(name, hy)] = dict(
                reps=reps,
                EV=tot("V") / reps,
                ER=tot("R") / reps,
                FDR=np.mean([r["fdp"] for r in rows]),
                P_fdp_gt_20=np.mean([r["fdp"] > 0.2 for r in rows]),
                P_V_ge1=np.mean([r["V"] >= 1 for r in rows]),
                null_rate=tot("V") / max(tot("n_null"), 1),
                null_ever=tot("Ve") / max(tot("n_null"), 1),
                EVe=tot("Ve") / reps,
                FDR_ever=np.mean([r["fdp_ever"] for r in rows]),
                power=tot("tp") / max(tot("n_true"), 1),
                power_bh_pair=tot("tp_pair") / max(tot("n_true"), 1),
                hon_null_rate=tot("hon_V") / max(tot("hon_null"), 1),
                att_V=tot("att_V") / reps,
                hon_power=tot("hon_tp") / max(tot("hon_true"), 1),
                luck_share=tot("V") / max(tot("V") + tot("tp"), 1),
                marg_luck=tot("marg_V") / max(tot("marg_R"), 1),
                marg_R=tot("marg_R") / reps,
            )
    return res


REPS = {10: 20000, 100: 3000, 1000: 300, 10000: 60}


def main():
    t0 = time.time()
    print("Gaussian critical values for one rule's 8 pairs (correlation 0.5), measured:")
    print(f"  two-sided 95%: {crit(0.05, LOGP2):.3f}   one-sided 97.5%: {crit(0.025, LOGP1):.3f}")
    for M in (10, 100, 1000, 10000):
        a1 = Q1 / M
        print(
            f"  M={M:>5}: alpha with R=1 is {a1:.2e}, one-sided c={crit(a1, LOGP1):.2f};"
            f" R=M/10: c={crit(Q1 / 10, LOGP1):.2f}; every-rule Sidak two-sided c="
            f"{crit(1 - 0.95 ** (1 / M), LOGP2):.2f}"
        )
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    lines = []

    def emit(s):
        print(s, flush=True)
        lines.append(s)

    if which in ("all", "null"):
        emit("\n## Null site (every rule null). Rho does not enter the null in this model.")
        emit("method | M | reps | H | E[false wins] now | P(any false win) now | per-rule now | per-rule ever by H | E[rules ever shown a false win]")
        for M in (10, 100, 1000, 10000):
            s = summarize(run(M, 0.75, reps=REPS[M], seed=M))
            for name in ("own95", "bh", "by", "all95"):
                for hy in (1, 3, 5):
                    r = s[(name, hy)]
                    emit(
                        f"{name} | {M} | {r['reps']} | {hy}y | {r['EV']:.3f} | {r['P_V_ge1']:.3f} |"
                        f" {r['null_rate']:.2e} | {r['null_ever']:.2e} | {r['EVe']:.2f}"
                    )
            emit(f"  ({time.time() - t0:.0f}s)")
    if which == "all" or which.startswith("mix"):
        emit("\n## Mixed site: 2% of rules have true advantage d over buy and hold, 98% null.")
        emit("rho | d | method | M | H | power (win on any pair) | power (win vs buy and hold) | FDR now | P(FDP>0.2) | luck share of wins now | luck share among rules ever shown a win | E[wins shown] | marginal-half luck share")
        rhos = (0.75, 0.25) if which in ("all", "mix") else (float(which.split(":")[1]),)
        ds = (0.3, 0.5, 1.0) if which.count(":") < 2 else (float(which.split(":")[2]),)
        for rho in rhos:
            for d in ds:
                for M in (10, 100, 1000, 10000):
                    s = summarize(run(M, rho, 0.02, d, reps=REPS[M], seed=7 * M + int(d * 10)))
                    for name in ("own95", "bh", "by", "all95"):
                        for hy in (1, 3, 5):
                            r = s[(name, hy)]
                            emit(
                                f"{rho} | {d} | {name} | {M} | {hy}y | {r['power']:.3f} |"
                                f" {r['power_bh_pair']:.3f} | {r['FDR']:.3f} | {r['P_fdp_gt_20']:.3f} |"
                                f" {r['luck_share']:.3f} | {r['FDR_ever']:.3f} | {r['ER']:.2f} |"
                                f" {r['marg_luck']:.3f}"
                            )
                    emit(f"  ({time.time() - t0:.0f}s)")
    if which in ("all", "attack"):
        emit("\n## Attacks. Honest site: M=1000 rules, 2% with d=0.5, rho=0.75, look at 3 years.")
        emit("attack | method | honest null win rate | honest power | attacker's false wins | luck share of all wins")
        base = dict(M=1000, rho=0.75, frac_true=0.02, d=0.5)
        for label, extra in (
            ("none", None),
            ("+9000 null rules (many accounts)", dict(kind="nulls", k=9000)),
            ("+9000 certain losers d=-2", dict(kind="losers", k=9000, d=-2.0)),
            ("+1000 clones of one d=1.0 edge +1000 nulls", dict(kind="clones", k=1000, d=1.0)),
        ):
            reps = 40 if extra else 100
            s = summarize(run(**base, reps=reps, seed=99, extra=extra, T=756))
            for name in ("own95", "bh", "bh2", "by"):
                r = s[(name, 3)]
                emit(
                    f"{label} | {name} | {r['hon_null_rate']:.2e} | {r['hon_power']:.3f} |"
                    f" {r['att_V']:.2f} | {r['luck_share']:.3f}"
                )
            emit(f"  ({time.time() - t0:.0f}s)")
    with open(f"results-{which.replace(':', '_')}.md", "w") as fh:
        fh.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
