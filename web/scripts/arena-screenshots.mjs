import { mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

const [base = "http://127.0.0.1:4317"] = process.argv.slice(2);
const out = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "docs", "assets", "trade-arena");
const DEVICES = {
  desktop: { viewport: { width: 1280, height: 900 } },
  phone: { viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 },
};
const MARKETS = { daily: "Daily", hourly: "Hourly" };
const VIEWS = {
  line: async (page) => page.getByTestId("line-chart").waitFor(),
  "candles-trades": async (page) => {
    await page.getByRole("button", { name: "Candles" }).click();
    await page.getByRole("switch", { name: "Show trades" }).check();
    await page.getByTestId("candle-chart").waitFor();
  },
};

mkdirSync(out, { recursive: true });
const browser = await chromium.launch();
const problems = [];
for (const [device, options] of Object.entries(DEVICES)) {
  const context = await browser.newContext(options);
  for (const [market, label] of Object.entries(MARKETS)) {
    for (const [view, show] of Object.entries(VIEWS)) {
      const name = `${device}-${market}-1y-${view}`;
      const page = await context.newPage();
      page.on("console", (m) => m.type() === "error" && problems.push(`${name}: console error: ${m.text()}`));
      page.on("pageerror", (e) => problems.push(`${name}: page error: ${e.message}`));
      await page.goto(`${base}/preview/`, { waitUntil: "networkidle" });
      await page.getByRole("group", { name: "Bar size" }).getByRole("button", { name: label }).click();
      await show(page);
      await page.waitForTimeout(500);
      const scroll = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      if (scroll > 0) problems.push(`${name}: the page scrolls ${scroll}px sideways`);
      const file = path.join(out, `${name}.png`);
      await page.screenshot({ path: file, fullPage: true });
      console.log(`wrote ${path.relative(process.cwd(), file)}`);
      await page.close();
    }
  }
  await context.close();
}
await browser.close();
if (problems.length) {
  console.error(problems.join("\n"));
  process.exit(1);
}
