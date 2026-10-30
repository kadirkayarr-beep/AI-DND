import { readAsiChoices, sourceAsiChoice, asiChoiceKey, type AsiChoice } from './asi-choices.ts';
import type { CharacterCreateInput, SorcererStartingCreationOptions, SorcererLevelChoices } from '@workspace/api-client-react';

/** Choice draft only: the server owns all character mechanics and resources. */
export type StartingDraft = {
  startingLevel: 1 | 2 | 3 | 4 | 5;
  level2Prepared: string[];
  metamagic: string[];
  level3Prepared: string[];
  subclassId: string;
  /** Barbarian start 3-5: the Primal Knowledge class skill (level 4/5 also reuse level4Asi and its explicit confirmation). */
  primalSkill?: string;
  level4Prepared?: string[];
  level4Cantrips?: string[];
  level4ConConfirmed?: boolean;
  level4Asi?: AsiChoice;
  level5Prepared?: string[];
};

export type Metadata = Omit<SorcererStartingCreationOptions, 'level_4' | 'level_5'> & Partial<Pick<SorcererStartingCreationOptions, 'level_4' | 'level_5'>>;
type Validation = { ok: boolean; message: string };

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function strings(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(item => typeof item === 'string' && item.trim().length > 0);
}

function uniqueOptions(value: unknown): value is string[] {
  return strings(value) && value.length > 0 && new Set(value).size === value.length;
}

/** Accept only the live fixed bundle; missing/invalid data is not a fallback capability. */
export function readStartingCreationOptions(raw: unknown): Metadata | undefined {
  if (!record(raw)) return undefined;
  const levels = raw.supported_starting_levels;
  const two = raw.level_2;
  const three = raw.level_3;
  const pending = raw.effects_pending_by_level;
  if (!Array.isArray(levels) || ![3, 5].includes(levels.length) || !levels.every((level, index) => level === index + 1)
      || !record(two) || !record(three) || !record(pending)
      || two.prepared_spell_count !== 2 || two.metamagic_count !== 2 || three.prepared_spell_count !== 2
      || !uniqueOptions(two.prepared_spell_ids) || !uniqueOptions(three.prepared_spell_ids)
      || !uniqueOptions(two.metamagic_options) || two.metamagic_options.length < 2
      || !Array.isArray(three.subclass_options) || three.subclass_options.length === 0
      || Object.keys(pending).length !== levels.length
      || !strings(pending['1']) || !strings(pending['2']) || !strings(pending['3'])) return undefined;
  if (levels.length === 5) {
    const four = raw.level_4, five = raw.level_5;
    if (!record(four) || !record(five) || four.prepared_spell_count !== 1 || four.cantrip_count !== 1
      || five.prepared_spell_count !== 2 || !uniqueOptions(four.prepared_spell_ids) || !uniqueOptions(four.cantrip_ids)
      || !uniqueOptions(five.prepared_spell_ids) || !strings(pending['4']) || !strings(pending['5'])
      || !readAsiChoices(four.supported_asi_choices)) return undefined;
  }
  const subclasses: { id: string; name: string }[] = [];
  for (const option of three.subclass_options) {
    if (!record(option) || typeof option.id !== 'string' || !option.id.trim()
        || typeof option.name !== 'string' || !option.name.trim()) return undefined;
    subclasses.push({ id: option.id, name: option.name });
  }
  if (new Set(subclasses.map(option => option.id)).size !== subclasses.length
      || new Set(subclasses.map(option => option.name)).size !== subclasses.length) return undefined;
  return {
    supported_starting_levels: [...levels],
    level_2: {
      prepared_spell_count: two.prepared_spell_count,
      prepared_spell_ids: [...two.prepared_spell_ids],
      metamagic_count: two.metamagic_count,
      metamagic_options: [...two.metamagic_options],
    },
    level_3: {
      prepared_spell_count: three.prepared_spell_count,
      prepared_spell_ids: [...three.prepared_spell_ids],
      subclass_options: subclasses,
    },
    effects_pending_by_level: { '1': [...pending['1']], '2': [...pending['2']], '3': [...pending['3']],
      ...(levels.length === 5 ? { '4': [...pending['4'] as string[]], '5': [...pending['5'] as string[]] } : {}) },
    ...(levels.length === 5 ? { level_4: structuredClone(raw.level_4), level_5: structuredClone(raw.level_5) } : {}),
  } as Metadata;
}

export function emptyStartingDraft(): StartingDraft {
  return { startingLevel: 1, level2Prepared: [], metamagic: [], level3Prepared: [], subclassId: '' };
}

