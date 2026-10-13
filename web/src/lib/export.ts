import "server-only";
import { createHash } from "node:crypto";
import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { z } from "zod";

const sha256 = z.string().regex(/^[0-9a-f]{64}$/, "expected a lowercase hex sha256");
const gitSha = z.string().regex(/^[0-9a-f]{40}$/, "expected a 40-character git commit sha");
const isoDate = z.iso.date();
const count = z.int().nonnegative();
const unit = z.number().min(0).max(1);

export const SPLITS = ["fit", "validate", "holdout"] as const;
const split = z.enum(SPLITS);
export type Split = z.infer<typeof split>;

export const OUTCOMES = ["jev_better", "jev_worse", "inconclusive"] as const;
const outcome = z.enum(OUTCOMES);
export type Outcome = z.infer<typeof outcome>;

export const ARM_NAMES = [
  "jev",
  "jev_matched",
  "empirical_table",
  "vote_trend",
  "vote_revert",
  "sma_filter",
  "buy_hold",
  "random_matched",
  "oracle",
] as const;
const armName = z.enum(ARM_NAMES);
export type ArmName = z.infer<typeof armName>;

const runName = z.enum(["holdout", "export"]);
export type RunName = z.infer<typeof runName>;

const span = { first: isoDate, last: isoDate };
const periods = z.tuple([
  z.strictObject({ split: z.literal("fit"), label: z.literal("development"), ...span }),
  z.strictObject({ split: z.literal("validate"), label: z.literal("development"), ...span }),
  z.strictObject({ split: z.literal("holdout"), label: z.literal("holdout"), ...span }),
]);
export type Period = z.infer<typeof periods>[number];
export type PeriodLabel = Period["label"];

const interval = z
  .strictObject({ point: z.number(), lo: z.number(), hi: z.number() })
  .refine((i) => i.lo <= i.hi, "lo must not exceed hi");
export type Interval = z.infer<typeof interval>;

const calibrationBin = z.strictObject({
  binLow: unit,
  binHigh: unit,
  rows: count,
  meanScore: unit,
  upRate: unit,
});
export type CalibrationBin = z.infer<typeof calibrationBin>;

const armBase = z.strictObject({
  name: armName,
  rule: z.string().min(1),
  lookahead: z.boolean(),
  auc: interval,
  excessSharpe: interval,
  excessSharpeByCost: z.array(z.strictObject({ costBps: count, value: z.number() })).min(1),
  exposure: unit,
  switchesPerYear: z.number().nonnegative(),
  maxDrawdown: unit,
});

const arm = z.discriminatedUnion("probability", [
  armBase.extend({
    probability: z.literal(true),
    brierSkill: interval,
    calibration: z.array(calibrationBin).min(1),
  }),
  armBase.extend({
    probability: z.literal(false),
    brierSkill: z.null(),
    calibration: z.null(),
  }),
]);
export type Arm = z.infer<typeof arm>;

const summarySchema = z.strictObject({
  run: z.literal("holdout"),
  period: z.strictObject({ label: z.literal("holdout"), ...span }),
  rows: count,
  labelled: count,
  blocks: count,
  sharpeBlocks: count,
  primary: z.strictObject({
    metric: z.string().min(1),
    candidate: armName,
    baseline: armName,
    point: z.number(),
    lo: z.number(),
    hi: z.number(),
  }),
  outcome,
  outcomeRule: z.strictObject({
    jev_better: z.string(),
    jev_worse: z.string(),
    inconclusive: z.string(),
  }),
  power: z.strictObject({
    alpha: unit,
    power: unit,
    devSe: z.number().positive(),
    mde: z.number().positive(),
    validateBlocks: count,
    holdoutBlocks: count,
  }),
  bootstrap: z.strictObject({ level: unit, block: z.int().positive(), reps: z.int().positive(), seed: z.int() }),
  costBps: count,
  costsBps: z.array(count).min(1),
  fitOn: z.array(split).min(1),
  arms: z.array(arm).min(1),
});
export type Summary = z.infer<typeof summarySchema>;

const dimension = z.strictObject({
  name: z.string().min(1),
  field: z.string().min(1),
  levels: z.array(z.strictObject({ level: z.string().min(1), text: z.string().min(1) })).min(1),
});
export type Dimension = z.infer<typeof dimension>;

