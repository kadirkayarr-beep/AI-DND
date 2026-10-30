import type { BarbarianLevel3Choices, BarbarianLevelChoices, BarbarianStartingCreationOptions, CharacterCreateInput } from '@workspace/api-client-react';
import type { StartingDraft } from './sorcerer-starting-creation';
import { readAsiChoices, sourceAsiChoice } from './asi-choices.ts';

const LEVEL_TWO = 2;
const LEVEL_THREE = 3;
const LEVEL_FOUR = 4;
const LEVEL_FIVE = 5;
const LEVEL_FOUR_KEYS = ['supported_asi_choices', 'effects_supported', 'effects_pending'];
const LEVEL_FIVE_KEYS = ['effects_supported', 'effects_pending'];
const BERSERKER = 'berserker';
const PRIMAL_SKILLS = ['Animal Handling', 'Athletics', 'Intimidation', 'Nature', 'Perception', 'Survival'];

type Level3 = NonNullable<BarbarianStartingCreationOptions['level_3']>;
type Level4 = NonNullable<BarbarianStartingCreationOptions['level_4']>;
type Level5 = NonNullable<BarbarianStartingCreationOptions['level_5']>;
type Level3Skill = BarbarianLevel3Choices['primal_knowledge_skill'];

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}
function effects(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(item => typeof item === 'string' && item.trim().length > 0);
}

function hasExactKeys(value: Record<string, unknown>, keys: string[]): boolean {
  return Object.keys(value).length === keys.length && keys.every(key => key in value);
}

/** The advertised levels must be the exact prefix 1..n (n = 2..5); the level blocks then decide how far this reader goes. */
function levelsArePrefix(levels: unknown[]): boolean {
  return levels.length >= LEVEL_TWO && levels.length <= LEVEL_FIVE && levels.every((level, index) => level === index + 1);
}

/** Exactly the source vocabulary: one Berserker subclass and the six Barbarian class skills. */
function readLevelThree(raw: unknown): Level3 | undefined {
  if (!record(raw) || !Array.isArray(raw.subclass_options) || raw.subclass_options.length !== 1) return undefined;
  const [subclass] = raw.subclass_options;
  const skills = raw.primal_knowledge_skill_options;
  if (!record(subclass) || subclass.id !== BERSERKER || typeof subclass.name !== 'string' || !subclass.name.trim()
    || !Array.isArray(skills) || skills.length !== PRIMAL_SKILLS.length || new Set(skills).size !== skills.length
    || !skills.every(skill => PRIMAL_SKILLS.includes(skill)) || !effects(raw.effects_supported) || !effects(raw.effects_pending)) return undefined;
  return { subclass_options: [{ id: BERSERKER, name: subclass.name }], primal_knowledge_skill_options: [...skills],
    effects_supported: [...raw.effects_supported], effects_pending: [...raw.effects_pending] };
}

/** Level 4: the server's ordinary-ASI family (validated by the shared ASI reader) and its effect lists; nothing else. */
function readLevelFour(raw: unknown): Level4 | undefined {
  if (!record(raw) || !hasExactKeys(raw, LEVEL_FOUR_KEYS)) return undefined;
  const choices = readAsiChoices(raw.supported_asi_choices);
  if (!choices || !effects(raw.effects_supported) || !effects(raw.effects_pending)) return undefined;
  return { supported_asi_choices: choices, effects_supported: [...raw.effects_supported], effects_pending: [...raw.effects_pending] };
}

/** Level 5 has no choices: only its effect lists. */
function readLevelFive(raw: unknown): Level5 | undefined {
  if (!record(raw) || !hasExactKeys(raw, LEVEL_FIVE_KEYS) || !effects(raw.effects_supported) || !effects(raw.effects_pending)) return undefined;
  return { effects_supported: [...raw.effects_supported], effects_pending: [...raw.effects_pending] };
}

/** A class name alone never grants a higher start. Each level needs its own validated block; a bad block hides it and everything above. */
export function readBarbarianStartingCreationOptions(raw: unknown): BarbarianStartingCreationOptions | undefined {
  if (!record(raw) || !Array.isArray(raw.supported_starting_levels)
    || !levelsArePrefix(raw.supported_starting_levels)
    || !record(raw.level_2) || !record(raw.level_2.choices) || Object.keys(raw.level_2.choices).length !== 0
    || !effects(raw.level_2.effects_supported) || !effects(raw.level_2.effects_pending)) return undefined;
  const claimed = raw.supported_starting_levels.length;
  const base = { level_2: { choices: {},
    effects_supported: [...raw.level_2.effects_supported], effects_pending: [...raw.level_2.effects_pending] } };
  const three = claimed >= LEVEL_THREE ? readLevelThree(raw.level_3) : undefined;
  if (!three) return { supported_starting_levels: [1, LEVEL_TWO], ...base };
  const four = claimed >= LEVEL_FOUR ? readLevelFour(raw.level_4) : undefined;
  if (!four) return { supported_starting_levels: [1, LEVEL_TWO, LEVEL_THREE], ...base, level_3: three };
  const five = claimed >= LEVEL_FIVE ? readLevelFive(raw.level_5) : undefined;
  if (!five) return { supported_starting_levels: [1, LEVEL_TWO, LEVEL_THREE, LEVEL_FOUR], ...base, level_3: three, level_4: four };
  return { supported_starting_levels: [1, LEVEL_TWO, LEVEL_THREE, LEVEL_FOUR, LEVEL_FIVE], ...base, level_3: three, level_4: four, level_5: five };
}

