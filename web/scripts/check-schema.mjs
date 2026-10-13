import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { cpSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const web = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const source = path.resolve(web, process.env.EXPORT_DIR ?? "../export/v1");
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

function build(exportDir) {
  const result = spawnSync(next, ["build"], {
    cwd: web,
    encoding: "utf8",
    env: { ...process.env, EXPORT_DIR: exportDir, NEXT_TELEMETRY_DISABLED: "1" },
  });
  return { status: result.status, output: `${result.stdout}\n${result.stderr}` };
}

const scratch = mkdtempSync(path.join(tmpdir(), "jev-export-"));
const failures = [];
try {
  for (const mutation of MUTATIONS) {
    const dir = path.join(scratch, String(MUTATIONS.indexOf(mutation)));
    cpSync(source, dir, { recursive: true });
    mutation.apply(dir);
    const { status, output } = build(dir);
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
console.log(`${clean.status === 0 ? "PASS" : "FAIL"} clean build of ${path.relative(web, source)}: build exited ${clean.status}`);
if (clean.status !== 0) {
  failures.push("clean build");
  console.log(clean.output.split("\n").slice(-30).join("\n"));
}

if (failures.length) {
  console.error(`check:schema failed: ${failures.join("; ")}`);
  process.exit(1);
}
console.log(`check:schema passed: ${MUTATIONS.length} broken exports failed the build, and the real export builds.`);
