// Throwaway measurement. A naive JS port of states.levels() and evaluate.backtest/portfolio/sharpe.
// Checks agreement with research/ and times the work a browser engine would do.
// Run: node bench.mjs <measure_dir> <summary.json>
import { readFileSync } from "node:fs";
import path from "node:path";

const [dir, summaryPath] = process.argv.slice(2);
const bars = JSON.parse(readFileSync(path.join(dir, "bars.json")));
const refLevels = JSON.parse(readFileSync(path.join(dir, "levels.json")));
const refRows = JSON.parse(readFileSync(path.join(dir, "rows.json")));
const summary = JSON.parse(readFileSync(summaryPath));
const CASH = "BIL";
const STUDY = Object.keys(bars).filter((s) => s !== CASH);
const END = "2026-10-09";

// polars ewm_mean(adjust=False, min_samples=m), leading nulls skipped.
function ewm(x, alpha, minSamples) {
  const out = new Array(x.length).fill(null);
  let y = null, n = 0;
  for (let i = 0; i < x.length; i++) {
    if (x[i] === null) continue;
    y = y === null ? x[i] : (1 - alpha) * y + alpha * x[i];
    n++;
    if (n >= minSamples) out[i] = y;
  }
  return out;
}
const wilder = (x) => ewm(x, 1 / 14, 14);
const ema = (x, span) => ewm(x, 2 / (span + 1), span);
function rollMean(x, w) {
  const out = new Array(x.length).fill(null);
  for (let i = w - 1; i < x.length; i++) {
    let s = 0;
    for (let j = i - w + 1; j <= i; j++) s += x[j];
    out[i] = s / w;
  }
  return out;
}
function rollStd0(x, w) {
  const out = new Array(x.length).fill(null);
  for (let i = w - 1; i < x.length; i++) {
    let s = 0;
    for (let j = i - w + 1; j <= i; j++) s += x[j];
    const m = s / w;
    let v = 0;
    for (let j = i - w + 1; j <= i; j++) v += (x[j] - m) ** 2;
    out[i] = Math.sqrt(v / w);
  }
  return out;
}
function rollRankMax(x, w) {
  const out = new Array(x.length).fill(null);
  for (let i = w - 1; i < x.length; i++) {
    let c = 0, ok = true;
    for (let j = i - w + 1; j <= i; j++) {
      if (x[j] === null) { ok = false; break; }
      if (x[j] <= x[i]) c++;
    }
    if (ok) out[i] = c;
  }
  return out;
}
const sub = (a, b) => a.map((v, i) => (v === null || b[i] === null ? null : v - b[i]));

function levels(b) {
  const { close, high, low } = b;
  const n = close.length;
  const change = close.map((c, i) => (i === 0 ? null : c - close[i - 1]));
  const gain = wilder(change.map((c) => (c === null ? null : Math.max(c, 0))));
  const loss = wilder(change.map((c) => (c === null ? null : Math.max(-c, 0))));
  const rsi = gain.map((g, i) => (g === null || loss[i] === null ? null : loss[i] === 0 ? 100 : 100 - 100 / (1 + g / loss[i])));
  const sma50 = rollMean(close, 50), sma200 = rollMean(close, 200);
  const macd = sub(ema(close, 12), ema(close, 26));
  const hist = sub(macd, ema(macd, 9));
  const mid = rollMean(close, 20), sd = rollStd0(close, 20);
  const tr = close.map((_, i) => i === 0 ? high[i] - low[i] : Math.max(high[i] - low[i], Math.abs(high[i] - close[i - 1]), Math.abs(low[i] - close[i - 1])));
  const atr = wilder(tr).map((a, i) => (a === null ? null : a / close[i]));
  const rank = rollRankMax(atr, 252);
  const L = { rsi14: [], vs_sma200: [], sma50_vs_sma200: [], macd_hist: [], bollinger: [], atr_regime: [] };
  for (let i = 0; i < n; i++) {
    const r = rsi[i];
    L.rsi14.push(r === null ? null : r < 30 ? "OVERSOLD" : r < 45 ? "WEAK" : r <= 55 ? "NEUTRAL" : r < 70 ? "STRONG" : "OVERBOUGHT");
    L.vs_sma200.push(sma200[i] === null ? null : close[i] > sma200[i] ? "ABOVE" : "BELOW");
    L.sma50_vs_sma200.push(sma200[i] === null ? null : sma50[i] > sma200[i] ? "ABOVE" : "BELOW");
    const h = hist[i], p = i > 0 ? hist[i - 1] : null;
    L.macd_hist.push(h === null || p === null ? null : `${h > 0 ? "POS" : "NEG"}_${h > p ? "RISING" : "FALLING"}`);
    const m = mid[i], band = sd[i] === null ? null : 2 * sd[i];
    L.bollinger.push(m === null ? null : close[i] < m - band ? "BELOW_LOWER" : close[i] < m ? "LOWER_HALF" : close[i] <= m + band ? "UPPER_HALF" : "ABOVE_UPPER");
    const k = rank[i];
    L.atr_regime.push(k === null ? null : k * 3 <= 252 ? "LOW" : k * 3 <= 504 ? "NORMAL" : "HIGH");
  }
  return { L, sma50, sma200, mid, sd };
}