export function changeStartingLevel(draft: StartingDraft, level: 1 | 2 | 3 | 4 | 5): StartingDraft {
  if (![1, 2, 3, 4, 5].includes(level)) throw new Error('Unsupported starting level.');
  if (level === 1) return emptyStartingDraft();
  return {
    startingLevel: level,
    level2Prepared: [...draft.level2Prepared],
    metamagic: [...draft.metamagic],
    level3Prepared: level >= 3 ? [...draft.level3Prepared] : [],
    subclassId: level >= 3 ? draft.subclassId : '',
    ...(level >= 3 && draft.primalSkill ? { primalSkill: draft.primalSkill } : {}),
    level4Prepared: level >= 4 ? [...draft.level4Prepared ?? []] : [],
    level4Cantrips: level >= 4 ? [...draft.level4Cantrips ?? []] : [],
    level4Asi: level >= 4 ? draft.level4Asi : undefined,
    level4ConConfirmed: level >= 4 ? draft.level4ConConfirmed === true : false,
    level5Prepared: level === 5 ? [...draft.level5Prepared ?? []] : [],
  };
}

export function availableStartingSpells(metadata: Metadata, initialSpells: string[], draft: StartingDraft, initialCantrips: string[] = []): { level2: string[]; level3: string[]; level4: string[]; cantrips4: string[]; level5: string[] } {
  return {
    level2: metadata.level_2.prepared_spell_ids.filter(id => !initialSpells.includes(id)),
    level3: metadata.level_3.prepared_spell_ids.filter(id => !initialSpells.includes(id) && !draft.level2Prepared.includes(id)),
    level4: (metadata.level_4?.prepared_spell_ids ?? []).filter(id => ![...initialSpells, ...draft.level2Prepared, ...draft.level3Prepared].includes(id)),
    cantrips4: (metadata.level_4?.cantrip_ids ?? []).filter(id => !initialCantrips.includes(id)),
    level5: (metadata.level_5?.prepared_spell_ids ?? []).filter(id => ![...initialSpells, ...draft.level2Prepared, ...draft.level3Prepared, ...draft.level4Prepared ?? []].includes(id)),
  };
}

function prunePicks(picks: string[], allowed: string[], excluded: string[] = []): string[] {
  return picks.filter((id, index) => picks.indexOf(id) === index && allowed.includes(id) && !excluded.includes(id));
}

function same(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((id, index) => id === b[index]);
}

export function pruneStartingDraft(draft: StartingDraft, initialSpells: string[], metadata: Metadata | undefined, initialCantrips: string[] = []): StartingDraft {
  if (!metadata) return draft;
  const level2Prepared = prunePicks(draft.level2Prepared, metadata.level_2.prepared_spell_ids, initialSpells);
  const level3Prepared = prunePicks(draft.level3Prepared, metadata.level_3.prepared_spell_ids, [...initialSpells, ...level2Prepared]);
  const metamagic = prunePicks(draft.metamagic, metadata.level_2.metamagic_options);
  const subclassId = metadata.level_3.subclass_options.some(option => option.id === draft.subclassId) ? draft.subclassId : '';
  const level4Prepared = draft.startingLevel >= 4 ? prunePicks(draft.level4Prepared ?? [], metadata.level_4?.prepared_spell_ids ?? [], [...initialSpells, ...level2Prepared, ...level3Prepared]) : [];
  const level4Cantrips = draft.startingLevel >= 4 ? prunePicks(draft.level4Cantrips ?? [], metadata.level_4?.cantrip_ids ?? [], initialCantrips) : [];
  const level5Prepared = draft.startingLevel === 5 ? prunePicks(draft.level5Prepared ?? [], metadata.level_5?.prepared_spell_ids ?? [], [...initialSpells, ...level2Prepared, ...level3Prepared, ...level4Prepared]) : [];
  const level4Asi = draft.startingLevel >= 4 && draft.level4Asi ? sourceAsiChoice(metadata.level_4?.supported_asi_choices, draft.level4Asi) : undefined;
  const level4ConConfirmed = draft.startingLevel >= 4 && draft.level4ConConfirmed === true && (!draft.level4Asi || !!level4Asi);
  if (same(level2Prepared, draft.level2Prepared) && same(level3Prepared, draft.level3Prepared)
      && same(metamagic, draft.metamagic) && subclassId === draft.subclassId
      && same(level4Prepared, draft.level4Prepared ?? []) && same(level4Cantrips, draft.level4Cantrips ?? [])
      && (draft.level4Asi ? !!level4Asi && asiChoiceKey(draft.level4Asi) === asiChoiceKey(level4Asi) : !level4Asi)
      && same(level5Prepared, draft.level5Prepared ?? []) && level4ConConfirmed === Boolean(draft.level4ConConfirmed)) return draft;
  return { ...draft, level2Prepared, level3Prepared, metamagic, subclassId, level4Prepared, level4Cantrips, level5Prepared, level4ConConfirmed, level4Asi };
}

function validPicks(picks: string[], count: number, allowed: string[], excluded: string[] = []): boolean {
  return picks.length === count && new Set(picks).size === picks.length
    && picks.every(id => allowed.includes(id) && !excluded.includes(id));
}