const development = z.union([
  z.strictObject({ n: z.literal(0), ups: z.literal(0), upRate: z.null(), empiricalP: unit }),
  z
    .strictObject({ n: z.int().positive(), ups: count, upRate: unit, empiricalP: unit })
    .refine((d) => d.ups <= d.n, "ups must not exceed n"),
]);
export type Development = z.infer<typeof development>;

const policyState = z.strictObject({
  key: sha256,
  levels: z.record(z.string(), z.string()),
  pUp: unit,
  pSd: z.number().nonnegative(),
  coherence: z.number().nonnegative(),
  samples: z.array(z.strictObject({ order: z.array(count), pHi: unit, pLo: unit })).min(1),
  development,
});
export type PolicyState = z.infer<typeof policyState>;

const question = z.strictObject({
  type: z.string(),
  instructions: z.string().min(1),
  criteria: z.strictObject({ true: z.string(), false: z.string() }),
});

const policySchema = z.strictObject({
  run: z.literal("export"),
  promptVersion: z.string().min(1),
  modelServed: z.string().min(1),
  samples: z.int().positive(),
  questions: z.record(z.string(), question),
  development: z.strictObject({
    splits: z.array(split).min(1),
    ...span,
    labelled: count,
    baseRate: unit,
    shrinkK: count,
  }),
  dimensions: z.array(dimension).min(1),
  states: z.array(policyState).min(1),
});
export type Policy = z.infer<typeof policySchema>;

const price = z.number().positive();
const symbolSchema = z.strictObject({
  run: z.literal("export"),
  symbol: z.string().min(1),
  inStudy: z.boolean(),
  days: z.strictObject({
    date: z.array(isoDate).min(1),
    open: z.array(price),
    high: z.array(price),
    low: z.array(price),
    close: z.array(price),
    split: z.array(split),
    state: z.array(count),
    jev: z.array(z.union([z.literal(0), z.literal(1)])),
    fwdRet20: z.array(z.number().nullable()),
  }),
  equity: z.strictObject({
    period: z.literal("holdout"),
    costBps: count,
    date: z.array(isoDate).min(1),
    arms: z.strictObject({
      jev: z.array(z.number().positive()),
      empirical_table: z.array(z.number().positive()),
      buy_hold: z.array(z.number().positive()),
    }),
  }),
});
export type SymbolFile = z.infer<typeof symbolSchema>;
export type Days = SymbolFile["days"];
export type Equity = SymbolFile["equity"];

const manifestSchema = z.strictObject({
  version: z.literal("v1"),
  study: z.strictObject({
    stateVersion: z.string().min(1),
    promptVersion: z.string().min(1),
    modelRequested: z.string().min(1),
    modelServed: z.string().min(1),
    horizon: z.int().positive(),
    symbols: z.array(z.string().regex(/^[A-Z]+$/, "expected an upper-case ticker")).min(1),
    cash: z.string().min(1),
    periods,
  }),
  datasets: z.strictObject({
    market: z.record(
      z.string(),
      z.strictObject({ sha256, ...span, rows: count, fetchedAt: z.string().min(1) }),
    ),
    policy: z.strictObject({ path: z.string().min(1), sha256 }),
    callLog: z.strictObject({ path: z.string().min(1), sha256, calls: count, costUsd: z.number().nonnegative() }),
  }),
  runs: z.strictObject({
    holdout: z.strictObject({
      command: z.literal("jt holdout"),
      gitCommit: gitSha,
      preregSha256: sha256,
      resultSha256: sha256,
      files: z.array(z.string().min(1)).min(1),
    }),
    export: z.strictObject({
      command: z.literal("jt export"),
      inputs: z.record(z.string(), sha256),
    }),
  }),
  files: z.record(z.string(), sha256),
});
export type Manifest = z.infer<typeof manifestSchema>;

export type Export = {
  manifest: Manifest;
  summary: Summary;
  policy: Policy;
  symbols: ReadonlyMap<string, SymbolFile>;
};

class ExportError extends Error {
  constructor(file: string, problems: string[]) {
    super(`Invalid export file ${file}:\n${problems.map((p) => `  - ${p}`).join("\n")}`);
    this.name = "ExportError";
  }
}

