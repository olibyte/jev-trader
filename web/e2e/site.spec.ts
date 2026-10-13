import { execFileSync } from "node:child_process";
import { expect, type Locator, type Page, test } from "@playwright/test";
import {
  type Arm,
  BANNED,
  f1,
  f2,
  f3,
  int,
  level,
  manifest,
  pct1,
  policy,
  range,
  signedPct2,
  summary,
  symbolData,
} from "./expected";

const OUTCOME_LABEL = { jev_better: "Jev better", jev_worse: "Jev worse", inconclusive: "Inconclusive" };

async function cellTexts(row: Locator): Promise<string[]> {
  return (await row.locator("th, td").allInnerTexts()).map((t) => t.replace(/\s+/g, " ").trim());
}

async function expectNoBannedWords(page: Page) {
  const text = await page.locator("body").innerText();
  const html = await page.content();
  for (const [pattern, name] of BANNED) {
    expect(pattern.test(text), `visible text contains ${name}`).toBe(false);
    expect(pattern.test(html), `HTML contains ${name}`).toBe(false);
  }
}

function armLabel(arm: Arm): string {
  return arm.lookahead ? `${arm.name} look-ahead check, not a strategy` : arm.name;
}

test("the result page shows the pre-registered holdout result from summary.json", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("outcome")).toHaveText(OUTCOME_LABEL[summary.outcome]);
  await expect(page.getByTestId("primary-point")).toHaveText(f3(summary.primary.point));
  await expect(page.getByTestId("primary-ci")).toHaveText(range(summary.primary, f3));
  await expect(page.getByTestId("mde")).toHaveText(f3(summary.power.mde));
  await expect(page.getByTestId("blocks")).toHaveText(int(summary.blocks));
  await expect(page.getByTestId("labelled")).toHaveText(int(summary.labelled));
  await expect(page.getByTestId("period-label")).toHaveText(summary.period.label);
  await expect(page.getByTestId("period-dates")).toHaveText(`${summary.period.first} to ${summary.period.last}`);
  await expect(page.getByTestId("model-served")).toHaveText(manifest.study.modelServed);
  expect(summary.outcome).toBe("inconclusive");
  expect(f3(summary.power.mde)).toBe("0.032");

  const arms = page.getByTestId("arms-table");
  await expect(arms.locator("thead")).toContainText(`n = ${int(summary.blocks)} blocks`);
  await expect(arms.locator("thead")).toContainText(`n = ${int(summary.sharpeBlocks)} blocks`);
  await expect(arms.locator("thead a")).toHaveAttribute("href", "/manifest/#run-export");
  await expect(arms.locator("tbody tr")).toHaveCount(summary.arms.length);
  for (const arm of summary.arms) {
    const brier = arm.brierSkill ? [f3(arm.brierSkill.point), range(arm.brierSkill, f3)] : ["Not a probability score"];
    expect(await cellTexts(arms.locator(`tr[data-arm="${arm.name}"]`))).toEqual([
      armLabel(arm),
      arm.rule,
      f3(arm.auc.point),
      range(arm.auc, f3),
      ...brier,
      f2(arm.excessSharpe.point),
      range(arm.excessSharpe, f2),
    ]);
  }

  const points = page.getByTestId("points-table");
  for (const arm of summary.arms) {
    expect(await cellTexts(points.locator(`tr[data-arm="${arm.name}"]`))).toEqual([
      armLabel(arm),
      pct1(arm.exposure),
      f1(arm.switchesPerYear),
      pct1(arm.maxDrawdown),
      ...summary.costsBps.map((bps) => f2(arm.excessSharpeByCost.find((c) => c.costBps === bps)?.value ?? NaN)),
    ]);
  }
  await expect(points.locator("thead")).toContainText(summary.costsBps.map((b) => `Excess Sharpe at ${b} bps`).join(""));

  for (const name of [summary.primary.candidate, summary.primary.baseline]) {
    const bins = summary.arms.find((a) => a.name === name)?.calibration ?? [];
    expect(bins.length).toBeGreaterThan(0);
    const rows = page.getByTestId(`calibration-${name}`).locator("tbody tr");
    await expect(rows).toHaveCount(bins.length);
    for (const [i, bin] of bins.entries()) {
      expect(await cellTexts(rows.nth(i))).toEqual([
        `${f1(bin.binLow)} to ${f1(bin.binHigh)}`,
        int(bin.rows),
        f3(bin.meanScore),
        pct1(bin.upRate),
      ]);
    }
  }
  for (const link of await page.getByRole("link", { name: /Source: holdout run/ }).all()) {
    await expect(link).toHaveAttribute("href", "/manifest/#run-holdout");
  }
  await expectNoBannedWords(page);
});

