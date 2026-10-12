import Link from "next/link";
import { Fragment } from "react";
import { CiChart } from "@/components/CiChart";
import { RunLink } from "@/components/RunLink";
import { type Arm, loadExport, type Outcome } from "@/lib/export";
import {
  formatBinEdge,
  formatCount,
  formatInterval,
  formatRate,
  formatScore,
  formatSharpe,
  formatTurnover,
} from "@/lib/format";
import { runHref } from "@/lib/site";

const OUTCOME_COPY: Record<Outcome, { label: string; explanation: string }> = {
  jev_better: { label: "Jev better", explanation: "The whole 95% confidence interval lies above zero." },
  jev_worse: { label: "Jev worse", explanation: "The whole 95% confidence interval lies below zero." },
  inconclusive: { label: "Inconclusive", explanation: "The 95% confidence interval includes zero." },
};

function ArmName({ arm }: { arm: Arm }) {
  return (
    <>
      <code>{arm.name}</code>
      {arm.lookahead ? <span className="note">look-ahead check, not a strategy</span> : null}
    </>
  );
}

export default function ResultPage() {
  const { summary, manifest, policy } = loadExport();
  const { primary, power, bootstrap } = summary;
  const primaryLabel = `AUC(${primary.candidate}) − AUC(${primary.baseline})`;
  const outcome = OUTCOME_COPY[summary.outcome];
  const calibrated = [primary.candidate, primary.baseline].flatMap((name) =>
    summary.arms.filter((a) => a.name === name).flatMap((a) => (a.probability ? [a] : [])),
  );

  return (
    <>
      <section className="panel" aria-labelledby="result-heading">
        <div className="panel-head">
          <p className="eyebrow">Pre-registered holdout result</p>
          <RunLink run="holdout" />
        </div>
        <div className="hero">
          <div>
            <h1 id="result-heading">
              Does Jev rank 20-day outcomes better than the history table?
            </h1>
            <p className="outcome" data-testid="outcome">
              <span className={`outcome-${summary.outcome}`}>{outcome.label}</span>
            </p>
            <p>
              {outcome.explanation} The rule was fixed before the holdout ran: <code>jev_better</code> if{" "}
              <code>{summary.outcomeRule.jev_better}</code>, <code>jev_worse</code> if{" "}
              <code>{summary.outcomeRule.jev_worse}</code>, <code>inconclusive</code>{" "}
              {summary.outcomeRule.inconclusive}.
            </p>
            <p className="primary-figure">
              <span className="muted">{primaryLabel}</span>
              <br />
              <strong className="num" data-testid="primary-point">
                {formatScore(primary.point)}
              </strong>{" "}
              <span>
                95% CI{" "}
                <span className="num" data-testid="primary-ci">
                  {formatInterval(primary, formatScore)}
                </span>
              </span>
            </p>
            <CiChart point={primary.point} lo={primary.lo} hi={primary.hi} mde={power.mde} label={primaryLabel} />
          </div>
          <dl className="facts">
            <div>
              <dt>Minimum detectable effect (MDE)</dt>
              <dd>
                <strong className="num" data-testid="mde">
                  {formatScore(power.mde)}
                </strong>
                <p className="small muted">
                  The holdout cannot rule out a true difference smaller than this. The study had{" "}
                  {formatRate(power.power)} power to detect a true difference of {formatScore(power.mde)} at a two-sided
                  significance level of {formatRate(power.alpha)}.
                </p>
              </dd>
            </div>
            <div>
              <dt>Independent observations</dt>
              <dd>
                <strong className="num" data-testid="blocks">
                  {formatCount(summary.blocks)}
                </strong>{" "}
                {bootstrap.block}-session date blocks
                <p className="small muted">
                  From <span data-testid="labelled">{formatCount(summary.labelled)}</span> labelled rows across{" "}
                  {manifest.study.symbols.length} ETFs. All tickers on a date share its block, and the bootstrap draws{" "}
                  {formatCount(bootstrap.reps)} resamples.
                </p>
              </dd>
            </div>
            <div>
              <dt>Period</dt>
              <dd>
                <span className="badge badge-holdout" data-testid="period-label">
                  {summary.period.label}
                </span>{" "}
                <span className="num" data-testid="period-dates">
                  {summary.period.first} to {summary.period.last}
                </span>
                <p className="small muted">
                  Arms were fitted on development ({summary.fitOn.join(" and ")}) and scored once on the holdout.
                </p>
              </dd>
            </div>
            <div>
              <dt>Model that served the calls</dt>
              <dd>
                <code translate="no" data-testid="model-served">
                  {manifest.study.modelServed}
                </code>
                <p className="small muted">
                  Jev answered each of the {formatCount(policy.states.length)} states {policy.samples} times, once, before the holdout. See the{" "}
                  <Link href="/rulebook/">rulebook</Link>.
                </p>
              </dd>
            </div>
          </dl>
        </div>
      </section>

      <section className="panel" aria-labelledby="arms-heading">
        <div className="panel-head">
          <h2 id="arms-heading">Every arm on the holdout</h2>
          <RunLink run="holdout" />
        </div>
        <p className="small muted">
          AUC measures how well an arm&rsquo;s score ranks the days that rose above the days that did not. 0.5 is a coin
          flip. Brier skill compares a probability with always predicting the development base rate. Excess Sharpe is the
          annualized return over cash (BIL) per unit of risk for the equal-weight portfolio of the {manifest.study.symbols.length} per-symbol sleeves.
        </p>
        <div className="table-scroll">
          <table data-testid="arms-table">
            <caption>
              Holdout {summary.period.first} to {summary.period.last}. Each cell shows the point value and its 95% CI
              from the joint-date block bootstrap.
            </caption>
            <thead>
              <tr>
                <th scope="col" rowSpan={2}>
                  Arm
                </th>
                <th scope="col" rowSpan={2}>
                  Rule
                </th>
                <th scope="colgroup" colSpan={2}>
                  AUC, n = {formatCount(summary.blocks)} blocks
                </th>
                <th scope="colgroup" colSpan={2}>
                  Brier skill, n = {formatCount(summary.blocks)} blocks
                </th>
                <th scope="colgroup" colSpan={2}>
                  Excess Sharpe at {summary.costBps} bps, n ={" "}
                  <a href={runHref("export")} title="Counted by the export run">
                    {formatCount(summary.sharpeBlocks)} blocks
                  </a>
                </th>
              </tr>
              <tr>
                {["auc", "brier", "sharpe"].map((metric) => (
                  <Fragment key={metric}>
                    <th scope="col" className="num">
                      Point
                    </th>
                    <th scope="col" className="num">
                      95% CI
                    </th>
                  </Fragment>
                ))}
              </tr>
            </thead>
            <tbody>
              {summary.arms.map((arm) => (
                <tr key={arm.name} data-arm={arm.name}>
                  <th scope="row">
                    <ArmName arm={arm} />
                  </th>
                  <td className="rule">{arm.rule}</td>
                  <td className="num">{formatScore(arm.auc.point)}</td>
                  <td className="num">{formatInterval(arm.auc, formatScore)}</td>
                  {arm.probability ? (
                    <>
                      <td className="num">{formatScore(arm.brierSkill.point)}</td>
                      <td className="num">{formatInterval(arm.brierSkill, formatScore)}</td>
                    </>
                  ) : (
                    <td colSpan={2} className="muted">
                      Not a probability score
                    </td>
                  )}
                  <td className="num">{formatSharpe(arm.excessSharpe.point)}</td>
                  <td className="num">{formatInterval(arm.excessSharpe, formatSharpe)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel" aria-labelledby="points-heading">
        <div className="panel-head">
          <h2 id="points-heading">Point values with no confidence interval</h2>
          <RunLink run="holdout" />
        </div>
        <p className="small muted">
          These figures come from the same holdout run, but the study computed no confidence interval for them. Read them
          as descriptions, not as measured differences between arms.
        </p>
        <div className="table-scroll">
          <table data-testid="points-table">
            <caption>
              Holdout {summary.period.first} to {summary.period.last}. Point values only.
            </caption>
            <thead>
              <tr>
                <th scope="col">Arm</th>
                <th scope="col" className="num">
                  Exposure
                </th>
                <th scope="col" className="num">
                  Turnover (switches per sleeve per year)
                </th>
                <th scope="col" className="num">
                  Max drawdown
                </th>
                {summary.costsBps.map((bps) => (
                  <th scope="col" className="num" key={bps}>
                    Excess Sharpe at {bps} bps
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {summary.arms.map((arm) => (
                <tr key={arm.name} data-arm={arm.name}>
                  <th scope="row">
                    <ArmName arm={arm} />
                  </th>
                  <td className="num">{formatRate(arm.exposure)}</td>
                  <td className="num">{formatTurnover(arm.switchesPerYear)}</td>
                  <td className="num">{formatRate(arm.maxDrawdown)}</td>
                  {arm.excessSharpeByCost.map((c) => (
                    <td className="num" key={c.costBps}>
                      {formatSharpe(c.value)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel" aria-labelledby="calibration-heading">
        <div className="panel-head">
          <h2 id="calibration-heading">Calibration on the holdout</h2>
          <RunLink run="holdout" />
        </div>
        <p className="small muted">
          Rows are grouped by score into bins 0.1 wide. A calibrated score has an observed up rate close to its mean score
          in every bin.
        </p>
        <div className="day-grid">
          {calibrated.map((arm) => (
            <div className="table-scroll" key={arm.name}>
              <table data-testid={`calibration-${arm.name}`}>
                <caption>
                  <code>{arm.name}</code> score bins
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Score bin</th>
                    <th scope="col" className="num">
                      Rows
                    </th>
                    <th scope="col" className="num">
                      Mean score
                    </th>
                    <th scope="col" className="num">
                      Observed up rate
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {arm.calibration.map((bin) => (
                    <tr key={bin.binLow}>
                      <th scope="row">
                        {formatBinEdge(bin.binLow)} to {formatBinEdge(bin.binHigh)}
                      </th>
                      <td className="num">{formatCount(bin.rows)}</td>
                      <td className="num">{formatScore(bin.meanScore)}</td>
                      <td className="num">{formatRate(bin.upRate)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      </section>

      <section className="panel" aria-labelledby="next-heading">
        <h2 id="next-heading">Look closer</h2>
        <p>
          The <Link href="/rulebook/">rulebook</Link> lists Jev&rsquo;s answer for every one of the {formatCount(policy.states.length)} described states. The{" "}
          <Link href="/symbols/">symbol pages</Link> let you step through each trading day and see exactly what Jev was
          shown. They are descriptive. The study result is the pooled comparison above.
        </p>
      </section>
    </>
  );
}