/** Uses the shared class-switch-cleared draft, but never inherits a caster choice bundle. */
export function barbarianStartingCreationFields(draft: StartingDraft, metadata: BarbarianStartingCreationOptions | undefined, ownedSkills: readonly string[] = []):
  { ok: true; fields: Pick<CharacterCreateInput, 'starting_level' | 'level_choices'> } | { ok: false; message: string } {
  const level = draft.startingLevel;
  if (draft.level2Prepared.length || draft.metamagic.length || draft.level3Prepared.length
    || draft.level4Prepared?.length || draft.level4Cantrips?.length || draft.level5Prepared?.length
    || ((draft.subclassId || draft.primalSkill) && level < LEVEL_THREE)
    || ((draft.level4Asi || draft.level4ConConfirmed) && level < LEVEL_FOUR))
    return { ok: false, message: 'Barbarian başlangıcı için önce diğer sınıfın veya üst seviyenin seçimlerini temizleyin.' };
  if (level === 1) return { ok: true, fields: {} };
  if (![LEVEL_TWO, LEVEL_THREE, LEVEL_FOUR, LEVEL_FIVE].includes(level)) return { ok: false, message: 'Barbarian için yalnız başlangıç seviyesi 1 ile 5 arası destekleniyor.' };
  const source = readBarbarianStartingCreationOptions(metadata);
  if (!source) return { ok: false, message: 'Barbarian seviye seçenekleri alınamadı. Yeniden deneyin veya açıkça seviye 1 seçin.' };
  if (!source.supported_starting_levels.includes(level)) return { ok: false, message: `Barbarian seviye ${level} kaynağı doğrulanamadı. Yeniden deneyin veya daha düşük bir seviye seçin.` };
  if (level === LEVEL_TWO) return { ok: true, fields: { starting_level: LEVEL_TWO, level_choices: { '2': {} } } };
  const three = source.level_3;
  if (!three) return { ok: false, message: 'Barbarian seviye 3 kaynağı doğrulanamadı. Yeniden deneyin veya seviye 1 ya da 2 seçin.' };
  const subclass = three.subclass_options.find(option => option.id === draft.subclassId);
  if (!subclass) return { ok: false, message: 'Bir alt sınıf seçin.' };
  const skill = three.primal_knowledge_skill_options.find(option => option === draft.primalSkill);
  if (!skill) return { ok: false, message: 'Primal Knowledge için bir beceri seçin.' };
  if (ownedSkills.includes(skill)) return { ok: false, message: 'Bu beceriye zaten sahipsin; Primal Knowledge için başka bir beceri seçin.' };
  const choices: BarbarianLevelChoices = { '2': {}, '3': { subclass_id: subclass.id, primal_knowledge_skill: skill as Level3Skill } };
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

/** Clears a pick the source or the character no longer allows; returns the same draft when nothing changed. */
export function pruneBarbarianDraft(draft: StartingDraft, metadata: BarbarianStartingCreationOptions | undefined, ownedSkills: readonly string[]): StartingDraft {
  if (draft.startingLevel < LEVEL_THREE) return draft;
  const source = readBarbarianStartingCreationOptions(metadata);
  const three = source?.level_3;
  const subclassId = three?.subclass_options.some(option => option.id === draft.subclassId) ? draft.subclassId : '';
  const eligible = three?.primal_knowledge_skill_options.filter(skill => !ownedSkills.includes(skill)) ?? [];
  const primalSkill = draft.primalSkill && eligible.includes(draft.primalSkill) ? draft.primalSkill : undefined;
  const four = draft.startingLevel >= LEVEL_FOUR ? source?.level_4 : undefined;
  const level4Asi = draft.level4Asi && four ? sourceAsiChoice(four.supported_asi_choices, draft.level4Asi) : undefined;
  const level4ConConfirmed = draft.level4ConConfirmed === true && level4Asi !== undefined;
  if (subclassId === draft.subclassId && primalSkill === draft.primalSkill
    && JSON.stringify(level4Asi) === JSON.stringify(draft.level4Asi) && level4ConConfirmed === (draft.level4ConConfirmed ?? false)) return draft;
  const { primalSkill: _dropped, level4Asi: _asi, ...rest } = draft;
  return { ...rest, subclassId, ...(primalSkill ? { primalSkill } : {}), ...(level4Asi ? { level4Asi } : {}), level4ConConfirmed };
}
