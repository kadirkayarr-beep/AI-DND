import type { CharacterCreateInput, PaladinLevelChoices, PaladinStartingCreationOptions } from '@workspace/api-client-react';
import type { StartingDraft } from './sorcerer-starting-creation';
import { readAsiChoices, sourceAsiChoice } from './asi-choices.ts';

const LEVEL_TWO = 2;
const LEVEL_THREE = 3;
const LEVEL_FOUR = 4;
const LEVEL_FIVE = 5;
const DEVOTION = 'oath_of_devotion';
const BLESSED_WARRIOR = 'Blessed Warrior';
const CANTRIPS = 2;
const LEVEL_TWO_KEYS = ['prepared_spell_count', 'prepared_spell_ids', 'fighting_style_options', 'blessed_warrior_cantrip_count', 'blessed_warrior_cantrip_ids', 'effects_supported', 'effects_pending'];
const LEVEL_THREE_KEYS = ['prepared_spell_count', 'prepared_spell_ids', 'subclass_options', 'effects_supported', 'effects_pending'];
const LEVEL_FOUR_KEYS = ['prepared_spell_count', 'prepared_spell_ids', 'supported_asi_choices', 'effects_supported', 'effects_pending'];
const LEVEL_FIVE_KEYS = ['prepared_spell_count', 'prepared_spell_ids', 'effects_supported', 'effects_pending'];

type Level2 = PaladinStartingCreationOptions['level_2'];
type Level3 = NonNullable<PaladinStartingCreationOptions['level_3']>;
type Level4 = NonNullable<PaladinStartingCreationOptions['level_4']>;
type Level5 = NonNullable<PaladinStartingCreationOptions['level_5']>;

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}
function strings(value: unknown): value is string[] {
  return Array.isArray(value) && value.length > 0 && value.every(item => typeof item === 'string' && item.trim().length > 0) && new Set(value).size === value.length;
}
function effects(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(item => typeof item === 'string' && item.trim().length > 0);
}
function hasExactKeys(value: Record<string, unknown>, keys: string[]): boolean {
  return Object.keys(value).length === keys.length && keys.every(key => key in value);
}
function preparedOk(raw: Record<string, unknown>): boolean {
  return raw.prepared_spell_count === 1 && strings(raw.prepared_spell_ids) && effects(raw.effects_supported) && effects(raw.effects_pending);
}

function readLevelTwo(raw: unknown): Level2 | undefined {
  if (!record(raw) || !hasExactKeys(raw, LEVEL_TWO_KEYS) || !preparedOk(raw) || raw.blessed_warrior_cantrip_count !== CANTRIPS
    || !strings(raw.fighting_style_options) || !raw.fighting_style_options.includes(BLESSED_WARRIOR)
    || !strings(raw.blessed_warrior_cantrip_ids) || raw.blessed_warrior_cantrip_ids.length < CANTRIPS) return undefined;
  return structuredClone(raw) as unknown as Level2;
}

function readLevelThree(raw: unknown): Level3 | undefined {
  if (!record(raw) || !hasExactKeys(raw, LEVEL_THREE_KEYS) || !preparedOk(raw) || !Array.isArray(raw.subclass_options) || raw.subclass_options.length !== 1) return undefined;
  const [subclass] = raw.subclass_options;
  if (!record(subclass) || !hasExactKeys(subclass, ['id', 'name']) || subclass.id !== DEVOTION || typeof subclass.name !== 'string' || !subclass.name.trim()) return undefined;
  return structuredClone(raw) as unknown as Level3;
}

function readLevelFour(raw: unknown): Level4 | undefined {
  if (!record(raw) || !hasExactKeys(raw, LEVEL_FOUR_KEYS) || !preparedOk(raw)) return undefined;
  const choices = readAsiChoices(raw.supported_asi_choices);
  return choices ? { ...(structuredClone(raw) as unknown as Level4), supported_asi_choices: choices } : undefined;
}

