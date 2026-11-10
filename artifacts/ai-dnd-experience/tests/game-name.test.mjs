// node:test + node:assert, source-contract style like the other .test.mjs files
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8");

test("browser tab and share metadata name the game Unwritten", () => {
  for (const file of ["index.html", "../ai-dnd-web/index.html"]) {
    const html = read(file);
    assert.match(html, /<title>Unwritten<\/title>/);
    assert.match(html, /property="og:title" content="Unwritten"/);
    assert.match(html, /name="twitter:title" content="Unwritten"/);
    assert.doesNotMatch(html, /AI-DND|Campaign Browser|Unwritten One/);
    for (const attr of ['name="description"', 'property="og:description"', 'name="twitter:description"']) {
      const tag = html.match(new RegExp(`<meta ${attr} content="([^"]*)"`));
      assert.ok(tag, `${file} has ${attr}`);
      assert.doesNotMatch(tag[1], /Replit/);
    }
    const description = html.match(/<meta name="description" content="([^"]*)"/)[1];
    assert.match(description, /Unwritten/);
  }
});

test("header and character-creation brand say Unwritten", () => {
  const browser = read("src/pages/game-browser.tsx");
  const creation = read("src/components/character-creation-screen.tsx");
  const web = read("../ai-dnd-web/src/pages/game-browser.tsx");
  assert.match(browser, /className="brand-name">Unwritten</);
  assert.match(creation, /aria-label="Unwritten"/);
  assert.match(creation, /<strong>Unwritten<\/strong>/);
  assert.match(web, />Unwritten<\/div>/);
  for (const src of [browser, creation, web]) {
    assert.doesNotMatch(src, /AI DUNGEON MASTER|AI Dungeon Master|>AI-DND<|Unwritten One/);
  }
});

test("Replit artifact titles carry the player-visible name", () => {
  for (const file of ["../ai-dnd-web/.replit-artifact/artifact.toml", ".replit-artifact/artifact.toml"]) {
    const toml = read(file);
    assert.match(toml, /^title = "Unwritten"\s*$/m);
    assert.doesNotMatch(toml.match(/^description = .*$/m)[0], /AI-DND/);
  }
});
