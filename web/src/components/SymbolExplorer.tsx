"use client";

import {
  AreaSeries,
  CandlestickSeries,
  type CandlestickData,
  createChart,
  createSeriesMarkers,
  HistogramSeries,
  type LineData,
  type IChartApi,
  type ISeriesApi,
  type MouseEventParams,
  type SeriesMarker,
  type Time,
  type WhitespaceData,
} from "lightweight-charts";
import { type KeyboardEvent, useCallback, useEffect, useEffectEvent, useMemo, useRef, useSyncExternalStore } from "react";
import type { Days, Development, PeriodLabel, Split } from "@/lib/export";
import { formatCount, formatPrice, formatRate, formatReturn, formatSampleProb, formatScore } from "@/lib/format";
import { CHART_COLORS, chartOptions } from "./chartTheme";

export type ExplorerState = {
  pUp: number;
  pSd: number;
  coherence: number;
  samples: { pHi: number; pLo: number }[];
  saw: { field: string; text: string }[];
  development: Development;
};

type Props = {
  symbol: string;
  days: Days;
  states: Record<number, ExplorerState>;
  periodLabels: Record<Split, PeriodLabel>;
  horizon: number;
};

const POSITION = { 0: "Flat", 1: "Long" } as const;
const KEY_STEPS: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1 };

function subscribeHash(onChange: () => void): () => void {
  window.addEventListener("hashchange", onChange);
  return () => window.removeEventListener("hashchange", onChange);
}
const readHash = () => decodeURIComponent(window.location.hash.slice(1));
const readServerHash = () => "";

function useSelectedDay(dates: string[]): [number, (index: number) => void] {
  const hash = useSyncExternalStore(subscribeHash, readHash, readServerHash);
  const byDate = useMemo(() => new Map(dates.map((d, i) => [d, i])), [dates]);
  const selected = byDate.get(hash) ?? dates.length - 1;
  const select = useCallback(
    (index: number) => {
      const clamped = Math.min(Math.max(index, 0), dates.length - 1);
      window.history.replaceState(null, "", `#${dates[clamped]}`);
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    },
    [dates],
  );
  return [selected, select];
}

function positionMarkers(days: Days): SeriesMarker<Time>[] {
  return days.jev.flatMap((position, i): SeriesMarker<Time>[] => {
    const previous = i === 0 ? 0 : days.jev[i - 1];
    if (position === previous) return [];
    return position === 1
      ? [{ time: days.date[i], position: "belowBar", shape: "arrowUp", color: CHART_COLORS.long, size: 0.6 }]
      : [{ time: days.date[i], position: "aboveBar", shape: "arrowDown", color: CHART_COLORS.flat, size: 0.6 }];
  });
}

function PriceChart({ days, selected, onSelect }: { days: Days; selected: number; onSelect: (i: number) => void }) {
  const container = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const highlight = useRef<ISeriesApi<"Histogram"> | null>(null);
  const handleClick = useEffectEvent((param: MouseEventParams<Time>) => {
    if (param.logical !== undefined) onSelect(Math.round(param.logical));
  });

  useEffect(() => {
    if (!container.current) return;
    const api = createChart(container.current, chartOptions());
    const candles = api.addSeries(CandlestickSeries, {
      upColor: CHART_COLORS.up,
      downColor: CHART_COLORS.down,
      borderVisible: false,
      wickUpColor: CHART_COLORS.up,
      wickDownColor: CHART_COLORS.down,
      priceLineVisible: false,
      lastValueVisible: false,
    });
    candles.setData(
      days.date.map((time, i): CandlestickData<Time> => {
        const bar = { time, open: days.open[i], high: days.high[i], low: days.low[i], close: days.close[i] };
        if (days.split[i] === "holdout") return bar;
        const color = days.close[i] >= days.open[i] ? CHART_COLORS.devUp : CHART_COLORS.devDown;
        return { ...bar, color, wickColor: color };
      }),
    );
    createSeriesMarkers(candles, positionMarkers(days));

    const band = {
      priceScaleId: "band",
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
      autoscaleInfoProvider: () => ({ priceRange: { minValue: 0, maxValue: 1 } }),
    } as const;
    const holdout = api.addSeries(AreaSeries, {
      ...band,
      lineVisible: false,
      topColor: CHART_COLORS.holdoutBand,
      bottomColor: CHART_COLORS.holdoutBand,
    });
    holdout.setData(
      days.date.map((time, i): LineData<Time> | WhitespaceData<Time> =>
        days.split[i] === "holdout" ? { time, value: 1 } : { time },
      ),
    );
    highlight.current = api.addSeries(HistogramSeries, { ...band, base: 0, color: CHART_COLORS.selected });
    api.priceScale("band").applyOptions({ visible: false, scaleMargins: { top: 0, bottom: 0 } });
    api.subscribeClick(handleClick);
    chart.current = api;
    return () => {
      api.unsubscribeClick(handleClick);
      api.remove();
      chart.current = null;
      highlight.current = null;
    };
  }, [days]);

  useEffect(() => {
    highlight.current?.setData([{ time: days.date[selected], value: 1 }]);
    const timeScale = chart.current?.timeScale();
    const range = timeScale?.getVisibleLogicalRange();
    if (!timeScale) return;
    if (!range || selected < range.from || selected > range.to) {
      const width = range ? range.to - range.from : 250;
      const to = Math.min(selected + width * 0.2, days.date.length - 1 + 5);
      timeScale.setVisibleLogicalRange({ from: to - width, to });
    }
  }, [days, selected]);

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const step = KEY_STEPS[event.key];
    if (step !== undefined) onSelect(selected + step);
    else if (event.key === "Home") onSelect(0);
    else if (event.key === "End") onSelect(days.date.length - 1);
    else return;
    event.preventDefault();
  };

  return (
    <div
      ref={container}
      className="chart"
      role="application"
      tabIndex={0}
      aria-label="Daily candlestick chart. Click a day to select it, or use the left and right arrow keys, Home, and End."
      onKeyDown={onKeyDown}
      data-testid="price-chart"
    />
  );
}

