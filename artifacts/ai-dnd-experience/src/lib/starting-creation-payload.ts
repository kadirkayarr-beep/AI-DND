import type { CharacterCreateInput } from '@workspace/api-client-react';
import { barbarianStartingCreationFields } from './barbarian-starting-creation.ts';
import { paladinStartingCreationFields } from './paladin-starting-creation.ts';
import { fighterStartingCreationFields, monkStartingCreationFields, rogueStartingCreationFields } from './simple-class-starting-creation.ts';
import { casterOptions, casterStartingFields, isCasterStartClass, type CasterStarting } from './prepared-caster-starting-creation.ts';
import { startingCreationFields, type StartingDraft } from './sorcerer-starting-creation.ts';

type StartingPayload = { ok: true; fields: Pick<CharacterCreateInput, 'starting_level' | 'level_choices'> } | { ok: false; message: string };

/** The live catalog blocks the screen read for each class, plus the picks every class check needs. Absent blocks mean the catalog did not offer the start. */
type StartingSources = {
  sorcerer?: Parameters<typeof startingCreationFields>[3];
  barbarian?: Parameters<typeof barbarianStartingCreationFields>[1];
  fighter?: Parameters<typeof fighterStartingCreationFields>[1];
  paladin?: Parameters<typeof paladinStartingCreationFields>[1];
  rogue?: Parameters<typeof rogueStartingCreationFields>[1];
  monk?: Parameters<typeof monkStartingCreationFields>[1];
  caster?: CasterStarting;
};
type StartingContext = StartingSources & { spells: string[]; cantrips: string[]; ownedSkills?: readonly string[] };

/** One place that turns the class, the draft and the catalog into the starting-level part of the create request (or the reason it cannot be built). */
export function startingCreationPayload(characterClass: string, draft: StartingDraft, context: StartingContext): StartingPayload {
  if (characterClass === 'Barbarian') return barbarianStartingCreationFields(draft, context.barbarian, context.ownedSkills);
  if (characterClass === 'Fighter') return fighterStartingCreationFields(draft, context.fighter);
  if (characterClass === 'Paladin') return paladinStartingCreationFields(draft, context.paladin, context.spells);
  if (characterClass === 'Rogue') return rogueStartingCreationFields(draft, context.rogue);
  if (characterClass === 'Monk') return monkStartingCreationFields(draft, context.monk);
  if (isCasterStartClass(characterClass)) return casterStartingFields(characterClass, draft, casterOptions(characterClass, context.caster), context.spells, context.cantrips);
  return startingCreationFields(characterClass, draft, context.spells, context.sorcerer, context.cantrips);
}
