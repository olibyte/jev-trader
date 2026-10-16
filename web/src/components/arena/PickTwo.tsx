"use client";

import { useMemo, useState } from "react";
import type { Fund, MarketView, Strategy } from "@/lib/arena";
import { formatDollars, formatMonth, formatShare } from "@/lib/format";
import { MARKET_IDS, MARKETS, type Market, type Range } from "@/lib/markets";
import { CandleView, LineView, type Side } from "./ArenaChart";
import { StrategyPicker } from "./StrategyPicker";

const START = 1000;
const SLOTS = [
  { label: "A", color: "#4c8dff" },
  { label: "B", color: "#f5a524" },
] as const;
type Slot = 0 | 1;

const SPAN: Record<Exclude<Range, "All">, string> = {
  "1D": "One day",
  "1W": "One week",
  "1M": "One month",
  "3M": "Three months",
  "1Y": "One year",
  "5Y": "Five years",
};

type View = { kind: "line" } | { kind: "candles"; fund: Fund; trades: boolean };
type Screen = { picks: [string, string]; market: Market; range: Range; view: View };

type Props = { strategies: Strategy[]; funds: Fund[]; markets: Record<Market, MarketView>; costBps: number };

export function PickTwo({ strategies, funds, markets, costBps }: Props) {
  const [screen, setScreen] = useState<Screen>({
    picks: [strategies[0].id, strategies[1].id],
    market: "daily",
    range: "1Y",
    view: { kind: "line" },
  });
  const [picking, setPicking] = useState<Slot | null>(null);
  const { picks, market, range, view } = screen;
  const { label, unit, formatTime, prices } = MARKETS[market];
  const { windows, first, last, tooClose } = markets[market];

  const sides = useMemo(
    (): Side[] => picks.map((id, k) => ({ id, label: SLOTS[k].label, color: SLOTS[k].color })),
    [picks],
  );
  const strategy = (id: string) => {
    const found = strategies.find((s) => s.id === id);
    if (!found) throw new Error(`no strategy "${id}"`);
    return found;
  };
  const chosen = picks.map(strategy);
  const [a, b] = chosen;
  const shown = windows.find((w) => w.range === range);
  if (!shown) throw new Error(`no window for range "${range}"`);
  const stats = (s: Strategy) => shown.strategies[s.id];
  const end = (s: Strategy) => START * stats(s).growth;
  const gap = Math.round(end(a)) - Math.round(end(b));
  const ahead = gap >= 0 ? a : b;
  const close = tooClose?.[`${a.id}:${b.id}`] ?? false;
  const startText = shown.base === null ? `in ${formatMonth(first.slice(0, 7))}` : `on ${formatTime(shown.base)}`;

  function pick(id: string) {
    setScreen((s) => ({ ...s, picks: picking === 0 ? [id, s.picks[1]] : [s.picks[0], id] }));
    setPicking(null);
  }

  function setView(next: View) {
    setScreen((s) => ({ ...s, view: next }));
  }

  function setMarket(next: Market) {
    setScreen((s) => ({ ...s, market: next, range: (MARKETS[next].ranges as readonly Range[]).includes(s.range) ? s.range : "1Y" }));
  }

  return (
    <>
      <div>
        <h1>Pick two strategies. See what $1,000 became.</h1>
        <p className="lede">
          Each one invests in the same 13 US stock funds, with {prices} from {formatMonth(first.slice(0, 7))} to{" "}
          {formatMonth(last.slice(0, 7))}, and pays the same small fee ({costBps / 100}%) every time it moves in or out.
        </p>
      </div>
      <section className="slots" aria-label="Your two strategies">
        {SLOTS.map((slot, k) => {
          const s = k === 0 ? a : b;
          return (
            <button
              key={slot.label}
              type="button"
              className="slot"
              style={{ "--c": slot.color }}
              aria-haspopup="dialog"
              onClick={() => setPicking(k === 0 ? 0 : 1)}
              data-testid={`slot-${slot.label}`}
            >
              <span className="slot-label">
                <i className="dot" />
                Strategy {slot.label}
              </span>
              <span className="slot-title">{s.title}</span>
              <span className="slot-change" aria-hidden="true">
                Change
              </span>
              <span className="slot-plain">{s.plain}</span>
            </button>
          );
        })}
      </section>

      <StrategyPicker
        strategies={strategies}
        slot={
          picking === null
            ? null
            : {
                label: SLOTS[picking].label,
                current: picks[picking],
                other: { label: SLOTS[1 - picking].label, id: picks[1 - picking] },
              }
        }
        onPick={pick}
        onClose={() => setPicking(null)}
      />

      <section className="panel" aria-label="What $1,000 became">
        <p className="muted">Put $1,000 in each {startText}.</p>
        <div className="money">
          {sides.map((side, k) => (
            <div key={side.label}>
              <p className="who">
                <i className="dot" style={{ "--c": side.color }} />
                {chosen[k].title}
              </p>
              <p className="amount" data-testid={`amount-${side.label}`}>
                {formatDollars(end(chosen[k]))}
              </p>
            </div>
          ))}
        </div>
        <p className="headline" data-testid="gap">
          {Math.abs(gap) < 50 ? (
            <>By {formatTime(last)}, they ended within $50 of each other.</>
          ) : (
            <>
              By {formatTime(last)}, <strong>{ahead.title}</strong> had {formatDollars(Math.abs(gap))} more.
            </>
          )}
        </p>
        {range !== "All" ? (
          <p className="luck" data-testid="luck">
            Does that make it the better strategy? {SPAN[range]} is too short to tell skill from luck.
          </p>
        ) : tooClose === null ? (
          <p className="luck" data-testid="luck">
            Does that make it the better strategy? We haven&apos;t tested {label.toLowerCase()} results for luck yet.
          </p>
        ) : close ? (
          <p className="luck" data-testid="luck">
            Does that make it the better strategy? These years can&apos;t tell us. <a href="#why">Here is why.</a>
          </p>
        ) : null}
      </section>

      <section className="panel chart-panel" aria-label="Chart">
        <div className="toolbar">
          <div className="seg seg-ranges" role="group" aria-label="Time range">
            {windows.map((w) => (
              <button
                key={w.range}
                type="button"
                aria-pressed={w.range === range}
                onClick={() => setScreen((s) => ({ ...s, range: w.range }))}
              >
                {w.range}
              </button>
            ))}
          </div>
          <div className="seg" role="group" aria-label="Chart type">
            <button type="button" aria-pressed={view.kind === "line"} onClick={() => setView({ kind: "line" })}>
              Line
            </button>
            <button
              type="button"
              aria-pressed={view.kind === "candles"}
              onClick={() => view.kind === "line" && setView({ kind: "candles", fund: funds[0], trades: false })}
            >
              Candles
            </button>
          </div>
          <div className="seg" role="group" aria-label="Bar size">
            {MARKET_IDS.map((m) => (
              <button key={m} type="button" aria-pressed={m === market} onClick={() => setMarket(m)}>
                {MARKETS[m].label}
              </button>
            ))}
          </div>
          {view.kind === "candles" ? (
            <>
              <select
                className="fund-select"
                aria-label="Fund"
                value={view.fund.ticker}
                onChange={(e) => setView({ ...view, fund: funds.find((f) => f.ticker === e.target.value) ?? view.fund })}
              >
                {funds.map((f) => (
                  <option key={f.ticker} value={f.ticker}>
                    {f.name} ({f.ticker})
                  </option>
                ))}
              </select>
              <label className="switch">
                <input
                  type="checkbox"
                  role="switch"
                  checked={view.trades}
                  onChange={(e) => setView({ ...view, trades: e.target.checked })}
                />
                Show trades
              </label>
            </>
          ) : null}
        </div>
        {view.kind === "line" ? (
          <>
            <LineView market={market} base={shown.base} sides={sides} />
            <p className="muted">Move across the chart to read any {unit}. The dashed line is the $1,000 you started with.</p>
          </>
        ) : (
          <>
            <CandleView market={market} fund={view.fund} base={shown.base} sides={sides} trades={view.trades} />
            {view.trades ? (
              <p className="legend" data-testid="trade-legend">
                {sides.map((side, k) => (
                  <span key={side.label}>
                    <i className="dot" style={{ "--c": side.color }} />
                    {chosen[k].title}
                  </span>
                ))}
                <span>▲ bought ▼ sold</span>
              </p>
            ) : null}
            <p className="muted">Trades are on {view.fund.name} alone. The amounts above cover all 13 funds.</p>
          </>
        )}
      </section>

      <section className="panel" id="why" aria-labelledby="why-heading">
        <h2 id="why-heading">More money is not the whole story.</h2>
        <p className="muted">
          A strategy can end with more just because it stayed invested while prices rose. Here is how differently these two
          got there.
        </p>
        <h3>Share of {unit}s invested</h3>
        <Bars name="exposure" sides={sides} values={[stats(a).exposure, stats(b).exposure]} titles={[a.title, b.title]} />
        <p className="muted">
          {[a, b]
            .filter((s) => stats(s).exposure < 1)
            .map((s) => `${s.title} sat in cash on ${formatShare(1 - stats(s).exposure)} of ${unit}s. `)}
          Cash earns a little interest. It can&apos;t grow with the market, and it can&apos;t fall with it either.
        </p>
        <h3>Biggest fall from a high point</h3>
        <Bars name="drawdown" sides={sides} values={[stats(a).maxDrawdown, stats(b).maxDrawdown]} titles={[a.title, b.title]} />
        <p className="muted">The share of its value each one lost at its worst moment before recovering.</p>
        {range === "All" && close ? (
          <div className="callout" data-testid="too-close">
            <p>
              <strong>So which one is better? We can&apos;t tell yet.</strong>
            </p>
            <p>
              Once you allow for how far each one fell along the way, the gap between these two is small enough to be luck.
              About 19 years of prices is not enough to tell them apart.
            </p>
          </div>
        ) : null}
      </section>
    </>
  );
}

function Bars({ name, sides, values, titles }: { name: string; sides: Side[]; values: number[]; titles: string[] }) {
  return (
    <div className="bars">
      {sides.map((side, k) => (
        <div className="bar-row" key={side.label} style={{ "--c": side.color }}>
          <span className="who">{titles[k]}</span>
          <span className="track">
            <span className="fill" style={{ display: "block", width: `${values[k] * 100}%` }} />
          </span>
          <span className="value" data-testid={`${name}-${side.label}`}>
            {formatShare(values[k])}
          </span>
        </div>
      ))}
    </div>
  );
}
