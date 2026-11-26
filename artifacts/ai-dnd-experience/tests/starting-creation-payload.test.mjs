import assert from 'node:assert/strict';
import { test } from 'node:test';
import { startingCreationPayload } from '../src/lib/starting-creation-payload.ts';
import { emptyStartingDraft } from '../src/lib/sorcerer-starting-creation.ts';

// D-561 / D-571 / D-560: one table drives every class starting bundle. These expectations were taken from the
// per-class functions before they were merged (Fighter, Monk, Rogue shared one copy each; Barbarian, Paladin and
// Sorcerer keep their own rules), so the merge must not change a single payload.
const ABILITIES = ['strength', 'constitution', 'intelligence', 'wisdom', 'charisma'];
const ASI = [...ABILITIES.map(a => ({ feat: 'Ability Score Improvement', increase: { [a]: 2 } })),
  ...ABILITIES.flatMap((a, i) => ABILITIES.slice(i + 1).map(b => ({ feat: 'Ability Score Improvement', increase: { [a]: 1, [b]: 1 } })))];
const STR2 = { feat: 'Ability Score Improvement', increase: { strength: 2 } };
const scope = { effects_supported: ['supported'], effects_pending: ['pending'] };
const simpleRaw = id => ({ supported_starting_levels: [1, 2, 3, 4, 5], level_2: { choices: {}, ...scope },
  level_3: { subclass_options: [{ id, name: 'Subclass' }], ...scope }, level_4: { supported_asi_choices: structuredClone(ASI), ...scope }, level_5: { ...scope } });
const draftN = (level, subclassId) => ({ ...emptyStartingDraft(), startingLevel: level, subclassId: level >= 3 ? subclassId : '',
  ...(level >= 4 ? { level4Asi: structuredClone(STR2), level4ConConfirmed: true } : {}) });
const ctx = (extra = {}) => ({ spells: [], cantrips: [], ...extra });

const SIMPLE = [['Fighter', 'fighter', 'champion'], ['Rogue', 'rogue', 'assassin'], ['Monk', 'monk', 'open_hand']];

for (const [cls, key, subclass] of SIMPLE) {
  test(`startingCreationPayload.${cls}: bundle for every start level`, () => {
    const sources = { [key]: simpleRaw(subclass) };
    assert.deepEqual(startingCreationPayload(cls, draftN(1), ctx(sources)), { ok: true, fields: {} });
    assert.deepEqual(startingCreationPayload(cls, draftN(2), ctx(sources)), { ok: true, fields: { starting_level: 2, level_choices: { '2': {} } } });
    assert.deepEqual(startingCreationPayload(cls, draftN(3, subclass), ctx(sources)),
      { ok: true, fields: { starting_level: 3, level_choices: { '2': {}, '3': { subclass_id: subclass } } } });
    assert.deepEqual(startingCreationPayload(cls, draftN(4, subclass), ctx(sources)),
      { ok: true, fields: { starting_level: 4, level_choices: { '2': {}, '3': { subclass_id: subclass }, '4': { asi: STR2 } } } });
    assert.deepEqual(startingCreationPayload(cls, draftN(5, subclass), ctx(sources)),
      { ok: true, fields: { starting_level: 5, level_choices: { '2': {}, '3': { subclass_id: subclass }, '4': { asi: STR2 }, '5': {} } } });
  });

  test(`startingCreationPayload.${cls}: refuses a missing catalog, a missing subclass and an unconfirmed ASI`, () => {
    const sources = { [key]: simpleRaw(subclass) };
    const missing = startingCreationPayload(cls, draftN(2), ctx());
    assert.equal(missing.ok, false);
    assert.match(missing.message, new RegExp(`^${cls} seviye seçenekleri alınamadı`));
    assert.equal(startingCreationPayload(cls, draftN(3, ''), ctx(sources)).message, `Bir ${cls} alt sınıfı seçin.`);
    assert.equal(startingCreationPayload(cls, { ...draftN(4, subclass), level4ConConfirmed: false }, ctx(sources)).message, 'Ability Score Improvement seçimini onaylayın.');
    // Another class subclass id is not this class subclass: the catalog block is hidden and the start falls back to level 2.
    const other = SIMPLE.find(([, , id]) => id !== subclass)[2];
    assert.equal(startingCreationPayload(cls, draftN(3, other), { ...ctx(), [key]: simpleRaw(other) }).ok, false);
  });
}

