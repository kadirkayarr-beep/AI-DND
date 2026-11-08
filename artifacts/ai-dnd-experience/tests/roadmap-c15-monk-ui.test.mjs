import assert from 'node:assert/strict';
import { before, after, test } from 'node:test';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { emptyStartingDraft } from '../src/lib/sorcerer-starting-creation.ts';

// Monk 1-5 UI. Behavioural tests only: real functions, real components called as functions or rendered, real screen code extracted by AST and run in vm.
const ABILITIES = ['strength', 'constitution', 'intelligence', 'wisdom', 'charisma'];
const ASI = [...ABILITIES.map(a => ({ feat: 'Ability Score Improvement', increase: { [a]: 2 } })),
  ...ABILITIES.flatMap((a, i) => ABILITIES.slice(i + 1).map(b => ({ feat: 'Ability Score Improvement', increase: { [a]: 1, [b]: 1 } })))];
const STR2 = { feat: 'Ability Score Improvement', increase: { strength: 2 } };
const raw2 = () => ({ supported_starting_levels: [1, 2], level_2: { choices: {}, effects_supported: ['Focus supported'], effects_pending: ['Jump pending'] } });
const raw3 = () => ({ ...raw2(), supported_starting_levels: [1, 2, 3], level_3: { subclass_options: [{ id: 'open_hand', name: 'Warrior of the Open Hand' }], effects_supported: ['Open Hand supported'], effects_pending: ['Addle pending'] } });
const raw4 = () => ({ ...raw3(), supported_starting_levels: [1, 2, 3, 4], level_4: { supported_asi_choices: structuredClone(ASI), effects_supported: ['ASI supported'], effects_pending: ['Higher-start equipment pending'] } });
const raw5 = () => ({ ...raw4(), supported_starting_levels: [1, 2, 3, 4, 5], level_5: { effects_supported: ['Stunning Strike supported'], effects_pending: ['Higher-start equipment pending'] } });
const draftN = (level, extra = {}) => ({ ...emptyStartingDraft(), startingLevel: level, subclassId: level >= 3 ? 'open_hand' : '', ...(level >= 4 ? { level4Asi: structuredClone(STR2), level4ConConfirmed: true } : {}), ...extra });
const yes = () => ({ available: true, reason: null });
const MONK = () => ({ martial_arts_die: 8, martial_arts_ready: true, movement_bonus_ft: 10, save_dc: 13, focus: { points_remaining: 3, max_points: 5 }, martial_arts_strike: yes(), flurry_of_blows: yes(), flurry_strikes_remaining: 0, patient_defense: yes(), step_of_the_wind: yes(), uncanny_metabolism: yes(), stunning_strike: yes(), deflect_mode: 'reduce', open_hand_techniques: ['push', 'topple'] });
const LEVEL_ONE = () => ({ ...MONK(), martial_arts_die: 6, movement_bonus_ft: 0, save_dc: 11, focus: null, flurry_of_blows: null, patient_defense: null, step_of_the_wind: null, uncanny_metabolism: null, stunning_strike: null, deflect_mode: null, open_hand_techniques: [] });
const campaign_id = '11111111-1111-4111-8111-111111111111';
const preview = (target, counts, extra = {}) => ({ session_id: 'session', campaign_id, revision: 7, status: 'ready', reason: null, class_name: 'Monk', from_level: target - 1, target_level: target, choices_required: counts, capacity: null, prepared_spell_ids: [], cantrip_ids: [], supported_asi_choices: [], metamagic_options: [], subclass_options: [], effects_supported: ['Supported'], effects_pending: ['Pending'], ...extra });

