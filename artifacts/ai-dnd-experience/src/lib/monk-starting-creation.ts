import type { CharacterCreateInput, MonkLevelChoices, MonkStartingCreationOptions } from '@workspace/api-client-react';
import type { StartingDraft } from './sorcerer-starting-creation';
import { readAsiChoices, sourceAsiChoice } from './asi-choices.ts';

const LEVEL_TWO = 2;
const LEVEL_THREE = 3;
const LEVEL_FOUR = 4;
const LEVEL_FIVE = 5;
const LEVEL_THREE_KEYS = ['subclass_options', 'effects_supported', 'effects_pending'];
const LEVEL_FOUR_KEYS = ['supported_asi_choices', 'effects_supported', 'effects_pending'];
const LEVEL_FIVE_KEYS = ['effects_supported', 'effects_pending'];
const OPEN_HAND = 'open_hand';

type Level3 = NonNullable<MonkStartingCreationOptions['level_3']>;
type Level4 = NonNullable<MonkStartingCreationOptions['level_4']>;
type Level5 = NonNullable<MonkStartingCreationOptions['level_5']>;

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}
function effects(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(item => typeof item === 'string' && item.trim().length > 0);
}
function hasExactKeys(value: Record<string, unknown>, keys: string[]): boolean {
  return Object.keys(value).length === keys.length && keys.every(key => key in value);
}

function readLevelThree(raw: unknown): Level3 | undefined {
  if (!record(raw) || !hasExactKeys(raw, LEVEL_THREE_KEYS) || !Array.isArray(raw.subclass_options) || raw.subclass_options.length !== 1) return undefined;
  const [subclass] = raw.subclass_options;
  if (!record(subclass) || !hasExactKeys(subclass, ['id', 'name']) || subclass.id !== OPEN_HAND || typeof subclass.name !== 'string' || !subclass.name.trim()
    || !effects(raw.effects_supported) || !effects(raw.effects_pending)) return undefined;
  return { subclass_options: [{ id: OPEN_HAND, name: subclass.name }], effects_supported: [...raw.effects_supported], effects_pending: [...raw.effects_pending] };
}

function readLevelFour(raw: unknown): Level4 | undefined {
  if (!record(raw) || !hasExactKeys(raw, LEVEL_FOUR_KEYS)) return undefined;
  const choices = readAsiChoices(raw.supported_asi_choices);
  if (!choices || !effects(raw.effects_supported) || !effects(raw.effects_pending)) return undefined;
  return { supported_asi_choices: choices, effects_supported: [...raw.effects_supported], effects_pending: [...raw.effects_pending] };
}

function readLevelFive(raw: unknown): Level5 | undefined {
  if (!record(raw) || !hasExactKeys(raw, LEVEL_FIVE_KEYS) || !effects(raw.effects_supported) || !effects(raw.effects_pending)) return undefined;
  return { effects_supported: [...raw.effects_supported], effects_pending: [...raw.effects_pending] };
}

/** A class name alone never grants a higher start. Each level needs its own validated block; a bad block hides it and everything above. */
export function readMonkStartingCreationOptions(raw: unknown): MonkStartingCreationOptions | undefined {
  if (!record(raw) || !Array.isArray(raw.supported_starting_levels)) return undefined;
  const levels = raw.supported_starting_levels;
  if (levels.length < LEVEL_TWO || levels.length > LEVEL_FIVE || !levels.every((level, index) => level === index + 1)) return undefined;
  if (!record(raw.level_2) || !record(raw.level_2.choices) || Object.keys(raw.level_2.choices).length !== 0
    || !effects(raw.level_2.effects_supported) || !effects(raw.level_2.effects_pending)) return undefined;
  const claimed = levels.length;
  const base = { level_2: { choices: {}, effects_supported: [...raw.level_2.effects_supported], effects_pending: [...raw.level_2.effects_pending] } };
  const three = claimed >= LEVEL_THREE ? readLevelThree(raw.level_3) : undefined;
  if (!three) return { supported_starting_levels: [1, LEVEL_TWO], ...base };
  const four = claimed >= LEVEL_FOUR ? readLevelFour(raw.level_4) : undefined;
  if (!four) return { supported_starting_levels: [1, LEVEL_TWO, LEVEL_THREE], ...base, level_3: three };
  const five = claimed >= LEVEL_FIVE ? readLevelFive(raw.level_5) : undefined;
  if (!five) return { supported_starting_levels: [1, LEVEL_TWO, LEVEL_THREE, LEVEL_FOUR], ...base, level_3: three, level_4: four };
  return { supported_starting_levels: [1, LEVEL_TWO, LEVEL_THREE, LEVEL_FOUR, LEVEL_FIVE], ...base, level_3: three, level_4: four, level_5: five };
}

