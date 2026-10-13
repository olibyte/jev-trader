"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const SCREENS = [
  { href: "/preview/pick-two/", label: "Pick two" },
  { href: "/preview/guess/", label: "Guess first" },
] as const;

export function PreviewNav() {
  const path = usePathname();
  return (
    <nav aria-label="Prototype screens">
      {SCREENS.map((s) => (
        <Link key={s.href} href={s.href} aria-current={path === s.href ? "page" : undefined}>
          {s.label}
        </Link>
      ))}
    </nav>
  );
}
