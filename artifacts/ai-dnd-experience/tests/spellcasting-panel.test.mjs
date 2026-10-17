import assert from 'node:assert/strict';
import { before, after, test } from 'node:test';
import path from 'node:path';
import { readFile } from 'node:fs/promises';

process.env.PORT ||= '4179';
process.env.BASE_PATH ||= '/';
delete process.env.REPL_ID;
let vite, render, renderCharacterPanel, renderReveal;
before(async () => {
  const { createServer } = await import('vite');
  vite = await createServer({ configFile: path.join(process.cwd(), 'vite.config.ts'),
    server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent',
    plugins: [{ name: 'test-only-spell-surfaces', enforce: 'pre', transform(code, id) {
      if (id.replaceAll('\\', '/').endsWith('/src/pages/game-browser.tsx')) {
        return code + '\nexport { LeftColumn as TestLeftColumn, DrawerSheet as TestDrawerSheet, CharacterReveal as TestCharacterReveal };';
      }
    } }] });
  const { SpellcastingPanel } = await vite.ssrLoadModule('/src/components/spellcasting-panel.tsx');
  const { TestDrawerSheet, TestCharacterReveal } = await vite.ssrLoadModule('/src/pages/game-browser.tsx');
  const React = await import('react');
  const { renderToStaticMarkup } = await import('react-dom/server');
  render = (spellcasting) => renderToStaticMarkup(React.createElement(SpellcastingPanel, { spellcasting }));
  renderCharacterPanel = (state) => renderToStaticMarkup(React.createElement(TestDrawerSheet, {
    drawer: 'character', state, onClose() {}, returnFocus: null, activeTab: 'world', setActiveTab() {},
    combatEntries: [], sessionId: 'spell-surface', campaignId: 'spell-surface',
  }));
  renderReveal = (state) => renderToStaticMarkup(React.createElement(TestCharacterReveal, {
    state, onContinue() {}, onBack() {},
  }));
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
  assert.match(page, /drawer === 'character' \? <LeftColumn state=\{state\} \/>/);
  assert.match(page, /<SpellcastingPanel spellcasting=\{state\.spellcasting\} \/>/);
  assert.doesNotMatch(page, /spellcasting=\{\{|spell_slots_remaining|CLASS_DEFINITIONS|slots\s*\[.*\]\s*=/);
});

function surfaceState(spellcasting) {
  return {
    campaign_time: {
      year: 1492, month: 'Mirtul', day: 12, hour: 18, minute: 40, second: 0,
      day_index: 12, calendar: 'Harptos', local_convention: 'Faerûn',
      time_of_day: 'evening', display: '12 Mirtul 1492 DR', detail: 'Akşam',
    },
    character: {
      name: 'Yolcu', race: 'human', class: 'rogue',
      strength: 10, dexterity: 14, constitution: 12, intelligence: 11, wisdom: 13, charisma: 10,
      proficient_skills: ['Stealth'], expertise_skills: [], level: 1, proficiency_bonus: 2,
      max_hp: 12, current_hp: 12, armor_class: 13, cantrips: [], spells: [],
      spell_slots_remaining: {}, xp: 0,
    },
    spellcasting,
    inventory: ['Kısa kılıç'],
  };
}

function spellPanels(html) {
  return html.match(/data-testid="panel-spellcasting"/g) ?? [];
}

test('open character panel and reveal each show one supplied spell panel', () => {
  const spells = supplied();
  spells.slots = { '1': 2 };
  const state = surfaceState(spells);
  const before = JSON.stringify(state);
  const panel = renderCharacterPanel(state);
  const reveal = renderReveal(state);
  assert.equal(JSON.stringify(state), before);
  for (const html of [panel, reveal]) {
    assert.equal(spellPanels(html).length, 1);
    assert.equal((html.match(/aria-label="Büyüler ve büyü yuvaları"/g) ?? []).length, 1);
    assert.match(html, /Fire Bolt/);
    assert.match(html, /Magic Missile/);
    assert.match(html, /data-testid="spell-slots-1">2</);
    assert.match(html, /Raunt 3 · Sıra 2/);
    assert.doesNotMatch(html, /hidden-combat-id/);
    const section = html.slice(html.indexOf('data-testid="panel-spellcasting"'), html.indexOf('</section>', html.indexOf('data-testid="panel-spellcasting"')));
    assert.doesNotMatch(section, /<button|<input|<select/);
  }
  assert.match(panel, /aria-label="Karakter paneli"/);
  assert.match(reveal, /data-testid="screen-character-reveal"/);
  assert.equal(state.character.cantrips.length, 0);
  const emptyPanel = renderCharacterPanel(surfaceState(null));
  const emptyReveal = renderReveal(surfaceState(null));
  assert.equal(spellPanels(emptyPanel).length, 0);
  assert.equal(spellPanels(emptyReveal).length, 0);
  assert.match(emptyPanel, /aria-label="Karakter paneli"/);
});