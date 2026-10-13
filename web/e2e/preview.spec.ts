import { expect, type Page, test } from "@playwright/test";

const JARGON = /sharpe|interval|confidence|bootstrap|significan|p-value|drawdown|outperform|winner|beats/i;

async function expectNoJargon(page: Page) {
  expect(await page.locator("main").innerText()).not.toMatch(JARGON);
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
  await expect(page.getByTestId("no-trades")).toHaveCount(0);

  await fund.selectOption("QQQ");
  await expect(page.getByTestId("readout")).toHaveText("Oct 9, 2026O 752.55 H 752.87 L 748.37 C 751.27");
  await expect(page.getByText("Trades are on Nasdaq 100 alone.")).toBeVisible();
  await page.getByRole("button", { name: "Line" }).click();
  await expect(fund).toHaveCount(0);
  await expectNoJargon(page);
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
});