/** Uses the shared class-switch-cleared draft, but never inherits a caster or Barbarian bundle. */
export function monkStartingCreationFields(draft: StartingDraft, metadata: MonkStartingCreationOptions | undefined):
  { ok: true; fields: Pick<CharacterCreateInput, 'starting_level' | 'level_choices'> } | { ok: false; message: string } {
  const level = draft.startingLevel;
  if (draft.level2Prepared.length || draft.metamagic.length || draft.level3Prepared.length || draft.primalSkill
    || draft.level4Prepared?.length || draft.level4Cantrips?.length || draft.level5Prepared?.length
    || (draft.subclassId && level < LEVEL_THREE) || ((draft.level4Asi || draft.level4ConConfirmed) && level < LEVEL_FOUR))
    return { ok: false, message: 'Monk başlangıcı için önce diğer sınıfın veya üst seviyenin seçimlerini temizleyin.' };
  if (level === 1) return { ok: true, fields: {} };
  const source = readMonkStartingCreationOptions(metadata);
  if (!source) return { ok: false, message: 'Monk seviye seçenekleri alınamadı. Yeniden deneyin veya açıkça seviye 1 seçin.' };
  if (!source.supported_starting_levels.includes(level)) return { ok: false, message: `Monk seviye ${level} kaynağı doğrulanamadı. Yeniden deneyin veya daha düşük bir seviye seçin.` };
  if (level === LEVEL_TWO) return { ok: true, fields: { starting_level: LEVEL_TWO, level_choices: { '2': {} } } };
  const subclass = source.level_3?.subclass_options.find(option => option.id === draft.subclassId);
  if (!subclass) return { ok: false, message: 'Bir Monk alt sınıfı seçin.' };
  const choices: MonkLevelChoices = { '2': {}, '3': { subclass_id: subclass.id } };
  if (level >= LEVEL_FOUR) {
    // Only an explicit pick from the server's family, explicitly confirmed; nothing is defaulted for the player.
    const asi = draft.level4Asi ? sourceAsiChoice(source.level_4?.supported_asi_choices, draft.level4Asi) : undefined;
    if (!asi) return { ok: false, message: 'Seviye 4 için sunucunun sunduğu bir Ability Score Improvement seçin.' };
    if (draft.level4ConConfirmed !== true) return { ok: false, message: 'Ability Score Improvement seçimini onaylayın.' };
    choices['4'] = { asi };
  }
  if (level === LEVEL_FIVE) choices['5'] = {};
  return { ok: true, fields: { starting_level: level, level_choices: choices } };
}

/** Clears a pick the source no longer allows while the catalog is known; a catalog gap keeps the pick and blocks submission instead. */
export function pruneMonkDraft(draft: StartingDraft, metadata: MonkStartingCreationOptions | undefined): StartingDraft {
  if (draft.startingLevel < LEVEL_THREE) return draft;
  const source = readMonkStartingCreationOptions(metadata);
  if (!source) return draft;
  const subclassId = source.level_3?.subclass_options.some(option => option.id === draft.subclassId) ? draft.subclassId : '';
  const four = draft.startingLevel >= LEVEL_FOUR ? source.level_4 : undefined;
  const level4Asi = draft.level4Asi && four ? sourceAsiChoice(four.supported_asi_choices, draft.level4Asi) : undefined;
  const level4ConConfirmed = draft.level4ConConfirmed === true && level4Asi !== undefined;
  if (subclassId === draft.subclassId && JSON.stringify(level4Asi) === JSON.stringify(draft.level4Asi) && level4ConConfirmed === (draft.level4ConConfirmed ?? false)) return draft;
  const { level4Asi: _asi, ...rest } = draft;
  return { ...rest, subclassId, ...(level4Asi ? { level4Asi } : {}), level4ConConfirmed };
}
