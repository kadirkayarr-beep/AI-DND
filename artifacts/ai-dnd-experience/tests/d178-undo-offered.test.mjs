import assert from 'node:assert/strict';
import { before, after, test } from 'node:test';
import path from 'node:path';
import { readGameBrowserSource } from './helpers/read-game-browser-source.mjs';

// D-178 (Kadir): "PERMADEATH'te ölüm kesin; ölüm turu Geri Al ile geri alınamaz." The panel offers the undo button
// on the same rule the server enforces (api/main.py _final_death), so a real death shows no button that always fails.
let lastTurn, vite;
before(async () => {
  process.env.PORT ||= '4191'; process.env.BASE_PATH ||= '/';
  const { createServer } = await import('vite');
  vite = await createServer({ configFile: path.join(process.cwd(), 'vite.config.ts'), server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' });
  lastTurn = await vite.ssrLoadModule('/src/components/last-turn-bar.tsx');
});
after(async () => await vite?.close());

const state = ({ mode = 'PERMADEATH', dead = false, terminal = false, combat = false } = {}) =>
  ({ combat: { active: combat }, death_state: { mode, dead, terminal } });

test('a real death (PERMADEATH) offers no undo; a living hero after a turn does', () => {
  assert.equal(lastTurn.undoOffered(state(), true), true);
  assert.equal(lastTurn.undoOffered(state({ dead: true }), true), false);
});

test('an Ironman death, a missing last turn and a running fight offer no undo', () => {
  assert.equal(lastTurn.undoOffered(state({ mode: 'IRONMAN', dead: true, terminal: true }), true), false);
  assert.equal(lastTurn.undoOffered(state(), false), false);
  assert.equal(lastTurn.undoOffered(state({ combat: true }), true), false);
});

test('the game screen asks undoOffered for the button', () => {
  assert.match(readGameBrowserSource(), /canUndo=\{undoOffered\(state, Boolean\(visibleLastTurn\)\)\}/);
});