function expectedRulebookRow(i: number): string[] {
  const s = policy.states[i];
  const dev = s.development;
  return [
    String(i + 1),
    ...policy.dimensions.map((d) => level(s.levels[d.name])),
    f3(s.pUp),
    f3(s.pSd),
    f3(s.coherence),
    dev.upRate === null ? "No rows" : pct1(dev.upRate),
    int(dev.n),
    f3(dev.empiricalP),
  ];
}

test("the rulebook's static HTML lists every state with Jev's answer and the development up rate", async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();
  await page.goto("/rulebook/");
  await expect(page.getByTestId("model-served")).toHaveText(policy.modelServed);
  const rows = page.getByTestId("rulebook-table").locator("tbody tr");
  await expect(rows).toHaveCount(policy.states.length);
  expect(policy.states.length).toBe(960);
  const all = await rows.evaluateAll((trs) =>
    trs.map((tr) => [...tr.querySelectorAll("th, td")].map((c) => (c.textContent ?? "").trim())),
  );
  all.forEach((cells, i) => expect(cells, `rulebook row ${i + 1}`).toEqual(expectedRulebookRow(i)));
  await expectNoBannedWords(page);
  await context.close();
});

test("the rulebook filters states by level on the client", async ({ page }) => {
  await page.goto("/rulebook/");
  const [dim] = policy.dimensions;
  const target = dim.levels[0].level;
  const matching = policy.states.flatMap((s, i) => (s.levels[dim.name] === target ? [i] : []));
  await page.getByLabel(dim.field).selectOption(target);
  const rows = page.getByTestId("rulebook-table").locator("tbody tr");
  await expect(rows).toHaveCount(matching.length);
  await expect(page.getByTestId("rulebook-count")).toHaveText(`Showing ${int(matching.length)} of ${int(960)} states.`);
  expect(await cellTexts(rows.first())).toEqual(expectedRulebookRow(matching[0]));
});

