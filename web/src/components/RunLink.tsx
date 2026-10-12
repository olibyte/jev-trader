import Link from "next/link";
import type { RunName } from "@/lib/export";
import { runHref } from "@/lib/site";

export function RunLink({ run }: { run: RunName }) {
  return (
    <Link className="run-link" href={runHref(run)}>
      Source: <code>{run}</code> run
    </Link>
  );
}