function fail(file: string, problem: string): never {
  throw new ExportError(file, [problem]);
}

function readJson<T>(dir: string, file: string, schema: z.ZodType<T>, bytes: Buffer): T {
  let raw: unknown;
  try {
    raw = JSON.parse(bytes.toString("utf8"));
  } catch (error) {
    fail(path.join(dir, file), `not valid JSON: ${String(error)}`);
  }
  const parsed = schema.safeParse(raw);
  if (!parsed.success) {
    throw new ExportError(
      path.join(dir, file),
      parsed.error.issues.map((i) => `at ${i.path.length ? i.path.join(".") : "(root)"}: ${i.message}`),
    );
  }
  return parsed.data;
}

function listFiles(dir: string, prefix = ""): string[] {
  return readdirSync(path.join(dir, prefix), { withFileTypes: true }).flatMap((entry) => {
    const rel = prefix ? `${prefix}/${entry.name}` : entry.name;
    return entry.isDirectory() ? listFiles(dir, rel) : [rel];
  });
}

function sameMembers(a: readonly string[], b: readonly string[]): boolean {
  const left = new Set(a);
  return left.size === b.length && b.every((x) => left.has(x));
}

function checkSummary(file: string, summary: Summary): void {
  const names = summary.arms.map((a) => a.name);
  const duplicate = names.find((n, i) => names.indexOf(n) !== i);
  if (duplicate) fail(file, `at arms: arm name "${duplicate}" appears more than once`);
  for (const name of [summary.primary.candidate, summary.primary.baseline]) {
    if (!names.includes(name)) fail(file, `at primary: arm "${name}" is not in arms`);
  }
  if (!summary.costsBps.includes(summary.costBps)) fail(file, `at costBps: ${summary.costBps} is not in costsBps`);
  summary.arms.forEach((a, i) => {
    const costs = a.excessSharpeByCost.map((c) => c.costBps);
    if (costs.join() !== summary.costsBps.join()) {
      fail(file, `at arms.${i}.excessSharpeByCost: costs ${costs.join(", ")} differ from costsBps`);
    }
  });
}

function checkPolicy(file: string, policy: Policy): void {
  const names = policy.dimensions.map((d) => d.name);
  const keys = new Set<string>();
  policy.states.forEach((state, i) => {
    if (keys.has(state.key)) fail(file, `at states.${i}.key: duplicate state key`);
    keys.add(state.key);
    if (!sameMembers(Object.keys(state.levels), names)) {
      fail(file, `at states.${i}.levels: keys must be the dimension names ${names.join(", ")}`);
    }
    for (const dim of policy.dimensions) {
      if (!dim.levels.some((l) => l.level === state.levels[dim.name])) {
        fail(file, `at states.${i}.levels.${dim.name}: "${state.levels[dim.name]}" is not a level of ${dim.name}`);
      }
    }
    if (state.samples.length !== policy.samples) {
      fail(file, `at states.${i}.samples: ${state.samples.length} samples, expected ${policy.samples}`);
    }
    state.samples.forEach((s, j) => {
      const sorted = s.order.toSorted((a, b) => a - b);
      if (sorted.length !== names.length || sorted.some((v, k) => v !== k)) {
        fail(file, `at states.${i}.samples.${j}.order: not a permutation of the ${names.length} dimension indexes`);
      }
    });
  });
}

function checkSymbol(file: string, symbol: SymbolFile, name: string, stateCount: number): void {
  if (symbol.symbol !== name) fail(file, `at symbol: "${symbol.symbol}" does not match the file name`);
  const { days, equity } = symbol;
  const n = days.date.length;
  for (const [column, values] of Object.entries(days)) {
    if (values.length !== n) fail(file, `at days.${column}: length ${values.length}, expected ${n} like days.date`);
  }
  for (const [arm, values] of Object.entries(equity.arms)) {
    if (values.length !== equity.date.length) {
      fail(file, `at equity.arms.${arm}: length ${values.length}, expected ${equity.date.length} like equity.date`);
    }
  }
  days.date.forEach((d, i) => {
    if (i > 0 && d <= days.date[i - 1]) fail(file, `at days.date.${i}: dates must ascend`);
  });
  days.state.forEach((s, i) => {
    if (s >= stateCount) fail(file, `at days.state.${i}: index ${s} is out of range for ${stateCount} policy states`);
  });
}

