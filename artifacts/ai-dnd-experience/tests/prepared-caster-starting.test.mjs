import assert from 'node:assert/strict';
import { test } from 'node:test';
import { startingCreationPayload } from '../src/lib/starting-creation-payload.ts';
import { emptyStartingDraft } from '../src/lib/sorcerer-starting-creation.ts';
import { pruneCasterDraft, readClericStartingCreationOptions, readWizardStartingCreationOptions } from '../src/lib/prepared-caster-starting-creation.ts';

// G2.12 / D-040: Wizard and Cleric start 2-5. The Wizard adds two spellbook spells at every level; both pick a subclass at 3 and a cantrip plus an ASI at 4.
const INT2 = { feat: 'Ability Score Improvement', increase: { intelligence: 2 } };
const WIS2 = { feat: 'Ability Score Improvement', increase: { wisdom: 2 } };
const asiList = [INT2, WIS2, { feat: 'Ability Score Improvement', increase: { strength: 2 } }];
const SPELLS = ['Magic Missile', 'Shield', 'Sleep', 'Thunderwave', 'Feather Fall', 'Identify', 'Misty Step', 'Charm Person', 'Web', 'Fireball', 'Counterspell'];
const book = level => ({ spellbook_spell_count: 2, spellbook_spell_ids: SPELLS.slice(0, level === 2 ? 5 : 11) });
const pending = Object.fromEntries([1, 2, 3, 4, 5].map(level => [String(level), [`pending ${level}`]]));
const four = () => ({ cantrip_count: 1, cantrip_ids: ['Fire Bolt', 'Mage Hand', 'Light', 'Prestidigitation', 'Thaumaturgy'], supported_asi_choices: structuredClone(asiList) });
const wizardRaw = () => ({ supported_starting_levels: [1, 2, 3, 4, 5], level_2: book(2), level_3: { ...book(3), subclass_options: [{ id: 'evoker', name: 'Evoker' }] },
  level_4: { ...book(4), ...four() }, level_5: book(5), effects_pending_by_level: structuredClone(pending) });
const clericRaw = () => ({ supported_starting_levels: [1, 2, 3, 4, 5], level_2: {}, level_3: { subclass_options: [{ id: 'life_domain', name: 'Life Domain' }] },
  level_4: four(), level_5: {}, effects_pending_by_level: structuredClone(pending) });
const INITIAL_BOOK = ['Magic Missile', 'Shield', 'Sleep'];
const INITIAL_CANTRIPS = ['Fire Bolt', 'Mage Hand', 'Light'];
const draftFor = (level, extra = {}) => ({ ...emptyStartingDraft(), startingLevel: level, ...extra });
const wizardDraft = level => draftFor(level, {
  level2Prepared: ['Thunderwave', 'Feather Fall'], level3Prepared: level >= 3 ? ['Identify', 'Misty Step'] : [], subclassId: level >= 3 ? 'evoker' : '',
  level4Prepared: level >= 4 ? ['Charm Person', 'Web'] : [], level4Cantrips: level >= 4 ? ['Prestidigitation'] : [],
  ...(level >= 4 ? { level4Asi: structuredClone(INT2), level4ConConfirmed: true } : {}), level5Prepared: level === 5 ? ['Fireball', 'Counterspell'] : [] });
const clericDraft = level => draftFor(level, { subclassId: level >= 3 ? 'life_domain' : '', level4Cantrips: level >= 4 ? ['Thaumaturgy'] : [],
  ...(level >= 4 ? { level4Asi: structuredClone(WIS2), level4ConConfirmed: true } : {}) });
const ctx = sources => ({ spells: INITIAL_BOOK, cantrips: INITIAL_CANTRIPS, caster: sources });
const wizardCtx = () => ctx({ wizard: readWizardStartingCreationOptions(wizardRaw()) });
const clericCtx = () => ctx({ cleric: readClericStartingCreationOptions(clericRaw()) });

test('Wizard: the bundle of every start level carries the spellbook picks the server asks for', () => {
  assert.deepEqual(startingCreationPayload('Wizard', draftFor(1), wizardCtx()), { ok: true, fields: {} });
  assert.deepEqual(startingCreationPayload('Wizard', wizardDraft(2), wizardCtx()).fields,
    { starting_level: 2, level_choices: { '2': { spellbook_spells: ['Thunderwave', 'Feather Fall'] } } });
  assert.deepEqual(startingCreationPayload('Wizard', wizardDraft(5), wizardCtx()).fields, { starting_level: 5, level_choices: {
    '2': { spellbook_spells: ['Thunderwave', 'Feather Fall'] },
    '3': { spellbook_spells: ['Identify', 'Misty Step'], subclass_id: 'evoker' },
    '4': { spellbook_spells: ['Charm Person', 'Web'], cantrips: ['Prestidigitation'], asi: INT2 },
    '5': { spellbook_spells: ['Fireball', 'Counterspell'] } } });
});

