import { readFileSync } from "node:fs";
import path from "node:path";

const MINUS = "−";
const nf = (o: Intl.NumberFormatOptions) => {
  const f = new Intl.NumberFormat("en-US", { signDisplay: "negative", ...o });
  return (v: number) => f.format(v).replace("-", MINUS);
};
export const f3 = nf({ minimumFractionDigits: 3, maximumFractionDigits: 3 });
export const f2 = nf({ minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const f1 = nf({ minimumFractionDigits: 1, maximumFractionDigits: 1 });
export const pct1 = nf({ style: "percent", minimumFractionDigits: 1, maximumFractionDigits: 1 });
export const signedPct2 = nf({ style: "percent", minimumFractionDigits: 2, maximumFractionDigits: 2, signDisplay: "exceptZero" });
export const int = nf({ maximumFractionDigits: 0 });
export const range = (i: { lo: number; hi: number }, f: (v: number) => string) => `${f(i.lo)} to ${f(i.hi)}`;
export const level = (code: string) => {
  const words = code
    .toLowerCase()
    .split("_")
    .map((w) => ({ pos: "positive", neg: "negative" })[w] ?? w)
    .join(" ");
  return words[0].toUpperCase() + words.slice(1);
};

export const BANNED: [RegExp, string][] = [
  [/confidence(?!\s+interval)/i, '"confidence" without "interval"'],
  [/reasoning/i, '"reasoning"'],
  [/chance of profit/i, '"chance of profit"'],
  [/\b(?:BUY|SELL|Buy|Sell)\b/, "Buy/Sell labels"],
];

type Interval = { point: number; lo: number; hi: number };
type Bin = { binLow: number; binHigh: number; rows: number; meanScore: number; upRate: number };
export type Arm = {
  name: string;
  rule: string;
  lookahead: boolean;
  auc: Interval;
  brierSkill: Interval | null;
  excessSharpe: Interval;
  excessSharpeByCost: { costBps: number; value: number }[];
  exposure: number;
  switchesPerYear: number;
  maxDrawdown: number;
  calibration: Bin[] | null;
};
type Summary = {
  outcome: "jev_better" | "jev_worse" | "inconclusive";
  period: { label: string; first: string; last: string };
  labelled: number;
  blocks: number;
  sharpeBlocks: number;
  primary: Interval & { candidate: string; baseline: string };
  power: { mde: number };
  costsBps: number[];
  arms: Arm[];
};
type State = {
  levels: Record<string, string>;
  pUp: number;
  pSd: number;
  coherence: number;
  samples: { order: number[]; pHi: number; pLo: number }[];
  development: { n: number; upRate: number | null; empiricalP: number };
};
type Policy = {
  modelServed: string;
  dimensions: { name: string; field: string; levels: { level: string; text: string }[] }[];
  states: State[];
};
type Manifest = {
  study: { symbols: string[]; modelServed: string; horizon: number };
  datasets: {
    market: Record<string, { sha256: string }>;
    policy: { sha256: string };
    callLog: { sha256: string };
  };
  runs: {
    holdout: { gitCommit: string; preregSha256: string; resultSha256: string };
    export: { inputs: Record<string, string> };
  };
  files: Record<string, string>;
};
type SymbolData = {
  days: {
    date: string[];
    split: ("fit" | "validate" | "holdout")[];
    state: number[];
    jev: (0 | 1)[];
    fwdRet20: (number | null)[];
  };
};

const dir = path.resolve(import.meta.dirname, "..", process.env.EXPORT_DIR ?? "../export/v1");
const read = (file: string): unknown => JSON.parse(readFileSync(path.join(dir, file), "utf8"));
export const manifest = read("manifest.json") as Manifest;
export const summary = read("summary.json") as Summary;
export const policy = read("policy.json") as Policy;
export const symbolData = (s: string) => read(`symbols/${s}.json`) as SymbolData;
