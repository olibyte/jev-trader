import type { Metadata } from "next";
import { PickTwo } from "@/components/arena/PickTwo";
import { loadArena, type MarketView } from "@/lib/arena";
import { formatTurnover } from "@/lib/format";

export const metadata: Metadata = { title: "Pick two" };

/** The client gets each market's figures, never its curve or bars, which it fetches on demand. */
const view = ({ windows, first, last, tooClose }: MarketView): MarketView => ({ windows, first, last, tooClose });

export default function PickTwoPage() {
  const { strategies, funds, costBps, markets } = loadArena();
  return (
    <>
      <PickTwo
        strategies={strategies}
        funds={funds}
        markets={{ daily: view(markets.daily), hourly: view(markets.hourly) }}
        costBps={costBps}
      />
      <Details />
    </>
  );
}

function Details() {
  const { strategies, switchesPerYear } = loadArena();
  return (
    <details className="panel">
      <summary>The numbers behind this, for the technically minded</summary>
      <p className="muted">
        All 13 funds held in equal parts, rebalanced each day: SPY, QQQ, IWM, DIA and nine sector funds. Each strategy decides
        after the close and trades at the next open. These years were already known when the strategies were picked, so this
        is a look back, not a test of the future.
      </p>
      <p className="muted">
        On hourly bars, each strategy decides at the close of an hour and trades at the next hour&apos;s open, inside regular
        hours, and it can hold overnight. The 13 funds return to equal parts every hour. The moves a year below count daily
        bars.
      </p>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th scope="col">Strategy</th>
              <th scope="col">Exact rule</th>
              <th scope="col">Moves a year</th>
            </tr>
          </thead>
          <tbody>
            {strategies.map((s) => (
              <tr key={s.id}>
                <th scope="row">{s.title}</th>
                <td>{s.rule}</td>
                <td>{formatTurnover(switchesPerYear[s.id])}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}
