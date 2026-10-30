import type { EconomyStepInput, FighterAvailability, RogueState } from '@workspace/api-client-react';

const SNEAK_DIE = 6;
const STRIKES = ['poison', 'trip', 'withdraw'];

function whole(value: unknown, minimum: number): value is number {
  return Number.isSafeInteger(value) && Number(value) >= minimum;
}
function availability(value: FighterAvailability | undefined): boolean {
  return !!value && typeof value.available === 'boolean' && (value.reason === null || typeof value.reason === 'string');
}

/** Read-only projection validation; the class name never stands in for it. A malformed block shows nothing. */
export function readRogueProjection(value: unknown): RogueState | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const raw = value as RogueState;
  const sneak = raw.sneak_attack;
  if (!sneak || !whole(sneak.dice, 1) || sneak.die !== SNEAK_DIE || typeof sneak.used_this_turn !== 'boolean') return null;
  if (raw.subclass !== null && typeof raw.subclass !== 'string') return null;
  const action = raw.cunning_action;
  if (action !== null && (!action || !availability(action.dash) || !availability(action.disengage))) return null;
  const aim = raw.steady_aim;
  if (aim !== null && (!aim || typeof aim.active !== 'boolean' || !availability(aim))) return null;
  const strike = raw.cunning_strike;
  if (strike !== null && (!strike || !Number.isSafeInteger(strike.dc) || !whole(strike.withdraw_max_ft, 0)
    || !Array.isArray(strike.trip_refused_targets) || !strike.trip_refused_targets.every(id => typeof id === 'string') || !Array.isArray(strike.options)
    || !strike.options.every(option => STRIKES.includes(option?.id) && whole(option?.cost, 1) && availability(option)))) return null;
  const dodge = raw.uncanny_dodge;
  if (dodge !== null && (!dodge || typeof dodge.enabled !== 'boolean' || typeof dodge.reaction_available !== 'boolean')) return null;
  return raw;
}

export type CunningStrikeFields = Pick<EconomyStepInput, 'cunning_strike' | 'cunning_strike_move_ft'>;

/** Only Trip depends on the target, and the server says which ones it refuses. */
export function tripRefused(rogue: RogueState | null, option: string, targetId: string): boolean {
  return option === 'trip' && !!rogue?.cunning_strike?.trip_refused_targets.includes(targetId);
}

/** The attack-step fields for the player's pick. Empty means no Cunning Strike; null means the pick cannot be sent. */
export function cunningStrikeFields(rogue: RogueState | null, option: string, distance: string, targetId: string): CunningStrikeFields | null {
  if (option === '') return {};
  const strike = rogue?.cunning_strike;
  const offered = strike?.options.find(item => item.id === option);
  if (!strike || !offered?.available || rogue?.sneak_attack.used_this_turn || tripRefused(rogue, option, targetId)) return null;
  if (offered.id !== 'withdraw') return { cunning_strike: offered.id };
  const feet = Number(distance);
  if (distance.trim() === '' || !Number.isSafeInteger(feet) || feet < 1 || feet > strike.withdraw_max_ft) return null;
  return { cunning_strike: 'withdraw', cunning_strike_move_ft: feet };
}