function readLevelFive(raw: unknown): Level5 | undefined {
  if (!record(raw) || !hasExactKeys(raw, LEVEL_FIVE_KEYS) || !preparedOk(raw)) return undefined;
  return structuredClone(raw) as unknown as Level5;
}

/** A class name alone never grants a higher start. Each level needs its own validated block; a bad block hides it and everything above. */
export function readPaladinStartingCreationOptions(raw: unknown): PaladinStartingCreationOptions | undefined {
  if (!record(raw) || !Array.isArray(raw.supported_starting_levels)) return undefined;
  const levels = raw.supported_starting_levels;
  if (levels.length < LEVEL_TWO || levels.length > LEVEL_FIVE || !levels.every((level, index) => level === index + 1)) return undefined;
  const two = readLevelTwo(raw.level_2);
  if (!two) return undefined;
  const claimed = levels.length;
  const three = claimed >= LEVEL_THREE ? readLevelThree(raw.level_3) : undefined;
  if (!three) return { supported_starting_levels: [1, LEVEL_TWO], level_2: two };
  const four = claimed >= LEVEL_FOUR ? readLevelFour(raw.level_4) : undefined;
  if (!four) return { supported_starting_levels: [1, LEVEL_TWO, LEVEL_THREE], level_2: two, level_3: three };
  const five = claimed >= LEVEL_FIVE ? readLevelFive(raw.level_5) : undefined;
  if (!five) return { supported_starting_levels: [1, LEVEL_TWO, LEVEL_THREE, LEVEL_FOUR], level_2: two, level_3: three, level_4: four };
  return { supported_starting_levels: [1, LEVEL_TWO, LEVEL_THREE, LEVEL_FOUR, LEVEL_FIVE], level_2: two, level_3: three, level_4: four, level_5: five };
}

function pick(list: string[] | undefined): string {
  return list?.[0] ?? '';
}

/** One new spell per step, each a server-listed id, none repeated against the level-1 list or an earlier step. */
function preparedProblem(draft: StartingDraft, source: PaladinStartingCreationOptions, initial: string[]): string | null {
  const steps: [number, string, string[] | undefined][] = [[LEVEL_TWO, pick(draft.level2Prepared), source.level_2.prepared_spell_ids], [LEVEL_THREE, pick(draft.level3Prepared), source.level_3?.prepared_spell_ids],
    [LEVEL_FOUR, pick(draft.level4Prepared), source.level_4?.prepared_spell_ids], [LEVEL_FIVE, pick(draft.level5Prepared), source.level_5?.prepared_spell_ids]];
  const taken = steps.filter(([level]) => level <= draft.startingLevel);
  const missing = taken.find(([, spell, offered]) => !spell || !offered?.includes(spell));
  if (missing) return `Seviye ${missing[0]} için sunucunun sunduğu bir hazır büyü seçin.`;
  const repeated = taken.find(([, spell], index) => initial.includes(spell) || taken.findIndex(([, other]) => other === spell) !== index);
  return repeated ? `Seviye ${repeated[0]} büyüsü daha önce seçildi.` : null;
}

function styleChoice(draft: StartingDraft, source: PaladinStartingCreationOptions): { fighting_style: string; cantrips?: string[] } | null {
  const style = draft.paladinStyle ?? '';
  if (!source.level_2.fighting_style_options.includes(style)) return null;
  if (style !== BLESSED_WARRIOR) return { fighting_style: style };
  const cantrips = draft.paladinCantrips ?? [];
  const valid = cantrips.length === CANTRIPS && new Set(cantrips).size === CANTRIPS && cantrips.every(id => source.level_2.blessed_warrior_cantrip_ids.includes(id));
  return valid ? { fighting_style: style, cantrips: [...cantrips] } : null;
}

