import { execFileSync } from "node:child_process";
import type { NextConfig } from "next";

function buildCommit(): string {
  const sha = execFileSync("git", ["rev-parse", "HEAD"], { encoding: "utf8" }).trim();
  if (!/^[0-9a-f]{40}$/.test(sha)) {
    throw new Error(`git rev-parse HEAD printed "${sha}", which is not a commit sha. The site must name the commit it was built from.`);
  }
  return sha;
}

const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  reactStrictMode: true,
  env: { BUILD_COMMIT: buildCommit() },
};

export default nextConfig;
