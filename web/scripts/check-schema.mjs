import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { cpSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const web = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const source = path.resolve(web, process.env.EXPORT_DIR ?? "../export/v1");
const arenaSource = path.resolve(web, process.env.ARENA_DIR ?? "../export/arena/v2");
const next = path.join(web, "node_modules", ".bin", "next");

const readJson = (dir, file) => JSON.parse(readFileSync(path.join(dir, file), "utf8"));
const writeJson = (dir, file, value) => writeFileSync(path.join(dir, file), `${JSON.stringify(value, null, 2)}\n`);

function rehash(dir, file) {
  const manifest = readJson(dir, "manifest.json");
  manifest.files[file] = createHash("sha256").update(readFileSync(path.join(dir, file))).digest("hex");
  writeJson(dir, "manifest.json", manifest);
}

function editJson(file, edit) {
  return (dir) => {
    const value = readJson(dir, file);
    edit(value);
    writeJson(dir, file, value);
    rehash(dir, file);
  };
}

const MUTATIONS = [
  {
    name: "outcome is not one of the three pre-declared outcomes",
    apply: editJson("summary.json", (s) => {
      s.outcome = "maybe";
    }),
    expect: ["summary.json", "at outcome"],
  },
  {
    name: "a required field is missing from summary.json",
    apply: editJson("summary.json", (s) => {
      delete s.blocks;
    }),
    expect: ["summary.json", "at blocks"],
  },
  {
    name: "a probability arm has no Brier skill",
    apply: editJson("summary.json", (s) => {
      s.arms[0].brierSkill = null;
    }),
    expect: ["summary.json", "at arms.0.brierSkill"],
  },
  {
    name: "a symbol day's state indexes past the policy states",
    apply: editJson("symbols/SPY.json", (s) => {
      s.days.state[0] = 960;
    }),
    expect: ["symbols/SPY.json", "at days.state.0"],
  },
  {
    name: "a columnar array is shorter than days.date",
    apply: editJson("symbols/QQQ.json", (s) => {
      s.days.fwdRet20.pop();
    }),
    expect: ["symbols/QQQ.json", "at days.fwdRet20"],
  },
  {
    name: "policy.json bytes no longer match the manifest hash",
    apply: (dir) => {
      const file = path.join(dir, "policy.json");
      writeFileSync(file, readFileSync(file, "utf8").replace(/\n$/, " \n"));
    },
    expect: ["policy.json", "does not match manifest.json"],
  },
  {
    name: "a study symbol has no symbols/ file",
    apply: (dir) => {
      rmSync(path.join(dir, "symbols", "XLY.json"));
      const manifest = readJson(dir, "manifest.json");
      delete manifest.files["symbols/XLY.json"];
      writeJson(dir, "manifest.json", manifest);
    },
    expect: ["manifest.json", "at study.symbols"],
  },
];

function editArena(file, edit) {
  return (dir) => {
    const value = readJson(dir, file);
    edit(value);
    writeFileSync(path.join(dir, file), `${JSON.stringify(value)}\n`);
  };
}

const ARENA_MUTATIONS = [
  {
    name: "a strategy has no plain sentence",
    apply: editArena("catalog.json", (c) => {
      delete c.strategies[1].plain;
    }),
    expect: ["catalog.json", "strategies", "plain"],
  },
  {
    name: "windows.json drops the 1Y range",
    apply: editArena("daily/windows.json", (w) => {
      w.windows.splice(3, 1);
    }),
    expect: ["daily/windows.json", "the ranges are 1W, 1M, 3M, 5Y, All"],
  },
  {
    name: "the All window's exposure differs from comparisons.json",
    apply: editArena("daily/windows.json", (w) => {
      w.windows.at(-1).strategies.golden_cross.exposure = 0.5;
    }),
    expect: ["daily/windows.json", 'the All window for "golden_cross" does not match its portfolio row'],
  },
  {
    name: "the All window's growth differs from the last curve value",
    apply: editArena("daily/windows.json", (w) => {
      w.windows.at(-1).strategies.buy_hold.growth = 8.24825;
    }),
    expect: ["daily/windows.json", 'All growth for "buy_hold" is 8.24825'],
  },
  {
    name: "a trade falls on a date with no bar",
    apply: editArena("daily/funds/SPY.json", (f) => {
      f.trades.macd_cross.buy[0] = "2008-01-05";
    }),
    expect: ["daily/funds/SPY.json", 'trade date 2008-01-05 for "macd_cross" is not a bar date'],
  },
];

function build(exportDir, arenaDir = arenaSource) {
  const result = spawnSync(next, ["build"], {
    cwd: web,
    encoding: "utf8",
    env: { ...process.env, EXPORT_DIR: exportDir, ARENA_DIR: arenaDir, NEXT_TELEMETRY_DISABLED: "1" },
  });
  return { status: result.status, output: `${result.stdout}\n${result.stderr}` };
}

const scratch = mkdtempSync(path.join(tmpdir(), "jev-export-"));
const failures = [];
try {
  const cases = [
    ...MUTATIONS.map((m) => ({ ...m, from: source, run: (dir) => build(dir) })),
    ...ARENA_MUTATIONS.map((m) => ({ ...m, from: arenaSource, run: (dir) => build(source, dir) })),
  ];
  for (const [i, mutation] of cases.entries()) {
    const dir = path.join(scratch, String(i));
    cpSync(mutation.from, dir, { recursive: true });
    mutation.apply(dir);
    const { status, output } = mutation.run(dir);
    const missing = mutation.expect.filter((text) => !output.includes(text));
    const ok = status !== 0 && missing.length === 0;
    console.log(`${ok ? "PASS" : "FAIL"} ${mutation.name}: build exited ${status}`);
    if (!ok) {
      failures.push(mutation.name);
      console.log(missing.length ? `  output does not name: ${missing.join(", ")}` : "  build succeeded on a broken export");
      console.log(output.split("\n").slice(-30).join("\n"));
    }
  }
} finally {
  rmSync(scratch, { recursive: true, force: true });
}

const clean = build(source);
console.log(
  `${clean.status === 0 ? "PASS" : "FAIL"} clean build of ${path.relative(web, source)} and ${path.relative(web, arenaSource)}: build exited ${clean.status}`,
);
if (clean.status !== 0) {
  failures.push("clean build");
  console.log(clean.output.split("\n").slice(-30).join("\n"));
}

if (failures.length) {
  console.error(`check:schema failed: ${failures.join("; ")}`);
  process.exit(1);
}
console.log(
  `check:schema passed: ${MUTATIONS.length + ARENA_MUTATIONS.length} broken exports failed the build, and the real exports build.`,
);
