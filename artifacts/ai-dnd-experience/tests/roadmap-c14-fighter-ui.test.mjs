import assert from 'node:assert/strict';
import { before, after, test } from 'node:test';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { emptyStartingDraft } from '../src/lib/sorcerer-starting-creation.ts';

// Fighter 1-5 UI. Behavioural tests only: real functions, real components called as functions or rendered, real screen code extracted by AST and run in vm.
const ABILITIES = ['strength', 'constitution', 'intelligence', 'wisdom', 'charisma'];
const ASI = [...ABILITIES.map(a => ({ feat: 'Ability Score Improvement', increase: { [a]: 2 } })),
  ...ABILITIES.flatMap((a, i) => ABILITIES.slice(i + 1).map(b => ({ feat: 'Ability Score Improvement', increase: { [a]: 1, [b]: 1 } })))];
const STR2 = { feat: 'Ability Score Improvement', increase: { strength: 2 } };
const raw2 = () => ({ supported_starting_levels: [1, 2], level_2: { choices: {}, effects_supported: ['Second Wind supported'], effects_pending: ['Weapon Mastery pending'] } });
const raw3 = () => ({ ...raw2(), supported_starting_levels: [1, 2, 3], level_3: { subclass_options: [{ id: 'champion', name: 'Champion' }], effects_supported: ['Champion supported'], effects_pending: ['Crit move pending'] } });
const raw4 = () => ({ ...raw3(), supported_starting_levels: [1, 2, 3, 4], level_4: { supported_asi_choices: structuredClone(ASI), effects_supported: ['ASI supported'], effects_pending: ['Higher-start equipment pending'] } });
const raw5 = () => ({ ...raw4(), supported_starting_levels: [1, 2, 3, 4, 5], level_5: { effects_supported: ['Extra Attack supported'], effects_pending: ['Higher-start equipment pending'] } });
const draftN = (level, extra = {}) => ({ ...emptyStartingDraft(), startingLevel: level, subclassId: level >= 3 ? 'champion' : '', ...(level >= 4 ? { level4Asi: structuredClone(STR2), level4ConConfirmed: true } : {}), ...extra });
const FIGHTER = () => ({ fighting_style: 'Defense', second_wind: { uses_remaining: 2, max_uses: 3, die: 10, level_bonus: 5, activate: { available: true, reason: null }, tactical_shift: true }, action_surge: { uses_remaining: 1, max_uses: 1, activate: { available: true, reason: null } } });
const campaign_id = '11111111-1111-4111-8111-111111111111';
const preview = (target, counts, extra = {}) => ({ session_id: 'session', campaign_id, revision: 7, status: 'ready', reason: null, class_name: 'Fighter', from_level: target - 1, target_level: target, choices_required: counts, capacity: null, prepared_spell_ids: [], cantrip_ids: [], supported_asi_choices: [], metamagic_options: [], subclass_options: [], effects_supported: ['Supported'], effects_pending: ['Weapon Mastery pending'], ...extra });

