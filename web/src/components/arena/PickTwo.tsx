"use client";

import { useState } from "react";
import type { Fund, Strategy } from "@/lib/arena";
import { formatDollars, formatMonth, formatShare } from "@/lib/format";
import { GrowthChart } from "./GrowthChart";

const START = 1000;

type Props = { strategies: Strategy[]; fund: Fund; tooClose: Record<string, boolean>; last: string };

export function PickTwo({ strategies, fund, tooClose, last }: Props) {
  // The most recent pick is last, so a third tap replaces the older pick.
  const [picks, setPicks] = useState<[string, string]>([strategies[0].id, strategies[1].id]);
  const [a, b] = strategies.filter((s) => picks.includes(s.id));
  const end = (s: Strategy) => fund.stats[s.id].end * START;
  const gap = Math.round(end(a)) - Math.round(end(b));
  const ahead = gap >= 0 ? a : b;
  const close = tooClose[`${a.id}:${b.id}`];
  const when = formatMonth(last.slice(0, 7));

  function pick(id: string) {
    if (!picks.includes(id)) setPicks([picks[1], id]);
  }

  return (
    <>
      <section aria-labelledby="pick-label">
        <p className="label" id="pick-label">
          Pick two
        </p>
        <ul className="chips">
          {strategies.map((s) => (
            <li key={s.id}>
              <button
                type="button"
                className="chip"
                aria-pressed={picks.includes(s.id)}
                style={{ "--c": s.color }}
                onClick={() => pick(s.id)}
              >
                <i className="dot" />
                {s.title}
              </button>
            </li>
          ))}
        </ul>
        <ul className="rules">
          {[a, b].map((s) => (
            <li key={s.id}>
              <i className="dot" style={{ "--c": s.color }} />
              <span>
                <strong>{s.title}.</strong> {s.plain}
              </span>
            </li>
          ))}
        </ul>
        <p className="muted">Tap another strategy to swap it in.</p>
      </section>

      <section className="arena-card" aria-label="What $1,000 became">
        <div className="money">
          {[a, b].map((s) => (
            <div key={s.id}>
              <p className="who">
                <i className="dot" style={{ "--c": s.color }} />
                {s.title}
              </p>
              <p className="amount" data-testid={`end-${s.id}`}>
                {formatDollars(end(s))}
              </p>
            </div>
          ))}
        </div>
        <p className="headline" data-testid="gap">
          {Math.abs(gap) < 50 ? (
            <>By {when}, they ended within $50 of each other.</>
          ) : (
            <>
              By {when}, <strong>{ahead.title}</strong> had {formatDollars(Math.abs(gap))} more.
            </>
          )}
        </p>
        {close ? (
          <p className="muted">
            Does that make it the better strategy? These years can&apos;t tell us. <a href="#why">Here is why.</a>
          </p>
        ) : null}
        <GrowthChart
          months={fund.months}
          start={START}
          lines={[a, b].map((s) => ({ id: s.id, label: s.title, color: s.color, values: fund.lines[s.id] }))}
        />
        <p className="muted">Drag across the chart to see any month. The dotted line is the $1,000 you started with.</p>
      </section>

      <section className="arena-card" id="why" aria-labelledby="why-heading">
        <h2 id="why-heading">More money is not the whole story.</h2>
        <p className="muted">
          A strategy can end with more just because it stayed invested while prices rose. Here is how differently these
          two got there.
        </p>
        <h3>Share of days invested</h3>
        <Bars items={[a, b].map((s) => ({ s, value: fund.stats[s.id].exposure }))} />
        <p className="muted">
          {[a, b]
            .filter((s) => fund.stats[s.id].exposure < 1)
            .map((s) => `${s.title} sat in cash on ${formatShare(1 - fund.stats[s.id].exposure)} of days. `)}
          Cash earns a little interest. It can&apos;t grow with the market, and it can&apos;t fall with it either.
        </p>
        <h3>Biggest fall from a high point</h3>
        <Bars items={[a, b].map((s) => ({ s, value: fund.stats[s.id].maxDrawdown }))} />
        <p className="muted">The share of its value each one lost at its worst moment before recovering.</p>
        {close ? (
          <div className="callout" data-testid="too-close">
            <p>
              <strong>So which one is better? We can&apos;t tell yet.</strong>
            </p>
            <p>
              Once you allow for how far each one fell along the way, the gap between these two is small enough to be
              luck. About 19 years of prices is not enough to tell them apart.
            </p>
          </div>
        ) : null}
      </section>
    </>
  );
}

function Bars({ items }: { items: { s: Strategy; value: number }[] }) {
  return (
    <div className="bars">
      {items.map(({ s, value }) => (
        <div className="bar-row" key={s.id} style={{ "--c": s.color }}>
          <span className="who">{s.title}</span>
          <span className="track">
            <span className="fill" style={{ display: "block", width: `${value * 100}%` }} />
          </span>
          <span className="value">{formatShare(value)}</span>
        </div>
      ))}
    </div>
  );
}
