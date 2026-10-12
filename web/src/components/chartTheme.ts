import { ColorType, CrosshairMode, type DeepPartial, type ChartOptions } from "lightweight-charts";

export const CHART_COLORS = {
  background: "#111a2b",
  text: "#a3b1c8",
  grid: "#1c2740",
  border: "#24314d",
  up: "#34d399",
  down: "#f87171",
  devUp: "#5b6f8f",
  devDown: "#3d4a63",
  long: "#34d399",
  flat: "#fbbf24",
  holdoutBand: "rgba(110, 168, 255, 0.14)",
  holdoutEdge: "#6ea8ff",
  selected: "rgba(255, 209, 102, 0.35)",
  selectedSolid: "#ffd166",
  jev: "#6ea8ff",
  empirical_table: "#fb923c",
  buy_hold: "#cbd5e1",
} as const;

export function chartOptions(): DeepPartial<ChartOptions> {
  return {
    autoSize: true,
    layout: {
      background: { type: ColorType.Solid, color: CHART_COLORS.background },
      textColor: CHART_COLORS.text,
      fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif",
    },
    grid: { vertLines: { color: CHART_COLORS.grid }, horzLines: { color: CHART_COLORS.grid } },
    rightPriceScale: { borderColor: CHART_COLORS.border },
    timeScale: { borderColor: CHART_COLORS.border, lockVisibleTimeRangeOnResize: true },
    crosshair: { mode: CrosshairMode.Normal },
    kineticScroll: { touch: false, mouse: false },
  };
}