let helper, ui, controls, levelUp, vite, React, render;
before(async () => {
  helper = await import('../src/lib/fighter-starting-creation.ts');
  process.env.PORT ||= '4186'; process.env.BASE_PATH ||= '/';
  const { createServer } = await import('vite');
  vite = await createServer({ configFile: path.join(process.cwd(), 'vite.config.ts'), server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' });
  ui = await vite.ssrLoadModule('/src/components/fighter-starting-creation.tsx');
  controls = await vite.ssrLoadModule('/src/components/fighter-controls.tsx');
  levelUp = await vite.ssrLoadModule('/src/components/level-up-controls.tsx');
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
  const read = helper.readFighterStartingCreationOptions;
  assert.deepEqual(read(raw5()), raw5());
  const copy = read(raw5()); copy.level_4.supported_asi_choices.pop();
  assert.equal(raw5().level_4.supported_asi_choices.length, 15);
  const levels = mutate => { const v = raw5(); mutate(v); return read(v)?.supported_starting_levels; };
  assert.deepEqual(levels(v => { v.level_5.extra = 1; }), [1, 2, 3, 4]);
  assert.deepEqual(levels(v => { v.level_4.supported_asi_choices = [{ feat: 'Ability Score Improvement', increase: { dexterity: 2 } }]; }), [1, 2, 3]);
  assert.deepEqual(levels(v => { v.level_3.subclass_options = [{ id: 'berserker', name: 'x' }]; }), [1, 2]);
  assert.deepEqual(levels(v => { v.level_3.subclass_options.push({ id: 'champion', name: 'Again' }); }), [1, 2]);
  assert.deepEqual(levels(v => { delete v.level_3; }), [1, 2]);
  assert.equal(levels(v => { v.level_2.choices = { x: 1 }; }), undefined);
  for (const list of [[1, 2, 3, 5], [2, 3, 4, 5], [1, 2, 3, 4, 5, 6], [1, 2, 3, 4, '5'], [1], []]) assert.equal(read({ ...raw5(), supported_starting_levels: list }), undefined);
  assert.equal(read(null), undefined); assert.equal(read([]), undefined);
});

test('fields send the exact bundle for each level and refuse anything unconfirmed, unoffered or inherited', () => {
  const fields = helper.fighterStartingCreationFields, source = raw5();
  assert.deepEqual(fields(draftN(1), source), { ok: true, fields: {} });
  assert.deepEqual(fields(draftN(2), source).fields, { starting_level: 2, level_choices: { 2: {} } });
  assert.deepEqual(fields(draftN(3), source).fields, { starting_level: 3, level_choices: { 2: {}, 3: { subclass_id: 'champion' } } });
  assert.deepEqual(fields(draftN(5), source).fields, { starting_level: 5, level_choices: { 2: {}, 3: { subclass_id: 'champion' }, 4: { asi: STR2 }, 5: {} } });
  for (const bad of [draftN(3, { subclassId: '' }), draftN(3, { subclassId: 'berserker' }), draftN(4, { level4ConConfirmed: false }), draftN(4, { level4Asi: undefined }),
    draftN(4, { level4Asi: { feat: 'Ability Score Improvement', increase: { dexterity: 2 } } }), draftN(3, { primalSkill: 'Nature' }), draftN(2, { level3Prepared: ['x'] }), draftN(2, { subclassId: 'champion' })])
    assert.equal(fields(bad, source).ok, false, JSON.stringify(bad));
  assert.equal(fields(draftN(4), raw3()).ok, false);
  assert.equal(fields(draftN(2), undefined).ok, false);
});

test('generated validator accepts the exact creation bundle under the Fighter class', async () => {
  const { CreateCampaignBody } = await import('../../../lib/api-zod/src/generated/api.ts');
  const character = { mode: 'custom', name: 'Kara', class: 'Fighter', race: 'Human', ...helper.fighterStartingCreationFields(draftN(5), raw5()).fields };
  const parsed = CreateCampaignBody.parse({ character }).character;
  assert.deepEqual(parsed.level_choices, character.level_choices);
});

test('pruning clears only a pick the verified source refuses and never rewrites on a catalog gap', () => {
  const prune = helper.pruneFighterDraft, keep = draftN(5);
  assert.equal(prune(keep, raw5()), keep);
  assert.equal(prune(keep, undefined), keep, 'a missing catalog blocks submission instead of erasing the pick');
  assert.equal(prune(draftN(5, { subclassId: 'berserker' }), raw5()).subclassId, '');
  const stale = prune(draftN(5, { level4Asi: { feat: 'Ability Score Improvement', increase: { dexterity: 2 } } }), raw5());
  assert.equal('level4Asi' in stale, false); assert.equal(stale.level4ConConfirmed, false);
});

test('starting components show the live levels and the server scope, and choosing never defaults', () => {
  let picked;
  const tree = nodes(ui.FighterStartingLevelControl({ draft: draftN(1), metadata: helper.readFighterStartingCreationOptions(raw3()), onChange: level => picked = level, onRetry: () => {} }));
  assert.deepEqual(tree.filter(n => n.type === 'option').map(n => n.props.value), [1, 2, 3]);
  const select = byId(tree, 'fighter-starting-level');
  select.props.onChange({ target: { value: '4' } }); assert.equal(picked, undefined);
  select.props.onChange({ target: { value: '3' } }); assert.equal(picked, 3);
  const html = render(React.createElement(ui.FighterStartingScope, { metadata: helper.readFighterStartingCreationOptions(raw5()), level: 5 }));
  assert.match(html, /Extra Attack supported/); assert.match(html, /Higher-start equipment pending/); assert.doesNotMatch(html, /Second Wind supported/);
  const missing = render(React.createElement(ui.FighterStartingLevelControl, { draft: draftN(3), onChange: () => {}, onRetry: () => {} }));
  assert.match(missing, /kullanılamıyor/);
  let next;
  const choices = nodes(ui.FighterStartingChoices({ draft: draftN(3, { subclassId: '' }), metadata: helper.readFighterStartingCreationOptions(raw5()), ownedSkills: [], onChange: d => next = d }));
  assert.equal(byId(choices, 'fighter-subclass').props.value, '');
  byId(choices, 'fighter-subclass').props.onChange({ target: { value: 'champion' } }); assert.equal(next.subclassId, 'champion');
  assert.equal(byId(choices, 'fighter-asi-confirm'), undefined, 'level 3 has no ASI');
});

test('real screen: class step, choices and summary follow the live catalog for Fighter only', async () => {
  const { evaluate, declaration, guards } = await screen();
  const read = helper.readFighterStartingCreationOptions, stepValid = declaration('isStepValid');
  const run = (metadata, startingLevel, characterClass = 'Fighter') => evaluate(stepValid, { characterClass, startingDraft: { ...emptyStartingDraft(), startingLevel }, fighterStartingMetadata: metadata, barbarianStartingMetadata: undefined, startingMetadata: undefined, Boolean })('class');
  for (const level of [1, 2, 3, 4, 5]) assert.equal(run(read(raw5()), level), true, `level ${level}`);
  assert.equal(run(read(raw3()), 4), false); assert.equal(run(undefined, 2), false); assert.equal(run(undefined, 1), true);
  assert.equal(run(read(raw5()), 4, 'Wizard'), false);
  for (const [tag, expected] of [['FighterStartingChoices', [false, false, true, true, true]], ['FighterStartingSummary', [false, true, true, true, true]]]) {
    const found = guards(tag); assert.equal(found.length, 1, tag);
    [1, 2, 3, 4, 5].forEach((level, i) => assert.equal(Boolean(evaluate(found[0], { characterClass: 'Fighter', startingDraft: { startingLevel: level } })), expected[i], `${tag} ${level}`));
    for (const other of ['Barbarian', 'Sorcerer']) assert.equal(Boolean(evaluate(found[0], { characterClass: other, startingDraft: { startingLevel: 5 } })), false);
  }
});

test('level-up: empty steps 2 and 5 need explicit confirmation and send an empty object', () => {
  for (const target of [2, 5]) {
    const h = harness(preview(target, {}));
    assert.equal(confirm(h).props.disabled, true);
    h.change('level-up-confirm-empty', true);
    confirm(h).props.onClick();
    assert.deepEqual(h.sent, { campaign_id, expected_revision: 7, target_level: target, choices: {} });
  }
});

test('level-up: level 3 sends exactly the offered subclass after confirmation', () => {
  const h = harness(preview(3, { subclass_id: 1 }, { subclass_options: [{ id: 'champion', name: 'Champion' }] }));
  assert.equal(confirm(h).props.disabled, true);
  h.change('level-up-subclass', 'champion');
  assert.equal(confirm(h).props.disabled, true);
  h.change('level-up-confirm-subclass', true);
  confirm(h).props.onClick();
  assert.deepEqual(h.sent, { campaign_id, expected_revision: 7, target_level: 3, choices: { subclass_id: 'champion' } });
  assert.equal(byId(h.tree(), 'level-up-primal-skill'), undefined);
});

test('level-up: level 4 sends only the server ASI; unknown shapes fail closed', async () => {
  const h = harness(preview(4, { asi: 1 }, { supported_asi_choices: structuredClone(ASI) }));
  assert.equal(confirm(h).props.disabled, true);
  h.tree().find(n => n.props?.testId === 'level-up-asi-choice').props.onChange(structuredClone(STR2));
  assert.equal(confirm(h).props.disabled, true, 'a pick still needs the confirmation');
  h.change('level-up-confirm-con', true);
  confirm(h).props.onClick();
  assert.deepEqual(h.sent.choices, { asi: STR2 });
  for (const p of [preview(3, { subclass_id: 1, primal_knowledge_skill: 1 }), preview(4, { asi: 1, cantrips: 1 }), preview(5, { asi: 1 }), preview(6, {}), preview(3, {})])
    assert.equal(confirm(harness(p)), undefined, JSON.stringify(p.choices_required));
  const { ApplyGameSessionLevelUpBody } = await import('../../../lib/api-zod/src/generated/api.ts');
  const body = { campaign_id, expected_revision: 7, target_level: 3, choices: { subclass_id: 'champion' }, action_id: '22222222-2222-4222-8222-222222222222' };
  assert.deepEqual(ApplyGameSessionLevelUpBody.parse(body), body);
  assert.throws(() => ApplyGameSessionLevelUpBody.parse({ ...body, choices: { subclass_id: 'battle-master' } }));
});

test('projection reader refuses malformed blocks; the panel never derives anything from the class', () => {
  const read = controls.readFighterProjection;
  assert.deepEqual(read(FIGHTER()), FIGHTER());
  for (const mutate of [v => { v.second_wind.uses_remaining = 4; }, v => { v.second_wind.die = 12; }, v => { v.second_wind.max_uses = 0; }, v => { v.action_surge.uses_remaining = 2; },
    v => { v.second_wind.activate = {}; }, v => { v.action_surge = undefined; }, v => { v.fighting_style = 7; }, v => { v.second_wind.tactical_shift = 'yes'; }, v => { delete v.second_wind; }]) {
    const v = FIGHTER(); mutate(v); assert.equal(read(v), null, JSON.stringify(v));
  }
  assert.equal(read(null), null); assert.equal(read([]), null);
  assert.equal(render(React.createElement(controls.FighterStatus, { fighter: { class: 'Fighter' } })), '');
});

test('Second Wind and Action Surge send the exact typed steps and respect the server availability', async () => {
  const sent = [];
  const tree = fighter => nodes(controls.FighterControl({ fighter, blocked: false, shift: '', onShiftChange: () => {}, onCommand: (label, step) => sent.push(step) }));
  const live = tree(FIGHTER());
  byId(live, 'button-second-wind').props.onClick();
  byId(live, 'button-action-surge').props.onClick();
  assert.deepEqual(sent, [{ kind: 'second_wind', resource: 'bonus' }, { kind: 'action_surge' }]);
  const spent = FIGHTER(); spent.second_wind.activate = { available: false, reason: 'second_wind_uses_exhausted' }; spent.action_surge.activate = { available: false, reason: 'action_surge_uses_exhausted' };
  const off = tree(spent); assert.equal(byId(off, 'button-second-wind').props.disabled, true); assert.equal(byId(off, 'button-action-surge').props.disabled, true);
  const blocked = nodes(controls.FighterControl({ fighter: FIGHTER(), blocked: true, shift: '', onShiftChange: () => {}, onCommand: () => assert.fail('sent') }));
  assert.equal(byId(blocked, 'button-second-wind').props.disabled, true);
  const low = FIGHTER(); low.action_surge = null; low.second_wind.tactical_shift = false;
  const lowTree = tree(low); assert.equal(byId(lowTree, 'button-action-surge'), undefined); assert.equal(byId(lowTree, 'fighter-tactical-shift'), undefined);
  const { PlayGameTurnBody } = await import('../../../lib/api-zod/src/generated/api.ts');
  for (const step of sent) assert.deepEqual(PlayGameTurnBody.parse({ message: 'x', combat_action: { steps: [step] } }).combat_action.steps[0].kind, step.kind);
});

test('Tactical Shift distance is sent only when the server offers it and the value is a positive whole number', () => {
  const step = controls.secondWindStep, f = FIGHTER();
  assert.deepEqual(step(f, ''), { kind: 'second_wind', resource: 'bonus' });
  assert.deepEqual(step(f, '15'), { kind: 'second_wind', resource: 'bonus', distance_ft: 15 });
  for (const bad of ['0', '-5', '2.5', 'x']) assert.equal(step(f, bad), null, bad);
  f.second_wind.tactical_shift = false; assert.equal(step(f, '15'), null);
  const disabled = nodes(controls.FighterControl({ fighter: FIGHTER(), blocked: false, shift: 'x', onShiftChange: () => {}, onCommand: () => assert.fail('sent') }));
  assert.equal(byId(disabled, 'button-second-wind').props.disabled, true);
});
