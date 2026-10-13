// Throwaway: reproduce published excess Sharpe CIs with numpy's block draws shipped as data.
import { readFileSync } from "node:fs";
const dir = process.argv[2];
const src = readFileSync(dir + "/bench.mjs", "utf8");
const body = src.slice(src.indexOf("const [dir"), src.indexOf("// 1. Level agreement"));
const lib = new Function("process", "readFileSync", "path", body.replace(/^import.*$/gm, "") + "; return { levels, excessByDate, sharpe, bars, refRows, STUDY, summary };");
const pathMod = await import("node:path");
const L = lib({ argv: [0, 0, dir, process.argv[3]] }, readFileSync, pathMod.default);
const draws = JSON.parse(readFileSync(dir + "/draws98.json"));
function quantileLinear(sorted, q) { const h = (sorted.length - 1) * q, lo = Math.floor(h); return sorted[lo] + (h - lo) * (sorted[Math.min(lo + 1, sorted.length - 1)] - sorted[lo]); }
const lv = Object.fromEntries(L.STUDY.map((s) => [s, L.levels(L.bars[s])]));
const rules = { sma_filter: (l, i) => (l.L.sma50_vs_sma200[i] === "ABOVE" ? 1 : 0), buy_hold: () => 1 };
for (const [arm, rule] of Object.entries(rules)) {
  const positions = {};
  for (const s of L.STUDY) { const idx = new Map(L.bars[s].date.map((d, i) => [d, i])); const m = new Map();
    L.refRows[s].date.forEach((d, j) => { if (L.refRows[s].split[j] === "holdout") m.set(d, rule(lv[s], idx.get(d))); }); positions[s] = m; }
  const { excess } = L.excessByDate(positions, L.bars, 5);
  const blocks = Int32Array.from(excess, (_, i) => Math.floor(i / 20));
  const out = draws.map((d) => { const c = new Float64Array(98); for (const k of d) c[k]++; return L.sharpe(excess, Float64Array.from(blocks, (b) => c[b])); }).sort((a, b) => a - b);
  const ref = L.summary.arms.find((a) => a.name === arm).excessSharpe;
  console.log(arm, "lo", quantileLinear(out, 0.025) - ref.lo, "hi", quantileLinear(out, 0.975) - ref.hi);
}