test('Cleric: levels 2 and 5 take no pick, 3 a subclass, 4 a cantrip and a confirmed ASI', () => {
  assert.deepEqual(startingCreationPayload('Cleric', clericDraft(2), clericCtx()).fields, { starting_level: 2, level_choices: { '2': {} } });
  assert.deepEqual(startingCreationPayload('Cleric', clericDraft(5), clericCtx()).fields, { starting_level: 5, level_choices: {
    '2': {}, '3': { subclass_id: 'life_domain' }, '4': { cantrips: ['Thaumaturgy'], asi: WIS2 }, '5': {} } });
});

test('a missing catalog, a short pick or a duplicate of the creation book blocks the start', () => {
  assert.match(startingCreationPayload('Wizard', wizardDraft(2), ctx({})).message, /^Wizard seviye seçenekleri alınamadı/);
  assert.match(startingCreationPayload('Cleric', clericDraft(2), ctx({})).message, /^Cleric seviye seçenekleri alınamadı/);
  assert.equal(startingCreationPayload('Wizard', { ...wizardDraft(2), level2Prepared: ['Thunderwave'] }, wizardCtx()).message, 'Seviye 2 için iki farklı yeni büyü seçin.');
  assert.equal(startingCreationPayload('Wizard', { ...wizardDraft(2), level2Prepared: ['Shield', 'Thunderwave'] }, wizardCtx()).message, 'Seviye 2 için iki farklı yeni büyü seçin.');
  assert.equal(startingCreationPayload('Wizard', { ...wizardDraft(3), level3Prepared: ['Thunderwave', 'Identify'] }, wizardCtx()).message, 'Seviye 3 için iki farklı yeni büyü seçin.');
  assert.equal(startingCreationPayload('Wizard', { ...wizardDraft(3), subclassId: '' }, wizardCtx()).message, 'Bir Wizard alt sınıfı seçin.');
  assert.equal(startingCreationPayload('Cleric', { ...clericDraft(4), level4ConConfirmed: false }, clericCtx()).ok, false);
  assert.equal(startingCreationPayload('Cleric', { ...clericDraft(4), level4Cantrips: ['Light'] }, clericCtx()).message, 'Seviye 4 için bir yeni cantrip seçin.');
});

test('picks of a higher level, a Cleric book pick and another class bundle are refused, never sent', () => {
  assert.equal(startingCreationPayload('Wizard', { ...wizardDraft(2), level3Prepared: ['Identify', 'Misty Step'] }, wizardCtx()).message, 'Üst seviye seçimlerini temizleyin.');
  assert.equal(startingCreationPayload('Cleric', { ...clericDraft(2), level2Prepared: ['Shield', 'Sleep'] }, clericCtx()).ok, false);
  assert.match(startingCreationPayload('Wizard', { ...wizardDraft(2), metamagic: ['Twinned Spell'] }, wizardCtx()).message, /önce diğer sınıfın seçimlerini temizleyin/);
});

test('the readers accept only the full start 1-5 block of their own class', () => {
  assert.ok(readWizardStartingCreationOptions(wizardRaw()));
  assert.ok(readClericStartingCreationOptions(clericRaw()));
  assert.equal(readWizardStartingCreationOptions(clericRaw()), undefined);
  assert.equal(readClericStartingCreationOptions(wizardRaw()), undefined);
  const short = wizardRaw();
  short.supported_starting_levels = [1, 2, 3];
  assert.equal(readWizardStartingCreationOptions(short), undefined);
  const wrongSubclass = clericRaw();
  wrongSubclass.level_3.subclass_options[0].id = 'evoker';
  assert.equal(readClericStartingCreationOptions(wrongSubclass), undefined);
  const noAsi = wizardRaw();
  noAsi.level_4.supported_asi_choices = [];
  assert.equal(readWizardStartingCreationOptions(noAsi), undefined);
  const oneSpell = wizardRaw();
  oneSpell.level_5.spellbook_spell_count = 1;
  assert.equal(readWizardStartingCreationOptions(oneSpell), undefined);
});

test('pruning clears a pick the creation book or cantrips now own, and every pick above the level', () => {
  const wizard = readWizardStartingCreationOptions(wizardRaw());
  const taken = pruneCasterDraft('Wizard', wizardDraft(4), wizard, [...INITIAL_BOOK, 'Thunderwave'], [...INITIAL_CANTRIPS, 'Prestidigitation']);
  assert.deepEqual(taken.level2Prepared, ['Feather Fall']);
  assert.deepEqual(taken.level4Cantrips, []);
  const lower = pruneCasterDraft('Wizard', { ...wizardDraft(5), startingLevel: 3 }, wizard, INITIAL_BOOK, INITIAL_CANTRIPS);
  assert.deepEqual([lower.level4Prepared, lower.level5Prepared, lower.level4Cantrips], [[], [], []]);
  assert.equal(lower.level4Asi, undefined);
  const same = wizardDraft(3);
  assert.equal(pruneCasterDraft('Wizard', same, wizard, INITIAL_BOOK, INITIAL_CANTRIPS), same);
  assert.equal(pruneCasterDraft('Wizard', wizardDraft(2), undefined, INITIAL_BOOK, INITIAL_CANTRIPS).level2Prepared.length, 2);
});
