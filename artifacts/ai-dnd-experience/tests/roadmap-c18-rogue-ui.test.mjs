const visibleText = e => Array.isArray(e) ? e.map(visibleText).join('') : e && typeof e === 'object' ? visibleText(e.props?.children) : e == null ? '' : String(e);
import * as terms from '../src/lib/tr-terms.ts';
import assert from 'node:assert/strict';
import { before, after, test } from 'node:test';
import path from 'node:path';
import { emptyStartingDraft } from '../src/lib/sorcerer-starting-creation.ts';
import { sacredWeaponFields } from '../src/lib/paladin-projection.ts';

// Rogue 1-5 UI. Behavioural tests only: real functions and real components called as functions.
const ABILITIES = ['strength', 'constitution', 'intelligence', 'wisdom', 'charisma'];
const ASI = [...ABILITIES.map(a => ({ feat: 'Ability Score Improvement', increase: { [a]: 2 } })),
  ...ABILITIES.flatMap((a, i) => ABILITIES.slice(i + 1).map(b => ({ feat: 'Ability Score Improvement', increase: { [a]: 1, [b]: 1 } })))];
const INT2 = { feat: 'Ability Score Improvement', increase: { intelligence: 2 } };
const raw2 = () => ({ supported_starting_levels: [1, 2], level_2: { choices: {}, effects_supported: ['Cunning Action supported'], effects_pending: ['Weapon Mastery pending'] } });
const raw3 = () => ({ ...raw2(), supported_starting_levels: [1, 2, 3], level_3: { subclass_options: [{ id: 'assassin', name: 'Assassin' }], effects_supported: ['Assassin supported'], effects_pending: ['Hide pending'] } });
const raw4 = () => ({ ...raw3(), supported_starting_levels: [1, 2, 3, 4], level_4: { supported_asi_choices: structuredClone(ASI), effects_supported: ['ASI supported'], effects_pending: ['Higher-start equipment pending'] } });
const raw5 = () => ({ ...raw4(), supported_starting_levels: [1, 2, 3, 4, 5], level_5: { effects_supported: ['Cunning Strike supported'], effects_pending: ['Higher-start equipment pending'] } });
const draftN = (level, extra = {}) => ({ ...emptyStartingDraft(), startingLevel: level, subclassId: level >= 3 ? 'assassin' : '', ...(level >= 4 ? { level4Asi: structuredClone(INT2), level4ConConfirmed: true } : {}), ...extra });
const open = { available: true, reason: null };
const ROGUE = () => ({ subclass: 'assassin', sneak_attack: { dice: 3, die: 6, used_this_turn: false },
  cunning_action: { dash: { ...open }, disengage: { ...open } }, steady_aim: { ...open, active: false },
  cunning_strike: { dc: 14, withdraw_max_ft: 15, trip_refused_targets: [], options: [{ id: 'poison', cost: 1, ...open }, { id: 'trip', cost: 1, ...open }, { id: 'withdraw', cost: 1, ...open }] },
  uncanny_dodge: { enabled: true, reaction_available: true } });

const campaign_id = '11111111-1111-4111-8111-111111111111';
const preview = (target, counts, extra = {}) => ({ session_id: 'session', campaign_id, revision: 7, status: 'ready', reason: null, class_name: 'Rogue', from_level: target - 1, target_level: target, choices_required: counts, capacity: null, prepared_spell_ids: [], cantrip_ids: [], supported_asi_choices: [], metamagic_options: [], subclass_options: [], effects_supported: ['Supported'], effects_pending: ['Pending'], ...extra });
const action_id = '22222222-2222-4222-8222-222222222222';

