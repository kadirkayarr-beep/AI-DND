import assert from 'node:assert/strict';
import { before, after, test } from 'node:test';
import path from 'node:path';
import { changeStartingLevel, emptyStartingDraft } from '../src/lib/sorcerer-starting-creation.ts';

// Paladin 1-5 UI. Behavioural tests only: real functions, real components called as functions or rendered.
const STR2 = { feat: 'Ability Score Improvement', increase: { strength: 2 } };
const ABILITIES = ['strength', 'constitution', 'intelligence', 'wisdom', 'charisma'];
const ASI = [...ABILITIES.map(a => ({ feat: 'Ability Score Improvement', increase: { [a]: 2 } })),
  ...ABILITIES.flatMap((a, i) => ABILITIES.slice(i + 1).map(b => ({ feat: 'Ability Score Improvement', increase: { [a]: 1, [b]: 1 } })))];
const scope = { effects_supported: ['Lay On Hands supported'], effects_pending: ['catalog-only spells pending'] };
const prep = (...ids) => ({ prepared_spell_count: 1, prepared_spell_ids: ids });
const raw2 = () => ({ supported_starting_levels: [1, 2], level_2: { ...prep('Bless', 'Heroism', 'Divine Favor', 'Shield of Faith'), fighting_style_options: ['Defense', 'Dueling', 'Blessed Warrior'], blessed_warrior_cantrip_count: 2, blessed_warrior_cantrip_ids: ['Guidance', 'Sacred Flame', 'Light'], ...scope } });
const raw3 = () => ({ ...raw2(), supported_starting_levels: [1, 2, 3], level_3: { ...prep('Bless', 'Heroism', 'Divine Favor'), subclass_options: [{ id: 'oath_of_devotion', name: 'Oath of Devotion' }], ...scope } });
const raw4 = () => ({ ...raw3(), supported_starting_levels: [1, 2, 3, 4], level_4: { ...prep('Bless', 'Heroism', 'Divine Favor'), supported_asi_choices: structuredClone(ASI), ...scope } });
const raw5 = () => ({ ...raw4(), supported_starting_levels: [1, 2, 3, 4, 5], level_5: { ...prep('Bless', 'Heroism', 'Lesser Restoration'), ...scope } });
const draftN = (level, extra = {}) => ({ ...emptyStartingDraft(), startingLevel: level, paladinStyle: 'Defense', paladinCantrips: [], level2Prepared: ['Bless'],
  ...(level >= 3 ? { level3Prepared: ['Heroism'], subclassId: 'oath_of_devotion' } : {}), ...(level >= 4 ? { level4Prepared: ['Divine Favor'], level4Asi: structuredClone(STR2), level4ConConfirmed: true } : {}),
  ...(level >= 5 ? { level5Prepared: ['Lesser Restoration'] } : {}), ...extra });
const available = { available: true, reason: null };
const refused = reason => ({ available: false, reason });
const PALADIN = () => ({ fighting_style: 'Defense', lay_on_hands: { pool_remaining: 12, pool_maximum: 15, poison_cost: 5, activate: available },
  divine_smite: { activate: available, target_id: 'npc-1', free_cast_available: true, slot_levels: [1] }, channel_divinity: { uses_remaining: 1, max_uses: 2 },
  divine_sense: { active: true, remaining_seconds: 300, detected: [{ target_id: 'npc-1', creature_type: 'fiend', distance_ft: 30 }], activate: available },
  sacred_weapon: { active: false, weapon_id: null, remaining_seconds: null, attack_bonus: 3, start: available }, always_prepared: ['Divine Smite'],
  prepared_spells: [{ id: 'Cure Wounds', castable: true }, { id: 'Bless', castable: false }] });
const campaign_id = '11111111-1111-4111-8111-111111111111';
const preview = (target, counts, extra = {}) => ({ session_id: 'session', campaign_id, revision: 7, status: 'ready', reason: null, class_name: 'Paladin', from_level: target - 1, target_level: target, choices_required: counts, capacity: { prepared_spells: 3, slots: { 1: 2 } }, prepared_spell_ids: ['Bless', 'Heroism'], cantrip_ids: [], supported_asi_choices: [], metamagic_options: [], subclass_options: [], effects_supported: ['Supported'], effects_pending: ['Weapon Mastery pending'], ...extra });
const TWO = { prepared_spells: 1, fighting_style: 1, cantrips: 2 };

