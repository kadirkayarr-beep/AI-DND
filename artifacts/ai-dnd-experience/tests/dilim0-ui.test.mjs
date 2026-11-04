// Dilim 0 (UI tour): pure helpers and components rendered from the real modules.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { after, before, test } from 'node:test';

process.env.PORT ||= '4191';
process.env.BASE_PATH ||= '/';
delete process.env.REPL_ID;

let vite, React, render;
let coins, purse, notice, panel;            // Görev 4
let history, transcript, lastTurn, banner, resumeMode;  // Görev 5
let counter, questUi;                       // Görev 6
let panels;                                 // Görev 7
let economy, terms, rogueUi;                // Görev 8, 10
let strip;                                  // Görev 9
let display, inv, sorcerer;                 // Görev 11

before(async () => {
  const { createServer } = await import('vite');
  vite = await createServer({ configFile: path.join(process.cwd(), 'vite.config.ts'),
    server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' });
  coins = await vite.ssrLoadModule('/src/lib/coins.ts');
  purse = await vite.ssrLoadModule('/src/lib/starting-purse.ts');
  notice = await vite.ssrLoadModule('/src/components/starting-equipment-notice.tsx');
  panel = await vite.ssrLoadModule('/src/components/character-panel.tsx');
  React = await import('react');
  const { renderToStaticMarkup } = await import('react-dom/server');
  render = (type, props) => renderToStaticMarkup(React.createElement(type, props));
});
after(async () => { await vite?.close(); });

/** Visible text only: drops title="…" attributes so the English hover names are not counted. */
const stripTitles = (html) => html.replace(/\stitle="[^"]*"/g, '');
/** Same as makeState in tests/combat-panel.test.mjs:89-134. */
function makeState(overrides = {}) {
  const { combat: combatOverrides = {}, ...stateOverrides } = overrides;
  return {
    character: { name: 'Arven', current_hp: 12, max_hp: 14, armor_class: 15 },
    player_combat_status: 'active',
    death_state: { mode: 'CHECKPOINT_ROLLBACK', status: 'conscious', successes: 0, failures: 0, terminal: false, last_death_save: null },
    combat: { active: false, status: 'ended', round: 0, initiative_order: [], current_turn_index: 0, current_actor_id: null,
      turn_owner: null, participants: [], participant_records: [], target_id: null, end_reason: null, ...combatOverrides },
    npcs: [{ id: 'npc_bandit', name: 'Bandit', current_hp: 2, max_hp: 12, armor_class: 13, combat_status: 'active' },
      { id: 'npc_wolf', name: 'Wolf', current_hp: 8, max_hp: 8, armor_class: 12, combat_status: 'active' }],
    ...stateOverrides,
  };
}
/** A player turn with every resource ready (shape of tests/combat-panel.test.mjs:59-66). */
const playerTurnState = makeState({ combat: { active: true, status: 'active', round: 1, current_actor_id: 'player',
  action_economy: { actors: { player: {
    base_action_spent: false, additional_actions: [], bonus_action_spent: false, bonus_action_available: false,
    bonus_rules: [], reaction_available: true, movement_remaining: 30, speed_ft: 30, ready: null, opportunity: null,
    legal_actions: [{ kind: 'attack', legal: true }, { kind: 'dash', legal: true }, { kind: 'ready', legal: true }],
  } } } } });

const fighter = { name: 'Kadir', race: 'Human', class: 'Fighter', level: 1, current_hp: 12, max_hp: 12,
  armor_class: 16, proficiency_bonus: 2, xp: 0, strength: 17, dexterity: 13, constitution: 15,
  intelligence: 12, wisdom: 10, charisma: 8, proficient_skills: [], progression_effects_pending: [] };
const catalog = { classes: { Fighter: { equipment_packages: [{ id: 'C', coin_gp: 10, coin_items: ['10 Altın'] }] } },
  backgrounds: { Soldier: { coin_gp: 14, coin_items: ['14 Altın'] }, Artisan: { coin_gp: 32, coin_items: ['32 GP'] } },
  equipment_rules: { background_option_b_gp: 50 } };

test('coinText shows gold, silver and copper like the counter', () => {
  assert.equal(coins.coinText(6000), '60 altın 0 gümüş 0 bakır');
  assert.equal(coins.coinText(5741), '57 altın 4 gümüş 1 bakır');
  assert.equal(coins.coinText(-1), '—');
});
test('the starting purse adds the class package and the background', () => {
  assert.deepEqual(purse.startingPurse(catalog, 'Fighter', 'C', 'Soldier', 'B'), { classGp: 10, backgroundGp: 50, totalGp: 60 });
  assert.deepEqual(purse.startingPurse(catalog, 'Fighter', 'C', 'Soldier', 'A'), { classGp: 10, backgroundGp: 14, totalGp: 24 });
  assert.deepEqual(purse.startingPurse(catalog, 'Fighter', 'C', 'Artisan', 'A'), { classGp: 10, backgroundGp: 32, totalGp: 42 });
  assert.equal(purse.startingPurse({ classes: {} }, 'Fighter', 'C', 'Soldier', 'B'), null);
});
test('the notice says one sentence for every class', () => {
  const html = render(notice.StartingEquipmentNotice, { characterClass: 'Fighter', classes: catalog.classes,
    equipmentPackage: 'C', background: 'Soldier', backgroundOption: 'B', backgroundData: catalog.backgrounds.Soldier, catalog });
  assert.match(html, /Başlangıç kesesi: sınıf paketi 10 altın \+ geçmiş 50 altın = 60 altın\./);
  assert.doesNotMatch(html, /sunucu|cüzdan|servet|GP/);
  const optionA = render(notice.StartingEquipmentNotice, { characterClass: 'Fighter', classes: catalog.classes,
    equipmentPackage: 'C', background: 'Soldier', backgroundOption: 'A', backgroundData: catalog.backgrounds.Soldier, catalog });
  assert.match(optionA, /sınıf paketi 10 altın \+ geçmiş 14 altın = 24 altın\./);
  // A sourced background A (decision 40): its "32 GP" is the purse line, never a good.
  const sourcedA = render(notice.StartingEquipmentNotice, { characterClass: 'Fighter', classes: catalog.classes,
    equipmentPackage: 'C', background: 'Artisan', backgroundOption: 'A', backgroundData: catalog.backgrounds.Artisan, catalog });
  assert.match(sourcedA, /sınıf paketi 10 altın \+ geçmiş 32 altın = 42 altın\./);
  assert.doesNotMatch(sourcedA, /GP/);
  // The welcome call site knows neither package nor background: nothing is drawn, no amount is guessed.
  assert.equal(render(notice.StartingEquipmentNotice, { characterClass: 'Fighter', classes: catalog.classes, catalog }), '');
});
test('the character panel shows the purse from the wallet', () => {
  const html = render(panel.CharacterPanel, { character: fighter, walletTotalCp: 6000 });
  assert.match(html, /data-testid="text-character-purse"[^>]*>Kese: 60 altın 0 gümüş 0 bakır</);
  assert.doesNotMatch(render(panel.CharacterPanel, { character: fighter, walletTotalCp: null }), /text-character-purse/);
});
test('the package list shows goods only; coin is the purse line; an old catalog keeps its list', () => {
  const pack = { id: 'C', items: ['Ağır Tatar Yayı & 20 Ok', '10 Altın', 'Macera Çantası'], coin_items: ['10 Altın'] };
  assert.deepEqual(purse.packageGoods(pack), ['Ağır Tatar Yayı & 20 Ok', 'Macera Çantası']);
  assert.deepEqual(purse.packageGoods({ id: 'A', items: ['Zırh', '10 Altın'] }), ['Zırh', '10 Altın']);
  assert.deepEqual(purse.packageGoods({ id: 'B', items: ['75 GP'], coin_items: ['75 GP'] }), []);
  assert.deepEqual(purse.packageGoods(null), []);
});
