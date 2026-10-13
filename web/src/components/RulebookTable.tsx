"use client";

import { useState } from "react";
import type { Development } from "@/lib/export";
import { formatCount, formatLevel, formatRate, formatScore } from "@/lib/format";

export type RulebookDimension = { name: string; field: string; levels: string[] };
export type RulebookRow = {
  index: number;
  levels: string[];
  pUp: number;
  pSd: number;
  coherence: number;
  development: Development;
};

const ALL = "";

export function RulebookTable({ dimensions, rows }: { dimensions: RulebookDimension[]; rows: RulebookRow[] }) {
  const [filters, setFilters] = useState<string[]>(() => dimensions.map(() => ALL));
  const visible = rows.filter((row) => filters.every((f, d) => f === ALL || row.levels[d] === f));

  return (
    <>
      <fieldset className="filters">
        <legend>Filter by level</legend>
        {dimensions.map((dim, d) => (
          <label key={dim.name}>
            <code>{dim.field}</code>
            <select
              name={dim.name}
              autoComplete="off"
              value={filters[d]}
              onChange={(event) => {
                const value = event.target.value;
                setFilters((current) => current.map((f, i) => (i === d ? value : f)));
              }}
            >
              <option value={ALL}>All levels</option>
              {dim.levels.map((level) => (
                <option key={level} value={level}>
                  {formatLevel(level)}
                </option>
              ))}
            </select>
          </label>
        ))}
      </fieldset>
      <p className="small muted" aria-live="polite" data-testid="rulebook-count">
        Showing {formatCount(visible.length)} of {formatCount(rows.length)} states.
      </p>
      <div className="table-scroll rulebook-scroll">
        <table className="rulebook-table" data-testid="rulebook-table">
          <thead>
            <tr>
              <th scope="col" className="num">
                State
              </th>
              {dimensions.map((dim) => (
                <th scope="col" key={dim.name}>
                  <code>{dim.field}</code>
                </th>
              ))}
              <th scope="col" className="num">
                P(higher in 20 trading days)
              </th>
              <th scope="col" className="num">
                Sample spread (p_sd)
              </th>
              <th scope="col" className="num">
                Coherence
              </th>
              <th scope="col" className="num">
                Development up rate
              </th>
              <th scope="col" className="num">
                Development n
              </th>
              <th scope="col" className="num">
                Empirical-table score
              </th>
            </tr>
          </thead>
          <tbody>
            {visible.map((row) => (
              <tr key={row.index}>
                <th scope="row" className="num">
                  {row.index + 1}
                </th>
                {row.levels.map((level, d) => (
                  <td key={dimensions[d].name}>{formatLevel(level)}</td>
                ))}
                <td className="num">{formatScore(row.pUp)}</td>
                <td className="num">{formatScore(row.pSd)}</td>
                <td className="num">{formatScore(row.coherence)}</td>
                <td className="num">
                  {row.development.upRate === null ? "No rows" : formatRate(row.development.upRate)}
                </td>
                <td className="num">{formatCount(row.development.n)}</td>
                <td className="num">{formatScore(row.development.empiricalP)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