let helper, projection, ui, controls, levelUp, plain, vite, React, render;
before(async () => {
  helper = await import('../src/lib/paladin-starting-creation.ts');
  projection = await import('../src/lib/paladin-projection.ts');
  process.env.PORT ||= '4187'; process.env.BASE_PATH ||= '/';
  const { createServer } = await import('vite');
  vite = await createServer({ configFile: path.join(process.cwd(), 'vite.config.ts'), server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' });
  ui = await vite.ssrLoadModule('/src/components/paladin-starting-creation.tsx');
  controls = await vite.ssrLoadModule('/src/components/paladin-controls.tsx');
  levelUp = await vite.ssrLoadModule('/src/components/paladin-level-up.tsx');
  plain = await vite.ssrLoadModule('/src/components/level-up-controls.tsx');
  React = await import('react'); render = (await import('react-dom/server')).renderToStaticMarkup;
});
after(async () => await vite?.close());
const html = element => render(element);
function nodes(e) { return Array.isArray(e) ? e.flatMap(nodes) : e && typeof e === 'object' ? [e, ...nodes(e.props?.children)] : []; }
const byId = (tree, id) => tree.find(n => n.props?.['data-testid'] === id);

test('the catalog reader takes each verified level and a bad block hides it and everything above', () => {
  assert.deepEqual(helper.readPaladinStartingCreationOptions(raw5()).supported_starting_levels, [1, 2, 3, 4, 5]);
  assert.equal(helper.readPaladinStartingCreationOptions(null), undefined);
  assert.equal(helper.readPaladinStartingCreationOptions({ ...raw2(), level_2: {} }), undefined);
  const noCantrips = raw2(); noCantrips.level_2.blessed_warrior_cantrip_ids = ['Guidance'];
  assert.equal(helper.readPaladinStartingCreationOptions(noCantrips), undefined, 'Blessed Warrior needs two choices');
  const badThree = raw5(); badThree.level_3.subclass_options = [{ id: 'oath_of_glory', name: 'Oath of Glory' }];
  assert.deepEqual(helper.readPaladinStartingCreationOptions(badThree).supported_starting_levels, [1, 2]);
  const badFour = raw5(); delete badFour.level_4.prepared_spell_ids;
  assert.deepEqual(helper.readPaladinStartingCreationOptions(badFour).supported_starting_levels, [1, 2, 3]);
  const badFive = raw5(); badFive.level_5.extra = 1;
  assert.deepEqual(helper.readPaladinStartingCreationOptions(badFive).supported_starting_levels, [1, 2, 3, 4]);
});

test('the creation bundle is exact for every start and nothing is picked for the player', () => {
  const initial = ['Cure Wounds', 'Command'];
  assert.deepEqual(helper.paladinStartingCreationFields({ ...emptyStartingDraft() }, raw5(), initial), { ok: true, fields: {} });
  const two = helper.paladinStartingCreationFields(draftN(2), raw5(), initial);
  assert.deepEqual(two.fields, { starting_level: 2, level_choices: { 2: { prepared_spells: ['Bless'], fighting_style: 'Defense' } } });
  const five = helper.paladinStartingCreationFields(draftN(5), raw5(), initial);
  assert.deepEqual(Object.keys(five.fields.level_choices), ['2', '3', '4', '5']);
  assert.deepEqual(five.fields.level_choices['3'], { prepared_spells: ['Heroism'], subclass_id: 'oath_of_devotion' });
  assert.deepEqual(five.fields.level_choices['4'], { prepared_spells: ['Divine Favor'], asi: STR2 });
  assert.deepEqual(five.fields.level_choices['5'], { prepared_spells: ['Lesser Restoration'] });
  const blessed = helper.paladinStartingCreationFields(draftN(2, { paladinStyle: 'Blessed Warrior', paladinCantrips: ['Guidance', 'Sacred Flame'] }), raw5(), initial);
  assert.deepEqual(blessed.fields.level_choices['2'].cantrips, ['Guidance', 'Sacred Flame']);
});

test('the creation bundle refuses every incomplete or repeated pick', () => {
  const initial = ['Cure Wounds', 'Command'];
  const bad = [draftN(2, { paladinStyle: '' }), draftN(2, { paladinStyle: 'Protection' }), draftN(2, { level2Prepared: [] }), draftN(2, { level2Prepared: ['Aid'] }),
    draftN(2, { level2Prepared: ['Cure Wounds'] }), draftN(3, { level3Prepared: ['Bless'] }), draftN(3, { subclassId: '' }), draftN(4, { level4ConConfirmed: false }),
    draftN(4, { level4Asi: undefined }), draftN(5, { level5Prepared: [] }), draftN(2, { paladinStyle: 'Blessed Warrior', paladinCantrips: ['Guidance'] }),
    draftN(2, { paladinStyle: 'Blessed Warrior', paladinCantrips: ['Guidance', 'Guidance'] }), draftN(2, { paladinStyle: 'Blessed Warrior', paladinCantrips: ['Guidance', 'Fire Bolt'] }),
    draftN(2, { metamagic: ['Quickened Spell'] }), draftN(3, { primalSkill: 'Nature' })];
  for (const draft of bad) assert.equal(helper.paladinStartingCreationFields(draft, raw5(), initial).ok, false, JSON.stringify(draft));
  assert.equal(helper.paladinStartingCreationFields(draftN(5), raw3(), initial).ok, false, 'a level the catalog does not list');
  assert.equal(helper.paladinStartingCreationFields(draftN(2), undefined, initial).ok, false, 'a missing catalog blocks');
});

test('pruning clears only what the known catalog no longer allows and keeps picks during a catalog gap', () => {
  const stale = draftN(3, { level2Prepared: ['Gone'], paladinStyle: 'Gone', paladinCantrips: ['Gone', 'Guidance'] });
  const pruned = helper.prunePaladinDraft(stale, raw5());
  assert.deepEqual(pruned.level2Prepared, []);
  assert.equal(pruned.paladinStyle, '');
  assert.deepEqual(pruned.paladinCantrips, ['Guidance']);
  assert.equal(helper.prunePaladinDraft(stale, undefined), stale);
  const clean = draftN(2);
  assert.deepEqual(helper.prunePaladinDraft(clean, raw5()).paladinStyle, 'Defense');
});

test('changing the starting level keeps the Fighting Style picks until level 1 clears everything', () => {
  const draft = draftN(2, { paladinStyle: 'Blessed Warrior', paladinCantrips: ['Guidance', 'Sacred Flame'] });
  const higher = changeStartingLevel(draft, 4);
  assert.equal(higher.paladinStyle, 'Blessed Warrior');
  assert.deepEqual(higher.paladinCantrips, ['Guidance', 'Sacred Flame']);
  assert.equal(changeStartingLevel(draft, 1).paladinStyle, undefined);
});

test('changing the spell clears a confirmation given for the earlier pick', () => {
  const changes = [];
  const props = { preview: preview(5, { prepared_spells: 1 }), draft: { preparedSpell: 'Bless', confirmed: true }, onChange: value => changes.push(value), onConfirm() {}, onCancel() {} };
  byId(nodes(levelUp.PaladinLevelChoices(props)), 'level-up-prepared').props.onChange({ target: { value: 'Heroism' } });
  assert.deepEqual(changes[0], { preparedSpell: 'Heroism', confirmed: false });
});

test('the projection reader refuses a malformed block', () => {
  assert.ok(projection.readPaladinProjection(PALADIN()));
  assert.equal(projection.readPaladinProjection(null), null);
  for (const fault of [p => { p.lay_on_hands.pool_remaining = 99; }, p => { p.lay_on_hands.poison_cost = 1; }, p => { delete p.lay_on_hands; }, p => { p.divine_smite.slot_levels = ['1']; },
    p => { p.channel_divinity.uses_remaining = 3; }, p => { p.sacred_weapon.attack_bonus = 0; }, p => { p.prepared_spells = [{ id: 'Bless' }]; }, p => { p.divine_sense.detected = 'x'; }]) {
    const value = PALADIN(); fault(value);
    assert.equal(projection.readPaladinProjection(value), null);
  }
  assert.ok(projection.readPaladinProjection({ ...PALADIN(), divine_smite: null, channel_divinity: null, divine_sense: null, sacred_weapon: null }), 'level 1 has null blocks');
});

test('the Lay On Hands step stays inside the pool and picks nothing by itself', () => {
  const value = PALADIN();
  assert.deepEqual(projection.layOnHandsStep(value, '7', false), { kind: 'lay_on_hands', resource: 'bonus', healing_amount: 7 });
  assert.deepEqual(projection.layOnHandsStep(value, '', true), { kind: 'lay_on_hands', resource: 'bonus', remove_poisoned: true });
  assert.deepEqual(projection.layOnHandsStep(value, '7', true), { kind: 'lay_on_hands', resource: 'bonus', healing_amount: 7, remove_poisoned: true });
  for (const [amount, poison] of [['', false], ['0', false], ['1.5', false], ['13', false], ['8', true], ['x', false]]) assert.equal(projection.layOnHandsStep(value, amount, poison), null);
});

test('the Divine Smite step sends a server-listed slot or the free cast', () => {
  const value = PALADIN();
  assert.deepEqual(projection.divineSmiteStep(value, ''), { kind: 'divine_smite', resource: 'bonus' });
  assert.deepEqual(projection.divineSmiteStep(value, '1'), { kind: 'divine_smite', resource: 'bonus', slot_level: 1 });
  assert.equal(projection.divineSmiteStep(value, '2'), null);
  assert.equal(projection.divineSmiteStep({ ...value, divine_smite: { ...value.divine_smite, free_cast_available: false } }, ''), null);
  assert.equal(projection.divineSmiteStep({ ...value, divine_smite: null }, '1'), null);
});

test('Sacred Weapon fields follow the server block', () => {
  const value = PALADIN();
  assert.deepEqual(projection.sacredWeaponFields(value, true, true), { sacred_weapon: true, radiant_damage: true });
  assert.deepEqual(projection.sacredWeaponFields(value, false, true), {});
  assert.deepEqual(projection.sacredWeaponFields(null, true, true), {});
  const unavailable = { ...value, sacred_weapon: { ...value.sacred_weapon, start: refused('channel_divinity_uses_exhausted') } };
  assert.deepEqual(projection.sacredWeaponFields(unavailable, true, false), {});
  const active = { ...value, sacred_weapon: { ...value.sacred_weapon, active: true } };
  assert.deepEqual(projection.sacredWeaponFields(active, true, true), { radiant_damage: true }, 'an active effect is never restarted by accident');
});

test('the status names what is catalog-only and what is detected', () => {
  const text = html(React.createElement(controls.PaladinStatus, { paladin: PALADIN() }));
  assert.match(text.replace(/<[^>]+>/g, ''), /Şifa Eli: 12\/15/); assert.match(text, /title="Lay on Hands"/);
  assert.match(text, /Channel Divinity: 1\/2/);
  assert.match(text, /fiend 30 ft/);
  assert.match(text, /Her zaman hazır: Divine Smite/);
  assert.match(text, /etkisi yok: Bless/);
  assert.equal(html(React.createElement(controls.PaladinStatus, { paladin: { bad: true } })), '');
});

test('the combat controls send only an available command and show the server reason', () => {
  const commands = [];
  const text = html(React.createElement(controls.PaladinControl, { paladin: PALADIN(), blocked: false, onCommand: (label, step) => commands.push(step) }));
  assert.match(text, /button-divine-smite/);
  assert.match(text, /button-divine-sense/);
  const blocked = { ...PALADIN(), divine_smite: { ...PALADIN().divine_smite, activate: refused('divine_smite_requires_a_melee_hit') } };
  assert.match(html(React.createElement(controls.PaladinControl, { paladin: blocked, blocked: false, onCommand() {} })), /divine_smite_requires_a_melee_hit/);
  const level1 = { ...PALADIN(), divine_smite: null, channel_divinity: null, divine_sense: null, sacred_weapon: null };
  const low = html(React.createElement(controls.PaladinControl, { paladin: level1, blocked: false, onCommand() {} }));
  assert.doesNotMatch(low, /button-divine-smite|button-divine-sense/);
  assert.equal(html(React.createElement(controls.PaladinControl, { paladin: null, blocked: false, onCommand() {} })), '');
});

test('the Sacred Weapon choice appears only with the server block', () => {
  const props = { wanted: false, radiant: false, disabled: false, onChange() {} };
  assert.match(html(React.createElement(controls.SacredWeaponChoice, { ...props, paladin: PALADIN() })), /paladin-sacred-weapon-start/);
  assert.equal(html(React.createElement(controls.SacredWeaponChoice, { ...props, paladin: { ...PALADIN(), sacred_weapon: null } })), '');
  const active = { ...PALADIN(), sacred_weapon: { ...PALADIN().sacred_weapon, active: true, weapon_id: 'longsword' } };
  const text = html(React.createElement(controls.SacredWeaponChoice, { ...props, paladin: active }));
  assert.match(text, /paladin-radiant-damage/);
  assert.doesNotMatch(text, /paladin-sacred-weapon-start/);
});

test('the level-up request is exact per step and only a confirmed server choice makes one', () => {
  const two = preview(2, TWO, { fighting_style_options: ['Defense', 'Blessed Warrior'], cantrip_ids: ['Guidance', 'Sacred Flame'] });
  const base = { preparedSpell: 'Bless', confirmed: true };
  assert.deepEqual(levelUp.paladinLevelUpRequest(two, { ...base, fightingStyle: 'Defense' }).choices, { prepared_spells: ['Bless'], fighting_style: 'Defense' });
  assert.deepEqual(levelUp.paladinLevelUpRequest(two, { ...base, fightingStyle: 'Blessed Warrior', blessedCantrips: ['Guidance', 'Sacred Flame'] }).choices.cantrips, ['Guidance', 'Sacred Flame']);
  for (const draft of [{ ...base }, { ...base, fightingStyle: 'Protection' }, { ...base, fightingStyle: 'Blessed Warrior', blessedCantrips: ['Guidance'] }, { ...base, fightingStyle: 'Defense', confirmed: false }, { ...base, preparedSpell: 'Aid', fightingStyle: 'Defense' }])
    assert.equal(levelUp.paladinLevelUpRequest(two, draft), null);
  const three = preview(3, { prepared_spells: 1, subclass_id: 1 }, { subclass_options: [{ id: 'oath_of_devotion', name: 'Oath of Devotion' }] });
  assert.deepEqual(levelUp.paladinLevelUpRequest(three, { ...base, subclassId: 'oath_of_devotion' }).choices, { prepared_spells: ['Bless'], subclass_id: 'oath_of_devotion' });
  assert.equal(levelUp.paladinLevelUpRequest(three, base), null);
  const four = preview(4, { prepared_spells: 1, asi: 1 }, { supported_asi_choices: structuredClone(ASI) });
  assert.deepEqual(levelUp.paladinLevelUpRequest(four, { ...base, asi: STR2 }).choices, { prepared_spells: ['Bless'], asi: STR2 });
  const five = preview(5, { prepared_spells: 1 });
  assert.deepEqual(levelUp.paladinLevelUpRequest(five, base).choices, { prepared_spells: ['Bless'] });
  assert.equal(levelUp.paladinLevelUpRequest(preview(5, { prepared_spells: 2 }), base), null, 'an unexpected count is not sent');
  assert.equal(levelUp.paladinLevelUpRequest({ ...five, campaign_id: null }, base), null);
});

test('the shared level-up surface hands a Paladin preview to its own component', () => {
  const props = { draft: { cantrip: '', preparedSpell: '', confirmed: false }, onChange() {}, onConfirm() {}, onCancel() {} };
  const text = html(React.createElement(plain.LevelUpChoices, { ...props, preview: preview(2, TWO, { fighting_style_options: ['Defense'] }) }));
  assert.match(text, /level-up-style/);
  assert.match(text,/Bu seviyedeki 1 özellik henüz oyunda tam işlemiyor\./);assert.doesNotMatch(text,/Weapon Mastery pending/);
  assert.match(html(React.createElement(plain.LevelUpChoices, { ...props, preview: preview(2, { prepared_spells: 9 }) })), /henüz desteklenmiyor/);
});

test('start controls offer only catalog levels and the choices show exactly the needed picks', () => {
  const level = html(React.createElement(ui.PaladinStartingLevelControl, { draft: draftN(1), metadata: helper.readPaladinStartingCreationOptions(raw3()), onChange() {}, onRetry() {} }));
  assert.match(level, /<option value="3">/);
  assert.doesNotMatch(level, /<option value="4">/);
  const missing = html(React.createElement(ui.PaladinStartingLevelControl, { draft: draftN(3), onChange() {}, onRetry() {} }));
  assert.match(missing, /doğrulanamıyor/);
  const metadata = helper.readPaladinStartingCreationOptions(raw5());
  const two = html(React.createElement(ui.PaladinStartingChoices, { draft: draftN(2), metadata, onChange() {} }));
  assert.match(two, /paladin-style-choice/);
  assert.doesNotMatch(two, /paladin-subclass|paladin-cantrip-1|paladin-asi-confirm/);
  const blessed = html(React.createElement(ui.PaladinStartingChoices, { draft: draftN(5, { paladinStyle: 'Blessed Warrior' }), metadata, onChange() {} }));
  assert.match(blessed, /paladin-cantrip-2/);
  assert.match(blessed, /paladin-subclass/);
  assert.match(blessed, /paladin-prepared-5/);
  const changes = [];
  const tree = nodes(ui.PaladinStartingChoices({ draft: draftN(2), metadata, onChange: value => changes.push(value) }));
  byId(tree, 'paladin-style-choice').props.onChange({ target: { value: 'Blessed Warrior' } });
  assert.equal(changes[0].paladinStyle, 'Blessed Warrior');
  assert.deepEqual(changes[0].paladinCantrips, []);
  const summary = html(React.createElement(ui.PaladinStartingSummary, { draft: draftN(4), metadata }));
  assert.match(summary, /Oath of Devotion/);
  assert.match(summary,/Bu seviyedeki 1 özellik henüz oyunda tam işlemiyor\./);assert.doesNotMatch(summary,/catalog-only/);
});