function roundBars(b, d) {
  const f = 10 ** d;
  const r = (x) => x.map((v) => Math.round(v * f) / f);
  return { date: b.date, open: r(b.open), high: r(b.high), low: r(b.low), close: r(b.close) };
}

// open_returns: r(t) = open[t+2]/open[t+1]-1 on bars dated <= END, null dropped.
function openReturns(b) {
  const m = new Map();
  for (let i = 0; i + 2 < b.date.length; i++) if (b.date[i] <= END) m.set(b.date[i], b.open[i + 2] / b.open[i + 1] - 1);
  return m;
}

// evaluate.backtest + portfolio + sharpe for one arm. positions: symbol -> Map(date -> 0|1) over holdout state rows.
function excessByDate(positions, allBars, costBps) {
  const cash = openReturns(allBars[CASH]);
  const byDate = new Map();
  for (const s of STUDY) {
    const r = openReturns(allBars[s]);
    let prev = 0;
    for (const [d, pos] of positions[s]) {
      if (!r.has(d) || !cash.has(d)) continue;
      const sw = pos !== prev ? 1 : 0;
      prev = pos;
      const ret = (1 - (costBps / 1e4) * sw) * (1 + pos * r.get(d) + (1 - pos) * cash.get(d)) - 1;
      const e = byDate.get(d) ?? { sum: 0, n: 0, cash: cash.get(d) };
      e.sum += ret; e.n++;
      byDate.set(d, e);
    }
  }
  const dates = [...byDate.keys()].sort();
  return { dates, excess: Float64Array.from(dates.map((d) => byDate.get(d).sum / byDate.get(d).n - byDate.get(d).cash)) };
}
function sharpe(x, w) {
  let n = 0, s = 0;
  for (let i = 0; i < x.length; i++) { const wi = w ? w[i] : 1; n += wi; s += wi * x[i]; }
  const m = s / n;
  let v = 0;
  for (let i = 0; i < x.length; i++) { const wi = w ? w[i] : 1; v += wi * (x[i] - m) ** 2; }
  return (m / Math.sqrt(v / (n - 1))) * Math.sqrt(252);
}
function mulberry32(a) {
  return () => { a |= 0; a = (a + 0x6d2b79f5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}
function bootstrapSharpe(x, reps = 2000, block = 20) {
  const blocks = Int32Array.from(x, (_, i) => Math.floor(i / block));
  const count = blocks[blocks.length - 1] + 1;
  const rng = mulberry32(0);
  const out = new Float64Array(reps), counts = new Float64Array(count), w = new Float64Array(x.length);
  for (let r = 0; r < reps; r++) {
    counts.fill(0);
    for (let k = 0; k < count; k++) counts[Math.floor(rng() * count)]++;
    for (let i = 0; i < x.length; i++) w[i] = counts[blocks[i]];
    out[r] = sharpe(x, w);
  }
  out.sort();
  return { lo: out[Math.floor(0.025 * reps)], hi: out[Math.floor(0.975 * reps)], count };
}

// 1. Level agreement with states.levels().
let t0 = performance.now();
const computed = Object.fromEntries(STUDY.map((s) => [s, levels(bars[s])]));
const tLevels = performance.now() - t0;
let cells = 0, mismatch = 0;
const mismatchByDim = {};
for (const s of STUDY) for (const [dim, ref] of Object.entries(refLevels[s])) {
  for (let i = 0; i < ref.length; i++) {
    cells++;
    if (ref[i] !== computed[s].L[dim][i]) { mismatch++; mismatchByDim[dim] = (mismatchByDim[dim] ?? 0) + 1; }
  }
}
console.log(`levels: ${mismatch} mismatches in ${cells} cells (${JSON.stringify(mismatchByDim)}), naive port ${tLevels.toFixed(0)} ms for 13 symbols`);

// 2. Reproduce published holdout Sharpe for sma_filter and buy_hold.
function holdoutPositions(allBars, lv, rule) {
  const out = {};
  for (const s of STUDY) {
    const idx = new Map(allBars[s].date.map((d, i) => [d, i]));
    const m = new Map();
    refRows[s].date.forEach((d, j) => { if (refRows[s].split[j] === "holdout") m.set(d, rule(lv[s], idx.get(d))); });
    out[s] = m;
  }
  return out;
}
const rules = { sma_filter: (l, i) => (l.L.sma50_vs_sma200[i] === "ABOVE" ? 1 : 0), buy_hold: () => 1 };
const published = Object.fromEntries(summary.arms.map((a) => [a.name, a]));
for (const [label, b] of [["full precision", bars], ["export rounding (4 dp)", Object.fromEntries(Object.entries(bars).map(([s, x]) => [s, roundBars(x, 4)]))]]) {
  const lv = label === "full precision" ? computed : Object.fromEntries(STUDY.map((s) => [s, levels(b[s])]));
  for (const [arm, rule] of Object.entries(rules)) {
    for (const bps of [0, 5, 20]) {
      const { excess } = excessByDate(holdoutPositions(b, lv, rule), b, bps);
      const ref = published[arm].excessSharpeByCost.find((c) => c.costBps === bps).value;
      console.log(`${label} ${arm} @${bps}bps: js ${sharpe(excess).toPrecision(15)} vs holdout.json ${ref.toPrecision(15)} diff ${(sharpe(excess) - ref).toExponential(2)}`);
    }
  }
}

// 3. Time a user-composed strategy: Bollinger bounce, long below lower band until close > mid, full 13-symbol holdout run.
function bollingerBounce(b, w, k) {
  const mid = rollMean(b.close, w), sd = rollStd0(b.close, w);
  const pos = new Array(b.close.length).fill(0);
  let p = 0;
  for (let i = 0; i < b.close.length; i++) {
    if (mid[i] === null) { pos[i] = 0; continue; }
    if (p === 0 && b.close[i] < mid[i] - k * sd[i]) p = 1;
    else if (p === 1 && b.close[i] > mid[i]) p = 0;
    pos[i] = p;
  }
  return pos;
}
function runBounce(w, k, withCi) {
  const positions = {};
  for (const s of STUDY) {
    const pos = bollingerBounce(bars[s], w, k);
    const idx = new Map(bars[s].date.map((d, i) => [d, i]));
    const m = new Map();
    refRows[s].date.forEach((d, j) => { if (refRows[s].split[j] === "holdout") m.set(d, pos[idx.get(d)]); });
    positions[s] = m;
  }
  const { excess } = excessByDate(positions, bars, 5);
  return { sharpe: sharpe(excess), ci: withCi ? bootstrapSharpe(excess) : null };
}
t0 = performance.now();
const one = runBounce(20, 2, false);
const tOne = performance.now() - t0;
t0 = performance.now();
const oneCi = runBounce(20, 2, true);
const tOneCi = performance.now() - t0;
console.log(`bounce(20,2) holdout excess Sharpe ${one.sharpe.toFixed(3)} CI [${oneCi.ci.lo.toFixed(3)}, ${oneCi.ci.hi.toFixed(3)}] over ${oneCi.ci.count} blocks; run ${tOne.toFixed(0)} ms, run + 2000-rep bootstrap ${tOneCi.toFixed(0)} ms`);

const windows = [10, 15, 20, 25, 30, 40, 50, 60, 80], ks = [1, 1.5, 1.75, 2, 2.25, 2.5, 3];
t0 = performance.now();
const grid = [];
for (const w of windows) for (const k of ks) grid.push({ w, k, ...runBounce(w, k, false) });
const tGrid = performance.now() - t0;
grid.sort((a, b) => b.sharpe - a.sharpe);
const best = grid[0], median = grid[Math.floor(grid.length / 2)], worst = grid[grid.length - 1];
console.log(`grid ${grid.length} combos in ${tGrid.toFixed(0)} ms; best (${best.w},${best.k}) ${best.sharpe.toFixed(3)}, median ${median.sharpe.toFixed(3)}, worst (${worst.w},${worst.k}) ${worst.sharpe.toFixed(3)}`);
