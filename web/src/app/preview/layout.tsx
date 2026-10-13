import type { Metadata, Viewport } from "next";
import Link from "next/link";
import type { ReactNode } from "react";
import { PreviewNav } from "@/components/arena/PreviewNav";
import { loadArena } from "@/lib/arena";
import "./preview.css";

export const metadata: Metadata = {
  title: { default: "Trade Arena prototype", template: "%s · Trade Arena prototype" },
  description: "Famous trading strategies, run on the same US funds with the same costs, explained in plain words.",
};

export const viewport: Viewport = { themeColor: "#f6f5f1", colorScheme: "light" };

export default function PreviewLayout({ children }: { children: ReactNode }) {
  const { costBps } = loadArena();
  return (
    <div className="arena">
      <header className="arena-top">
        <span>
          <Link href="/preview/" className="arena-brand">
            Trade Arena
          </Link>
          <span className="arena-tag">Prototype</span>
        </span>
        <PreviewNav />
      </header>
      <main className="arena-main" id="main">
        {children}
      </main>
      <footer className="arena-foot">
        <p>
          <strong>Not investment advice.</strong> Nothing here is a recommendation to buy or sell any security.
        </p>
        <p>Backtests are hypothetical, include modeled trading costs only, and do not predict future returns.</p>
        <p>
          Real daily prices from January 2008 to October 2026. Every move in or out of the market costs{" "}
          {costBps / 100}%. &ldquo;In cash&rdquo; means short-term US Treasury bills, which pay a little interest.
        </p>
      </footer>
    </div>
  );
}
