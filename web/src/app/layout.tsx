import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: { default: "Jev Trader", template: "%s · Jev Trader" },
  description: "Research on whether Jev, TypeSafe AI's decision model, ranks 20-day ETF outcomes better than technical-analysis baselines.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