let helper, ui, controls, levelUp, panel, vite;
before(async () => {
  helper = await import('../src/lib/rogue-starting-creation.ts');
  process.env.PORT ||= '4187'; process.env.BASE_PATH ||= '/';
  const { createServer } = await import('vite');
  vite = await createServer({ configFile: path.join(process.cwd(), 'vite.config.ts'), server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' });
  ui = await vite.ssrLoadModule('/src/components/rogue-starting-creation.tsx');
  controls = await vite.ssrLoadModule('/src/components/rogue-controls.tsx');
  levelUp = await vite.ssrLoadModule('/src/components/level-up-controls.tsx');
  panel = await vite.ssrLoadModule('/src/components/action-economy-panel.tsx');
});
after(async () => { await vite?.close(); });

const nodes = element => {
  const found = [];
  const walk = value => {
    if (Array.isArray(value)) return value.forEach(walk);
    if (!value || typeof value !== 'object') return;
    found.push(value);
    if (typeof value.type === 'function') return walk(value.type(value.props));
    walk(value.props?.children);
  };
  walk(element);
  return found;
};
const byId = (tree, id) => tree.find(node => node.props?.['data-testid'] === id);

test('reader keeps the verified prefix and hides a bad block and everything above it', () => {
  assert.deepEqual(helper.readRogueStartingCreationOptions(raw5()).supported_starting_levels, [1, 2, 3, 4, 5]);
  const badThree = raw5(); badThree.level_3.subclass_options = [{ id: 'thief', name: 'Thief' }];
  assert.deepEqual(helper.readRogueStartingCreationOptions(badThree).supported_starting_levels, [1, 2]);
  const badFour = raw5(); delete badFour.level_4.effects_pending;
  assert.deepEqual(helper.readRogueStartingCreationOptions(badFour).supported_starting_levels, [1, 2, 3]);
  assert.equal(helper.readRogueStartingCreationOptions({ supported_starting_levels: [1] }), undefined);
});

test('fields send the exact bundle for each level and refuse anything unconfirmed or inherited', () => {
  const source = helper.readRogueStartingCreationOptions(raw5());
  assert.deepEqual(helper.rogueStartingCreationFields(draftN(1), source), { ok: true, fields: {} });
  assert.deepEqual(helper.rogueStartingCreationFields(draftN(2), source).fields, { starting_level: 2, level_choices: { '2': {} } });
  assert.deepEqual(helper.rogueStartingCreationFields(draftN(5), source).fields,
    { starting_level: 5, level_choices: { '2': {}, '3': { subclass_id: 'assassin' }, '4': { asi: INT2 }, '5': {} } });
  assert.equal(helper.rogueStartingCreationFields(draftN(3, { subclassId: '' }), source).ok, false);
  assert.equal(helper.rogueStartingCreationFields(draftN(4, { level4ConConfirmed: false }), source).ok, false);
  assert.equal(helper.rogueStartingCreationFields(draftN(2, { primalSkill: 'Stealth' }), source).ok, false);
  assert.equal(helper.rogueStartingCreationFields(draftN(3), undefined).ok, false);
});

test('generated validator keeps the exact creation bundle under the Rogue class and refuses a bad one', async () => {
  const { CreateCampaignBody, PlayGameTurnBody } = await import('../../../lib/api-zod/src/generated/api.ts');
  const source = helper.readRogueStartingCreationOptions(raw5());
  for (const level of [2, 3, 4, 5]) {
    const { fields } = helper.rogueStartingCreationFields(draftN(level), source);
    const character = { mode: 'custom', class: 'Rogue', ...fields };
    const parsed = CreateCampaignBody.parse({ character }).character;
    assert.equal(parsed.starting_level, level);
    assert.deepEqual(parsed.level_choices, fields.level_choices);
  }
  const { fields } = helper.rogueStartingCreationFields(draftN(5), source);
  const forged = { ...fields, level_choices: { ...fields.level_choices, '3': { subclass_id: 'thief' } } };
  assert.equal(CreateCampaignBody.safeParse({ character: { mode: 'custom', class: 'Rogue', ...forged } }).success, false);
  assert.ok(PlayGameTurnBody.parse({ message: 'x', combat_action: { steps: [{ kind: 'attack', target_id: 'a', cunning_strike: 'trip' }] } }));
});

function levelHarness(p) {
  let draft = { cantrip: '', preparedSpell: '', confirmed: false }, sent;
  const props = () => ({ preview: p, draft, onChange: d => draft = d, onConfirm: r => sent = r, onCancel: () => {} });
  const tree = () => nodes(levelUp.LevelUpChoices(props()));
  return { tree, get sent() { return sent; }, change: (id, value) => { const c = byId(tree(), id); assert.ok(c, id); c.props.onChange({ target: { value, checked: value } }); } };
}
const confirmButton = h => byId(h.tree(), 'button-confirm-level-up');

test('level-up: Rogue empty steps 2 and 5 need explicit confirmation and pass the generated validator', async () => {
  const { ApplyGameSessionLevelUpBody } = await import('../../../lib/api-zod/src/generated/api.ts');
  for (const target of [2, 5]) {
    const h = levelHarness(preview(target, {}));
    assert.equal(confirmButton(h).props.disabled, true);
    h.change('level-up-confirm-empty', true);
    confirmButton(h).props.onClick();
    assert.deepEqual(h.sent, { campaign_id, expected_revision: 7, target_level: target, choices: {} });
    assert.deepEqual(ApplyGameSessionLevelUpBody.parse({ ...h.sent, action_id }).choices, {});
  }
});

test('level-up: Rogue 3 sends the offered Assassin only after confirmation; an id outside the contract cannot be sent', async () => {
  const assassin = preview(3, { subclass_id: 1 }, { subclass_options: [{ id: 'assassin', name: 'Assassin' }] });
  const h = levelHarness(assassin);
  assert.equal(confirmButton(h).props.disabled, true);
  h.change('level-up-subclass', 'assassin');
  assert.equal(confirmButton(h).props.disabled, true, 'a pick still needs the confirmation');
  h.change('level-up-confirm-subclass', true);
  confirmButton(h).props.onClick();
  assert.deepEqual(h.sent, { campaign_id, expected_revision: 7, target_level: 3, choices: { subclass_id: 'assassin' } });
  const { ApplyGameSessionLevelUpBody } = await import('../../../lib/api-zod/src/generated/api.ts');
  assert.deepEqual(ApplyGameSessionLevelUpBody.parse({ ...h.sent, action_id }).choices, { subclass_id: 'assassin' });
  const unknown = levelHarness(preview(3, { subclass_id: 1 }, { subclass_options: [{ id: 'thief', name: 'Thief' }] }));
  unknown.change('level-up-subclass', 'thief');
  unknown.change('level-up-confirm-subclass', true);
  assert.equal(confirmButton(unknown).props.disabled, true);
  confirmButton(unknown).props.onClick();
  assert.equal(unknown.sent, undefined);
  const notOffered = levelHarness(assassin);
  notOffered.change('level-up-subclass', 'champion');
  notOffered.change('level-up-confirm-subclass', true);
  assert.equal(confirmButton(notOffered).props.disabled, true, 'a contract id the server did not offer stays unsent');
});

test('level-up: Rogue 4 sends only the server ASI, and other shapes show no confirm button', () => {
  const h = levelHarness(preview(4, { asi: 1 }, { supported_asi_choices: structuredClone(ASI) }));
  assert.equal(confirmButton(h).props.disabled, true);
  h.tree().find(n => n.props?.testId === 'level-up-asi-choice').props.onChange(structuredClone(INT2));
  assert.equal(confirmButton(h).props.disabled, true, 'a pick still needs the confirmation');
  h.change('level-up-confirm-con', true);
  confirmButton(h).props.onClick();
  assert.deepEqual(h.sent.choices, { asi: INT2 });
  for (const p of [preview(3, { subclass_id: 1, primal_knowledge_skill: 1 }), preview(4, { asi: 1, cantrips: 1 }), preview(5, { asi: 1 }), preview(3, {})])
    assert.equal(confirmButton(levelHarness(p)), undefined, JSON.stringify(p.choices_required));
});

// The real ActionEconomyPanel source, extracted by AST and run with a small hook stand-in, as reckless-attack-ui does; the Rogue parts are real.
const panelState = (rogue, resources = {}) => ({ character: { rogue }, spellcasting: null, combat: { active: true, combat_id: 'c', round: 2, current_turn_index: 0, current_actor_id: 'player', participant_records: [],
  action_economy: { actors: { player: { base_action_spent: false, additional_actions: [], bonus_action_available: true, bonus_action_spent: false, bonus_rules: [], reaction_available: true, movement_remaining: 30, speed_ft: 30, ready: null, opportunity: null, attack_action: { remaining_attacks: 1 }, legal_actions: [{ kind: 'attack', legal: true, reason: null }], reckless_attack: null, ...resources } } } } });

async function panelHarness(state) {
  const ts = await import('typescript'), vm = await import('node:vm'), { readFile } = await import('node:fs/promises');
  const source = await readFile(new URL('../src/components/action-economy-panel.tsx', import.meta.url), 'utf8');
  const ast = ts.createSourceFile('panel.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const pick = name => ast.statements.find(n => ts.isFunctionDeclaration(n) && n.name?.text === name).getText(ast).replace(/^export /, '');
  const code = ts.transpileModule([...['createQuickenedIntent', 'quickenedProjection', 'ActionEconomyPanel'].map(pick), 'globalThis.Panel = ActionEconomyPanel;'].join('\n'),
    { compilerOptions: { jsx: ts.JsxEmit.React, target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText;
  const slots = []; let cursor = 0; const sent = [];
  const env = { FighterControl: 'FighterControl', MonkControl: 'MonkControl', RogueControl: 'RogueControl', CunningStrikeControl: 'CunningStrikeControl', RageControl: 'RageControl', MagicMissileControl: 'MagicMissileControl',
    PaladinControl: 'PaladinControl', SacredWeaponChoice: 'SacredWeaponChoice', readPaladinProjection: value => value ?? null, sacredWeaponFields,
    readRogueProjection: controls.readRogueProjection, cunningStrikeFields: controls.cunningStrikeFields, readRageProjection: panel.readRageProjection, createRecklessIntent: panel.createRecklessIntent, RecklessAttackControl: panel.RecklessAttackControl,
    React: { createElement: (type, props, ...children) => ({ type, props: { ...props, children } }) },
    useRef(value) { const index = cursor++; return slots[index] ??= { current: value }; },
    useState(value) { const index = cursor++; if (!(index in slots)) slots[index] = value; return [slots[index], next => { slots[index] = typeof next === 'function' ? next(slots[index]) : next; }]; } };
  Object.assign(env, terms); vm.runInNewContext(code, env);
  const props = { state, targetId: 'npc', sending: false, onCommand: (_, command) => sent.push(JSON.parse(JSON.stringify(command))) };
  const flat = e => Array.isArray(e) ? e.flatMap(flat) : e && typeof e === 'object' ? [e, ...flat(e.props?.children)] : [];
  const render = () => { cursor = 0; return flat(env.Panel(props)); };
  const button = label => render().find(n => n.type === 'button' && visibleText(n.props.children) === label);
  const strike = () => render().find(n => n.type === 'CunningStrikeControl').props;
  const settle = () => { props.sending = true; render(); props.sending = false; render(); };  // one send finishing, as the owner reports it
  return { props, sent, render, button, strike, settle };
}
const ATTACK = 'Saldır · Eylem', CONTINUE = 'Saldırı eylemine devam';

test('panel: the picked strike travels on the attack and the pick is cleared once it is sent', async () => {
  const h = await panelHarness(panelState(ROGUE()));
  h.strike().onOptionChange('trip');
  h.button(ATTACK).props.onClick();
  assert.deepEqual(h.sent, [{ steps: [{ kind: 'attack', target_id: 'npc', cunning_strike: 'trip' }] }]);
  assert.equal(h.strike().option, '');
  h.settle();
  h.strike().onOptionChange('withdraw');
  h.strike().onDistanceChange('15');
  h.button(CONTINUE).props.onClick();
  assert.deepEqual(h.sent[1], { steps: [{ kind: 'continue_attack', target_id: 'npc', cunning_strike: 'withdraw', cunning_strike_move_ft: 15 }] });
  assert.equal(h.strike().option, '');
  assert.equal(h.strike().distance, '');
});

test('panel: after the class merge a Paladin choice still travels on both attack buttons, and is cleared once sent', async () => {
  const state = panelState(undefined);
  state.character.paladin = { sacred_weapon: { active: false, start: { available: true } } };
  const h = await panelHarness(state);
  const choice = () => h.render().find(n => n.type === 'SacredWeaponChoice').props;
  choice().onChange({ wanted: true, radiant: true });
  h.button(ATTACK).props.onClick();
  assert.deepEqual(h.sent, [{ steps: [{ kind: 'attack', target_id: 'npc', sacred_weapon: true, radiant_damage: true }] }]);
  assert.equal(choice().wanted, false);
  h.settle();
  choice().onChange({ wanted: true, radiant: false });
  h.button(CONTINUE).props.onClick();
  assert.deepEqual(h.sent[1], { steps: [{ kind: 'continue_attack', target_id: 'npc', sacred_weapon: true }] });
});

test('panel: a move or other step keeps the pick; an attack with no pick sends no strike field', async () => {
  const h = await panelHarness(panelState(ROGUE()));
  h.button(ATTACK).props.onClick();
  assert.deepEqual(h.sent, [{ steps: [{ kind: 'attack', target_id: 'npc' }] }]);
  h.settle();
  h.strike().onOptionChange('trip');
  h.button('Turu bitir').props.onClick();
  assert.equal(h.strike().option, 'trip');
});

test('panel: both attack buttons are disabled while the pick cannot be sent, and enabled again once it can', async () => {
  const h = await panelHarness(panelState(ROGUE()));
  assert.equal(h.button(ATTACK).props.disabled, false);
  h.strike().onOptionChange('withdraw');
  assert.equal(h.button(ATTACK).props.disabled, true, 'Withdraw has no distance yet');
  assert.equal(h.button(CONTINUE).props.disabled, true);
  h.strike().onDistanceChange('20');
  assert.equal(h.button(ATTACK).props.disabled, true, 'beyond half Speed');
  h.strike().onDistanceChange('15');
  assert.equal(h.button(ATTACK).props.disabled, false);
  const used = ROGUE(); used.sneak_attack.used_this_turn = true;
  h.props.state = panelState(used);
  assert.equal(h.button(ATTACK).props.disabled, true, 'Sneak Attack already dealt');
});

test('panel: Trip on a target the server refuses disables the attack; another target or no pick is fine', async () => {
  const large = ROGUE(); large.cunning_strike.trip_refused_targets = ['npc'];
  const h = await panelHarness(panelState(large));
  assert.equal(h.button(ATTACK).props.disabled, false);
  h.strike().onOptionChange('trip');
  assert.equal(h.button(ATTACK).props.disabled, true);
  h.strike().onOptionChange('poison');
  assert.equal(h.button(ATTACK).props.disabled, false, 'only Trip reads the target');
  h.strike().onOptionChange('trip');
  h.props.targetId = 'other';
  assert.equal(h.button(ATTACK).props.disabled, false);
});

test('the picker marks Trip as refused for the selected target and says why', () => {
  const large = ROGUE(); large.cunning_strike.trip_refused_targets = ['npc'];
  const render = (targetId, option) => nodes(controls.CunningStrikeControl({ rogue: large, targetId, option, distance: '', disabled: false, onOptionChange: () => {}, onDistanceChange: () => {} }));
  const trip = tree => tree.find(n => n.type === 'option' && n.props.value === 'trip');
  assert.equal(trip(render('npc', '')).props.disabled, true);
  assert.equal(trip(render('other', '')).props.disabled, false);
  assert.ok(byId(render('npc', 'trip'), 'cunning-strike-refused'));
  assert.equal(byId(render('other', 'trip'), 'cunning-strike-refused'), undefined);
});

test('starting components show the live levels and never default a choice', () => {
  const tree = nodes(ui.RogueStartingLevelControl({ draft: draftN(1), metadata: raw5(), onChange: () => {}, onRetry: () => {} }));
  assert.deepEqual(tree.filter(n => n.type === 'option').map(n => n.props.value), [1, 2, 3, 4, 5]);
  const choices = nodes(ui.RogueStartingChoices({ draft: { ...draftN(3), subclassId: '' }, metadata: raw5(), onChange: () => {} }));
  assert.equal(byId(choices, 'rogue-subclass').props.value, '');
});

test('projection reader refuses malformed blocks', () => {
  assert.ok(controls.readRogueProjection(ROGUE()));
  for (const change of [r => { r.sneak_attack.die = 8; }, r => { r.sneak_attack.dice = 0; }, r => { r.cunning_action = {}; },
    r => { delete r.cunning_strike.trip_refused_targets; }, r => { r.cunning_strike.trip_refused_targets = [7]; },
    r => { r.cunning_strike.options[0].id = 'daze'; }, r => { r.uncanny_dodge = { enabled: 'yes', reaction_available: true }; }, r => { delete r.subclass; }]) {
    const value = ROGUE(); change(value);
    assert.equal(controls.readRogueProjection(value), null);
  }
  assert.equal(controls.readRogueProjection(null), null);
  assert.equal(nodes(controls.RogueControl({ rogue: { sneak_attack: {} }, blocked: false, onCommand: () => assert.fail('sent') })).length, 0);
});

test('Cunning Action, Steady Aim and Uncanny Dodge send the exact typed steps and respect the server availability', async () => {
  const sent = [];
  const tree = rogue => nodes(controls.RogueControl({ rogue, blocked: false, onCommand: (label, step) => sent.push(step) }));
  const live = tree(ROGUE());
  byId(live, 'button-cunning-dash').props.onClick();
  byId(live, 'button-cunning-disengage').props.onClick();
  byId(live, 'button-steady-aim').props.onClick();
  byId(live, 'uncanny-dodge-toggle').props.onChange({ target: { checked: false } });
  assert.deepEqual(sent, [{ kind: 'cunning_action', resource: 'bonus', cunning_option: 'dash' }, { kind: 'cunning_action', resource: 'bonus', cunning_option: 'disengage' },
    { kind: 'steady_aim', resource: 'bonus' }, { kind: 'uncanny_dodge', uncanny_dodge_enabled: false }]);
  const spent = ROGUE(); spent.cunning_action.dash = { available: false, reason: 'bonus_action_spent' }; spent.steady_aim = { available: false, reason: 'steady_aim_moved', active: false };
  const off = tree(spent);
  assert.equal(byId(off, 'button-cunning-dash').props.disabled, true);
  assert.equal(byId(off, 'button-steady-aim').props.disabled, true);
  const blocked = nodes(controls.RogueControl({ rogue: ROGUE(), blocked: true, onCommand: () => assert.fail('sent') }));
  assert.equal(byId(blocked, 'button-cunning-dash').props.disabled, true);
  const low = ROGUE(); low.cunning_action = null; low.steady_aim = null; low.uncanny_dodge = null; low.cunning_strike = null;
  const lowTree = tree(low);
  assert.equal(byId(lowTree, 'button-cunning-dash'), undefined);
  assert.equal(byId(lowTree, 'uncanny-dodge-toggle'), undefined);
  const { PlayGameTurnBody } = await import('../../../lib/api-zod/src/generated/api.ts');
  for (const step of sent) assert.equal(PlayGameTurnBody.parse({ message: 'x', combat_action: { steps: [step] } }).combat_action.steps[0].kind, step.kind);
});

test('Cunning Strike fields go on the attack only when the pick can be sent', () => {
  const rogue = ROGUE();
  const fields = (value, option, distance, target = 'npc') => controls.cunningStrikeFields(value, option, distance, target);
  assert.deepEqual(fields(rogue, '', ''), {});
  assert.deepEqual(fields(rogue, 'trip', ''), { cunning_strike: 'trip' });
  assert.deepEqual(fields(rogue, 'withdraw', '15'), { cunning_strike: 'withdraw', cunning_strike_move_ft: 15 });
  assert.equal(fields(rogue, 'withdraw', '20'), null);
  assert.equal(fields(rogue, 'withdraw', ''), null);
  assert.equal(fields(rogue, 'withdraw', '2.5'), null);
  assert.equal(fields(rogue, 'daze', ''), null);
  assert.equal(fields(null, 'trip', ''), null);
  const noKit = ROGUE(); noKit.cunning_strike.options[0] = { id: 'poison', cost: 1, available: false, reason: 'cunning_strike_kit_required' };
  assert.equal(fields(noKit, 'poison', ''), null);
  const used = ROGUE(); used.sneak_attack.used_this_turn = true;
  assert.equal(fields(used, 'trip', ''), null);
  const huge = ROGUE(); huge.cunning_strike.trip_refused_targets = ['npc'];
  assert.equal(fields(huge, 'trip', ''), null);
  assert.deepEqual(fields(huge, 'trip', '', 'other'), { cunning_strike: 'trip' });
  assert.deepEqual(fields(huge, 'poison', ''), { cunning_strike: 'poison' });
});

test('the Cunning Strike picker shows the options and hides once Sneak Attack was dealt', () => {
  const picks = [];
  const render = (rogue, option) => nodes(controls.CunningStrikeControl({ rogue, targetId: 'npc', option, distance: '', disabled: false, onOptionChange: value => picks.push(value), onDistanceChange: () => {} }));
  const tree = render(ROGUE(), '');
  assert.deepEqual(tree.filter(n => n.type === 'option').map(n => n.props.value), ['', 'poison', 'trip', 'withdraw']);
  byId(tree, 'cunning-strike-option').props.onChange({ target: { value: 'trip' } });
  assert.deepEqual(picks, ['trip']);
  assert.ok(byId(render(ROGUE(), 'withdraw'), 'cunning-strike-distance'));
  const used = ROGUE(); used.sneak_attack.used_this_turn = true;
  assert.equal(render(used, '').length, 0);
});
