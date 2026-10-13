// Throwaway: how many state levels flip when the engine reads 4-dp export prices instead of full precision.
import { readFileSync } from "node:fs";
const src = readFileSync(new URL("./bench.mjs", import.meta.url), "utf8");
const fnSrc = src.slice(src.indexOf("// polars ewm_mean"), src.indexOf("// open_returns"));
const { levels, roundBars } = new Function(fnSrc + "; return { levels, roundBars };")();
const dir = process.argv[2];
const bars = JSON.parse(readFileSync(dir + "/bars.json"));
const ref = JSON.parse(readFileSync(dir + "/levels.json"));
let cells = 0, mism = 0, by = {};
for (const s of Object.keys(ref)) { const L = levels(roundBars(bars[s], 4)).L;
  for (const [d, r] of Object.entries(ref[s])) for (let i = 0; i < r.length; i++) { cells++; if (r[i] !== L[d][i]) { mism++; by[d] = (by[d] ?? 0) + 1; } } }
console.log(`4dp levels: ${mism} mismatches in ${cells} cells`, by);
