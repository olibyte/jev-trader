import { expect, type Page, test } from "@playwright/test";
import { type ArenaMarket, arenaBarKeys, arenaWindows, day, dollars, share } from "./expected";

const JARGON = /sharpe|interval|confidence|bootstrap|significan|p-value|drawdown|outperform|winner|beats/i;

async function expectNoJargon(page: Page) {
  expect(await page.locator("main").innerText()).not.toMatch(JARGON);
}

const LABELS: Record<ArenaMarket, string> = { daily: "Daily", hourly: "Hourly" };

const barSize = (page: Page, market: ArenaMarket) =>
  page.getByRole("group", { name: "Bar size" }).getByRole("button", { name: LABELS[market] });
const rangeButton = (page: Page, range: string) =>
  page.getByRole("group", { name: "Time range" }).getByRole("button", { name: range, exact: true });

async function hoverLeftEdge(page: Page, testId: string, inset = 2) {
  const chart = page.getByTestId(testId);
  await chart.scrollIntoViewIfNeeded();
  const box = await chart.boundingBox();
  if (!box) throw new Error(`${testId} has no box`);
  await page.mouse.move(0, 0);
  await page.mouse.move(box.x + inset, box.y + box.height / 2);
}

test("pick two opens on one year with the first two strategies", async ({ page }) => {
  await page.goto("/preview/");
  await expect(page.getByRole("group", { name: "Time range" }).getByRole("button", { name: "1Y" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(page.getByTestId("slot-A")).toContainText("Buy and hold");
  await expect(page.getByTestId("slot-B")).toContainText("Golden cross");
  await expect(page.getByTestId("slot-B")).toContainText("Stay in while prices are on a long climb.");
  await expect(page.locator(".lede")).toHaveText(
    "Each one invests in the same 13 US stock funds, with real prices from Jan 2008 to Oct 2026, and pays the same small fee (0.05%) every time it moves in or out.",
  );
  await expect(page.getByText("Put $1,000 in each on Oct 7, 2025.")).toBeVisible();
  await expect(page.getByTestId("amount-A")).toHaveText("$1,151");
  await expect(page.getByTestId("amount-B")).toHaveText("$1,125");
  await expect(page.getByTestId("gap")).toHaveText("By Oct 7, 2026, they ended within $50 of each other.");
  await expect(page.getByTestId("luck")).toHaveText(
    "Does that make it the better strategy? One year is too short to tell skill from luck.",
  );
  await expect(page.getByTestId("too-close")).toHaveCount(0);
  await expect(page.getByTestId("readout")).toHaveText("Oct 7, 2026A $1,151B $1,125");
  await expectNoJargon(page);
});

test("All shows the whole period and says the gap could be luck", async ({ page }) => {
  await page.goto("/preview/");
  await page.getByRole("button", { name: "All", exact: true }).click();
  await expect(page.getByText("Put $1,000 in each in Jan 2008.")).toBeVisible();
  await expect(page.getByTestId("amount-A")).toHaveText("$8,248");
  await expect(page.getByTestId("amount-B")).toHaveText("$4,748");
  await expect(page.getByTestId("gap")).toHaveText("By Oct 7, 2026, Buy and hold had $3,500 more.");
  await expect(page.getByTestId("luck")).toHaveText("Does that make it the better strategy? These years can't tell us. Here is why.");
  await expect(page.getByTestId("too-close")).toContainText("We can't tell yet.");
  await expectNoJargon(page);
});

test("the picker searches titles and plain sentences and swaps a slot", async ({ page }) => {
  await page.goto("/preview/");
  await page.getByTestId("slot-B").click();
  const dialog = page.getByRole("dialog", { name: "Choose strategy B" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("searchbox", { name: "Search strategies" })).toBeFocused();
  await expect(dialog.getByRole("heading", { level: 3 })).toHaveText(["Benchmarks", "Indicator rules"]);
  await expect(dialog.getByRole("button", { name: /Buy and hold/ })).toBeDisabled();
  await expect(dialog.getByRole("button", { name: /Buy and hold/ })).toContainText("Picked as A");

  await dialog.getByRole("searchbox").fill("SPEEDING");
  await expect(dialog.locator(".picker-row")).toHaveCount(1);
  await expect(dialog.locator(".picker-row")).toContainText("MACD crossover");
  await dialog.getByRole("searchbox").fill("zzz");
  await expect(dialog).toContainText("No strategy matches “zzz”.");
  await dialog.getByRole("searchbox").fill("bollinger");
  await dialog.getByRole("button", { name: /Bollinger bounce/ }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByTestId("slot-B")).toContainText("Bollinger bounce");
  await expect(page.getByTestId("amount-A")).toHaveText("$1,151");
  await expect(page.getByTestId("amount-B")).toHaveText("$1,085");
  await expect(page.getByTestId("gap")).toHaveText("By Oct 7, 2026, Buy and hold had $66 more.");

  await page.getByTestId("slot-A").click();
  await expect(page.getByRole("dialog", { name: "Choose strategy A" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toBeHidden();
  await page.getByTestId("slot-A").click();
  await page.getByRole("button", { name: "Close" }).click();
  await expect(page.getByRole("dialog")).toBeHidden();
});

test("the candles view shows one fund's prices and marks each strategy's trades", async ({ page }) => {
  await page.goto("/preview/");
  const fund = page.getByRole("combobox", { name: "Fund" });
  await expect(fund).toHaveCount(0);
  await page.getByRole("button", { name: "Candles" }).click();
  await expect(fund).toHaveValue("SPY");
  await expect(fund.locator("option")).toHaveCount(13);
  await expect(page.getByTestId("readout")).toHaveText("Oct 9, 2026O 776.24 H 779.42 L 775.14 C 778.57");
  await expect(page.getByTestId("candle-chart")).toBeVisible();
  await expect(page.getByText("Trades are on S&P 500 alone. The amounts above cover all 13 funds.")).toBeVisible();

  const trades = page.getByRole("switch", { name: "Show trades" });
  await expect(trades).not.toBeChecked();
  await expect(page.getByTestId("trade-legend")).toHaveCount(0);
  await trades.check();
  await expect(page.getByTestId("trade-legend")).toHaveText("Buy and holdGolden cross▲ bought ▼ sold");
  await expect(page.getByTestId("no-trades")).toHaveText("Neither strategy bought or sold S&P 500 in this range.");
  await page.getByRole("button", { name: "5Y" }).click();
  await expect(page.getByTestId("candle-cap")).toHaveText("Showing the last 250 days of this range.");
  await expect(page.getByTestId("no-trades")).toHaveText("Neither strategy bought or sold S&P 500 in this range.");
  await fund.selectOption("XLF");
  await expect(page.getByTestId("no-trades")).toHaveCount(0);

  await fund.selectOption("QQQ");
  await expect(page.getByTestId("readout")).toHaveText("Oct 9, 2026O 752.55 H 752.87 L 748.37 C 751.27");
  await expect(page.getByText("Trades are on Nasdaq 100 alone.")).toBeVisible();
  await page.getByRole("button", { name: "Line" }).click();
  await expect(fund).toHaveCount(0);
  await expectNoJargon(page);
});

for (const market of ["daily", "hourly"] as const) {
  test(`every ${market} amount and share matches ${market}/windows.json`, async ({ page }) => {
    await page.goto("/preview/");
    await barSize(page, market).click();
    for (const w of arenaWindows(market).windows) {
      await rangeButton(page, w.range).click();
      for (const [side, id] of [
        ["A", "buy_hold"],
        ["B", "golden_cross"],
      ]) {
        const figures = w.strategies[id];
        await expect(page.getByTestId(`amount-${side}`)).toHaveText(dollars(1000 * figures.growth));
        await expect(page.getByTestId(`exposure-${side}`)).toHaveText(share(figures.exposure));
        await expect(page.getByTestId(`drawdown-${side}`)).toHaveText(share(figures.maxDrawdown));
      }
    }
  });
}

test("the candles view shows the last 250 bars of a long range and every bar of a short one", async ({ page }) => {
  await page.goto("/preview/");
  await page.getByRole("button", { name: "Candles" }).click();
  await rangeButton(page, "All").click();
  await expect(page.getByTestId("candle-cap")).toHaveText("Showing the last 250 days of this range.");
  const spy = arenaBarKeys("daily", "SPY");
  await hoverLeftEdge(page, "candle-chart");
  await expect(page.getByTestId("readout")).toHaveText(new RegExp(`^${day(spy[spy.length - 250])}O `));

  await barSize(page, "hourly").click();
  await rangeButton(page, "1D").click();
  await expect(page.getByTestId("candle-chart")).toBeVisible();
  await expect(page.getByTestId("candle-cap")).toHaveCount(0);
  await hoverLeftEdge(page, "candle-chart");
  await expect(page.getByTestId("readout")).toHaveText(/^Oct 8, 2026, 2:30 pmO /);

  await rangeButton(page, "1Y").click();
  await expect(page.getByTestId("candle-cap")).toHaveText("Showing the last 250 hours of this range.");
});

test("the bar size switch keeps the range when the other has it and falls back to 1Y", async ({ page }) => {
  await page.goto("/preview/");
  await rangeButton(page, "1M").click();
  await barSize(page, "hourly").click();
  await expect(barSize(page, "hourly")).toHaveAttribute("aria-pressed", "true");
  await expect(rangeButton(page, "1M")).toHaveAttribute("aria-pressed", "true");

  await barSize(page, "daily").click();
  await rangeButton(page, "5Y").click();
  await barSize(page, "hourly").click();
  await expect(rangeButton(page, "1Y")).toHaveAttribute("aria-pressed", "true");

  await rangeButton(page, "1D").click();
  await barSize(page, "daily").click();
  await expect(rangeButton(page, "1Y")).toHaveAttribute("aria-pressed", "true");
  await expect(rangeButton(page, "1D")).toHaveCount(0);
});

test("hourly All says luck has not been tested and never says the gap could be luck", async ({ page }) => {
  await page.goto("/preview/");
  await barSize(page, "hourly").click();
  await rangeButton(page, "All").click();
  await expect(page.getByTestId("luck")).toHaveText(
    "Does that make it the better strategy? We haven't tested hourly results for luck yet.",
  );
  await expect(page.getByTestId("too-close")).toHaveCount(0);
  const text = await page.locator("main").innerText();
  expect(text).not.toMatch(/could be luck|enough to be luck/);
  expect(text.match(/luck/g)).toHaveLength(1);
  await expectNoJargon(page);

  await barSize(page, "daily").click();
  await expect(page.getByTestId("too-close")).toContainText("We can't tell yet.");
});

test("hourly bars read New York time and count hours", async ({ page }) => {
  await page.goto("/preview/");
  await barSize(page, "hourly").click();
  await expect(page.locator(".lede")).toHaveText(
    "Each one invests in the same 13 US stock funds, with about 2.7 years of hourly prices from Jan 2024 to Oct 2026, and pays the same small fee (0.05%) every time it moves in or out.",
  );
  await expect(page.getByText("Put $1,000 in each on Oct 9, 2025, 1:30 pm.")).toBeVisible();
  await expect(page.getByTestId("gap")).toContainText("By Oct 9, 2026, 1:30 pm,");
  await expect(page.getByTestId("readout")).toHaveText(/^Oct 9, 2026, 1:30 pmA /);
  await expect(page.getByText("Move across the chart to read any hour.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Share of hours invested" })).toBeVisible();
  await expect(page.getByText(/sat in cash on \d+% of hours\./)).toBeVisible();
  await expect(page.getByTestId("line-chart")).toHaveAttribute("aria-label", /^What \$1,000 became each hour /);
  await page.getByRole("button", { name: "Candles" }).click();
  await expect(page.getByTestId("candle-chart")).toHaveAttribute("aria-label", "Hourly prices of S&P 500");
  await expectNoJargon(page);
});

test("the page fetches a market's files only when a visitor first picks it", async ({ page }) => {
  const paths: string[] = [];
  page.on("request", (r) => paths.push(new URL(r.url()).pathname));
  const hourly = () => paths.filter((p) => p.startsWith("/preview/data/hourly/"));
  await page.goto("/preview/");
  await expect(page.getByTestId("line-chart")).toBeVisible();
  await page.getByRole("button", { name: "Candles" }).click();
  await expect(page.getByTestId("candle-chart")).toBeVisible();
  expect(paths).toContain("/preview/data/daily/portfolio.json");
  expect(paths).toContain("/preview/data/daily/funds/SPY.json");
  expect(hourly()).toEqual([]);

  await barSize(page, "hourly").click();
  await expect(page.getByTestId("candle-chart")).toHaveAttribute("aria-label", "Hourly prices of S&P 500");
  expect(hourly()).toEqual(["/preview/data/hourly/funds/SPY.json"]);
});

test.describe("on a phone screen", () => {
  test.use({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 });

  test("the line chart still shows the whole year after a resize soon after it draws", async ({ page }) => {
    await page.goto("/preview/");
    const chart = page.getByTestId("line-chart");
    await chart.waitFor();
    await page.waitForTimeout(400);
    // A full-page capture resizes the viewport, as a phone's address bar does when it collapses.
    await page.screenshot({ fullPage: true });
    await chart.scrollIntoViewIfNeeded();
    const box = await chart.boundingBox();
    if (!box) throw new Error("the line chart has no box");
    await page.mouse.move(box.x + 2, box.y + box.height / 2);
    await expect(page.getByTestId("readout")).toContainText(/^Oct \d+, 2025/);
  });

  for (const [market, range, month] of [
    ["daily", "All", /^Jan \d+, 2008A /],
    ["hourly", "1Y", /^Oct \d+, 2025, .+A /],
    ["hourly", "All", /^Jan \d+, 2024, .+A /],
  ] as const) {
    test(`the ${market} ${range} line starts in the range's first month`, async ({ page }) => {
      await page.goto("/preview/");
      await barSize(page, market).click();
      await rangeButton(page, range).click();
      await expect(page.getByTestId("line-chart")).toBeVisible();
      // A pixel spans many points here, so the edge reads the first month, not the first point.
      await hoverLeftEdge(page, "line-chart", 0.1);
      await expect(page.getByTestId("readout")).toHaveText(month);
    });
  }
});
