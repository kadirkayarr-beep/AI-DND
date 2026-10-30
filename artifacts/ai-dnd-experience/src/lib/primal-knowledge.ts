import type { CombatActionInput, GameCharacter, GameState } from '@workspace/api-client-react';
import type { InteractionMode } from './action-suggestions';

const SKILLS = ['Acrobatics', 'Intimidation', 'Perception', 'Stealth', 'Survival'] as const;
type Projection = NonNullable<GameCharacter['primal_knowledge_check']>;
type Metadata = { interaction_mode: InteractionMode; target_id: string | null };

/** Display only the optional server capability; character names, level and prose are not entitlement. */
export function readPrimalKnowledgeProjection(value: unknown): Projection | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const projection = value as Projection;
  if (typeof projection.available !== 'boolean'
    || !(projection.reason === null || typeof projection.reason === 'string')
    || !Array.isArray(projection.skills) || projection.skills.length !== SKILLS.length
    || !SKILLS.every((skill, index) => projection.skills[index] === skill)) return null;
  return projection;
}

export function primalKnowledgeAvailable(state: GameState | undefined, metadata: Metadata | null, command?: CombatActionInput): boolean {
  return readPrimalKnowledgeProjection(state?.character?.primal_knowledge_check)?.available === true
    && state?.combat.active === false && metadata?.interaction_mode === 'do'
    && !metadata.target_id && !command;
}

/** Ephemeral, one-command consent. Pending-action alone owns already submitted consent and retry input. */
export function createPrimalKnowledgeIntent() {
  let key = ''; let available = false; let selected = false;
  return {
    get selected() { return selected; },
    sync(next: { key: string; available: boolean }) {
      if (key !== next.key || !next.available) selected = false;
      key = next.key; available = next.available;
    },
    choose(value: boolean) { selected = value === true && available; },
  };
}

