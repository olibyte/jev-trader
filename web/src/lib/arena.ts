import "server-only";
import { readFileSync } from "node:fs";
import path from "node:path";
import { z } from "zod";
import { MARKET_IDS, MARKETS, type Market, type Range } from "./markets";

const ARENA_DIR = path.resolve(process.env.ARENA_DIR ?? path.join(process.cwd(), "..", "export", "arena", "v2"));

const KINDS = ["benchmark", "indicator", "candlestick", "ml", "jev", "control"] as const;

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

/** Each market's bar key: a session date, or a New York clock time such as 2026-10-09T13:30. */
const KEYS = {
  daily: { field: "date", schema: z.iso.date() },
  // The length check rejects a zone suffix, which the local datetime schema allows.
  hourly: { field: "time", schema: z.iso.datetime({ local: true, precision: -1 }).length(16) },
} as const;

const stats = z.object({ growth: z.number().positive(), exposure: z.number().min(0).max(1), maxDrawdown: z.number().min(0).max(1) });
const prices = z.array(z.number().positive()).min(2);
const equity = z.record(z.string(), z.array(z.number().positive()));

function shapes(market: Market) {
  const key = KEYS[market].schema;
  return {
    windows: z.object({
      scope: z.literal("portfolio"),
      last: key,
      windows: z.array(z.object({ range: z.enum(MARKETS[market].ranges), base: key.nullable(), strategies: z.record(z.string(), stats) })),
    }),
    keys: z.array(key).min(2),
    fund: {
      symbol: z.string(),
      open: prices,
      high: prices,
      low: prices,
      close: prices,
      trades: z.record(z.string(), z.object({ buy: z.array(key), sell: z.array(key) })),
    },
  };
}

const daily = shapes("daily");
const hourly = shapes("hourly");
const portfolio = <T extends z.ZodRawShape>(backtest: T) =>
  z.object({ scope: z.literal("portfolio"), periods: z.object({ backtest: z.object(backtest) }) });

/** Each market's file schemas, which rename the daily `date` key to `time` so the rest of the site reads one shape. */
const SCHEMAS = {
  daily: {
    windows: daily.windows,
    curve: portfolio({ date: daily.keys, equity }).transform(({ periods }) => ({ time: periods.backtest.date, equity: periods.backtest.equity })),
    fund: z.object({ ...daily.fund, date: daily.keys }).transform(({ date, ...fund }) => ({ ...fund, time: date })),
  },
  hourly: {
    windows: hourly.windows,
    curve: portfolio({ time: hourly.keys, equity }).transform(({ periods }) => periods.backtest),
    fund: z.object({ ...hourly.fund, time: hourly.keys }),
  },
} satisfies Record<
  Market,
  { windows: z.ZodType<{ last: string; windows: Window[] }>; curve: z.ZodType<Curve>; fund: z.ZodType<FundBars> }
>;

const marketEntry = z.object({ statistics: z.boolean() });
const manifestSchema = z.object({
  markets: z.object({ daily: marketEntry.extend({ scopes: z.array(z.string()).min(1) }), hourly: marketEntry }),
  settings: z.object({ costBps: z.number().min(0) }),
});

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
export type { Market, Range };
export type Strategy = { id: string; title: string; plain: string; rule: string; kind: Kind };
export type WindowStats = { growth: number; exposure: number; maxDrawdown: number };
export type Window = { range: Range; base: string | null; strategies: Record<string, WindowStats> };
export type Fund = { ticker: string; name: string };
/** The portfolio's growth of $1 for each strategy at each bar, served at /preview/data/{market}/portfolio.json. */
export type Curve = { time: string[]; equity: Record<string, number[]> };
/** One fund's bars and each strategy's trades, served at /preview/data/{market}/funds/{ticker}.json. */
export type FundBars = {
  symbol: string;
  time: string[];
  open: number[];
  high: number[];
  low: number[];
  close: number[];
  trades: Record<string, { buy: string[]; sell: string[] }>;
};
/** What the screen needs for one market. `tooClose` is null when the market has no statistics (no comparisons.json). */
export type MarketView = {
  windows: Window[];
  first: string;
  last: string;
  /** Whether the all-funds result could not separate a pair, keyed `${a}:${b}` in both orders. */
  tooClose: Record<string, boolean> | null;
};
export type Arena = {
  strategies: Strategy[];
  costBps: number;
  funds: Fund[];
  /** From the daily comparisons. */
  switchesPerYear: Record<string, number>;
  markets: Record<Market, MarketView & { curve: Curve; bars: Record<string, FundBars> }>;
};

type Comparisons = z.output<typeof comparisonsSchema>;

function read<T>(file: string, schema: z.ZodType<T>): T {
  const full = path.join(ARENA_DIR, file);
  const parsed = schema.safeParse(JSON.parse(readFileSync(full, "utf8")));
  if (!parsed.success) throw new Error(`${full}: ${parsed.error.message}`);
  return parsed.data;
}

function check(ok: boolean, file: string, message: string): asserts ok {
  if (!ok) throw new Error(`${path.join(ARENA_DIR, file)}: ${message}`);
}

