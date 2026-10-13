"use client";

import { type PointerEvent, useEffect, useRef, useState } from "react";
import { formatDollars, formatMonth } from "@/lib/format";

export type Line = { id: string; label: string; color: string; values: number[] };

const PAD = { top: 12, right: 12, bottom: 24, left: 44 };

function niceStep(max: number): number {
  const raw = max / 4;
  const pow = 10 ** Math.floor(Math.log10(raw));
  return ([1, 2, 2.5, 5, 10].find((m) => m * pow >= raw) ?? 10) * pow;
}

/** Growth of `start` dollars, one point per month, linear axis, with a drag-to-read cursor. */
export function GrowthChart({ months, lines, start }: { months: string[]; lines: Line[]; start: number }) {
  const [cursor, setCursor] = useState<number | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const [W, setW] = useState(640);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => setW(Math.round(entry.contentRect.width)));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  const H = Math.round(Math.min(300, Math.max(200, W * 0.45)));
  const top = Math.max(1, ...lines.flatMap((l) => l.values)) * start;
  const step = niceStep(top);
  const yMax = Math.ceil(top / step) * step;
  const ticks = Array.from({ length: Math.round(yMax / step) + 1 }, (_, i) => i * step);
  const x = (i: number) => PAD.left + (i / (months.length - 1)) * (W - PAD.left - PAD.right);
  const y = (v: number) => PAD.top + (1 - v / yMax) * (H - PAD.top - PAD.bottom);
  const marks = months.flatMap((m, i) => (m.endsWith("-01") ? [{ i, text: m.slice(0, 4) }] : []));
  const every = Math.ceil(marks.length / Math.max(3, Math.floor(W / 90)));
  const shown = cursor ?? months.length - 1;

  function onPointer(event: PointerEvent<SVGSVGElement>) {
    const box = event.currentTarget.getBoundingClientRect();
    const px = ((event.clientX - box.left) / box.width) * W;
    const i = Math.round(((px - PAD.left) / (W - PAD.left - PAD.right)) * (months.length - 1));
    setCursor(Math.min(months.length - 1, Math.max(0, i)));
  }

  return (
    <div className="growth" ref={box}>
      <p className="readout" aria-live="polite">
        <strong>{formatMonth(months[shown])}</strong>
        {lines.map((l) => (
          <span key={l.id}>
            <i className="dot" style={{ "--c": l.color }} />
            {l.label} {formatDollars(l.values[shown] * start)}
          </span>
        ))}
      </p>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={`What $${start} became each month, ${lines.map((l) => l.label).join(" and ")}`}
        onPointerMove={onPointer}
        onPointerDown={onPointer}
        onPointerLeave={() => setCursor(null)}
      >
        {ticks.map((t) => (
          <g key={t}>
            <line className="grid" x1={PAD.left} x2={W - PAD.right} y1={y(t)} y2={y(t)} />
            <text x={PAD.left - 6} y={y(t) + 4} textAnchor="end">
              {formatDollars(t, { compact: true })}
            </text>
          </g>
        ))}
        {marks
          .filter((_, k) => k % every === 0)
          .map(({ i, text }) => (
            <text key={i} x={x(i)} y={H - 6} textAnchor="middle">
              {text}
            </text>
          ))}
        <line className="start" x1={PAD.left} x2={W - PAD.right} y1={y(start)} y2={y(start)} />
        {lines.map((l) => (
          <polyline
            key={l.id}
            fill="none"
            stroke={l.color}
            strokeWidth={2}
            strokeLinejoin="round"
            points={l.values.map((v, i) => `${x(i).toFixed(1)},${y(v * start).toFixed(1)}`).join(" ")}
          />
        ))}
        {cursor !== null && <line className="cursor" x1={x(cursor)} x2={x(cursor)} y1={PAD.top} y2={H - PAD.bottom} />}
      </svg>
    </div>
  );
}
