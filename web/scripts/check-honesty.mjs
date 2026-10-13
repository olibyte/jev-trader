import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const RULES = [
  {
    pattern: /confidence(?!\s+interval)/i,
    rule: 'Jev returns no confidence value. Write "confidence interval" or "95% CI", never "confidence" alone (product spec honesty rule 2).',
  },
  {
    pattern: /reasoning/i,
    rule: 'Jev returns no reasoning. Show a "What Jev saw" panel, never a "Reasoning" panel (honesty rule 1).',
  },
  {
    pattern: /chance of profit/i,
    rule: 'Label Jev\'s number "P(higher in 20 trading days)", never a chance of profit (honesty rule 2).',
  },
  {
    pattern: /\b(?:BUY|SELL|Buy|Sell)\b/,
    rule: "The study is long-only. Label positions Long or Flat, never Buy or Sell.",
  },
];

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "src");

function files(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
    e.isDirectory() ? files(path.join(dir, e.name)) : [path.join(dir, e.name)],
  );
}

const violations = files(root).flatMap((file) =>
  readFileSync(file, "utf8")
    .split("\n")
    .flatMap((line, i) =>
      RULES.filter((r) => r.pattern.test(line)).map(
        (r) => `${path.relative(process.cwd(), file)}:${i + 1}: ${line.trim()}\n  ${r.rule}`,
      ),
    ),
);

const e2e = path.join(root, "..", "e2e");
for (const file of files(e2e)) {
  readFileSync(file, "utf8")
    .split("\n")
    .forEach((line, i) => {
      if (/from\s+["'][^"']*\/src\//.test(line)) {
        violations.push(
          `${path.relative(process.cwd(), file)}:${i + 1}: ${line.trim()}\n  The end-to-end test checks the site against the export with its own rules, so it never imports app code from src/.`,
        );
      }
    });
}

if (violations.length) {
  console.error(`check:honesty found ${violations.length} banned wording(s):\n${violations.join("\n")}`);
  process.exit(1);
}
console.log(`check:honesty passed: no banned wording in ${path.relative(process.cwd(), root) || "src"}.`);
