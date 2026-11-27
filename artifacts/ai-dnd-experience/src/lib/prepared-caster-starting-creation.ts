import type { CharacterCreateInput, ClericStartingCreationOptions, WizardLevelChoices, WizardStartingCreationOptions } from '@workspace/api-client-react';
import { readAsiChoices, sourceAsiChoice } from './asi-choices.ts';
import type { StartingDraft } from './sorcerer-starting-creation.ts';

// Wizard and Cleric start 1-5. The server sends every level or none: a bad block hides the whole start, nothing is inferred from the class name.
export type CasterStarting = { wizard?: WizardStartingCreationOptions; cleric?: ClericStartingCreationOptions };
type CasterClass = 'Wizard' | 'Cleric';
type CasterOptions = WizardStartingCreationOptions | ClericStartingCreationOptions;
type Fields = { ok: true; fields: Pick<CharacterCreateInput, 'starting_level' | 'level_choices'> } | { ok: false; message: string };

const LEVELS = [1, 2, 3, 4, 5];
const SUBCLASS = { Wizard: 'evoker', Cleric: 'life_domain' } as const;
const BOOK_LEVELS = [2, 3, 4, 5] as const;

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}
function strings(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(item => typeof item === 'string' && item.trim().length > 0);
}
function uniqueIds(value: unknown): value is string[] {
  return strings(value) && value.length > 0 && new Set(value).size === value.length;
}

function readCommon(cls: CasterClass, raw: unknown): Record<string, unknown> | undefined {
  if (!record(raw) || !Array.isArray(raw.supported_starting_levels) || raw.supported_starting_levels.join() !== LEVELS.join()) return undefined;
  const { level_3: three, level_4: four, effects_pending_by_level: pending } = raw;
  if (!record(three) || !Array.isArray(three.subclass_options) || three.subclass_options.length !== 1) return undefined;
  const [subclass] = three.subclass_options;
  if (!record(subclass) || subclass.id !== SUBCLASS[cls] || typeof subclass.name !== 'string' || !subclass.name.trim()) return undefined;
  if (!record(four) || four.cantrip_count !== 1 || !uniqueIds(four.cantrip_ids) || !readAsiChoices(four.supported_asi_choices)) return undefined;
  if (!record(pending) || !LEVELS.every(level => strings(pending[String(level)]))) return undefined;
  return raw;
}

/** The Wizard's spellbook picks of each level 2-5: exactly two different ids from the level's own list. */
function readBook(raw: Record<string, unknown>): boolean {
  return BOOK_LEVELS.every(level => {
    const block = raw[`level_${level}`];
    return record(block) && block.spellbook_spell_count === 2 && uniqueIds(block.spellbook_spell_ids);
  });
}

function noPick(value: unknown): boolean {
  return record(value) && Object.keys(value).length === 0;
}

export function readWizardStartingCreationOptions(raw: unknown): WizardStartingCreationOptions | undefined {
  const common = readCommon('Wizard', raw);
  return common && readBook(common) ? structuredClone(common) as unknown as WizardStartingCreationOptions : undefined;
}

export function readClericStartingCreationOptions(raw: unknown): ClericStartingCreationOptions | undefined {
  const common = readCommon('Cleric', raw);
  return common && noPick(common.level_2) && noPick(common.level_5) ? structuredClone(common) as unknown as ClericStartingCreationOptions : undefined;
}

export function casterOptions(characterClass: string, sources: CasterStarting | undefined): CasterOptions | undefined {
  return characterClass === 'Wizard' ? sources?.wizard : characterClass === 'Cleric' ? sources?.cleric : undefined;
}

export const isCasterStartClass = (characterClass: string): characterClass is CasterClass => characterClass === 'Wizard' || characterClass === 'Cleric';

type BookField = 'level2Prepared' | 'level3Prepared' | 'level4Prepared' | 'level5Prepared';
const BOOK_FIELDS: Record<(typeof BOOK_LEVELS)[number], BookField> = { 2: 'level2Prepared', 3: 'level3Prepared', 4: 'level4Prepared', 5: 'level5Prepared' };

function wizardBlock(metadata: CasterOptions, level: (typeof BOOK_LEVELS)[number]) {
  return (metadata as unknown as Record<string, { spellbook_spell_count: number; spellbook_spell_ids: string[] }>)[`level_${level}`];
}

/** The spells a Wizard may still add at `level`: the level's own list minus the creation book and every earlier pick. */
export function availableBookSpells(metadata: CasterOptions, draft: StartingDraft, initialSpells: string[], level: (typeof BOOK_LEVELS)[number]): string[] {
  const taken = [...initialSpells, ...BOOK_LEVELS.filter(earlier => earlier < level).flatMap(earlier => draft[BOOK_FIELDS[earlier]] ?? [])];
  return wizardBlock(metadata, level).spellbook_spell_ids.filter(id => !taken.includes(id));
}

export function availableCasterCantrips(metadata: CasterOptions, initialCantrips: string[]): string[] {
  return metadata.level_4.cantrip_ids.filter(id => !initialCantrips.includes(id));
}

