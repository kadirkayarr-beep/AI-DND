import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
process.env.PORT ||= '4179';
process.env.BASE_PATH ||= '/';
delete process.env.REPL_ID;
let vite, Help, render;
before(async () => {
  const { createServer } = await import('vite');
  vite = await createServer({ configFile: path.join(process.cwd(), 'vite.config.ts'),
    server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' });
  Help = (await vite.ssrLoadModule('/src/components/courtyard-help.tsx')).CourtyardHelp;
  render = (await import('react-dom/server')).renderToStaticMarkup;
});
after(async () => { await vite?.close(); });
const state = () => ({ location: 'city', character: {current_hp: 12}, combat: {active: false},
  npcs: [{id: 'private-id', name: 'Yakındaki kişi', location: 'city', current_hp: 4, combat_status: 'active'}],
  bounded_encounter: {scenario_id: 'open_courtyard_commoner_v1', location_id: 'city',
    visible_opponent: {npc_id: 'private-id', distance_ft: 60}} });
test('accessible courtyard choice drafts only, with public name and actual distance', () => {
  const s = state(); const before = structuredClone(s); const drafts = [];
  const tree = Help({state:s, disabled:false, onDraft: text => drafts.push(text)});
  const html = render(tree);
  assert.match(html, /<summary/); assert.match(html, /Yakındaki kişi/);
  assert.match(html, /60 feet/); assert.doesNotMatch(html, /private-id/);
  const button = tree.props.children.find(child => child.type === 'button');
  assert.equal(button.props.type, 'button');
  assert.equal(button.props['aria-describedby'], 'courtyard-draft-help');
  assert.deepEqual(drafts, []);
  button.props.onClick();
  assert.deepEqual(drafts, ['Avlu çatışmasını başlat']);
  assert.deepEqual(s, before);
  assert.match(render(Help({state:s, disabled:true, onDraft(){}})), /disabled/);
});
test('help is absent without the current observable living encounter', () => {
  const changes = [s => delete s.bounded_encounter, s => s.bounded_encounter.visible_opponent = null,
    s => s.bounded_encounter.location_id = 'elsewhere', s => s.combat.active = true,
    s => s.npcs[0].current_hp = 0, s => s.npcs[0].combat_status = 'unconscious',
    s => s.character.current_hp = 0, s => s.pending_event_decisions = [{}]];
  for (const change of changes) { const s=state(); change(s);
    assert.equal(Help({state:s, disabled:false, onDraft(){throw Error('must not act');}}), null); }
});
test('story wiring only fills editable input and focuses it; no turn submit', async () => {
  const source = await readFile('src/pages/game-browser.tsx', 'utf8');
  const wiring = source.match(/<CourtyardHelp[\s\S]*?\}\} \/>/)?.[0];
  assert.ok(wiring); assert.match(wiring, /setMessage\(text\)/);
  assert.match(wiring, /setInteractionMode\('do'\)/);
  assert.match(wiring, /messageInputRef.current\?\.focus/);
  assert.doesNotMatch(wiring, /submitTurn|onSubmit|onExplorationCommand|onEconomyCommand/);
});