function DayPanel({ days, index, state, periodLabels, horizon }: { days: Days; index: number; state: ExplorerState } & Pick<Props, "periodLabels" | "horizon">) {
  const split = days.split[index];
  const label = periodLabels[split];
  const nextOpen = days.date[index + 1];
  const exitOpen = days.date[index + 1 + horizon];
  const fwd = days.fwdRet20[index];
  const position = POSITION[days.jev[index]];
  const dev = state.development;

  return (
    <section className="day-panel" aria-labelledby="day-heading" data-testid="day-panel">
      <h2 id="day-heading" className="day-heading">
        <span data-testid="tt-date" className="num">
          {days.date[index]}
        </span>{" "}
        <span className={label === "holdout" ? "badge badge-holdout" : "badge"} data-testid="tt-period">
          {label === "holdout" ? "holdout" : `development (${split})`}
        </span>
      </h2>
      <div className="day-grid">
        <section aria-labelledby="saw-heading">
          <h3 id="saw-heading">What Jev saw</h3>
          <ol className="saw" data-testid="tt-saw">
            {state.saw.map((line) => (
              <li key={line.field}>
                {line.field}: {line.text}
              </li>
            ))}
          </ol>
          <p className="small muted">
            This is sample 1 exactly as logged. Jev was asked {state.samples.length} times about this state, with the line
            order shuffled each time. It saw no ticker, date, or price.
          </p>
        </section>
        <section aria-labelledby="answer-heading">
          <h3 id="answer-heading">What Jev answered</h3>
          <dl className="answer">
            <div>
              <dt>Jev&rsquo;s answer, P(higher in 20 trading days)</dt>
              <dd>
                <strong className="num" data-testid="tt-pup">
                  {formatScore(state.pUp)}
                </strong>
                <ol className="samples" data-testid="tt-samples">
                  {state.samples.map((s, i) => (
                    <li key={i} className="num">
                      P(higher) {formatSampleProb(s.pHi)}, P(lower or equal) {formatSampleProb(s.pLo)}
                    </li>
                  ))}
                </ol>
                <span className="small muted">
                  Sample spread {formatScore(state.pSd)}, coherence {formatScore(state.coherence)}.
                </span>
              </dd>
            </div>
            <div>
              <dt>How often this state rose in development</dt>
              <dd data-testid="tt-dev">
                {dev.upRate === null ? (
                  "This state never occurred on a labelled development day."
                ) : (
                  <>
                    <strong className="num">{formatRate(dev.upRate)}</strong> of{" "}
                    <span className="num">{formatCount(dev.n)}</span> labelled symbol-days
                  </>
                )}
              </dd>
            </div>
            <div>
              <dt>Jev&rsquo;s position</dt>
              <dd data-testid="tt-position">
                <strong className={position === "Long" ? "long" : "flat"}>{position}</strong>
                {nextOpen ? `, held from the next open (${nextOpen})` : ", held from the next open"}
              </dd>
            </div>
            <div>
              <dt>What the price did over the next {horizon} sessions</dt>
              <dd data-testid="tt-fwd">
                {fwd === null || !nextOpen || !exitOpen ? (
                  <strong>Not yet known</strong>
                ) : (
                  <>
                    <strong className={fwd > 0 ? "num ret-up" : "num ret-down"}>{formatReturn(fwd)}</strong> from the open
                    of {nextOpen} to the open of {exitOpen}
                  </>
                )}
              </dd>
            </div>
          </dl>
          <p className="small muted">
            Close {formatPrice(days.close[index])}. Open {formatPrice(days.open[index])}, high {formatPrice(days.high[index])},
            low {formatPrice(days.low[index])}.
          </p>
        </section>
      </div>
    </section>
  );
}

export function SymbolExplorer({ symbol, days, states, periodLabels, horizon }: Props) {
  const [selected, select] = useSelectedDay(days.date);
  const state = states[days.state[selected]];
  const last = days.date.length - 1;

  return (
    <>
      <PriceChart days={days} selected={selected} onSelect={select} />
      <ul className="chart-legend" aria-label="Chart legend">
        <li>
          <span className="swatch" style={{ background: CHART_COLORS.holdoutBand, outline: `1px solid ${CHART_COLORS.holdoutEdge}` }} />
          Shaded: holdout. Unshaded, muted candles: development (fit, validate).
        </li>
        <li>
          <span className="swatch" style={{ background: CHART_COLORS.long }} />
          Arrow up: Jev moves to Long at that close
        </li>
        <li>
          <span className="swatch" style={{ background: CHART_COLORS.flat }} />
          Arrow down: Jev moves to Flat at that close
        </li>
        <li>
          <span className="swatch" style={{ background: CHART_COLORS.selectedSolid }} />
          Selected day
        </li>
      </ul>
      <div className="day-nav">
        <button type="button" onClick={() => select(selected - 1)} disabled={selected === 0}>
          <span aria-hidden="true">&larr;</span> Previous trading day
        </button>
        <button type="button" onClick={() => select(selected + 1)} disabled={selected === last}>
          Next trading day <span aria-hidden="true">&rarr;</span>
        </button>
        <span className="small muted" aria-live="polite">
          {symbol} on {days.date[selected]}
        </span>
      </div>
      <DayPanel days={days} index={selected} state={state} periodLabels={periodLabels} horizon={horizon} />
    </>
  );
}
