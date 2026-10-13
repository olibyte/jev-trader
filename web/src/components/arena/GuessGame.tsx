"use client";

import Link from "next/link";
import { useState } from "react";
import type { Fund, Strategy } from "@/lib/arena";
import { formatDollars, formatMonth, formatShare } from "@/lib/format";
import { GrowthChart } from "./GrowthChart";

const START = 1000;
const ROUNDS = 3;
const FIRST_FUND = "SPY";

/** A round asks about one fund over the whole stretch (`year` null) or one calendar year. */
type Round = { fund: string; year: number | null };

type Game = { pair: number; rounds: Round[]; guesses: string[] };

type Window = { months: string[]; lines: Record<string, number[]> };

/** The months of one round, with each line scaled so the round starts at $1. */
function windowOf(fund: Fund, year: number | null): Window {
  if (year === null) return { months: fund.months, lines: fund.lines };
  const from = fund.months.indexOf(`${year - 1}-12`);
  const to = fund.months.indexOf(`${year}-12`);
  const lines = Object.fromEntries(
    Object.entries(fund.lines).map(([id, v]) => {
      const base = from < 0 ? 1 : v[from];
      return [id, [base, ...v.slice(from + 1, to + 1)].map((x) => x / base)];
    }),
  );
  return { months: [`${year - 1}-12`, ...fund.months.slice(from + 1, to + 1)], lines };
}

function fullYears(fund: Fund): number[] {
  return fund.months.filter((m) => m.endsWith("-12")).map((m) => Number(m.slice(0, 4)));
}

function last<T>(values: T[]): T {
  return values[values.length - 1];
}

/** Which of the two ended with more, or null when they ended within 0.1% of each other. */
function ahead(w: Window, a: Strategy, b: Strategy): Strategy | null {
  const ea = last(w.lines[a.id]);
  const eb = last(w.lines[b.id]);
  if (Math.abs(ea - eb) / Math.max(ea, eb) < 0.001) return null;
  return ea > eb ? a : b;
}

function pick<T>(items: T[]): T {
  return items[Math.floor(Math.random() * items.length)];
}

type Props = { strategies: Strategy[]; funds: Fund[]; tooClose: Record<string, boolean> };

