import type { CombatActionInput, FighterAvailability, FighterState, GameState } from '@workspace/api-client-react';
import type { InteractionMode } from './action-suggestions';

const SECOND_WIND_DIE = 10;

function whole(value: unknown, minimum: number): value is number {
  return Number.isSafeInteger(value) && Number(value) >= minimum;
}
function availability(value: FighterAvailability | undefined): boolean {
  return !!value && typeof value.available === 'boolean' && (value.reason === null || typeof value.reason === 'string');
}

/** Read-only projection validation; class name and inventory never stand in for it. A malformed block shows nothing. */
export function readFighterProjection(value: unknown): FighterState | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const raw = value as FighterState;
  const wind = raw.second_wind;
  const surge = raw.action_surge;
  if (!wind || !whole(wind.max_uses, 1) || !whole(wind.uses_remaining, 0) || wind.uses_remaining > wind.max_uses
    || wind.die !== SECOND_WIND_DIE || !whole(wind.level_bonus, 1) || !availability(wind.activate) || typeof wind.tactical_shift !== 'boolean'
    || (raw.fighting_style !== null && typeof raw.fighting_style !== 'string')
    || (raw.tactical_mind !== null && !availability(raw.tactical_mind))) return null;
  if (surge !== null && (!surge || !whole(surge.max_uses, 1) || !whole(surge.uses_remaining, 0) || surge.uses_remaining > surge.max_uses
    || !availability(surge.activate))) return null;
  return raw;
}

/** One-command consent: the server projection and an untargeted Do check, never the class name. */
export function tacticalMindAvailable(state: GameState | undefined, metadata: { interaction_mode: InteractionMode; target_id: string | null } | null, command?: CombatActionInput): boolean {
  return readFighterProjection(state?.character?.fighter)?.tactical_mind?.available === true
    && state?.combat.active === false && metadata?.interaction_mode === 'do' && !metadata.target_id && !command;
}
