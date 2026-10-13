"use client";

import { type MouseEvent, useEffect, useRef, useState } from "react";
import type { Kind, Strategy } from "@/lib/arena";

const KIND_HEADINGS: Record<Kind, string> = {
  benchmark: "Benchmarks",
  indicator: "Indicator rules",
  candlestick: "Candlestick patterns",
  ml: "Learned models",
  jev: "Jev",
  control: "Controls",
};

type Props = {
  strategies: Strategy[];
  /** The slot being changed, or null when the picker is closed. */
  slot: { label: string; current: string; other: { label: string; id: string } } | null;
  onPick: (id: string) => void;
  onClose: () => void;
};

export function StrategyPicker({ strategies, slot, onPick, onClose }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const search = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    const el = dialog.current;
    if (!el) return;
    if (slot && !el.open) {
      el.showModal();
      search.current?.focus();
    } else if (!slot && el.open) {
      el.close();
    }
  }, [slot]);

  const needle = query.trim().toLowerCase();
  const matches = strategies.filter((s) => `${s.title}\n${s.plain}`.toLowerCase().includes(needle));
  const groups = Object.entries(KIND_HEADINGS)
    .map(([kind, heading]) => ({ kind, heading, rows: matches.filter((s) => s.kind === kind) }))
    .filter((g) => g.rows.length > 0);

  function closed() {
    setQuery("");
    onClose();
  }

  function onBackdrop(event: MouseEvent<HTMLDialogElement>) {
    if (event.target === event.currentTarget) onClose();
  }

  return (
    <dialog ref={dialog} className="picker" aria-labelledby="picker-heading" onClose={closed} onClick={onBackdrop}>
      <div className="picker-head">
        <h2 id="picker-heading">Choose strategy {slot?.label}</h2>
        <button type="button" className="picker-close" onClick={onClose} aria-label="Close">
          <span aria-hidden="true">×</span>
        </button>
      </div>
      <input
        ref={search}
        type="search"
        className="picker-search"
        placeholder="Search by name or idea"
        aria-label="Search strategies"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />
      <div className="picker-list">
        {groups.map(({ kind, heading, rows }) => (
          <section key={kind} aria-labelledby={`kind-${kind}`}>
            <h3 id={`kind-${kind}`}>{heading}</h3>
            <ul>
              {rows.map((s) => {
                const taken = s.id === slot?.other.id;
                return (
                  <li key={s.id}>
                    <button
                      type="button"
                      className="picker-row"
                      disabled={taken}
                      aria-current={s.id === slot?.current ? "true" : undefined}
                      onClick={() => onPick(s.id)}
                    >
                      <span className="picker-title">
                        {s.title}
                        {taken ? <span className="picker-taken">Picked as {slot?.other.label}</span> : null}
                      </span>
                      <span className="picker-plain">{s.plain}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
        {groups.length === 0 ? <p className="muted">No strategy matches &ldquo;{query.trim()}&rdquo;.</p> : null}
      </div>
    </dialog>
  );
}
