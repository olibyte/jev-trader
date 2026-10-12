import { formatScore } from "@/lib/format";

const WIDTH = 560;
const HEIGHT = 120;
const PAD = 24;
const AXIS_Y = 64;

type Props = { point: number; lo: number; hi: number; mde: number; label: string };

export function CiChart({ point, lo, hi, mde, label }: Props) {
  const reach = Math.max(Math.abs(lo), Math.abs(hi), mde) * 1.25;
  const x = (v: number) => Math.round((PAD + ((v + reach) / (2 * reach)) * (WIDTH - 2 * PAD)) * 10) / 10;
  const description = `${label}: point ${formatScore(point)}, 95% confidence interval ${formatScore(lo)} to ${formatScore(hi)}. Shaded band: minus to plus the minimum detectable effect, ${formatScore(mde)}. Vertical line: zero.`;
  return (
    <svg className="ci-chart" viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label={description}>
      <rect x={x(-mde)} y={20} width={x(mde) - x(-mde)} height={88} fill="var(--holdout)" stroke="var(--accent)" strokeDasharray="4 3" />
      <text x={x(mde)} y={14} textAnchor="middle">
        +MDE
      </text>
      <text x={x(-mde)} y={14} textAnchor="middle">
        {"−"}MDE
      </text>
      <line x1={PAD} x2={WIDTH - PAD} y1={AXIS_Y} y2={AXIS_Y} stroke="var(--border)" />
      <line x1={x(0)} x2={x(0)} y1={20} y2={108} stroke="var(--text)" strokeWidth={1.5} />
      <text x={x(0)} y={HEIGHT - 2} textAnchor="middle">
        0
      </text>
      <line x1={x(lo)} x2={x(hi)} y1={AXIS_Y} y2={AXIS_Y} stroke="var(--warn)" strokeWidth={4} strokeLinecap="round" />
      <line x1={x(lo)} x2={x(lo)} y1={AXIS_Y - 10} y2={AXIS_Y + 10} stroke="var(--warn)" strokeWidth={2} />
      <line x1={x(hi)} x2={x(hi)} y1={AXIS_Y - 10} y2={AXIS_Y + 10} stroke="var(--warn)" strokeWidth={2} />
      <circle cx={x(point)} cy={AXIS_Y} r={6} fill="var(--warn)" stroke="var(--bg)" strokeWidth={2} />
    </svg>
  );
}
