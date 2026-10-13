import type { Metadata } from "next";
import Link from "next/link";
import { RunLink } from "@/components/RunLink";
import { loadExport } from "@/lib/export";

export const metadata: Metadata = { title: "Symbols" };

export default function SymbolsPage() {
  const { manifest } = loadExport();
  return (
    <section className="panel" aria-labelledby="symbols-heading">
      <div className="panel-head">
        <div>
          <p className="eyebrow">Descriptive</p>
          <h1 id="symbols-heading">Symbols</h1>
        </div>
        <RunLink run="export" />
      </div>
      <p>
        Each page shows one ETF day by day: what Jev saw, what it answered, and what the price did next. These pages are
        descriptive. The study result is the pooled holdout comparison on the <Link href="/">home page</Link>.
      </p>
      <ul className="symbol-list">
        {manifest.study.symbols.map((symbol) => (
          <li key={symbol}>
            <Link href={`/symbols/${symbol}/`} translate="no">
              {symbol}
            </Link>
          </li>
        ))}
      </ul>
      <div className="table-scroll" style={{ marginTop: "1rem" }}>
        <table>
          <caption>Study periods</caption>
          <thead>
            <tr>
              <th scope="col">Split</th>
              <th scope="col">Label</th>
              <th scope="col">First session</th>
              <th scope="col">Last session</th>
            </tr>
          </thead>
          <tbody>
            {manifest.study.periods.map((p) => (
              <tr key={p.split}>
                <th scope="row">{p.split}</th>
                <td>{p.label}</td>
                <td className="num">{p.first}</td>
                <td className="num">{p.last}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
