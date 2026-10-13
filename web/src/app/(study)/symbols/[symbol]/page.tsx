import type { Metadata } from "next";
import Link from "next/link";
import { EquityChart } from "@/components/EquityChart";
import { RunLink } from "@/components/RunLink";
import { type ExplorerState, SymbolExplorer } from "@/components/SymbolExplorer";
import { loadExport, periodLabels, sawLines, symbolFile } from "@/lib/export";

export const dynamicParams = false;

export function generateStaticParams() {
  return loadExport().manifest.study.symbols.map((symbol) => ({ symbol }));
}

export async function generateMetadata({ params }: PageProps<"/symbols/[symbol]">): Promise<Metadata> {
  const { symbol } = await params;
  return { title: `${symbol} (descriptive)` };
}

export default async function SymbolPage({ params }: PageProps<"/symbols/[symbol]">) {
  const { symbol } = await params;
  const { manifest, policy } = loadExport();
  const { days, equity } = symbolFile(symbol);
  const states: Record<number, ExplorerState> = {};
  for (const index of new Set(days.state)) {
    const s = policy.states[index];
    states[index] = {
      pUp: s.pUp,
      pSd: s.pSd,
      coherence: s.coherence,
      samples: s.samples.map(({ pHi, pLo }) => ({ pHi, pLo })),
      saw: sawLines(policy, s, 0),
      development: s.development,
    };
  }
  const holdout = manifest.study.periods[2];

  return (
    <>
      <section className="panel" aria-labelledby="symbol-heading">
        <div className="panel-head">
          <div>
            <p className="eyebrow">Descriptive</p>
            <h1 id="symbol-heading" translate="no">
              {symbol}
            </h1>
          </div>
          <RunLink run="export" />
        </div>
        <p>
          The study result is the pooled holdout comparison on the <Link href="/">home page</Link>. This page describes one
          ETF so you can check what Jev was shown on any day. Select a day on the chart, or step through days with the
          buttons or the arrow keys.
        </p>
        <SymbolExplorer
          symbol={symbol}
          days={days}
          states={states}
          periodLabels={periodLabels(manifest)}
          horizon={manifest.study.horizon}
        />
      </section>
      <section className="panel" aria-labelledby="equity-heading">
        <div className="panel-head">
          <div>
            <p className="eyebrow">Descriptive per-symbol sleeve</p>
            <h2 id="equity-heading">Holdout equity at {equity.costBps} bps</h2>
          </div>
          <RunLink run="export" />
        </div>
        <p className="small muted">
          Growth of 1 in the {symbol} sleeve alone, {equity.period} only ({holdout.first} to {holdout.last}), with{" "}
          {equity.costBps} bps per side when the position changes and the BIL return while flat. Arms were fitted on
          development. One symbol over one window is not the study result and carries no confidence interval.
        </p>
        <EquityChart
          equity={equity}
          label={`Holdout equity of the ${symbol} sleeve for jev, empirical_table, and buy_hold at ${equity.costBps} bps.`}
        />
      </section>
    </>
  );
}