/** Uses the shared class-switch-cleared draft, but never inherits a Sorcerer or Barbarian bundle. */
export function paladinStartingCreationFields(draft: StartingDraft, metadata: PaladinStartingCreationOptions | undefined, initialSpells: string[]):
  { ok: true; fields: Pick<CharacterCreateInput, 'starting_level' | 'level_choices'> } | { ok: false; message: string } {
  const level = draft.startingLevel;
  if (draft.metamagic.length || draft.primalSkill || draft.level4Cantrips?.length || (draft.subclassId && level < LEVEL_THREE) || ((draft.level4Asi || draft.level4ConConfirmed) && level < LEVEL_FOUR))
    return { ok: false, message: 'Paladin başlangıcı için önce diğer sınıfın veya üst seviyenin seçimlerini temizleyin.' };
  if (level === 1) return { ok: true, fields: {} };
  const source = readPaladinStartingCreationOptions(metadata);
  if (!source) return { ok: false, message: 'Paladin seviye seçenekleri alınamadı. Yeniden deneyin veya açıkça seviye 1 seçin.' };
  if (!source.supported_starting_levels.includes(level)) return { ok: false, message: `Paladin seviye ${level} kaynağı doğrulanamadı. Yeniden deneyin veya daha düşük bir seviye seçin.` };
  const problem = preparedProblem(draft, source, initialSpells);
  if (problem) return { ok: false, message: problem };
  const style = styleChoice(draft, source);
  if (!style) return { ok: false, message: 'Bir Fighting Style seçin; Blessed Warrior için iki farklı Cleric cantrip gerekir.' };
  const choices: PaladinLevelChoices = { '2': { prepared_spells: [pick(draft.level2Prepared)], fighting_style: style.fighting_style as PaladinLevelChoices['2']['fighting_style'], ...(style.cantrips ? { cantrips: style.cantrips } : {}) } };
  if (level >= LEVEL_THREE) {
    if (!source.level_3?.subclass_options.some(option => option.id === draft.subclassId)) return { ok: false, message: 'Bir Paladin alt sınıfı seçin.' };
    choices['3'] = { prepared_spells: [pick(draft.level3Prepared)], subclass_id: DEVOTION };
  }
  if (level >= LEVEL_FOUR) {
    const asi = draft.level4Asi ? sourceAsiChoice(source.level_4?.supported_asi_choices, draft.level4Asi) : undefined;
    if (!asi) return { ok: false, message: 'Seviye 4 için sunucunun sunduğu bir Ability Score Improvement seçin.' };
    if (draft.level4ConConfirmed !== true) return { ok: false, message: 'Ability Score Improvement seçimini onaylayın.' };
    choices['4'] = { prepared_spells: [pick(draft.level4Prepared)], asi };
  }
  if (level === LEVEL_FIVE) choices['5'] = { prepared_spells: [pick(draft.level5Prepared)] };
  return { ok: true, fields: { starting_level: level, level_choices: choices } };
}

/** Clears a pick the source no longer allows while the catalog is known; a catalog gap keeps the pick and blocks submission instead. */
export function prunePaladinDraft(draft: StartingDraft, metadata: PaladinStartingCreationOptions | undefined): StartingDraft {
  if (draft.startingLevel < LEVEL_TWO) return draft;
  const source = readPaladinStartingCreationOptions(metadata);
  if (!source) return draft;
  const keep = (list: string[], offered: string[] | undefined) => (list.length && !offered?.includes(list[0]) ? [] : list);
  const next: StartingDraft = {
    ...draft,
    level2Prepared: keep(draft.level2Prepared, source.level_2.prepared_spell_ids),
    level3Prepared: keep(draft.level3Prepared, source.level_3?.prepared_spell_ids),
    level4Prepared: keep(draft.level4Prepared ?? [], source.level_4?.prepared_spell_ids),
    level5Prepared: keep(draft.level5Prepared ?? [], source.level_5?.prepared_spell_ids),
    subclassId: source.level_3?.subclass_options.some(option => option.id === draft.subclassId) ? draft.subclassId : '',
    paladinStyle: draft.paladinStyle && source.level_2.fighting_style_options.includes(draft.paladinStyle) ? draft.paladinStyle : '',
    paladinCantrips: (draft.paladinCantrips ?? []).filter(id => source.level_2.blessed_warrior_cantrip_ids.includes(id)),
  };
  return JSON.stringify(next) === JSON.stringify(draft) ? draft : next;
}