function exactPicks(picks: string[], count: number, allowed: string[]): boolean {
  return picks.length === count && new Set(picks).size === count && picks.every(id => allowed.includes(id));
}

/** Clears a pick the source no longer allows (a changed creation spell or cantrip, a lower level); a missing catalog keeps the draft and blocks submission. */
export function pruneCasterDraft(cls: CasterClass, draft: StartingDraft, metadata: CasterOptions | undefined, initialSpells: string[], initialCantrips: string[]): StartingDraft {
  if (!metadata || draft.startingLevel === 1) return draft;
  const next: StartingDraft = { ...draft, level4Cantrips: draft.startingLevel >= 4 ? (draft.level4Cantrips ?? []).filter(id => availableCasterCantrips(metadata, initialCantrips).includes(id)) : [] };
  if (cls === 'Wizard') {
    for (const level of BOOK_LEVELS) {
      const field = BOOK_FIELDS[level];
      next[field] = level > draft.startingLevel ? [] : (draft[field] ?? []).filter((id, index, all) => all.indexOf(id) === index && availableBookSpells(metadata, next, initialSpells, level).includes(id));
    }
  }
  if (draft.startingLevel < 3 || !metadata.level_3.subclass_options.some(option => option.id === draft.subclassId)) next.subclassId = '';
  const asi = draft.startingLevel >= 4 && draft.level4Asi ? sourceAsiChoice(metadata.level_4.supported_asi_choices, draft.level4Asi) : undefined;
  if (asi) next.level4Asi = asi; else delete next.level4Asi;
  next.level4ConConfirmed = draft.level4ConConfirmed === true && asi !== undefined;
  const picks = ['level2Prepared', 'level3Prepared', 'level4Prepared', 'level5Prepared', 'level4Cantrips'] as const;
  const unchanged = picks.every(field => (next[field] ?? []).join() === (draft[field] ?? []).join()) && next.subclassId === draft.subclassId
    && JSON.stringify(next.level4Asi) === JSON.stringify(draft.level4Asi) && next.level4ConConfirmed === (draft.level4ConConfirmed === true);
  return unchanged ? draft : next;
}

/** One place that turns the draft and the catalog into the starting-level part of the request, or the reason it cannot be built. */
export function casterStartingFields(cls: CasterClass, draft: StartingDraft, metadata: CasterOptions | undefined, initialSpells: string[], initialCantrips: string[]): Fields {
  const level = draft.startingLevel;
  if (draft.metamagic.length || draft.primalSkill || draft.paladinStyle || draft.paladinCantrips?.length || (cls === 'Cleric' && BOOK_LEVELS.some(at => draft[BOOK_FIELDS[at]]?.length)))
    return { ok: false, message: `${cls} başlangıcı için önce diğer sınıfın seçimlerini temizleyin.` };
  if (BOOK_LEVELS.some(at => at > level && (draft[BOOK_FIELDS[at]]?.length ?? 0) > 0) || (level < 3 && draft.subclassId) || (level < 4 && (draft.level4Cantrips?.length || draft.level4Asi || draft.level4ConConfirmed)))
    return { ok: false, message: 'Üst seviye seçimlerini temizleyin.' };
  if (level === 1) return { ok: true, fields: {} };
  if (!metadata?.supported_starting_levels.includes(level)) return { ok: false, message: `${cls} seviye seçenekleri alınamadı. Yeniden deneyin veya açıkça seviye 1 seçin.` };
  if (cls === 'Wizard') {
    for (const at of BOOK_LEVELS.filter(step => step <= level)) {
      if (!exactPicks(draft[BOOK_FIELDS[at]] ?? [], 2, availableBookSpells(metadata, draft, initialSpells, at))) return { ok: false, message: `Seviye ${at} için iki farklı yeni büyü seçin.` };
    }
  }
  const book = (at: (typeof BOOK_LEVELS)[number]) => cls === 'Wizard' ? { spellbook_spells: [...draft[BOOK_FIELDS[at]] ?? []] } : {};
  const choices: Record<string, unknown> = { '2': book(2) };
  if (level >= 3) {
    if (!metadata.level_3.subclass_options.some(option => option.id === draft.subclassId)) return { ok: false, message: `Bir ${cls} alt sınıfı seçin.` };
    choices['3'] = { ...book(3), subclass_id: draft.subclassId };
  }
  if (level >= 4) {
    const asi = draft.level4Asi ? sourceAsiChoice(metadata.level_4.supported_asi_choices, draft.level4Asi) : undefined;
    if (!exactPicks(draft.level4Cantrips ?? [], 1, availableCasterCantrips(metadata, initialCantrips))) return { ok: false, message: 'Seviye 4 için bir yeni cantrip seçin.' };
    if (!asi || draft.level4ConConfirmed !== true) return { ok: false, message: 'Seviye 4 için sunucunun sunduğu ASI seçimini yapıp onaylayın.' };
    choices['4'] = { ...book(4), cantrips: [...draft.level4Cantrips ?? []], asi };
  }
  if (level === 5) choices['5'] = book(5);
  return { ok: true, fields: { starting_level: level, level_choices: choices as unknown as WizardLevelChoices } };
}
