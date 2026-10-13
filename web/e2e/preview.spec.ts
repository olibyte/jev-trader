import { expect, test } from "@playwright/test";

const JARGON = /sharpe|interval|confidence|bootstrap|significan|p-value|drawdown|outperform|winner/i;

test("pick two shows what $1,000 became for the default pair and swaps in a third tap", async ({ page }) => {
  await page.goto("/preview/");
  await expect(page.getByTestId("end-buy_hold")).toHaveText("$8,248");
  await expect(page.getByTestId("end-golden_cross")).toHaveText("$4,748");
  await expect(page.getByTestId("gap")).toHaveText("By Oct 2026, Buy and hold had $3,500 more.");
  await expect(page.getByTestId("too-close")).toContainText("We can't tell yet.");

  await page.getByRole("button", { name: "MACD crossover" }).click();
  await expect(page.getByTestId("end-golden_cross")).toHaveText("$4,748");
  await expect(page.getByTestId("end-macd_cross")).toHaveText("$2,779");
  await expect(page.getByTestId("end-buy_hold")).toHaveCount(0);
  expect(await page.locator("main").innerText()).not.toMatch(JARGON);
});
