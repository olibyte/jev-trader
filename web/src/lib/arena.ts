import "server-only";
import { readFileSync } from "node:fs";
import path from "node:path";
import { z } from "zod";

const ARENA_DIR = path.resolve(process.env.ARENA_DIR ?? path.join(process.cwd(), "..", "export", "arena", "v1"));

const KINDS = ["benchmark", "indicator", "candlestick", "ml", "jev", "control"] as const;
const RANGES = ["1W", "1M", "3M", "1Y", "5Y", "All"] as const;

const catalogSchema = z.object({
  catalogVersion: z.number().int(),
  strategies: z
    .array(z.object({ id: z.string(), title: z.string(), plain: z.string().min(1), rule: z.string(), kind: z.enum(KINDS) }))
    .min(2),
});

const comparisonsSchema = z.object({
  pairs: z.array(
    z.object({
      a: z.string(),
      b: z.string(),
      scope: z.string(),
      period: z.string(),
      verdict: z.enum(["a_ahead", "b_ahead", "no_difference", "too_early"]).nullable(),
    }),
  ),
  strategies: z.array(
    z.object({
      id: z.string(),
      scope: z.string(),
      period: z.string(),
      maxDrawdown: z.number().min(0).max(1),
      switchesPerYear: z.number().min(0),
      exposure: z.number().min(0).max(1),
    }),
  ),
});

const windowsSchema = z.object({
  scope: z.literal("portfolio"),
  last: z.iso.date(),
  windows: z.array(
    z.object({
      range: z.enum(RANGES),
      base: z.iso.date().nullable(),
      strategies: z.record(
        z.string(),
        z.object({ growth: z.number().positive(), exposure: z.number().min(0).max(1), maxDrawdown: z.number().min(0).max(1) }),
      ),
    }),
  ),
});

const curveSchema = z.object({
  scope: z.literal("portfolio"),
  periods: z.object({
    backtest: z.object({ date: z.array(z.iso.date()).min(2), equity: z.record(z.string(), z.array(z.number().positive())) }),
  }),
});

const prices = z.array(z.number().positive()).min(2);
const fundSchema = z.object({
  symbol: z.string(),
  date: z.array(z.iso.date()).min(2),
  open: prices,
  high: prices,
  low: prices,
  close: prices,
  trades: z.record(z.string(), z.object({ buy: z.array(z.iso.date()), sell: z.array(z.iso.date()) })),
});

const manifestSchema = z.object({ scopes: z.array(z.string()).min(1), settings: z.object({ costBps: z.number().min(0) }) });

const FUND_NAMES: Record<string, string> = {
  SPY: "S&P 500",
  QQQ: "Nasdaq 100",
  IWM: "Small companies",
  DIA: "Dow Jones",
  XLB: "Materials",
  XLE: "Energy",
  XLF: "Finance",
  XLI: "Industry",
  XLK: "Technology",
  XLP: "Everyday goods",
  XLU: "Utilities",
  XLV: "Health care",
  XLY: "Shopping and leisure",
};

export type Kind = (typeof KINDS)[number];
export type Range = (typeof RANGES)[number];
export type Strategy = { id: string; title: string; plain: string; rule: string; kind: Kind };
export type WindowStats = { growth: number; exposure: number; maxDrawdown: number };
export type Window = { range: Range; base: string | null; strategies: Record<string, WindowStats> };
export type Fund = { ticker: string; name: string };
/** The portfolio's daily growth of $1 for each strategy, served at /preview/data/portfolio.json. */
export type Curve = { date: string[]; equity: Record<string, number[]> };
/** One fund's daily bars and each strategy's trades, served at /preview/data/funds/{ticker}.json. */
export type FundBars = z.infer<typeof fundSchema>;

export type Arena = {
  strategies: Strategy[];
  windows: Window[];
  first: string;
  last: string;
  costBps: number;
  funds: Fund[];
  switchesPerYear: Record<string, number>;
  /** Whether the all-funds result could not separate a pair, keyed `${a}:${b}` in both orders. */
  tooClose: Record<string, boolean>;
  curve: Curve;
  bars: Record<string, FundBars>;
};

function read<T>(file: string, schema: z.ZodType<T>): T {
  const full = path.join(ARENA_DIR, file);
  const parsed = schema.safeParse(JSON.parse(readFileSync(full, "utf8")));
  if (!parsed.success) throw new Error(`${full}: ${parsed.error.message}`);
  return parsed.data;
}

