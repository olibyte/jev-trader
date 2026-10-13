import { mkdirSync } from "node:fs";
import path from "node:path";
import { chromium } from "@playwright/test";

const [base = "http://127.0.0.1:4317", outDir = "screenshots"] = process.argv.slice(2);
const PAGES = [
  ["result", "/"],
  ["rulebook", "/rulebook/"],
  ["symbol-SPY", "/symbols/SPY/#2018-12-24"],
  ["manifest", "/manifest/"],
];
const VIEWPORTS = [
  ["desktop", { width: 1366, height: 900 }],
  ["phone", { width: 390, height: 844 }],
];

mkdirSync(outDir, { recursive: true });
const browser = await chromium.launch();
for (const [vpName, viewport] of VIEWPORTS) {
  const page = await browser.newPage({ viewport });
  for (const [name, url] of PAGES) {
    await page.goto(base + url, { waitUntil: "networkidle" });
    await page.waitForTimeout(500);
    const scroll = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    if (scroll > 0) console.log(`${vpName} ${name}: horizontal page overflow ${scroll}px`);
    await page.screenshot({ path: path.join(outDir, `${name}-${vpName}.png`), fullPage: true });
  }
  await page.close();
}
await browser.close();