let helper, projection, ui, controls, levelUp, panel, vite, React, render;
before(async () => {
  helper = await import('../src/lib/monk-starting-creation.ts');
  projection = await import('../src/lib/monk-projection.ts');
  process.env.PORT ||= '4187'; process.env.BASE_PATH ||= '/';
  const { createServer } = await import('vite');
  vite = await createServer({ configFile: path.join(process.cwd(), 'vite.config.ts'), server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' });
  ui = await vite.ssrLoadModule('/src/components/monk-starting-creation.tsx');
  controls = await vite.ssrLoadModule('/src/components/monk-controls.tsx');
  levelUp = await vite.ssrLoadModule('/src/components/level-up-controls.tsx');
  panel = await vite.ssrLoadModule('/src/components/action-economy-panel.tsx');
  React = await import('react'); render = (await import('react-dom/server')).renderToStaticMarkup;
});
after(async () => await vite?.close());
function nodes(e) { return Array.isArray(e) ? e.flatMap(nodes) : e && typeof e === 'object' ? [e, ...nodes(e.props?.children)] : []; }
const byId = (tree, id) => tree.find(n => n.props?.['data-testid'] === id);

function harness(p) {
  let draft = { cantrip: '', preparedSpell: '', confirmed: false }, sent;
  const props = () => ({ preview: p, draft, onChange: d => draft = d, onConfirm: r => sent = r, onCancel: () => {} });
  const tree = () => nodes(levelUp.LevelUpChoices(props()));
  return { tree, get sent() { return sent; }, change: (id, value) => { const c = byId(tree(), id); assert.ok(c, id); c.props.onChange({ target: { value, checked: value } }); } };
}
const confirm = h => byId(h.tree(), 'button-confirm-level-up');

function control(monk, extra = {}) {
  const sent = [];
  const tree = nodes(controls.MonkControl({ monk, blocked: false, targetId: 'npc', attackEnabled: true, continueEnabled: false, technique: '', onTechniqueChange() {}, onCommand: (label, step) => sent.push(step), ...extra }));
  return { tree, sent };
}

async function screen() {
  const ts = await import('typescript'), vm = await import('node:vm');
  const source = await readFile('src/components/character-creation-screen.tsx', 'utf8');
  const ast = ts.createSourceFile('screen.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const evaluate = (code, env) => { vm.runInNewContext(ts.transpileModule(`globalThis.__r=(${code});`, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText, env); return env.__r; };
  const declaration = name => { let d; (function visit(n) { if (ts.isVariableDeclaration(n) && n.name.getText(ast) === name) d = n; ts.forEachChild(n, visit); })(ast); assert.ok(d, name); return d.initializer.getText(ast); };
  const guards = tag => { const found = []; (function visit(n) {
    if ((ts.isJsxSelfClosingElement(n) || ts.isJsxOpeningElement(n)) && n.tagName.getText(ast) === tag) {
      let node = ts.isJsxOpeningElement(n) ? n.parent : n; const conditions = [];
      while (node.parent && ts.isBinaryExpression(node.parent) && node.parent.operatorToken.kind === ts.SyntaxKind.AmpersandAmpersandToken && node.parent.right === node) { conditions.unshift(node.parent.left.getText(ast)); node = node.parent; }
      found.push(conditions.length ? conditions.map(c => `(${c})`).join(' && ') : 'true'); }
    ts.forEachChild(n, visit); })(ast); return found; };
  return { evaluate, declaration, guards };
}

test('reader keeps the verified prefix and hides a bad block and everything above it', () => {
  const read = helper.readMonkStartingCreationOptions;
  assert.deepEqual(read(raw5()), raw5());
  const levels = mutate => { const v = raw5(); mutate(v); return read(v)?.supported_starting_levels; };
  assert.deepEqual(levels(v => { v.level_5.extra = 1; }), [1, 2, 3, 4]);
  assert.deepEqual(levels(v => { v.level_4.supported_asi_choices = [{ feat: 'Ability Score Improvement', increase: { dexterity: 3 } }]; }), [1, 2, 3]);
  assert.deepEqual(levels(v => { v.level_3.subclass_options = [{ id: 'champion', name: 'x' }]; }), [1, 2]);
  assert.deepEqual(levels(v => { delete v.level_3; }), [1, 2]);
  assert.equal(levels(v => { v.level_2.choices = { x: 1 }; }), undefined);
  assert.equal(read(null), undefined);
});

test('fields send the exact bundle for each level and refuse anything unconfirmed, unoffered or inherited', () => {
  const fields = helper.monkStartingCreationFields, source = raw5();
  assert.deepEqual(fields(draftN(1), source), { ok: true, fields: {} });
  assert.deepEqual(fields(draftN(2), source).fields, { starting_level: 2, level_choices: { 2: {} } });
  assert.deepEqual(fields(draftN(5), source).fields, { starting_level: 5, level_choices: { 2: {}, 3: { subclass_id: 'open_hand' }, 4: { asi: STR2 }, 5: {} } });
  for (const bad of [draftN(3, { subclassId: '' }), draftN(3, { subclassId: 'champion' }), draftN(4, { level4ConConfirmed: false }), draftN(4, { level4Asi: undefined }),
    draftN(4, { level4Asi: { feat: 'Ability Score Improvement', increase: { dexterity: 3 } } }), draftN(3, { primalSkill: 'Nature' }), draftN(2, { subclassId: 'open_hand' })])
    assert.equal(fields(bad, source).ok, false, JSON.stringify(bad));
  assert.equal(fields(draftN(4), raw3()).ok, false);
  assert.equal(fields(draftN(2), undefined).ok, false);
});

test('generated validator accepts the exact creation bundle under the Monk class', async () => {
  const { CreateCampaignBody } = await import('../../../lib/api-zod/src/generated/api.ts');
  const character = { mode: 'custom', name: 'Kara', class: 'Monk', race: 'Human', ...helper.monkStartingCreationFields(draftN(5), raw5()).fields };
  assert.deepEqual(CreateCampaignBody.parse({ character }).character.level_choices, character.level_choices);
});

test('pruning clears only a pick the verified source refuses and never rewrites on a catalog gap', () => {
  const prune = helper.pruneMonkDraft, keep = draftN(5);
  assert.equal(prune(keep, raw5()), keep);
  assert.equal(prune(keep, undefined), keep);
  assert.equal(prune(draftN(5, { subclassId: 'champion' }), raw5()).subclassId, '');
});

test('starting components show the live levels and the server scope, and choosing never defaults', () => {
  let picked;
  const tree = nodes(ui.MonkStartingLevelControl({ draft: draftN(1), metadata: helper.readMonkStartingCreationOptions(raw3()), onChange: level => picked = level, onRetry: () => {} }));
  assert.deepEqual(tree.filter(n => n.type === 'option').map(n => n.props.value), [1, 2, 3]);
  const select = byId(tree, 'monk-starting-level');
  select.props.onChange({ target: { value: '4' } }); assert.equal(picked, undefined);
  select.props.onChange({ target: { value: '3' } }); assert.equal(picked, 3);
  const html = render(React.createElement(ui.MonkStartingScope, { metadata: helper.readMonkStartingCreationOptions(raw5()), level: 5 }));
  assert.match(html,/>1 özellik</);assert.doesNotMatch(html,/Stunning Strike supported/);assert.match(html,/Bu seviyede oyunda işleyenler/); assert.match(html,/Bu seviyedeki 1 özellik henüz oyunda tam işlemiyor\./);assert.doesNotMatch(html,/Higher-start equipment pending/); assert.doesNotMatch(html, /Focus supported/);
  let next;
  const choices = nodes(ui.MonkStartingChoices({ draft: draftN(3, { subclassId: '' }), metadata: helper.readMonkStartingCreationOptions(raw5()), onChange: d => next = d }));
  assert.equal(byId(choices, 'monk-subclass').props.value, '');
  byId(choices, 'monk-subclass').props.onChange({ target: { value: 'open_hand' } }); assert.equal(next.subclassId, 'open_hand');
  assert.equal(byId(choices, 'monk-asi-confirm'), undefined, 'level 3 has no ASI');
});

test('real screen: class step, choices and summary follow the live catalog for Monk only', async () => {
  const { evaluate, declaration, guards } = await screen();
  const read = helper.readMonkStartingCreationOptions, stepValid = declaration('isStepValid');
  const run = (metadata, startingLevel, characterClass = 'Monk') => evaluate(stepValid, { characterClass, startingDraft: { ...emptyStartingDraft(), startingLevel }, monkStartingMetadata: metadata, fighterStartingMetadata: undefined, barbarianStartingMetadata: undefined, startingMetadata: undefined, Boolean })('class');
  for (const level of [1, 2, 3, 4, 5]) assert.equal(run(read(raw5()), level), true, `level ${level}`);
  assert.equal(run(read(raw3()), 4), false); assert.equal(run(undefined, 2), false); assert.equal(run(undefined, 1), true);
  assert.equal(run(read(raw5()), 4, 'Wizard'), false);
  for (const [tag, expected] of [['MonkStartingChoices', [false, false, true, true, true]], ['MonkStartingSummary', [false, true, true, true, true]]]) {
    const found = guards(tag); assert.equal(found.length, 1, tag);
    [1, 2, 3, 4, 5].forEach((level, i) => assert.equal(Boolean(evaluate(found[0], { characterClass: 'Monk', startingDraft: { startingLevel: level } })), expected[i], `${tag} ${level}`));
    assert.equal(Boolean(evaluate(found[0], { characterClass: 'Fighter', startingDraft: { startingLevel: 5 } })), false);
  }
});

test('level-up: empty steps, the subclass step and the ASI step send exact bodies after confirmation', async () => {
  for (const target of [2, 5]) {
    const h = harness(preview(target, {}));
    assert.equal(confirm(h).props.disabled, true);
    h.change('level-up-confirm-empty', true);
    confirm(h).props.onClick();
    assert.deepEqual(h.sent, { campaign_id, expected_revision: 7, target_level: target, choices: {} });
  }
  const three = harness(preview(3, { subclass_id: 1 }, { subclass_options: [{ id: 'open_hand', name: 'Warrior of the Open Hand' }] }));
  three.change('level-up-subclass', 'open_hand');
  assert.equal(confirm(three).props.disabled, true);
  three.change('level-up-confirm-subclass', true);
  confirm(three).props.onClick();
  assert.deepEqual(three.sent.choices, { subclass_id: 'open_hand' });
  const four = harness(preview(4, { asi: 1 }, { supported_asi_choices: structuredClone(ASI) }));
  four.tree().find(n => n.props?.testId === 'level-up-asi-choice').props.onChange(structuredClone(STR2));
  four.change('level-up-confirm-con', true);
  confirm(four).props.onClick();
  assert.deepEqual(four.sent.choices, { asi: STR2 });
  const { ApplyGameSessionLevelUpBody } = await import('../../../lib/api-zod/src/generated/api.ts');
  const body = { campaign_id, expected_revision: 7, target_level: 3, choices: { subclass_id: 'open_hand' }, action_id: '22222222-2222-4222-8222-222222222222' };
  assert.deepEqual(ApplyGameSessionLevelUpBody.parse(body), body);
});

test('projection reader refuses malformed blocks; nothing is derived from the class name', () => {
  const read = controls.readMonkProjection;
  assert.deepEqual(read(MONK()), MONK());
  assert.deepEqual(read(LEVEL_ONE()), LEVEL_ONE());
  for (const mutate of [v => { v.martial_arts_die = 0; }, v => { v.focus.points_remaining = 6; }, v => { v.focus.max_points = 0; }, v => { v.flurry_of_blows = {}; },
    v => { v.martial_arts_strike = null; }, v => { v.deflect_mode = 'always'; }, v => { v.open_hand_techniques = ['addle']; }, v => { v.martial_arts_ready = 'yes'; },
    v => { delete v.save_dc; }, v => { v.flurry_strikes_remaining = -1; }]) {
    const v = MONK(); mutate(v); assert.equal(read(v), null, JSON.stringify(v));
  }
  assert.equal(read(null), null); assert.equal(read([]), null);
  assert.equal(render(React.createElement(controls.MonkStatus, { monk: { class: 'Monk' } })), '');
});

test('status shows the server values only', () => {
  const html = render(React.createElement(controls.MonkStatus, { monk: MONK() }));
  assert.match(html, /1d8/); assert.match(html, /3\/5/); assert.match(html, /DC 13/); assert.match(html.replace(/<[^>]+>/g, ''), /\+10 fit/); assert.match(html, /title="feet"/);
  const low = render(React.createElement(controls.MonkStatus, { monk: LEVEL_ONE() }));
  assert.match(low, /1d6/); assert.doesNotMatch(low, /Focus/);
});

test('every button sends its exact typed step and the generated body accepts it', async () => {
  const { tree, sent } = control(MONK());
  for (const id of ['button-martial-arts-strike', 'button-flurry', 'button-patient-defense', 'button-patient-defense-focus', 'button-step-of-the-wind', 'button-step-of-the-wind-focus', 'button-uncanny-metabolism', 'button-stunning-attack'])
    byId(tree, id).props.onClick();
  assert.deepEqual(sent, [{ kind: 'martial_arts_strike', target_id: 'npc' }, { kind: 'flurry_of_blows', target_id: 'npc' }, { kind: 'patient_defense' }, { kind: 'patient_defense', spend_focus: true },
    { kind: 'step_of_the_wind' }, { kind: 'step_of_the_wind', spend_focus: true }, { kind: 'uncanny_metabolism' }, { kind: 'attack', target_id: 'npc', stunning_strike: true }]);
  const { PlayGameTurnBody } = await import('../../../lib/api-zod/src/generated/api.ts');
  for (const step of sent) assert.deepEqual(PlayGameTurnBody.parse({ message: 'x', combat_action: { steps: [step] } }).combat_action.steps[0], { resource: 'action', ...step });
});

test('Flurry carries only a technique the server offers, and the second strike appears only with one left', () => {
  const chosen = control(MONK(), { technique: 'topple' });
  byId(chosen.tree, 'button-flurry').props.onClick();
  assert.deepEqual(chosen.sent, [{ kind: 'flurry_of_blows', target_id: 'npc', open_hand_technique: 'topple' }]);
  const low = { ...MONK(), open_hand_techniques: [] };
  const unoffered = control(low, { technique: 'topple' });
  byId(unoffered.tree, 'button-flurry').props.onClick();
  assert.deepEqual(unoffered.sent, [{ kind: 'flurry_of_blows', target_id: 'npc' }]);
  assert.equal(byId(unoffered.tree, 'button-flurry-strike'), undefined);
  const second = control({ ...MONK(), flurry_strikes_remaining: 1 });
  byId(second.tree, 'button-flurry-strike').props.onClick();
  assert.deepEqual(second.sent, [{ kind: 'flurry_strike', target_id: 'npc' }]);
});

test('availability, a block or a missing target disable the buttons; lower levels hide them', () => {
  const spent = MONK();
  spent.flurry_of_blows = { available: false, reason: 'focus_points_exhausted' }; spent.focus.points_remaining = 0;
  const off = control(spent);
  assert.equal(byId(off.tree, 'button-flurry').props.disabled, true);
  assert.equal(byId(off.tree, 'button-patient-defense').props.disabled, false, 'the free option stays');
  assert.equal(byId(off.tree, 'button-patient-defense-focus').props.disabled, true);
  assert.equal(byId(control(MONK(), { blocked: true }).tree, 'button-martial-arts-strike').props.disabled, true);
  assert.equal(byId(control(MONK(), { targetId: null }).tree, 'button-martial-arts-strike').props.disabled, true);
  assert.equal(byId(control(MONK(), { attackEnabled: false }).tree, 'button-stunning-attack').props.disabled, true);
  const low = control(LEVEL_ONE()).tree;
  for (const id of ['button-flurry', 'button-patient-defense', 'button-step-of-the-wind', 'button-uncanny-metabolism', 'button-stunning-attack', 'monk-deflect', 'monk-technique'])
    assert.equal(byId(low, id), undefined, id);
  assert.ok(byId(low, 'button-martial-arts-strike'));
  assert.match(render(React.createElement(controls.MonkControl, { monk: spent, blocked: false, targetId: 'npc', attackEnabled: true, continueEnabled: false, technique: '', onTechniqueChange() {}, onCommand() {} })), /focus_points_exhausted/);
});

test('Deflect setting sends only a new valid mode; technique choice is limited to the offered list', () => {
  const { tree, sent } = control(MONK());
  const deflect = byId(tree, 'monk-deflect');
  deflect.props.onChange({ target: { value: 'reduce' } });
  deflect.props.onChange({ target: { value: 'always' } });
  assert.deepEqual(sent, []);
  deflect.props.onChange({ target: { value: 'redirect' } });
  assert.deepEqual(sent, [{ kind: 'set_deflect_attacks', deflect_mode: 'redirect' }]);
  let technique;
  const select = byId(control(MONK(), { onTechniqueChange: value => technique = value }).tree, 'monk-technique');
  select.props.onChange({ target: { value: 'push' } }); assert.equal(technique, 'push');
  select.props.onChange({ target: { value: 'addle' } }); assert.equal(technique, '');
});

test('the continuation button appears only while the Attack action has an attack left', () => {
  assert.equal(byId(control(MONK()).tree, 'button-stunning-continue'), undefined);
  const live = control(MONK(), { continueEnabled: true });
  byId(live.tree, 'button-stunning-continue').props.onClick();
  assert.deepEqual(live.sent, [{ kind: 'continue_attack', target_id: 'npc', stunning_strike: true }]);
});

test('the action panel mounts the control from the projection', async () => {
  const source = await readFile('src/components/action-economy-panel.tsx', 'utf8');
  const ts = await import('typescript');
  const ast = ts.createSourceFile('panel.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  let props;
  (function visit(n) { if (ts.isJsxSelfClosingElement(n) && n.tagName.getText(ast) === 'MonkControl') props = n.attributes.properties.map(p => p.name.getText(ast) + '=' + p.initializer.getText(ast)); ts.forEachChild(n, visit); })(ast);
  assert.ok(props, 'mounted');
  assert.ok(props.includes('monk={state.character?.monk}'));
  assert.ok(typeof panel.ActionEconomyPanel === 'function' || Object.keys(panel).length > 0);
});