test('startingCreationPayload: a caster bundle leaking into a Fighter start is refused with the class name', () => {
  const dirty = { ...draftN(2), level2Prepared: ['Shield'] };
  assert.deepEqual(startingCreationPayload('Fighter', dirty, ctx({ fighter: simpleRaw('champion') })),
    { ok: false, message: 'Fighter başlangıcı için önce diğer sınıfın veya üst seviyenin seçimlerini temizleyin.' });
});

test('startingCreationPayload.Barbarian: level 1 and 2, and a missing catalog blocks', () => {
  const barbarian = { supported_starting_levels: [1, 2], level_2: { choices: {}, ...scope } };
  assert.deepEqual(startingCreationPayload('Barbarian', draftN(1), ctx({ barbarian })), { ok: true, fields: {} });
  assert.deepEqual(startingCreationPayload('Barbarian', draftN(2), ctx({ barbarian })), { ok: true, fields: { starting_level: 2, level_choices: { '2': {} } } });
  assert.equal(startingCreationPayload('Barbarian', draftN(2), ctx()).ok, false);
});

test('startingCreationPayload.Paladin: start 2 bundle keeps the style and the one prepared spell', () => {
  const paladin = { supported_starting_levels: [1, 2], level_2: { prepared_spell_count: 1, prepared_spell_ids: ['Bless', 'Heroism'],
    fighting_style_options: ['Defense', 'Dueling', 'Blessed Warrior'], blessed_warrior_cantrip_count: 2, blessed_warrior_cantrip_ids: ['Guidance', 'Sacred Flame'], ...scope } };
  const draft = { ...draftN(2), paladinStyle: 'Defense', paladinCantrips: [], level2Prepared: ['Bless'] };
  assert.deepEqual(startingCreationPayload('Paladin', draft, ctx({ paladin, spells: ['Cure Wounds'] })),
    { ok: true, fields: { starting_level: 2, level_choices: { 2: { prepared_spells: ['Bless'], fighting_style: 'Defense' } } } });
  assert.equal(startingCreationPayload('Paladin', draft, ctx({ spells: ['Cure Wounds'] })).ok, false);
});

test('startingCreationPayload.Sorcerer and non-progression classes', () => {
  const ids = ['Magic Missile', 'Shield', 'Burning Hands', 'Chromatic Orb', 'Disguise Self', 'Detect Magic', 'Chaos Bolt'];
  const sorcerer = { supported_starting_levels: [1, 2, 3], level_2: { prepared_spell_count: 2, prepared_spell_ids: [...ids], metamagic_count: 2, metamagic_options: ['Quickened Spell', 'Twinned Spell', 'Careful Spell'] },
    level_3: { prepared_spell_count: 2, prepared_spell_ids: [...ids], subclass_options: [{ id: 'aberrant', name: 'Aberrant' }, { id: 'draconic', name: 'Draconic' }] },
    effects_pending_by_level: { '1': ['Innate'], '2': ['Font', 'Metamagic'], '3': ['Subclass'] } };
  const draft = { startingLevel: 3, level2Prepared: ['Burning Hands', 'Chromatic Orb'], metamagic: ['Quickened Spell', 'Twinned Spell'], level3Prepared: ['Disguise Self', 'Detect Magic'], subclassId: 'aberrant' };
  assert.deepEqual(startingCreationPayload('Sorcerer', draft, ctx({ sorcerer, spells: ['Magic Missile', 'Shield'] })), { ok: true, fields: { starting_level: 3, level_choices: {
    '2': { prepared_spells: ['Burning Hands', 'Chromatic Orb'], metamagic: ['Quickened Spell', 'Twinned Spell'] }, '3': { prepared_spells: ['Disguise Self', 'Detect Magic'], subclass_id: 'aberrant' } } } });
  assert.equal(startingCreationPayload('Sorcerer', draft, ctx({ spells: ['Magic Missile', 'Shield'] })).ok, false, 'a missing catalog blocks a high start');
  assert.deepEqual(startingCreationPayload('Wizard', emptyStartingDraft(), ctx()), { ok: true, fields: {} });
});
