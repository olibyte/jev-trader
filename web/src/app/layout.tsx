import type { Metadata, Viewport } from "next";
import Link from "next/link";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Jev Trader", template: "%s · Jev Trader" },
  description: "Research on whether Jev, TypeSafe AI's decision model, ranks 20-day ETF outcomes better than technical-analysis baselines.",
};

export const viewport: Viewport = { themeColor: "#0b1220", colorScheme: "dark" };

const NAV = [
  { href: "/", label: "Result" },
  { href: "/rulebook/", label: "Rulebook" },
  { href: "/symbols/", label: "Symbols" },
  { href: "/manifest/", label: "Manifest" },
] as const;

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <a className="skip-link" href="#main">
          Skip to content
        </a>
        <header className="site-header">
          <Link href="/" className="brand" translate="no">
            Jev Trader
          </Link>
          <nav aria-label="Main">
            <ul>
              {NAV.map((item) => (
                <li key={item.href}>
                  <Link href={item.href}>{item.label}</Link>
                </li>
              ))}
            </ul>
          </nav>
        </header>
        <main id="main" tabIndex={-1}>
          {children}
        </main>
        <footer className="site-footer">
          <p>Research, not investment advice. Nothing here is a recommendation to buy or sell any security.</p>
          <p>Backtests are hypothetical, include modeled trading costs only, and do not predict future returns.</p>
        </footer>
      </body>
    </html>
  );
}
