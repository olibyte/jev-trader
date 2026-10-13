"use client";

import {
  CandlestickSeries,
  type CandlestickData,
  createChart,
  createSeriesMarkers,
  type IChartApi,
  LineSeries,
  LineStyle,
  type LineData,
  type MouseEventParams,
  type SeriesMarker,
  type Time,
} from "lightweight-charts";
import { type RefObject, useEffect, useMemo, useRef, useState } from "react";
import type { Curve, Fund, FundBars } from "@/lib/arena";
import { formatDay, formatDollars, formatPrice } from "@/lib/format";
import { CHART_COLORS, chartOptions } from "../chartTheme";

const START = 1000;

export type Side = { id: string; label: string; color: string };

const cache = new Map<string, Promise<unknown>>();

/** Fetches a build-time JSON file once per page. Its route handler validated it with the arena schemas. */
function useData<T>(url: string): { data: T | null; failed: boolean } {
  const [state, setState] = useState<{ url: string; data: T | null; failed: boolean } | null>(null);
  useEffect(() => {
    let live = true;
    let request = cache.get(url);
    if (!request) {
      request = fetch(url).then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${url}: ${r.status}`))));
      request.catch(() => cache.delete(url));
      cache.set(url, request);
    }
    request.then(
      (data) => live && setState({ url, data: data as T, failed: false }),
      () => live && setState({ url, data: null, failed: true }),
    );
    return () => {
      live = false;
    };
  }, [url]);
  return state?.url === url ? state : { data: null, failed: false };
}

/**
 * A chart in `container` for the component's lifetime, and the hovered point's index, null off the chart.
 * React cleans up this effect before the caller's series effects, so those check that the chart is still current.
 */
function useChart(container: RefObject<HTMLDivElement | null>): [RefObject<IChartApi | null>, number | null] {
  const chart = useRef<IChartApi | null>(null);
  const [hovered, setHovered] = useState<number | null>(null);
  useEffect(() => {
    if (!container.current) return;
    const api = createChart(container.current, { ...chartOptions(), handleScroll: false, handleScale: false });
    const onMove = (param: MouseEventParams<Time>) =>
      setHovered(param.logical === undefined || param.point === undefined ? null : Math.round(param.logical));
    // Zoom and scroll are off, so the whole range always shows. A resize soon after the first draw otherwise keeps the old bar spacing.
    const fit = () => api.timeScale().fitContent();
    api.subscribeCrosshairMove(onMove);
    api.timeScale().subscribeSizeChange(fit);
    chart.current = api;
    return () => {
      api.timeScale().unsubscribeSizeChange(fit);
      api.unsubscribeCrosshairMove(onMove);
      api.remove();
      chart.current = null;
    };
  }, [container]);
  return [chart, hovered];
}

function at(hovered: number | null, n: number): number {
  return hovered === null ? n - 1 : Math.min(n - 1, Math.max(0, hovered));
}

function Waiting({ failed }: { failed: boolean }) {
  return (
    <>
      <p className="readout" />
      <div className="chart-box chart-wait">{failed ? "The chart could not load. Reload the page to try again." : "Loading the chart…"}</div>
    </>
  );
}

export function LineView({ base, sides }: { base: string | null; sides: Side[] }) {
  const { data, failed } = useData<Curve>("/preview/data/portfolio.json");
  return data ? <LineChart curve={data} base={base} sides={sides} /> : <Waiting failed={failed} />;
}

function LineChart({ curve, base, sides }: { curve: Curve; base: string | null; sides: Side[] }) {
  const container = useRef<HTMLDivElement>(null);
  const [chart, hovered] = useChart(container);
  const { dates, values } = useMemo(() => {
    const from = base === null ? 0 : curve.date.indexOf(base);
    return {
      dates: curve.date.slice(from),
      values: sides.map(({ id }) => {
        const series = curve.equity[id].slice(from);
        const start = base === null ? 1 : series[0];
        return series.map((v) => (START * v) / start);
      }),
    };
  }, [curve, base, sides]);

  useEffect(() => {
    const api = chart.current;
    if (!api) return;
    api.applyOptions({ localization: { priceFormatter: (v: number) => formatDollars(v) } });
    const lines = sides.map((s, k) => {
      const line = api.addSeries(LineSeries, { color: s.color, lineWidth: 2, priceLineVisible: false, lastValueVisible: false });
      line.setData(dates.map((time, i): LineData<Time> => ({ time, value: values[k][i] })));
      return line;
    });
    lines[0].createPriceLine({ price: START, color: CHART_COLORS.text, lineStyle: LineStyle.Dashed, lineWidth: 1, axisLabelVisible: false });
    api.timeScale().fitContent();
    return () => {
      if (chart.current === api) lines.forEach((line) => api.removeSeries(line));
    };
  }, [chart, dates, values, sides]);

  const i = at(hovered, dates.length);
  return (
    <>
      <p className="readout" aria-live="polite" data-testid="readout">
        <strong>{formatDay(dates[i])}</strong>
        {sides.map((s, k) => (
          <span key={s.id}>
            <i className="dot" style={{ "--c": s.color }} />
            {s.label} {formatDollars(values[k][i])}
          </span>
        ))}
      </p>
      <div
        ref={container}
        className="chart-box"
        role="img"
        aria-label={`What $1,000 became each day in strategy ${sides.map((s) => s.label).join(" and ")}. The dashed line is the $1,000 you started with.`}
        data-testid="line-chart"
      />
    </>
  );
}

type CandleProps = { fund: Fund; base: string | null; sides: Side[]; trades: boolean };

export function CandleView(props: CandleProps) {
  const { data, failed } = useData<FundBars>(`/preview/data/funds/${props.fund.ticker}.json`);
  return data ? <CandleChart bars={data} {...props} /> : <Waiting failed={failed} />;
}

function CandleChart({ bars, fund, base, sides, trades }: CandleProps & { bars: FundBars }) {
  const container = useRef<HTMLDivElement>(null);
  const [chart, hovered] = useChart(container);
  const from = useMemo(() => (base === null ? 0 : bars.date.findIndex((d) => d > base)), [bars, base]);

  useEffect(() => {
    const api = chart.current;
    if (!api) return;
    api.applyOptions({ localization: { priceFormatter: formatPrice } });
    const candles = api.addSeries(CandlestickSeries, {
      upColor: CHART_COLORS.up,
      downColor: CHART_COLORS.down,
      borderVisible: false,
      wickUpColor: CHART_COLORS.up,
      wickDownColor: CHART_COLORS.down,
      priceLineVisible: false,
      lastValueVisible: false,
    });
    const dates = bars.date.slice(from);
    candles.setData(
      dates.map((time, k): CandlestickData<Time> => {
        const i = from + k;
        return { time, open: bars.open[i], high: bars.high[i], low: bars.low[i], close: bars.close[i] };
      }),
    );
    if (trades) {
      const markers = sides
        .flatMap(({ id, color }) => [
          ...bars.trades[id].buy.map((time) => ({ time, color, position: "belowBar", shape: "arrowUp" }) satisfies SeriesMarker<Time>),
          ...bars.trades[id].sell.map((time) => ({ time, color, position: "aboveBar", shape: "arrowDown" }) satisfies SeriesMarker<Time>),
        ])
        .filter((m) => m.time >= dates[0])
        .sort((a, b) => a.time.localeCompare(b.time));
      createSeriesMarkers(candles, markers);
    }
    api.timeScale().fitContent();
    return () => {
      if (chart.current === api) api.removeSeries(candles);
    };
  }, [chart, bars, from, sides, trades]);

  const traded = sides.some(({ id }) => [...bars.trades[id].buy, ...bars.trades[id].sell].some((d) => d >= bars.date[from]));
  const i = from + at(hovered, bars.date.length - from);
  return (
    <>
      <p className="readout" aria-live="polite" data-testid="readout">
        <strong>{formatDay(bars.date[i])}</strong>
        <span>
          O {formatPrice(bars.open[i])} H {formatPrice(bars.high[i])} L {formatPrice(bars.low[i])} C {formatPrice(bars.close[i])}
        </span>
      </p>
      <div
        ref={container}
        className="chart-box"
        role="img"
        aria-label={`Daily prices of ${fund.name}${trades ? ", marked where each strategy bought and sold" : ""}`}
        data-testid="candle-chart"
      />
      {trades && !traded ? (
        <p className="muted" data-testid="no-trades">
          Neither strategy bought or sold {fund.name} in this range.
        </p>
      ) : null}
    </>
  );
}
