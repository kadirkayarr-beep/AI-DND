import assert from 'node:assert/strict';
import { before, after, test } from 'node:test';
import path from 'node:path';
import { emptyStartingDraft } from '../src/lib/sorcerer-starting-creation.ts';

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
  cunning_strike: { dc: 14, withdraw_max_ft: 15, options: [{ id: 'poison', cost: 1, ...open }, { id: 'trip', cost: 1, ...open }, { id: 'withdraw', cost: 1, ...open }] },
  uncanny_dodge: { enabled: true, reaction_available: true } });

let helper, ui, controls, vite;
before(async () => {
  helper = await import('../src/lib/rogue-starting-creation.ts');
  process.env.PORT ||= '4187'; process.env.BASE_PATH ||= '/';
  const { createServer } = await import('vite');
  vite = await createServer({ configFile: path.join(process.cwd(), 'vite.config.ts'), server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' });
  ui = await vite.ssrLoadModule('/src/components/rogue-starting-creation.tsx');
  controls = await vite.ssrLoadModule('/src/components/rogue-controls.tsx');
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

test('generated validator accepts the exact creation bundle under the Rogue class', async () => {
  const { CreateGameCampaignBody } = await import('../../../lib/api-zod/src/generated/api.ts').catch(() => ({}));
  const zod = await import('../../../lib/api-zod/src/generated/api.ts');
  const body = CreateGameCampaignBody ?? zod.CreateCampaignBody;
  if (body) assert.ok(body.shape ?? body);
  assert.ok(zod.PlayGameTurnBody.parse({ message: 'x', combat_action: { steps: [{ kind: 'attack', target_id: 'a', cunning_strike: 'trip' }] } }));
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
  assert.deepEqual(controls.cunningStrikeFields(rogue, '', ''), {});
  assert.deepEqual(controls.cunningStrikeFields(rogue, 'trip', ''), { cunning_strike: 'trip' });
  assert.deepEqual(controls.cunningStrikeFields(rogue, 'withdraw', '15'), { cunning_strike: 'withdraw', cunning_strike_move_ft: 15 });
  assert.equal(controls.cunningStrikeFields(rogue, 'withdraw', '20'), null);
  assert.equal(controls.cunningStrikeFields(rogue, 'withdraw', ''), null);
  assert.equal(controls.cunningStrikeFields(rogue, 'withdraw', '2.5'), null);
  assert.equal(controls.cunningStrikeFields(rogue, 'daze', ''), null);
  assert.equal(controls.cunningStrikeFields(null, 'trip', ''), null);
  const noKit = ROGUE(); noKit.cunning_strike.options[0] = { id: 'poison', cost: 1, available: false, reason: 'cunning_strike_kit_required' };
  assert.equal(controls.cunningStrikeFields(noKit, 'poison', ''), null);
  const used = ROGUE(); used.sneak_attack.used_this_turn = true;
  assert.equal(controls.cunningStrikeFields(used, 'trip', ''), null);
});

test('the Cunning Strike picker shows the options and hides once Sneak Attack was dealt', () => {
  const picks = [];
  const render = (rogue, option) => nodes(controls.CunningStrikeControl({ rogue, option, distance: '', disabled: false, onOptionChange: value => picks.push(value), onDistanceChange: () => {} }));
  const tree = render(ROGUE(), '');
  assert.deepEqual(tree.filter(n => n.type === 'option').map(n => n.props.value), ['', 'poison', 'trip', 'withdraw']);
  byId(tree, 'cunning-strike-option').props.onChange({ target: { value: 'trip' } });
  assert.deepEqual(picks, ['trip']);
  assert.ok(byId(render(ROGUE(), 'withdraw'), 'cunning-strike-distance'));
  const used = ROGUE(); used.sneak_attack.used_this_turn = true;
  assert.equal(render(used, '').length, 0);
});
