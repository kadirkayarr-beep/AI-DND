import assert from 'node:assert/strict';
import { before, after, test } from 'node:test';
import path from 'node:path';
import { readGameBrowserSource } from './helpers/read-game-browser-source.mjs';

// D-234 (Kadir): "önce motorun savaşta Geri Al'ı testle doğrulanır; güvenliyse savaşta Geri Al açılır". The engine
// tests (api/tests/test_d234_combat_undo.py) showed a fight turn undone whole, so the last fight turn is offered too.
let lastTurn, vite, React, renderToStaticMarkup;
before(async () => {
  process.env.PORT ||= '4191'; process.env.BASE_PATH ||= '/';
  const { createServer } = await import('vite');
  vite = await createServer({ configFile: path.join(process.cwd(), 'vite.config.ts'), server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' });
  lastTurn = await vite.ssrLoadModule('/src/components/last-turn-bar.tsx');
  React = await import('react');
  ({ renderToStaticMarkup } = await import('react-dom/server'));
});
after(async () => await vite?.close());

const state = ({ combat = true, dead = false } = {}) =>
  ({ combat: { active: combat }, death_state: { mode: 'PERMADEATH', dead, terminal: false } });

test('in a fight the last turn is offered for undo', () => {
  assert.equal(lastTurn.undoOffered(state(), true), true);
  assert.equal(lastTurn.undoOffered(state({ dead: true }), true), false, 'a real death stays final (D-178)');
});

test('the bar shows Geri al in a fight and no "no undo in a fight" line', () => {
  const html = renderToStaticMarkup(React.createElement(lastTurn.LastTurnBar, {
    summary: null, canUndo: true, recoveringUndo: false, busy: false, onUndo() {}, justUndone: false }));
  assert.match(html, /data-testid="button-undo-last-turn"/);
  assert.doesNotMatch(html, /text-undo-combat|Savaş sürerken/);
  assert.doesNotMatch(readGameBrowserSource(), /combatActive=\{Boolean\(visibleLastTurn\)/);
});
