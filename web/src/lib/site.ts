import type { RunName } from "./export";

export const REPO_URL = "https://github.com/olibyte/jev-trader";

const commit = process.env.BUILD_COMMIT;
if (!commit || !/^[0-9a-f]{40}$/.test(commit)) {
  throw new Error("BUILD_COMMIT is not a git commit sha. next.config.ts sets it from git rev-parse HEAD.");
}
export const BUILD_COMMIT: string = commit;

export function commitUrl(sha: string): string {
  return `${REPO_URL}/commit/${sha}`;
}

export function runHref(run: RunName): string {
  return `/manifest/#run-${run}`;
}
