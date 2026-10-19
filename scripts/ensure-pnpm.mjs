// Cross-platform replacement for the old `sh -c '...'` preinstall hook, which
// failed on Windows because `sh` does not exist there. Same behavior:
// remove stray npm/yarn lockfiles, then refuse any installer except pnpm.
import { rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
for (const lockfile of ["package-lock.json", "yarn.lock"]) {
  rmSync(join(root, lockfile), { force: true });
}

const agent = process.env.npm_config_user_agent ?? "";
if (!agent.startsWith("pnpm/")) {
  console.error("Use pnpm instead");
  process.exit(1);
}