function checkManifest(file: string, manifest: Manifest, onDisk: string[], policy: Policy): void {
  const listed = Object.keys(manifest.files);
  const extra = onDisk.filter((f) => !(f in manifest.files));
  const missing = listed.filter((f) => !onDisk.includes(f));
  if (extra.length) fail(file, `at files: ${extra.join(", ")} exist on disk but are not listed`);
  if (missing.length) fail(file, `at files: ${missing.join(", ")} are listed but missing on disk`);
  const symbolFiles = onDisk.filter((f) => f.startsWith("symbols/")).map((f) => f.slice("symbols/".length, -".json".length));
  if (!sameMembers(manifest.study.symbols, symbolFiles)) {
    fail(file, `at study.symbols: ${manifest.study.symbols.join(", ")} differ from the symbols/ files ${symbolFiles.join(", ")}`);
  }
  for (const s of [...manifest.study.symbols, manifest.study.cash]) {
    if (!(s in manifest.datasets.market)) fail(file, `at datasets.market: no dataset for ${s}`);
  }
  if (policy.modelServed !== manifest.study.modelServed) {
    fail(file, `at study.modelServed: "${manifest.study.modelServed}" differs from policy.json "${policy.modelServed}"`);
  }
  if (policy.promptVersion !== manifest.study.promptVersion) {
    fail(file, `at study.promptVersion: "${manifest.study.promptVersion}" differs from policy.json "${policy.promptVersion}"`);
  }
}

function readExport(dir: string): Export {
  const onDisk = listFiles(dir).filter((f) => f !== "manifest.json").sort();
  const manifest = readJson(dir, "manifest.json", manifestSchema, readFileSync(path.join(dir, "manifest.json")));

  const bytes = new Map<string, Buffer>();
  for (const file of onDisk) {
    const content = readFileSync(path.join(dir, file));
    const digest = createHash("sha256").update(content).digest("hex");
    const expected = manifest.files[file];
    if (expected !== undefined && digest !== expected) {
      fail(path.join(dir, file), `sha256 ${digest} does not match manifest.json files["${file}"] ${expected}`);
    }
    bytes.set(file, content);
  }
  const source = (file: string): Buffer => bytes.get(file) ?? fail(path.join(dir, file), "file is missing");

  const summary = readJson(dir, "summary.json", summarySchema, source("summary.json"));
  checkSummary(path.join(dir, "summary.json"), summary);
  const policy = readJson(dir, "policy.json", policySchema, source("policy.json"));
  checkPolicy(path.join(dir, "policy.json"), policy);
  checkManifest(path.join(dir, "manifest.json"), manifest, onDisk, policy);

  const symbols = new Map<string, SymbolFile>();
  for (const name of manifest.study.symbols) {
    const file = `symbols/${name}.json`;
    const symbol = readJson(dir, file, symbolSchema, source(file));
    checkSymbol(path.join(dir, file), symbol, name, policy.states.length);
    symbols.set(name, symbol);
  }
  return { manifest, summary, policy, symbols };
}

const EXPORT_DIR = path.resolve(process.env.EXPORT_DIR ?? path.join(process.cwd(), "..", "export", "v1"));
let loaded: Export | undefined;

export function loadExport(): Export {
  loaded ??= readExport(EXPORT_DIR);
  return loaded;
}

export function symbolFile(name: string): SymbolFile {
  const symbol = loadExport().symbols.get(name);
  if (!symbol) throw new Error(`No export file for symbol ${name}`);
  return symbol;
}

export function sawLines(policy: Policy, state: PolicyState, sample: number): { field: string; text: string }[] {
  return state.samples[sample].order.map((d) => {
    const dim = policy.dimensions[d];
    const level = dim.levels.find((l) => l.level === state.levels[dim.name]);
    if (!level) throw new Error(`policy.json: state ${state.key} has no text for ${dim.name}`);
    return { field: dim.field, text: level.text };
  });
}

export function periodLabels(manifest: Manifest): Record<Split, PeriodLabel> {
  const [fit, validate, holdout] = manifest.study.periods;
  return { fit: fit.label, validate: validate.label, holdout: holdout.label };
}
