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
  type UTCTimestamp,
} from "lightweight-charts";
import { type RefObject, useEffect, useMemo, useRef, useState } from "react";
import type { Curve, Fund, FundBars, Market } from "@/lib/arena";
import { formatDollars, formatPrice } from "@/lib/format";
import { MARKETS } from "@/lib/markets";
import { CHART_COLORS, chartOptions } from "../chartTheme";

const START = 1000;
/** The candles view shows at most this many bars, the last of the range. */
const CANDLES = 250;

export type Side = { id: string; label: string; color: string };

/** How each market's bar key goes on the chart's time axis. */
const AXES: Record<Market, { time: (key: string) => Time; timeVisible: boolean }> = {
  daily: { time: (key) => key, timeVisible: false },
  // The key is New York clock time. Placed on the chart's UTC axis as is, the axis reads New York time.
  hourly: { time: (key) => (Date.parse(`${key}Z`) / 1000) as UTCTimestamp, timeVisible: true },
};

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

export function LineView({ market, base, sides }: { market: Market; base: string | null; sides: Side[] }) {
  const { data, failed } = useData<Curve>(`/preview/data/${market}/portfolio.json`);
  return data ? <LineChart market={market} curve={data} base={base} sides={sides} /> : <Waiting failed={failed} />;
}

function LineChart({ market, curve, base, sides }: { market: Market; curve: Curve; base: string | null; sides: Side[] }) {
  const container = useRef<HTMLDivElement>(null);
  const [chart, hovered] = useChart(container);
  const { dates, values } = useMemo(() => {
    const from = base === null ? 0 : curve.time.indexOf(base);
    return {
      dates: curve.time.slice(from),
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
    const { time, timeVisible } = AXES[market];
    api.applyOptions({ localization: { priceFormatter: (v: number) => formatDollars(v) }, timeScale: { timeVisible } });
    const lines = sides.map((s, k) => {
      const line = api.addSeries(LineSeries, { color: s.color, lineWidth: 2, priceLineVisible: false, lastValueVisible: false });
      line.setData(dates.map((key, i): LineData<Time> => ({ time: time(key), value: values[k][i] })));
      return line;
    });
    lines[0].createPriceLine({ price: START, color: CHART_COLORS.text, lineStyle: LineStyle.Dashed, lineWidth: 1, axisLabelVisible: false });
    api.timeScale().fitContent();
    return () => {
      if (chart.current === api) lines.forEach((line) => api.removeSeries(line));
    };
  }, [chart, market, dates, values, sides]);

  const { formatTime, unit } = MARKETS[market];
  const i = at(hovered, dates.length);
  return (
    <>
      <p className="readout" aria-live="polite" data-testid="readout">
        <strong>{formatTime(dates[i])}</strong>
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
        aria-label={`What $1,000 became each ${unit} in strategy ${sides.map((s) => s.label).join(" and ")}. The dashed line is the $1,000 you started with.`}
        data-testid="line-chart"
      />
    </>
  );
}

type CandleProps = { market: Market; fund: Fund; base: string | null; sides: Side[]; trades: boolean };

export function CandleView(props: CandleProps) {
  const { data, failed } = useData<FundBars>(`/preview/data/${props.market}/funds/${props.fund.ticker}.json`);
  return data ? <CandleChart bars={data} {...props} /> : <Waiting failed={failed} />;
}

function CandleChart({ bars, market, fund, base, sides, trades }: CandleProps & { bars: FundBars }) {
  const container = useRef<HTMLDivElement>(null);
  const [chart, hovered] = useChart(container);
  const { start, from } = useMemo(() => {
    const start = base === null ? 0 : bars.time.findIndex((key) => key > base);
    return { start, from: Math.max(start, bars.time.length - CANDLES) };
  }, [bars, base]);

  useEffect(() => {
    const api = chart.current;
    if (!api) return;
    const { time, timeVisible } = AXES[market];
    api.applyOptions({ localization: { priceFormatter: formatPrice }, timeScale: { timeVisible } });
    const candles = api.addSeries(CandlestickSeries, {
      upColor: CHART_COLORS.up,
      downColor: CHART_COLORS.down,
      borderVisible: false,
      wickUpColor: CHART_COLORS.up,
      wickDownColor: CHART_COLORS.down,
      priceLineVisible: false,
      lastValueVisible: false,
    });
    const keys = bars.time.slice(from);
    candles.setData(
      keys.map((key, k): CandlestickData<Time> => {
        const i = from + k;
        return { time: time(key), open: bars.open[i], high: bars.high[i], low: bars.low[i], close: bars.close[i] };
      }),
    );
    if (trades) {
      const markers = sides
        .flatMap(({ id, color }) => [
          ...bars.trades[id].buy.map((key) => ({ key, color, position: "belowBar", shape: "arrowUp" }) as const),
          ...bars.trades[id].sell.map((key) => ({ key, color, position: "aboveBar", shape: "arrowDown" }) as const),
        ])
        .filter((m) => m.key >= keys[0])
        .sort((a, b) => a.key.localeCompare(b.key))
        .map(({ key, ...m }): SeriesMarker<Time> => ({ ...m, time: time(key) }));
      createSeriesMarkers(candles, markers);
    }
    api.timeScale().fitContent();
    return () => {
      if (chart.current === api) api.removeSeries(candles);
    };
  }, [chart, market, bars, from, sides, trades]);

  const { formatTime, label, unit } = MARKETS[market];

  const traded = sides.some(({ id }) => [...bars.trades[id].buy, ...bars.trades[id].sell].some((d) => d >= bars.time[from]));
  const i = from + at(hovered, bars.time.length - from);
  return (
    <>
      <p className="readout" aria-live="polite" data-testid="readout">
        <strong>{formatTime(bars.time[i])}</strong>
        <span>
          O {formatPrice(bars.open[i])} H {formatPrice(bars.high[i])} L {formatPrice(bars.low[i])} C {formatPrice(bars.close[i])}
        </span>
      </p>
      <div
        ref={container}
        className="chart-box"
        role="img"
        aria-label={`${label} prices of ${fund.name}${trades ? ", marked where each strategy bought and sold" : ""}`}
        data-testid="candle-chart"
      />
      {from > start ? (
        <p className="muted" data-testid="candle-cap">
          Showing the last {CANDLES} {unit}s of this range.
        </p>
      ) : null}
      {trades && !traded ? (
        <p className="muted" data-testid="no-trades">
          Neither strategy bought or sold {fund.name} in this range.
        </p>
      ) : null}
    </>
  );
}
