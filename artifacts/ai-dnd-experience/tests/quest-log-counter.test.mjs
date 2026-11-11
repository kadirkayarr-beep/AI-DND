// node:test + node:assert, as the other .test.mjs files
import test from "node:test";
import { readGameBrowserSource } from './helpers/read-game-browser-source.mjs';
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
const browser = readGameBrowserSource();
const journal = readFileSync(new URL("../src/components/quest-journal-section.tsx", import.meta.url), "utf8");
test("the top bar counts quest_log.active_count", () => {
  assert.match(browser, /quest_log\?\.active_count/);
  assert.doesNotMatch(browser, /quests\?\.length|quests\.length/);
});
test("the page hands the journal the quest_log view", () => {
  // the only call site of QuestJournalSection must pass the new prop, or the
  // component falls back to today's drawing and the trails never reach the real page
  const call = browser.match(/<QuestJournalSection\b[\s\S]*?\/>/);
  assert.ok(call, "QuestJournalSection call site not found");
  assert.match(call[0], /questLog=\{state\.quest_log\}/);
  assert.equal((browser.match(/<QuestJournalSection\b/g) || []).length, 1);
});
test("the journal reads the questLog prop, not a state field", () => {
  assert.match(journal, /questLog\??\.active\b/);
  assert.match(journal, /questLog\??\.trails\b/);
  assert.doesNotMatch(journal, /quest_log\?\.|state\.quest_log/);   // the component has no state; the page passes the view
});
