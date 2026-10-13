import "server-only";
import { readFileSync } from "node:fs";
import path from "node:path";
import { z } from "zod";

const ARENA_DIR = path.resolve(process.env.ARENA_DIR ?? path.join(process.cwd(), "..", "export", "arena", "v1"));

const catalogSchema = z.object({
  catalogVersion: z.number().int(),
  strategies: z.array(z.object({ id: z.string(), title: z.string(), rule: z.string() })).min(2),
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

const curveSchema = z.object({
  scope: z.string(),
  periods: z.object({
    backtest: z.object({ date: z.array(z.iso.date()).min(2), equity: z.record(z.string(), z.array(z.number().positive())) }),
  }),
});

const manifestSchema = z.object({ scopes: z.array(z.string()).min(1), settings: z.object({ costBps: z.number().min(0) }) });

// Plain-language copy lives here until the catalog carries it. Every catalog id needs an entry, or the build fails.
const PLAIN: Record<string, string> = {
  buy_hold: "Put the money in on day one and never take it out.",
  golden_cross: "Stay in while prices are on a long climb. Move to cash when the climb ends.",
  macd_cross: "Stay in while prices are speeding up. Move to cash when they slow down.",
  bollinger_bounce: "Jump in after an unusually sharp drop. Get out once the price is back to normal.",
};

const COLORS = ["#2f6fdf", "#e2622b", "#14966a", "#8a4fd1", "#b8860b", "#c2185b", "#00838f", "#5d4037"];

const FUNDS: Record<string, string> = {
  portfolio: "All 13 funds",
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

export type Strategy = { id: string; title: string; rule: string; plain: string; color: string };

export type Stats = { end: number; maxDrawdown: number; exposure: number; switchesPerYear: number };

/** One fund's growth of $1, thinned to the last trading day of each month. */
export type Fund = {
  scope: string;
  name: string;
  ticker: string | null;
  months: string[];
  lines: Record<string, number[]>;
  stats: Record<string, Stats>;
};

export type Arena = {
  strategies: Strategy[];
  first: string;
  last: string;
  costBps: number;
  funds: Fund[];
  /** Whether the all-funds result could not separate a pair, keyed `${a}:${b}` in catalog order. */
  tooClose: Record<string, boolean>;
};

function read<T>(file: string, schema: z.ZodType<T>): T {
  const full = path.join(ARENA_DIR, file);
  const parsed = schema.safeParse(JSON.parse(readFileSync(full, "utf8")));
  if (!parsed.success) throw new Error(`${full}: ${parsed.error.message}`);
  return parsed.data;
}

function monthEnds(dates: string[]): number[] {
  return dates.flatMap((d, i) => (i === dates.length - 1 || dates[i + 1].slice(0, 7) !== d.slice(0, 7) ? [i] : []));
}

function readArena(): Arena {
  const catalog = read("catalog.json", catalogSchema);
  const comparisons = read("comparisons.json", comparisonsSchema);
  const { scopes, settings } = read("manifest.json", manifestSchema);

  const strategies = catalog.strategies.map((s, i) => {
    const plain = PLAIN[s.id];
    if (!plain) throw new Error(`web/src/lib/arena.ts: PLAIN has no sentence for catalog id "${s.id}"`);
    return { id: s.id, title: s.title, rule: s.rule, plain, color: COLORS[i % COLORS.length] };
  });

  let first = "";
  let last = "";
  const funds = scopes.map((scope): Fund => {
    const name = FUNDS[scope];
    if (!name) throw new Error(`web/src/lib/arena.ts: FUNDS has no name for scope "${scope}"`);
    const { date, equity } = read(`curves/${scope}.json`, curveSchema).periods.backtest;
    first ||= date[0];
    last ||= date[date.length - 1];
    const keep = monthEnds(date);
    const lines: Record<string, number[]> = {};
    const stats: Record<string, Stats> = {};
    for (const s of strategies) {
      const series = equity[s.id];
      const row = comparisons.strategies.find((r) => r.id === s.id && r.scope === scope && r.period === "backtest");
      if (series?.length !== date.length || !row) throw new Error(`${scope}: missing curve or stats for "${s.id}"`);
      lines[s.id] = keep.map((i) => series[i]);
      stats[s.id] = {
        end: series[series.length - 1],
        maxDrawdown: row.maxDrawdown,
        exposure: row.exposure,
        switchesPerYear: row.switchesPerYear,
      };
    }
    return { scope, name, ticker: scope === "portfolio" ? null : scope, months: keep.map((i) => date[i].slice(0, 7)), lines, stats };
  });

  const tooClose = Object.fromEntries(
    comparisons.pairs
      .filter((p) => p.scope === "portfolio" && p.period === "backtest")
      .map((p) => [`${p.a}:${p.b}`, p.verdict === "no_difference"]),
  );

  return { strategies, first, last, costBps: settings.costBps, funds, tooClose };
}

let loaded: Arena | undefined;

export function loadArena(): Arena {
  loaded ??= readArena();
  return loaded;
}