export function GuessGame({ strategies, funds, tooClose }: Props) {
  const pairs = strategies.flatMap((a, i) => strategies.slice(i + 1).map((b) => [a, b] as const));
  const [game, setGame] = useState<Game>({ pair: 0, rounds: [{ fund: FIRST_FUND, year: null }], guesses: [] });
  const [a, b] = pairs[game.pair];
  const fundOf = (scope: string) => funds.find((f) => f.scope === scope) ?? funds[0];
  const at = game.rounds.length - 1;
  const round = game.rounds[at];
  const fund = fundOf(round.fund);
  const w = windowOf(fund, round.year);
  const guess = game.guesses[at];
  const result = ahead(w, a, b);
  const done = guess !== undefined && at === ROUNDS - 1;
  const fundYears = funds
    .filter((f) => f.scope !== "portfolio")
    .flatMap((f) => fullYears(f).map((y) => ahead(windowOf(f, y), a, b)?.id));
  const yearly = { a: fundYears.filter((id) => id === a.id).length, b: fundYears.filter((id) => id === b.id).length };

  function next() {
    const singles = funds.filter((f) => f.scope !== "portfolio");
    const scope = at === 0 ? FIRST_FUND : pick(singles.filter((f) => f.scope !== round.fund)).scope;
    // Level years still show in the year strip, but a round where both end level teaches nothing.
    const year = pick(fullYears(fundOf(scope)).filter((y) => ahead(windowOf(fundOf(scope), y), a, b) !== null));
    setGame({ ...game, rounds: [...game.rounds, { fund: scope, year }] });
  }

  function replay() {
    setGame({ pair: (game.pair + 1) % pairs.length, rounds: [{ fund: FIRST_FUND, year: null }], guesses: [] });
  }

  const span =
    round.year === null
      ? `${formatMonth(fund.months[0])} to ${formatMonth(last(fund.months))}`
      : `${round.year} only`;
  const score = game.guesses.filter((g, i) => {
    const r = game.rounds[i];
    const winner = ahead(windowOf(fundOf(r.fund), r.year), a, b);
    return winner === null || winner.id === g;
  }).length;

  return (
    <>
      <section className="arena-card" aria-labelledby="round-heading">
        <p className="label">
          Round {at + 1} of {ROUNDS} · {fund.name}
          {fund.ticker ? ` (${fund.ticker})` : ""} · {span}
        </p>
        <h2 id="round-heading" className="question">
          Who ended with more money?
        </h2>
        <p className="muted">
          Each started with $1,000 in the {fund.name} fund
          {round.year === null ? " and followed its rule the whole time." : ` at the start of ${round.year}.`}
        </p>
        <div className="choices">
          {[a, b].map((s) => (
            <button
              key={s.id}
              type="button"
              className="choice"
              style={{ "--c": s.color }}
              aria-pressed={guess === s.id}
              disabled={guess !== undefined}
              onClick={() => setGame({ ...game, guesses: [...game.guesses, s.id] })}
            >
              <span className="who">
                <i className="dot" />
                {s.title}
                {guess === s.id ? <span className="your-guess">Your guess</span> : null}
              </span>
              <span className="muted">{s.plain}</span>
              {guess !== undefined ? (
                <span className="amount" data-testid={`end-${s.id}`}>
                  {formatDollars(last(w.lines[s.id]) * START)}
                </span>
              ) : null}
            </button>
          ))}
        </div>
        {guess === undefined ? (
          <p className="muted">Tap your guess. Real prices, simulated trades, trading costs included.</p>
        ) : (
          <>
            <p className="headline" data-testid="gap">
              {result === null ? (
                <>They ended level.</>
              ) : (
                <>
                  <strong>{result.title}</strong> ended with{" "}
                  {formatDollars(
                    Math.abs(Math.round(last(w.lines[a.id]) * START) - Math.round(last(w.lines[b.id]) * START)),
                  )}{" "}
                  more.
                </>
              )}
            </p>
            <GrowthChart
              months={w.months}
              start={START}
              lines={[a, b].map((s) => ({ id: s.id, label: s.title, color: s.color, values: w.lines[s.id] }))}
            />
            <Lesson round={round} fund={fund} funds={funds} a={a} b={b} />
            {done ? null : (
              <button type="button" className="primary" onClick={next}>
                Next round
              </button>
            )}
          </>
        )}
      </section>

      {done ? (
        <section className="arena-card" aria-labelledby="end-heading" data-testid="end-card">
          <h2 id="end-heading">
            You guessed {score} of {ROUNDS}.
          </h2>
          <ol className="takeaways">
            <li>
              <strong>One year at a time, the answer changed.</strong> Across the 13 funds, {a.title} ended a year with
              more {yearly.a} times and {b.title} {yearly.b} times. A single good year says very little.
            </li>
            <li>
              <strong>Over the whole stretch, more time invested meant bigger gains and bigger falls.</strong> Across all
              13 funds, {a.title} was invested {formatShare(fundOf("portfolio").stats[a.id].exposure)} of the time and
              fell as much as {formatShare(fundOf("portfolio").stats[a.id].maxDrawdown)}. {b.title} was invested{" "}
              {formatShare(fundOf("portfolio").stats[b.id].exposure)} of the time and fell as much as{" "}
              {formatShare(fundOf("portfolio").stats[b.id].maxDrawdown)}.
            </li>
            {tooClose[`${a.id}:${b.id}`] ? (
              <li>
                <strong>So neither is clearly better.</strong> Once you allow for those falls, the gap between these two
                is small enough to be luck.
              </li>
            ) : null}
          </ol>
          <div className="end-actions">
            <button type="button" className="primary" onClick={replay}>
              Play again: {pairs[(game.pair + 1) % pairs.length].map((s) => s.title).join(" vs ")}
            </button>
            <Link href="/preview/pick-two/">Compare any two yourself</Link>
          </div>
        </section>
      ) : null}
    </>
  );
}

function Lesson({ round, fund, funds, a, b }: { round: Round; fund: Fund; funds: Fund[]; a: Strategy; b: Strategy }) {
  if (round.year === null) {
    const ends = funds.filter((f) => f.scope !== "portfolio").map((f) => ahead(windowOf(f, null), a, b)?.id);
    return (
      <div className="lesson">
        <h3>The same years, fund by fund</h3>
        <ul className="tiles">
          {funds
            .filter((f) => f.scope !== "portfolio")
            .map((f) => {
              const winner = ahead(windowOf(f, null), a, b);
              return (
                <li key={f.scope} className="tile" data-current={f.scope === fund.scope}>
                  <span className="tile-name">{f.name}</span>
                  <i className="dot" style={{ "--c": winner?.color ?? "#9a9aa2" }} />
                </li>
              );
            })}
        </ul>
        <p className="muted">
          The dot shows which one ended with more in each fund.{" "}
          {Math.max(...[a, b].map((s) => ends.filter((e) => e === s.id).length)) >= 10
            ? "Over a long stretch, the answer was the same in most funds."
            : "Even over a long stretch, the answer changed from fund to fund."}{" "}
          Next, try a single year.
        </p>
      </div>
    );
  }
  const years = fullYears(fund).map((year) => ({ year, winner: ahead(windowOf(fund, year), a, b) }));
  const count = (s: Strategy) => years.filter((y) => y.winner?.id === s.id);
  const level = years.filter((y) => y.winner === null).length;
  return (
    <div className="lesson">
      <h3>{fund.name}, one year at a time</h3>
      <ul className="tiles">
        {years.map(({ year, winner }) => (
          <li key={year} className="tile" data-current={year === round.year}>
            <span className="tile-name">{year}</span>
            <i className="dot" style={{ "--c": winner?.color ?? "#9a9aa2" }} />
          </li>
        ))}
      </ul>
      <p className="muted">
        {a.title} ended the year with more {count(a).length} times. {b.title} did {count(b).length} times
        {level ? `, and ${level} years ended level` : ""}. Which one comes out ahead depends on the year you pick.
      </p>
    </div>
  );
}