function check(ok: boolean, file: string, message: string) {
  if (!ok) throw new Error(`${path.join(ARENA_DIR, file)}: ${message}`);
}

function readArena(): Arena {
  const catalog = read("catalog.json", catalogSchema);
  const comparisons = read("comparisons.json", comparisonsSchema);
  const { scopes, settings } = read("manifest.json", manifestSchema);
  const { last, windows } = read("windows.json", windowsSchema);
  const curve = read("curves/portfolio.json", curveSchema).periods.backtest;
  const strategies = catalog.strategies.map(({ id, title, plain, rule, kind }) => ({ id, title, plain, rule, kind }));
  const ids = strategies.map((s) => s.id);

  check(curve.date.at(-1) === last, "windows.json", `last is ${last}, not the last curve date ${curve.date.at(-1)}`);
  check(
    windows.map((w) => w.range).join() === RANGES.join(),
    "windows.json",
    `the ranges are ${windows.map((w) => w.range).join(", ")}, not ${RANGES.join(", ")}`,
  );
  const portfolioRows = comparisons.strategies.filter((r) => r.scope === "portfolio" && r.period === "backtest");
  for (const w of windows) {
    check((w.base === null) === (w.range === "All"), "windows.json", `the ${w.range} window has base ${w.base}`);
    check(w.base === null || curve.date.includes(w.base), "windows.json", `the ${w.range} base ${w.base} is not a curve date`);
    for (const id of ids) check(id in w.strategies, "windows.json", `the ${w.range} window has no figures for "${id}"`);
  }
  const all = windows[windows.length - 1].strategies;
  for (const id of ids) {
    const series = curve.equity[id];
    check(series?.length === curve.date.length, "curves/portfolio.json", `the curve for "${id}" does not span the dates`);
    const end = series[series.length - 1];
    check(all[id].growth * 1000 === end * 1000, "windows.json", `All growth for "${id}" is ${all[id].growth}, not ${end}`);
    const row = portfolioRows.find((r) => r.id === id);
    check(
      row?.exposure === all[id].exposure && row.maxDrawdown === all[id].maxDrawdown,
      "windows.json",
      `the All window for "${id}" does not match its portfolio row in comparisons.json`,
    );
  }

  const tickers = scopes.filter((s) => s !== "portfolio");
  const funds = tickers.map((ticker) => {
    const name = FUND_NAMES[ticker];
    if (!name) throw new Error(`web/src/lib/arena.ts: FUND_NAMES has no name for scope "${ticker}"`);
    return { ticker, name };
  });
  const bars = Object.fromEntries(
    tickers.map((ticker) => {
      const file = `funds/${ticker}.json`;
      const fund = read(file, fundSchema);
      check(fund.symbol === ticker, file, `symbol is ${fund.symbol}`);
      for (const column of ["open", "high", "low", "close"] as const) {
        check(fund[column].length === fund.date.length, file, `${column} has ${fund[column].length} values for ${fund.date.length} dates`);
      }
      const dates = new Set(fund.date);
      for (const id of ids) {
        const trades = fund.trades[id];
        check(trades !== undefined, file, `no trades for "${id}"`);
        const off = [...trades.buy, ...trades.sell].find((d) => !dates.has(d));
        check(off === undefined, file, `trade date ${off} for "${id}" is not a bar date`);
      }
      return [ticker, fund];
    }),
  );

  const tooClose = Object.fromEntries(
    comparisons.pairs
      .filter((p) => p.scope === "portfolio" && p.period === "backtest")
      .flatMap((p) => [
        [`${p.a}:${p.b}`, p.verdict === "no_difference"],
        [`${p.b}:${p.a}`, p.verdict === "no_difference"],
      ]),
  );

  return {
    strategies,
    windows,
    first: curve.date[0],
    last,
    costBps: settings.costBps,
    funds,
    switchesPerYear: Object.fromEntries(portfolioRows.map((r) => [r.id, r.switchesPerYear])),
    tooClose,
    curve: { date: curve.date, equity: Object.fromEntries(ids.map((id) => [id, curve.equity[id]])) },
    bars,
  };
}

let loaded: Arena | undefined;

export function loadArena(): Arena {
  loaded ??= readArena();
  return loaded;
}
