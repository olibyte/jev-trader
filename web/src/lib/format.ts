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

const dollars = numberFormat({ style: "currency", currency: "USD", maximumFractionDigits: 0 });
const compactDollars = numberFormat({ style: "currency", currency: "USD", notation: "compact", maximumFractionDigits: 1 });
export const formatDollars = (value: number, { compact = false } = {}) => (compact ? compactDollars : dollars)(value);
export const formatShare = percent(0);

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
/** "2008-01" reads "Jan 2008". */
export const formatMonth = (month: string) => `${MONTHS[Number(month.slice(5, 7)) - 1]} ${month.slice(0, 4)}`;
/** "2025-10-07" reads "Oct 7, 2025". */
export const formatDay = (day: string) => `${MONTHS[Number(day.slice(5, 7)) - 1]} ${Number(day.slice(8, 10))}, ${day.slice(0, 4)}`;
/** "2026-10-09T13:30" reads "Oct 9, 2026, 1:30 pm". The key is already New York clock time, so no zone math. */
export const formatHour = (time: string) => {
  const hour = Number(time.slice(11, 13));
  return `${formatDay(time)}, ${hour % 12 || 12}:${time.slice(14, 16)} ${hour < 12 ? "am" : "pm"}`;
};
