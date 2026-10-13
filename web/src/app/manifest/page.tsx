import type { Metadata } from "next";
import { loadExport } from "@/lib/export";
import { formatCount, formatUsd } from "@/lib/format";
import { BUILD_COMMIT, commitUrl } from "@/lib/site";

export const metadata: Metadata = { title: "Manifest" };

function HashTable({ caption, rows }: { caption: string; rows: [string, string][] }) {
  return (
    <div className="table-scroll">
      <table>
        <caption>{caption}</caption>
        <thead>
          <tr>
            <th scope="col">File</th>
            <th scope="col">sha256</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([file, sha]) => (
            <tr key={file}>
              <th scope="row">
                <code>{file}</code>
              </th>
              <td className="hash">{sha}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function ManifestPage() {
  const { manifest } = loadExport();
  const { study, datasets, runs } = manifest;

  return (
    <>
      <section className="panel" aria-labelledby="manifest-heading">
        <h1 id="manifest-heading">Run manifest</h1>
        <p>
          Two runs produced every number on this site. Each number links here. The hashes pin the exact input files, so
          anyone with the repository can rerun both and compare bytes.
        </p>
        <dl className="legend-list">
          <div>
            <dt>Site built from commit</dt>
            <dd>
              <a className="hash" href={commitUrl(BUILD_COMMIT)} data-testid="build-commit">
                {BUILD_COMMIT}
              </a>
            </dd>
          </div>
          <div>
            <dt>Export version</dt>
            <dd>
              <code>{manifest.version}</code>
            </dd>
          </div>
        </dl>
      </section>

      <section className="panel" id="run-holdout" aria-labelledby="run-holdout-heading">
        <h2 id="run-holdout-heading">
          Run <code>holdout</code>
        </h2>
        <p className="small muted">
          The one-shot, pre-registered holdout. Every metric on the result page comes from this run, copied without
          recomputation.
        </p>
        <dl className="legend-list">
          <div>
            <dt>Command</dt>
            <dd>
              <code>{runs.holdout.command}</code>
            </dd>
          </div>
          <div>
            <dt>Git commit</dt>
            <dd>
              <a className="hash" href={commitUrl(runs.holdout.gitCommit)}>
                {runs.holdout.gitCommit}
              </a>
            </dd>
          </div>
          <div>
            <dt>Pre-registration sha256</dt>
            <dd className="hash">{runs.holdout.preregSha256}</dd>
          </div>
          <div>
            <dt>Result sha256</dt>
            <dd className="hash">{runs.holdout.resultSha256}</dd>
          </div>
          <div>
            <dt>Files</dt>
            <dd>
              <ul>
                {runs.holdout.files.map((f) => (
                  <li key={f}>
                    <code>{f}</code>
                  </li>
                ))}
              </ul>
            </dd>
          </div>
        </dl>
      </section>

      <section className="panel" id="run-export" aria-labelledby="run-export-heading">
        <h2 id="run-export-heading">
          Run <code>export</code>
        </h2>
        <p className="small muted">
          Derives the rulebook, the per-symbol days, the per-symbol equity curves, and the Sharpe block count from the
          same hashed inputs the pre-registration pins. It records no time and no commit, because its output is a pure
          function of these inputs.
        </p>
        <p>
          <code>{runs.export.command}</code>
        </p>
        <HashTable caption="Inputs" rows={Object.entries(runs.export.inputs)} />
        <HashTable caption="Files written to export/v1" rows={Object.entries(manifest.files)} />
      </section>

      <section className="panel" aria-labelledby="datasets-heading">
        <h2 id="datasets-heading">Datasets</h2>
        <div className="table-scroll">
          <table>
            <caption>Market data snapshots (Twelve Data, adjusted daily bars)</caption>
            <thead>
              <tr>
                <th scope="col">Symbol</th>
                <th scope="col">sha256</th>
                <th scope="col">First</th>
                <th scope="col">Last</th>
                <th scope="col" className="num">
                  Rows
                </th>
                <th scope="col">Fetched at</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(datasets.market).map(([symbol, d]) => (
                <tr key={symbol}>
                  <th scope="row" translate="no">
                    {symbol}
                  </th>
                  <td className="hash">{d.sha256}</td>
                  <td className="num">{d.first}</td>
                  <td className="num">{d.last}</td>
                  <td className="num">{formatCount(d.rows)}</td>
                  <td className="num">{d.fetchedAt}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <dl className="legend-list" style={{ marginTop: "1rem" }}>
          <div>
            <dt>Policy table</dt>
            <dd>
              <code>{datasets.policy.path}</code>
              <br />
              <span className="hash">{datasets.policy.sha256}</span>
            </dd>
          </div>
          <div>
            <dt>Jev call log</dt>
            <dd>
              <code>{datasets.callLog.path}</code>
              <br />
              <span className="hash">{datasets.callLog.sha256}</span>
              <br />
              {formatCount(datasets.callLog.calls)} calls, total cost {formatUsd(datasets.callLog.costUsd)}
            </dd>
          </div>
        </dl>
      </section>

      <section className="panel" aria-labelledby="study-heading">
        <h2 id="study-heading">Study versions</h2>
        <dl className="legend-list">
          <div>
            <dt>State version</dt>
            <dd>
              <code>{study.stateVersion}</code>
            </dd>
          </div>
          <div>
            <dt>Prompt version</dt>
            <dd>
              <code>{study.promptVersion}</code>
            </dd>
          </div>
          <div>
            <dt>Model requested</dt>
            <dd>
              <code translate="no">{study.modelRequested}</code>
            </dd>
          </div>
          <div>
            <dt>Model that served the calls</dt>
            <dd>
              <code translate="no">{study.modelServed}</code>
            </dd>
          </div>
          <div>
            <dt>Horizon</dt>
            <dd>{study.horizon} trading days</dd>
          </div>
          <div>
            <dt>Symbols</dt>
            <dd translate="no">
              {study.symbols.join(", ")}. Cash: {study.cash}.
            </dd>
          </div>
        </dl>
        <div className="table-scroll" style={{ marginTop: "1rem" }}>
          <table>
            <caption>Periods</caption>
            <thead>
              <tr>
                <th scope="col">Split</th>
                <th scope="col">Label</th>
                <th scope="col">First session</th>
                <th scope="col">Last session</th>
              </tr>
            </thead>
            <tbody>
              {study.periods.map((p) => (
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
    </>
  );
}
