import { formatDay, formatHour } from "./format";

/** What differs on screen between bar sizes. The export holds one folder per market. */
export const MARKETS = {
  daily: {
    label: "Daily",
    unit: "day",
    ranges: ["1W", "1M", "3M", "1Y", "5Y", "All"],
    formatTime: formatDay,
    prices: "real prices",
  },
  hourly: {
    label: "Hourly",
    unit: "hour",
    ranges: ["1D", "1W", "1M", "3M", "1Y", "All"],
    formatTime: formatHour,
    prices: "about 2.7 years of hourly prices",
  },
} as const;

export type Market = keyof typeof MARKETS;
export type Range = (typeof MARKETS)[Market]["ranges"][number];
export const MARKET_IDS = Object.keys(MARKETS) as Market[];
