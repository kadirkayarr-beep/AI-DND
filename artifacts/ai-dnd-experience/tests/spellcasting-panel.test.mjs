import assert from 'node:assert/strict';
import { before, after, test } from 'node:test';
import path from 'node:path';
import { readFile } from 'node:fs/promises';

process.env.PORT ||= '4179';
process.env.BASE_PATH ||= '/';
delete process.env.REPL_ID;
let vite, render;
before(async () => {
  const { createServer } = await import('vite');
  vite = await createServer({ configFile: path.join(process.cwd(), 'vite.config.ts'),
    server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' });
  const { SpellcastingPanel } = await vite.ssrLoadModule('/src/components/spellcasting-panel.tsx');
  const React = await import('react');
  const { renderToStaticMarkup } = await import('react-dom/server');
  render = (spellcasting) => renderToStaticMarkup(React.createElement(SpellcastingPanel, { spellcasting }));
});
after(async () => { await vite?.close(); });
const supplied = () => ({ cantrips: ['Fire Bolt'], prepared: ['Magic Missile'],
  slots: { '1': 0 }, slot_turn: ['hidden-combat-id', 3, 2] });

test('missing and null legacy projections grant nothing and render no invented state', () => {
  assert.equal(render(undefined), '');
  assert.equal(render(null), '');
});
test('renders exact supplied lists, zero slots and turn values without technical identity', () => {
  const html = render(supplied());
  assert.match(html, /Fire Bolt/);
  assert.match(html, /Magic Missile/);
  assert.match(html, /data-testid="spell-slots-1">0</);
  assert.match(html, /Raunt 3 · Sıra 2/);
  assert.doesNotMatch(html, /hidden-combat-id|Python|API|Qwen|backend/);
});
test('empty prepared list stays empty and does not infer from cantrips', () => {
  const value = supplied(); value.prepared = []; value.slot_turn = null;
  const html = render(value);
  assert.match(html, /Hazırlanmış büyü yok/);
  assert.doesNotMatch(html, /Magic Missile|spell-slot-turn/);
});
test('rerenders new authoritative slots without mutation or casting controls', () => {
  const value = supplied(); const before = JSON.stringify(value);
  assert.match(render(value), /spell-slots-1">0</);
  assert.equal(JSON.stringify(value), before);
  const next = { ...value, slots: { '1': 1 } };
  assert.match(render(next), /spell-slots-1">1</);
  assert.doesNotMatch(render(next), /<button|<input|<select/);
});
test('panel has no local state, requests, legality calculation or resource consumption', async () => {
  const source = await readFile('src/components/spellcasting-panel.tsx', 'utf8');
  assert.doesNotMatch(source, /useState|useReducer|localStorage|fetch\(|\.mutate|slots\s*\[.*\]\s*=|CLASS_DEFINITIONS/);
  const page = await readFile('src/pages/game-browser.tsx', 'utf8');
  assert.equal((page.match(/<SpellcastingPanel spellcasting=\{state\.spellcasting\}/g) ?? []).length, 3);
});