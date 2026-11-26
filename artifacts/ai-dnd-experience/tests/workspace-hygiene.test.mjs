// G1.5: dead artifacts stay gone, zod stays on the patched major, dev server stays loopback + named hosts
import test from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync, readdirSync } from "node:fs";

const root = (file) => new URL(`../../../${file}`, import.meta.url);
const text = (file) => readFileSync(root(file), "utf8");

test("only the player UI remains under artifacts", () => {
  assert.deepEqual(readdirSync(root("artifacts")).sort(), ["ai-dnd-experience"]);
  for (const dead of ["api-server", "mockup-sandbox", "ai-dnd-web"]) {
    assert.equal(existsSync(root(`artifacts/${dead}`)), false, `${dead} must stay removed`);
  }
});

test("zod catalog is on a patched release (GHSA-mrhx-c7xc-m3w5, >=4.6.6)", () => {
  const match = text("pnpm-workspace.yaml").match(/^\s+zod:\s*\^?(\d+)\.(\d+)\.(\d+)\s*$/m);
  assert.ok(match, "zod catalog entry present");
  const [major, minor, patch] = match.slice(1).map(Number);
  const ok = major > 4 || (major === 4 && (minor > 6 || (minor === 6 && patch >= 6)));
  assert.ok(ok, `zod ${major}.${minor}.${patch} is below 4.6.6`);
});

test("vite dev server listens on loopback with named hosts only", () => {
  const cfg = text("artifacts/ai-dnd-experience/vite.config.ts");
  assert.match(cfg, /'127\.0\.0\.1'/);
  assert.doesNotMatch(cfg, /allowedHosts:\s*true/);
  assert.doesNotMatch(cfg, /host:\s*['"]0\.0\.0\.0['"]\s*,/);
});
