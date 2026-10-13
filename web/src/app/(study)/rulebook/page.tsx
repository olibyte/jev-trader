import type { Metadata } from "next";
import { RulebookTable } from "@/components/RulebookTable";
import { RunLink } from "@/components/RunLink";
import { loadExport } from "@/lib/export";
import { formatCount, formatLevel, formatRate } from "@/lib/format";

export const metadata: Metadata = { title: "Rulebook" };

export default function RulebookPage() {
  const { policy } = loadExport();
  const dev = policy.development;
  const dimensions = policy.dimensions.map((d) => ({ name: d.name, field: d.field, levels: d.levels.map((l) => l.level) }));
  const rows = policy.states.map((state, index) => ({
    index,
    levels: policy.dimensions.map((d) => state.levels[d.name]),
    pUp: state.pUp,
    pSd: state.pSd,
    coherence: state.coherence,
    development: state.development,
  }));

  return (
    <>
      <section className="panel" aria-labelledby="rulebook-heading">
        <div className="panel-head">
          <h1 id="rulebook-heading">Jev&rsquo;s rulebook</h1>
          <RunLink run="export" />
        </div>
        <p>
          Every trading day in the study maps to one of {formatCount(policy.states.length)} described states. Jev was asked
          about each state {policy.samples} times, with the six lines in a shuffled order each time, and the answers were
          frozen. This table is the whole policy.
        </p>
        <dl className="legend-list">
          <div>
            <dt>Model that served the calls</dt>
            <dd>
              <code translate="no" data-testid="model-served">
                {policy.modelServed}
              </code>
            </dd>
          </div>
          <div>
            <dt>Prompt version</dt>
            <dd>
              <code>{policy.promptVersion}</code>
            </dd>
          </div>
          {Object.entries(policy.questions).map(([name, q]) => (
            <div key={name}>
              <dt>Question {name}</dt>
              <dd>{q.instructions}</dd>
            </div>
          ))}
        </dl>
        <h2>How to read the columns</h2>
        <dl className="legend-list">
          <div>
            <dt>P(higher in 20 trading days)</dt>
            <dd>
              Jev&rsquo;s answer. The mean over the {policy.samples} samples of (P(higher) + 1 &minus; P(lower or equal)) / 2.
              The <code>jev</code> arm is Long when it is above 0.5.
            </dd>
          </div>
          <div>
            <dt>Sample spread (p_sd)</dt>
            <dd>The standard deviation of the per-sample answers. Low means Jev gave the same answer each time.</dd>
          </div>
          <div>
            <dt>Coherence</dt>
            <dd>The mean of |P(higher) + P(lower or equal) &minus; 1|. Zero means the two answers agree exactly.</dd>
          </div>
          <div>
            <dt>Development up rate and n</dt>
            <dd>
              How often the state rose over 20 sessions in development ({dev.splits.join(" and ")}, {dev.first} to{" "}
              {dev.last}), out of n labelled symbol-days pooled across the ETFs. Development has{" "}
              {formatCount(dev.labelled)} labelled symbol-days with a base rate of {formatRate(dev.baseRate)}.
            </dd>
          </div>
          <div>
            <dt>Empirical-table score</dt>
            <dd>
              The <code>empirical_table</code> arm&rsquo;s score: the development up frequency shrunk toward the base rate
              with {dev.shrinkK} pseudo-observations. It is the study&rsquo;s primary comparator.
            </dd>
          </div>
        </dl>
        <h2>The six lines Jev could see</h2>
        <dl className="legend-list">
          {policy.dimensions.map((dim) => (
            <div key={dim.name}>
              <dt>{dim.field}</dt>
              <dd>
                <ul>
                  {dim.levels.map((l) => (
                    <li key={l.level}>
                      <strong>{formatLevel(l.level)}.</strong> {l.text}
                    </li>
                  ))}
                </ul>
              </dd>
            </div>
          ))}
        </dl>
      </section>
      <section className="panel" aria-labelledby="states-heading">
        <div className="panel-head">
          <h2 id="states-heading">All {formatCount(policy.states.length)} states</h2>
          <RunLink run="export" />
        </div>
        <RulebookTable dimensions={dimensions} rows={rows} />
      </section>
    </>
  );
}