/** Validate advancement independently of pruning; base character validation is still mandatory. */
export function validateStartingDraft(className: string, draft: StartingDraft, initialSpells: string[], metadata: Metadata | undefined, initialCantrips: string[] = []): Validation {
  const fail = (message: string): Validation => ({ ok: false, message });
  if (draft.startingLevel < 4 && ((draft.level4Prepared?.length ?? 0) || (draft.level4Cantrips?.length ?? 0) || draft.level4ConConfirmed || draft.level4Asi)
      || draft.startingLevel < 5 && (draft.level5Prepared?.length ?? 0)) return fail('Üst seviye seçimlerini temizleyin.');
  if (draft.startingLevel === 1) {
    return draft.level2Prepared.length || draft.metamagic.length || draft.level3Prepared.length || draft.subclassId
      ? fail('Seviye 1 için üst seviye seçimlerini temizleyin.') : { ok: true, message: '' };
  }
  if (![2, 3, 4, 5].includes(draft.startingLevel)) return fail('Desteklenen bir başlangıç seviyesi seçin.');
  if (className !== 'Sorcerer') return fail('Üst başlangıç seviyeleri yalnızca Sorcerer için destekleniyor.');
  if (!metadata || !metadata.supported_starting_levels.includes(draft.startingLevel))
    return fail('Seviye seçenekleri alınamadı. Kataloğu yeniden deneyin veya açıkça seviye 1 seçin.');
  if (new Set(initialSpells).size !== initialSpells.length
      || initialSpells.some(id => !metadata.level_2.prepared_spell_ids.includes(id)))
    return fail('Başlangıç büyülerini geçerli ve farklı seçeneklerden seçin.');
  if (!validPicks(draft.level2Prepared, metadata.level_2.prepared_spell_count, metadata.level_2.prepared_spell_ids, initialSpells))
    return fail(`Seviye 2 için ${metadata.level_2.prepared_spell_count} farklı ek büyü seçin.`);
  if (!validPicks(draft.metamagic, metadata.level_2.metamagic_count, metadata.level_2.metamagic_options))
    return fail(`${metadata.level_2.metamagic_count} farklı Metamagic seçeneği seçin.`);
  if (draft.startingLevel === 2) {
    if (draft.level3Prepared.length || draft.subclassId) return fail('Seviye 2 için seviye 3 seçimlerini temizleyin.');
  } else {
    if (!validPicks(draft.level3Prepared, metadata.level_3.prepared_spell_count, metadata.level_3.prepared_spell_ids, [...initialSpells, ...draft.level2Prepared]))
      return fail(`Seviye 3 için ${metadata.level_3.prepared_spell_count} farklı ek büyü seçin.`);
    if (!metadata.level_3.subclass_options.some(option => option.id === draft.subclassId))
      return fail('Geçerli bir Sorcerer alt sınıfı seçin.');
  }
  if (draft.startingLevel >= 4) {
    const four = metadata.level_4;
    if (!four || !validPicks(draft.level4Prepared ?? [], four.prepared_spell_count, four.prepared_spell_ids, [...initialSpells, ...draft.level2Prepared, ...draft.level3Prepared])
      || !validPicks(draft.level4Cantrips ?? [], four.cantrip_count, four.cantrip_ids, initialCantrips)
      || !draft.level4ConConfirmed || !sourceAsiChoice(four.supported_asi_choices, draft.level4Asi, draft.level4ConConfirmed)) return fail('Seviye 4 için yeni büyü, cantrip ve sunucunun sunduğu ASI seçiminin onayı gerekiyor.');
  }
  if (draft.startingLevel === 5) {
    const five = metadata.level_5;
    if (!five || !validPicks(draft.level5Prepared ?? [], five.prepared_spell_count, five.prepared_spell_ids, [...initialSpells, ...draft.level2Prepared, ...draft.level3Prepared, ...draft.level4Prepared ?? []])) return fail('Seviye 5 için iki farklı yeni büyü seçin.');
  }
  return { ok: true, message: '' };
}

export function startingCreationFields(className: string, draft: StartingDraft, initialSpells: string[], metadata: Metadata | undefined, initialCantrips: string[] = []):
  { ok: true; fields: Pick<CharacterCreateInput, 'starting_level' | 'level_choices'> } | { ok: false; message: string } {
  const validation = validateStartingDraft(className, draft, initialSpells, metadata, initialCantrips);
  if (!validation.ok) return { ok: false, message: validation.message };
  if (draft.startingLevel === 1) return { ok: true, fields: {} };
  const level_choices: SorcererLevelChoices = {
    '2': { prepared_spells: [...draft.level2Prepared], metamagic: [...draft.metamagic] },
  };
  if (draft.startingLevel >= 3) {
    level_choices['3'] = { prepared_spells: [...draft.level3Prepared], subclass_id: draft.subclassId };
  }
  if (draft.startingLevel >= 4) level_choices['4'] = { prepared_spells: [...draft.level4Prepared ?? []], cantrips: [...draft.level4Cantrips ?? []], asi: sourceAsiChoice(metadata?.level_4?.supported_asi_choices, draft.level4Asi, draft.level4ConConfirmed)! };
  if (draft.startingLevel === 5) level_choices['5'] = { prepared_spells: [...draft.level5Prepared ?? []] };
  return { ok: true, fields: { starting_level: draft.startingLevel, level_choices } };
}
