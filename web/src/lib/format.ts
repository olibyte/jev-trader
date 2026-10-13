import type { Interval } from "./export";

const MINUS = "−";

function numberFormat(options: Intl.NumberFormatOptions): (value: number) => string {
  const nf = new Intl.NumberFormat("en-US", { signDisplay: "negative", ...options });
  return (value) => nf.format(value).replace("-", MINUS);
}

const fixed = (digits: number) => numberFormat({ minimumFractionDigits: digits, maximumFractionDigits: digits });
const percent = (digits: number, signDisplay: Intl.NumberFormatOptions["signDisplay"] = "negative") =>
  numberFormat({ style: "percent", minimumFractionDigits: digits, maximumFractionDigits: digits, signDisplay });

export const formatScore = fixed(3);
export const formatSharpe = fixed(2);
export const formatSampleProb = fixed(2);
export const formatBinEdge = fixed(1);
export const formatTurnover = fixed(1);
export const formatRate = percent(1);
export const formatReturn = percent(2, "exceptZero");
export const formatCount = numberFormat({ maximumFractionDigits: 0 });
export const formatPrice = fixed(2);
const usd = fixed(4);
export const formatUsd = (value: number) => `$${usd(value)}`;

export function formatInterval(interval: Pick<Interval, "lo" | "hi">, format: (v: number) => string): string {
  return `${format(interval.lo)} to ${format(interval.hi)}`;
}

const ABBREVIATIONS: Record<string, string> = { pos: "positive", neg: "negative" };

export function formatLevel(level: string): string {
  const words = level
    .toLowerCase()
    .split("_")
    .map((w) => ABBREVIATIONS[w] ?? w)
    .join(" ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}
