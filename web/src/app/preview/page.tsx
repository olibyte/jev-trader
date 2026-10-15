import type { Metadata } from "next";
import { PickTwo } from "@/components/arena/PickTwo";
import { loadArena } from "@/lib/arena";
import { formatMonth, formatTurnover } from "@/lib/format";

export const metadata: Metadata = { title: "Pick two" };

export default function PickTwoPage() {
  const { strategies, funds, costBps, markets } = loadArena();
  const { windows, first, last, tooClose } = markets.daily;
  return (
    <>
      <div>
        <h1>Pick two strategies. See what $1,000 became.</h1>
        <p className="lede">
          Each one invests in the same 13 US stock funds, with real prices from {formatMonth(first.slice(0, 7))} to{" "}
          {formatMonth(last.slice(0, 7))}, and pays the same small fee ({costBps / 100}%) every time it moves in or out.
        </p>
      </div>
      <PickTwo strategies={strategies} windows={windows} funds={funds} tooClose={tooClose} first={first} last={last} />
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
