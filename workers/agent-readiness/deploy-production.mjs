import { execFileSync, spawnSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const workerRoot = dirname(fileURLToPath(import.meta.url));
const repositoryRoot = resolve(workerRoot, "../..");

function git(args) {
  return execFileSync("git", ["-C", repositoryRoot, ...args], {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  }).trim();
}

if (git(["status", "--porcelain", "--", "workers/agent-readiness"])) {
  throw new Error("Refusing to deploy Agent Readiness with uncommitted Worker source changes.");
}

const sourceSha = git(["log", "-1", "--format=%H", "HEAD", "--", "workers/agent-readiness/index.js", "workers/agent-readiness/wrangler.toml"]).toLowerCase();
if (!/^[0-9a-f]{40}$/.test(sourceSha)) {
  throw new Error("Could not resolve the exact Agent Readiness Worker source commit.");
}

const result = spawnSync("npx", [
  "wrangler", "deploy",
  "--config", "wrangler.toml",
  "--var", `AGENT_READINESS_SOURCE_SHA:${sourceSha}`,
], {
  cwd: workerRoot,
  stdio: "inherit",
  shell: process.platform === "win32",
});
if (result.status !== 0) process.exit(result.status || 1);
console.log(`Deployed Agent Readiness Worker from source ${sourceSha}.`);
