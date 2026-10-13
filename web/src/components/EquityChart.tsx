"use client";

import { createChart, LineSeries } from "lightweight-charts";
import { useEffect, useRef } from "react";
import type { Equity } from "@/lib/export";
import { CHART_COLORS, chartOptions } from "./chartTheme";

const ARMS = ["jev", "empirical_table", "buy_hold"] as const;

export function EquityChart({ equity, label }: { equity: Equity; label: string }) {
  const container = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!container.current) return;
    const api = createChart(container.current, { ...chartOptions(), handleScroll: false, handleScale: false });
    for (const arm of ARMS) {
      const series = api.addSeries(LineSeries, {
        color: CHART_COLORS[arm],
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: false,
        title: arm,
      });
      series.setData(equity.date.map((time, i) => ({ time, value: equity.arms[arm][i] })));
    }
    api.timeScale().fitContent();
    return () => api.remove();
  }, [equity]);

  return (
    <>
      <div ref={container} className="chart chart-small" role="img" aria-label={label} />
      <ul className="chart-legend" aria-label="Equity chart legend">
        {ARMS.map((arm) => (
          <li key={arm}>
            <span className="swatch" style={{ background: CHART_COLORS[arm] }} />
            <code>{arm}</code>
          </li>
        ))}
      </ul>
    </>
  );
}