function readMarket(market: Market, ids: string[], tickers: string[], comparisons: Comparisons | null): Arena["markets"][Market] {
  const { field } = KEYS[market];
  const { ranges } = MARKETS[market];
  const windowsFile = `${market}/windows.json`;
  const curveFile = `${market}/curves/portfolio.json`;
  const { last, windows } = read(windowsFile, SCHEMAS[market].windows);
  const curve = read(curveFile, SCHEMAS[market].curve);

  check(curve.time.at(-1) === last, windowsFile, `last is ${last}, not the last curve ${field} ${curve.time.at(-1)}`);
  check(
    windows.map((w) => w.range).join() === ranges.join(),
    windowsFile,
    `the ranges are ${windows.map((w) => w.range).join(", ")}, not ${ranges.join(", ")}`,
  );
  for (const w of windows) {
    check((w.base === null) === (w.range === "All"), windowsFile, `the ${w.range} window has base ${w.base}`);
    check(w.base === null || curve.time.includes(w.base), windowsFile, `the ${w.range} base ${w.base} is not a curve ${field}`);
    for (const id of ids) check(id in w.strategies, windowsFile, `the ${w.range} window has no figures for "${id}"`);
  }
  const portfolioRows = comparisons?.strategies.filter((r) => r.scope === "portfolio" && r.period === "backtest");
  const all = windows[windows.length - 1].strategies;
  for (const id of ids) {
    const series = curve.equity[id];
    check(series?.length === curve.time.length, curveFile, `the curve for "${id}" does not span the ${field}s`);
    const end = series[series.length - 1];
    check(all[id].growth * 1000 === end * 1000, windowsFile, `All growth for "${id}" is ${all[id].growth}, not ${end}`);
    if (!portfolioRows) continue;
    const row = portfolioRows.find((r) => r.id === id);
    check(
      row?.exposure === all[id].exposure && row.maxDrawdown === all[id].maxDrawdown,
      windowsFile,
      `the All window for "${id}" does not match its portfolio row in comparisons.json`,
    );
  }

  const bars = Object.fromEntries(
    tickers.map((ticker) => {
      const file = `${market}/funds/${ticker}.json`;
      const fund = read(file, SCHEMAS[market].fund);
      check(fund.symbol === ticker, file, `symbol is ${fund.symbol}`);
      for (const column of ["open", "high", "low", "close"] as const) {
        check(fund[column].length === fund.time.length, file, `${column} has ${fund[column].length} values for ${fund.time.length} ${field}s`);
      }
      const keys = new Set(fund.time);
      for (const id of ids) {
        const trades = fund.trades[id];
        check(trades !== undefined, file, `no trades for "${id}"`);
        const off = [...trades.buy, ...trades.sell].find((k) => !keys.has(k));
        check(off === undefined, file, `trade ${field} ${off} for "${id}" is not a bar ${field}`);
      }
      return [ticker, fund];
    }),
  );

  const tooClose =
    comparisons &&
    Object.fromEntries(
      comparisons.pairs
        .filter((p) => p.scope === "portfolio" && p.period === "backtest")
        .flatMap((p) => [
          [`${p.a}:${p.b}`, p.verdict === "no_difference"],
          [`${p.b}:${p.a}`, p.verdict === "no_difference"],
        ]),
    );

  return {
    windows,
    first: curve.time[0],
    last,
    tooClose,
    curve: { time: curve.time, equity: Object.fromEntries(ids.map((id) => [id, curve.equity[id]])) },
    bars,
  };
}

function readArena(): Arena {
  const catalog = read("catalog.json", catalogSchema);
  const { markets, settings } = read("manifest.json", manifestSchema);
  const strategies = catalog.strategies.map(({ id, title, plain, rule, kind }) => ({ id, title, plain, rule, kind }));
  const ids = strategies.map((s) => s.id);
  // Hourly scopes are only the portfolio, but each market writes a file for every daily fund.
  const tickers = markets.daily.scopes.filter((s) => s !== "portfolio");
  const funds = tickers.map((ticker) => {
    const name = FUND_NAMES[ticker];
    if (!name) throw new Error(`web/src/lib/arena.ts: FUND_NAMES has no name for scope "${ticker}"`);
    return { ticker, name };
  });

  const comparisons = Object.fromEntries(
    MARKET_IDS.map((m) => [m, markets[m].statistics ? read(`${m}/comparisons.json`, comparisonsSchema) : null]),
  ) as Record<Market, Comparisons | null>;
  const daily = comparisons.daily;
  check(daily !== null, "manifest.json", "the daily market has no statistics, so there are no moves a year");

  return {
    strategies,
    costBps: settings.costBps,
    funds,
    switchesPerYear: Object.fromEntries(
      daily.strategies.filter((r) => r.scope === "portfolio" && r.period === "backtest").map((r) => [r.id, r.switchesPerYear]),
    ),
    markets: Object.fromEntries(MARKET_IDS.map((m) => [m, readMarket(m, ids, tickers, comparisons[m])])) as Arena["markets"],
  };
}

let loaded: Arena | undefined;

export function loadArena(): Arena {
  loaded ??= readArena();
  return loaded;
}
