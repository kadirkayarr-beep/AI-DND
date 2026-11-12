import assert from 'node:assert/strict';
import { before, after, test } from 'node:test';
import path from 'node:path';
import { readFile } from 'node:fs/promises';

// UI slice 3, S2: Wizard/Cleric level-up controls (levels 2-5) on the server's offer; the engine is unchanged.
process.env.PORT ||= '4193';
process.env.BASE_PATH ||= '/';
delete process.env.REPL_ID;
let caster, plain, React, render, vite;
before(async () => {
  const { createServer } = await import('vite');
  vite = await createServer({ configFile: path.join(process.cwd(), 'vite.config.ts'), server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' });
  caster = await vite.ssrLoadModule('/src/components/caster-level-up.tsx');
  plain = await vite.ssrLoadModule('/src/components/level-up-controls.tsx');
  React = await import('react');
  render = (await import('react-dom/server')).renderToStaticMarkup;
});
after(async () => { await vite?.close(); });

const campaign_id = '11111111-1111-4111-8111-111111111111';
const WIS2 = { feat: 'Ability Score Improvement', increase: { wisdom: 2 } };
const INT2 = { feat: 'Ability Score Improvement', increase: { intelligence: 2 } };
const BOOK = ['Shield', 'Sleep', 'Misty Step', 'Scorching Ray'];
// The server's offer shapes (api/main.py level_up_projection + class_progression/{wizard,cleric}.py).
const wizard = (target, extra = {}) => ({ session_id: 's', campaign_id, revision: 9, status: 'ready', reason: null, class_name: 'Wizard', from_level: target - 1, target_level: target,
  choices_required: { spellbook_spells: 2, ...(target === 3 ? { subclass_id: 1 } : {}), ...(target === 4 ? { asi: 1, cantrips: 1 } : {}) },
  capacity: { cantrips: target >= 4 ? 4 : 3, prepared_spells: target + 4, slots: { 1: 4 } }, spellbook_spell_ids: BOOK, cantrip_ids: target === 4 ? ['Light', 'Mage Hand'] : [],
  subclass_options: target === 3 ? [{ id: 'evoker', name: 'Evoker' }] : [], supported_asi_choices: target === 4 ? [INT2, WIS2] : [], effects_supported: ['Spellcasting'], effects_pending: ['Arcane Recovery pending'], ...extra });
const cleric = (target, extra = {}) => ({ ...wizard(target), class_name: 'Cleric', spellbook_spell_ids: null,
  choices_required: { ...(target === 3 ? { subclass_id: 1 } : {}), ...(target === 4 ? { asi: 1, cantrips: 1 } : {}) },
  cantrip_ids: target === 4 ? ['Guidance', 'Thaumaturgy'] : [], subclass_options: target === 3 ? [{ id: 'life_domain', name: 'Life Domain' }] : [], ...extra });
const base = { campaign_id, expected_revision: 9 };
const draft = (extra = {}) => ({ cantrip: '', preparedSpell: '', confirmed: true, ...extra });

test('Wizard 2 and 5: exactly two different offered spellbook spells, confirmed', () => {
  for (const level of [2, 5]) {
    assert.deepEqual(caster.casterLevelUpRequest(wizard(level), draft({ spellbookSpells: ['Shield', 'Misty Step'] })), { ...base, target_level: level, choices: { spellbook_spells: ['Shield', 'Misty Step'] } });
    for (const bad of [['Shield'], ['Shield', 'Shield'], ['Shield', 'Fireball'], ['Shield', 'Sleep', 'Misty Step'], []]) {
      assert.equal(caster.casterLevelUpRequest(wizard(level), draft({ spellbookSpells: bad })), null, JSON.stringify(bad));
    }
    assert.equal(caster.casterLevelUpRequest(wizard(level), draft({ spellbookSpells: ['Shield', 'Sleep'], confirmed: false })), null);
  }
});

test('Wizard 3 adds Evoker only when the server offers it; Wizard 4 adds one offered cantrip and an offered ASI', () => {
  const book = ['Shield', 'Sleep'];
  assert.deepEqual(caster.casterLevelUpRequest(wizard(3), draft({ spellbookSpells: book, subclassId: 'evoker' })), { ...base, target_level: 3, choices: { spellbook_spells: book, subclass_id: 'evoker' } });
  assert.equal(caster.casterLevelUpRequest(wizard(3), draft({ spellbookSpells: book })), null, 'subclass not picked');
  assert.equal(caster.casterLevelUpRequest(wizard(3, { subclass_options: [] }), draft({ spellbookSpells: book, subclassId: 'evoker' })), null, 'not offered');
  assert.deepEqual(caster.casterLevelUpRequest(wizard(4), draft({ spellbookSpells: book, cantrip: 'Light', asi: INT2 })), { ...base, target_level: 4, choices: { spellbook_spells: book, cantrips: ['Light'], asi: INT2 } });
  assert.equal(caster.casterLevelUpRequest(wizard(4), draft({ spellbookSpells: book, cantrip: 'Fire Bolt', asi: INT2 })), null, 'cantrip not offered');
  assert.equal(caster.casterLevelUpRequest(wizard(4), draft({ spellbookSpells: book, cantrip: 'Light' })), null, 'no ASI');
  assert.equal(caster.casterLevelUpRequest(wizard(4), draft({ spellbookSpells: book, cantrip: 'Light', asi: { feat: 'Ability Score Improvement', increase: { strength: 2 } } })), null, 'ASI not offered');
});

test('Cleric 2/5 confirm an empty step; 3 takes Life Domain; 4 takes a cantrip and an ASI', () => {
  for (const level of [2, 5]) {
    assert.deepEqual(caster.casterLevelUpRequest(cleric(level), draft()), { ...base, target_level: level, choices: {} });
    assert.equal(caster.casterLevelUpRequest(cleric(level), draft({ confirmed: false })), null);
  }
  assert.deepEqual(caster.casterLevelUpRequest(cleric(3), draft({ subclassId: 'life_domain' })), { ...base, target_level: 3, choices: { subclass_id: 'life_domain' } });
  assert.equal(caster.casterLevelUpRequest(cleric(3), draft({ subclassId: 'evoker' })), null);
  assert.deepEqual(caster.casterLevelUpRequest(cleric(4), draft({ cantrip: 'Guidance', asi: WIS2 })), { ...base, target_level: 4, choices: { cantrips: ['Guidance'], asi: WIS2 } });
  assert.equal(caster.casterLevelUpRequest(cleric(4), draft({ cantrip: 'Light', asi: WIS2 })), null);
});

test('an unexpected shape, a missing campaign or revision sends nothing', () => {
  assert.equal(caster.casterLevelUpRequest(wizard(2, { choices_required: { spellbook_spells: 2, prepared_spells: 1 } }), draft({ spellbookSpells: ['Shield', 'Sleep'] })), null);
  assert.equal(caster.casterLevelUpRequest(cleric(2, { choices_required: { cantrips: 1 } }), draft()), null);
  assert.equal(caster.casterLevelUpRequest(wizard(2, { campaign_id: null }), draft({ spellbookSpells: ['Shield', 'Sleep'] })), null);
  assert.equal(caster.casterLevelUpRequest(wizard(2, { revision: null }), draft({ spellbookSpells: ['Shield', 'Sleep'] })), null);
  assert.equal(caster.casterLevelUpRequest({ ...wizard(2), class_name: 'Druid' }, draft({ spellbookSpells: ['Shield', 'Sleep'] })), null);
});

const props = (preview, d = draft({ confirmed: false })) => ({ preview, draft: d, onChange() {}, onConfirm() {}, onCancel() {} });
const html = (preview, d) => render(React.createElement(plain.LevelUpChoices, props(preview, d)));

test('the level-up form offers Wizard and Cleric steps 2-5 instead of the unsupported text', () => {
  for (const preview of [2, 3, 4, 5].flatMap(level => [wizard(level), cleric(level)])) {
    const page = html(preview);
    assert.doesNotMatch(page, /henüz desteklenmiyor/, `${preview.class_name} ${preview.target_level}`);
    assert.match(page, /data-testid="level-up-choices"/);
    assert.match(page, /data-testid="button-confirm-level-up"[^>]*disabled/, 'nothing picked yet');
  }
  assert.match(html(wizard(2, { choices_required: { spellbook_spells: 3 } })), /henüz desteklenmiyor/, 'an unknown shape stays honest');
});

test('every step says a preparation window opens, with the new limit and the add-only rule', () => {
  for (const preview of [wizard(2), cleric(5)]) {
    const page = html(preview);
    assert.match(page, /data-testid="level-up-prepare-window"/);
    assert.match(page, new RegExp(`hazırlık sınırın ${preview.capacity.prepared_spells} olur`));
    assert.match(page, /Büyü hazırlığı/);
    assert.match(page, /yalnız büyü ekleyebilirsin/);
  }
});

test('Wizard choices use Turkish names where the catalog has them and keep the English id as the value', () => {
  const page = html(wizard(4));
  assert.equal((page.match(/data-testid="level-up-spellbook-\d"/g) ?? []).length, 2);
  assert.match(page, /<option value="Shield">[^<]*\(Shield\)<\/option>/);
  assert.match(page, /<option value="Misty Step">Misty Step<\/option>/);
  assert.match(page, /data-testid="level-up-cantrip"/);
  assert.match(page, /<option value="Light">[^<]*\(Light\)<\/option>/);
  assert.match(page, /data-testid="level-up-asi-choice"/);
  assert.match(html(wizard(3)), /data-testid="level-up-subclass"/);
  assert.doesNotMatch(html(cleric(2)), /level-up-spellbook|level-up-cantrip|level-up-subclass/);
});

function nodes(e) { return Array.isArray(e) ? e.flatMap(nodes) : e && typeof e === 'object' ? [e, ...nodes(e.props?.children)] : []; }
test('confirm hands the exact request to the page, which owns sending it', () => {
  const sent = [];
  const tree = nodes(caster.CasterLevelChoices({ ...props(wizard(2), draft({ spellbookSpells: ['Shield', 'Sleep'] })), onConfirm: request => sent.push(request) }));
  const button = tree.find(n => n.props?.['data-testid'] === 'button-confirm-level-up');
  assert.equal(button.props.disabled, false);
  button.props.onClick();
  assert.deepEqual(sent, [{ ...base, target_level: 2, choices: { spellbook_spells: ['Shield', 'Sleep'] } }]);
  const changes = [];
  const picker = nodes(caster.CasterLevelChoices({ ...props(wizard(2)), onChange: d => changes.push(d) })).find(n => n.props?.['data-testid'] === 'level-up-spellbook-2');
  picker.props.onChange({ target: { value: 'Sleep' } });
  assert.deepEqual(changes.at(-1).spellbookSpells, ['', 'Sleep']);
  assert.equal(changes.at(-1).confirmed, false, 'a changed pick needs a new confirmation');
});

test('routing is one line in the shared form; the page request and save path are untouched', async () => {
  const source = await readFile('src/components/level-up-controls.tsx', 'utf8');
  assert.match(source, /if \(preview\.class_name === 'Wizard' \|\| preview\.class_name === 'Cleric'\) return <CasterLevelChoices preview=\{preview\} draft=\{draft\} onChange=\{next => onChange\(\{ \.\.\.draft, \.\.\.next \}\)\} onConfirm=\{onConfirm\} onCancel=\{onCancel\} disabled=\{disabled\} \/>;/);
  const own = await readFile('src/components/caster-level-up.tsx', 'utf8');
  assert.doesNotMatch(own, /applyGameSessionLevelUp|fetch\(|useState|localStorage/);
});