function mulberry32(seed: number) {
  let a = seed;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

async function expectDay(page: Page, symbol: string, i: number) {
  const { days } = symbolData(symbol);
  const state = policy.states[days.state[i]];
  const horizon = manifest.study.horizon;
  const split = days.split[i];
  const next = days.date[i + 1];
  const exit = days.date[i + 1 + horizon];
  const fwd = days.fwdRet20[i];
  const where = `${symbol} ${days.date[i]}`;

  await expect(page.getByTestId("tt-date"), where).toHaveText(days.date[i]);
  await expect(page.getByTestId("tt-period"), where).toHaveText(split === "holdout" ? "holdout" : `development (${split})`);
  const saw = state.samples[0].order.map((d) => {
    const dim = policy.dimensions[d];
    return `${dim.field}: ${dim.levels.find((l) => l.level === state.levels[dim.name])?.text}`;
  });
  await expect(page.getByTestId("tt-saw").locator("li"), where).toHaveText(saw);
  await expect(page.getByTestId("tt-pup"), where).toHaveText(f3(state.pUp));
  await expect(page.getByTestId("tt-samples").locator("li"), where).toHaveText(
    state.samples.map((s) => `P(higher) ${f2(s.pHi)}, P(lower or equal) ${f2(s.pLo)}`),
  );
  const dev = state.development;
  await expect(page.getByTestId("tt-dev"), where).toHaveText(
    dev.upRate === null ? "This state never occurred on a labelled development day." : `${pct1(dev.upRate)} of ${int(dev.n)} labelled symbol-days`,
  );
  const position = days.jev[i] === 1 ? "Long" : "Flat";
  await expect(page.getByTestId("tt-position"), where).toHaveText(
    next ? `${position}, held from the next open (${next})` : `${position}, held from the next open`,
  );
  await expect(page.getByTestId("tt-fwd"), where).toHaveText(
    fwd === null ? "Not yet known" : `${signedPct2(fwd)} from the open of ${next} to the open of ${exit}`,
  );
}

for (const symbol of manifest.study.symbols) {
  test(`the ${symbol} time-travel panel matches the export on the default day and 5 seeded days`, async ({ page }) => {
    const { days } = symbolData(symbol);
    await page.goto(`/symbols/${symbol}/`);
    await expect(page.getByText("Descriptive", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("The study result is the pooled holdout comparison on the")).toBeVisible();
    await expectDay(page, symbol, days.date.length - 1);

    const random = mulberry32([...symbol].reduce((h, c) => h * 31 + c.charCodeAt(0), 7));
    for (let k = 0; k < 5; k++) {
      const i = Math.floor(random() * days.date.length);
      await page.goto(`/symbols/${symbol}/#${days.date[i]}`);
      await expectDay(page, symbol, i);
    }
    await expectNoBannedWords(page);
  });
}

test("day selection follows the buttons, the arrow keys, and a chart click, and the hash links to the day", async ({ page }) => {
  const symbol = manifest.study.symbols[0];
  const { days } = symbolData(symbol);
  const start = days.split.indexOf("holdout");
  await page.goto(`/symbols/${symbol}/#${days.date[start]}`);
  await expectDay(page, symbol, start);
  await page.getByRole("button", { name: "Previous trading day" }).click();
  await expectDay(page, symbol, start - 1);
  expect(new URL(page.url()).hash).toBe(`#${days.date[start - 1]}`);
  await page.getByRole("button", { name: "Next trading day" }).click();
  await page.getByRole("button", { name: "Next trading day" }).click();
  await expectDay(page, symbol, start + 1);
  const chart = page.getByTestId("price-chart");
  await chart.focus();
  await page.keyboard.press("ArrowLeft");
  await expectDay(page, symbol, start);
  await page.keyboard.press("End");
  await expectDay(page, symbol, days.date.length - 1);
  const box = await chart.boundingBox();
  if (!box) throw new Error("price chart has no bounding box");
  await chart.click({ position: { x: box.width / 3, y: box.height / 2 } });
  const clicked = new URL(page.url()).hash.slice(1);
  const i = days.date.indexOf(clicked);
  expect(i, `chart click selected ${clicked}`).toBeGreaterThanOrEqual(0);
  expect(i).toBeLessThan(days.date.length - 1);
  await expectDay(page, symbol, i);
});

test("the symbol index links every study symbol", async ({ page }) => {
  await page.goto("/symbols/");
  for (const symbol of manifest.study.symbols) {
    await expect(page.getByRole("link", { name: symbol, exact: true })).toHaveAttribute("href", `/symbols/${symbol}/`);
  }
  await expectNoBannedWords(page);
});

test("the manifest page shows every hash, both runs, and the build commit", async ({ page }) => {
  await page.goto("/manifest/");
  await expect(page.locator("#run-holdout")).toBeVisible();
  await expect(page.locator("#run-export")).toBeVisible();
  const text = await page.locator("main").innerText();
  const hashes = [
    ...Object.values(manifest.files),
    ...Object.values(manifest.runs.export.inputs),
    ...Object.values(manifest.datasets.market).map((d) => d.sha256),
    manifest.datasets.policy.sha256,
    manifest.datasets.callLog.sha256,
    manifest.runs.holdout.preregSha256,
    manifest.runs.holdout.resultSha256,
    manifest.runs.holdout.gitCommit,
  ];
  for (const hash of hashes) expect(text, `manifest page shows ${hash}`).toContain(hash);
  const sha = manifest.runs.holdout.gitCommit;
  await expect(page.getByRole("link", { name: sha })).toHaveAttribute("href", `https://github.com/olibyte/jev-trader/commit/${sha}`);
  const head = execFileSync("git", ["rev-parse", "HEAD"], { encoding: "utf8" }).trim();
  await expect(page.getByTestId("build-commit")).toHaveText(head);
  await expect(page.getByTestId("build-commit")).toHaveAttribute("href", `https://github.com/olibyte/jev-trader/commit/${head}`);
  await expectNoBannedWords(page);
});

test("pages request nothing beyond the static host at run time", async ({ page, baseURL }) => {
  const host = new URL(baseURL ?? "").host;
  const offHost: string[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.protocol !== "data:" && url.host !== host) offHost.push(request.url());
  });
  for (const url of ["/", "/rulebook/", "/symbols/", `/symbols/${manifest.study.symbols[0]}/`, "/manifest/"]) {
    await page.goto(url, { waitUntil: "networkidle" });
  }
  expect(offHost).toEqual([]);
});

test("every page carries both disclaimers in its footer", async ({ page }) => {
  for (const url of ["/", "/rulebook/", "/symbols/", `/symbols/${manifest.study.symbols[0]}/`, "/manifest/"]) {
    await page.goto(url);
    const footer = page.locator("footer");
    await expect(footer).toContainText(
      "Research, not investment advice. Nothing here is a recommendation to buy or sell any security.",
    );
    await expect(footer).toContainText(
      "Backtests are hypothetical, include modeled trading costs only, and do not predict future returns.",
    );
  }
});
