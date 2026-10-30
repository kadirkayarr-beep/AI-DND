import type { LevelUpAsiChoice } from '@workspace/api-client-react';
export type AsiChoice = LevelUpAsiChoice;
const supported = new Set(['strength', 'constitution', 'intelligence', 'wisdom', 'charisma']);
/** Validate the advertised bounded family, never manufacture a choice or calculate derived scores. */
export function readAsiChoices(raw: unknown): AsiChoice[] | undefined {
  if (!Array.isArray(raw) || !raw.length) return undefined;
  const choices: AsiChoice[] = [];
  for (const item of raw) {
    if (!item || typeof item !== 'object' || Array.isArray(item) || item.feat !== 'Ability Score Improvement'
      || Object.keys(item).some(key => !['feat', 'increase'].includes(key))
      || !item.increase || typeof item.increase !== 'object' || Array.isArray(item.increase)) return undefined;
    const entries = Object.entries(item.increase);
    if (!entries.every(([key]) => supported.has(key))
      || !(entries.length === 1 && entries[0][1] === 2 || entries.length === 2 && entries.every(([, value]) => value === 1))) return undefined;
    choices.push(structuredClone(item) as AsiChoice);
  }
  return new Set(choices.map(asiChoiceKey)).size === choices.length ? choices : undefined;
}
export function asiChoiceKey(choice: AsiChoice): string { return JSON.stringify(Object.entries(choice.increase).sort(([a], [b]) => a.localeCompare(b))); }
export function asiChoiceLabel(choice: AsiChoice | undefined): string { return choice ? Object.entries(choice.increase).map(([key, value]) => `${key} +${value}`).join(' / ') : 'ASI seçimi yapılmadı'; }
export function sourceAsiChoice(raw: unknown, selected?: AsiChoice, legacyConConfirmed = false): AsiChoice | undefined {
  const choices = readAsiChoices(raw);
  if (selected !== undefined && !readAsiChoices([selected])) return undefined;
  if (selected) return choices?.find(choice => asiChoiceKey(choice) === asiChoiceKey(selected) && selected.feat === choice.feat);
  if (legacyConConfirmed || choices?.length === 1) return choices?.find(choice => asiChoiceKey(choice) === '[["constitution",2]]');
  return undefined;
}
