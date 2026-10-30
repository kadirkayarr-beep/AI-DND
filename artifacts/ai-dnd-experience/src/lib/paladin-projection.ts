import type { EconomyStepInput, FighterAvailability, PaladinState } from '@workspace/api-client-react';

const POISON_COST = 5;
const MINIMUM_POOL = 5;

function whole(value: unknown, minimum: number): value is number {
  return Number.isSafeInteger(value) && Number(value) >= minimum;
}
function availability(value: FighterAvailability | undefined): boolean {
  return !!value && typeof value.available === 'boolean' && (value.reason === null || typeof value.reason === 'string');
}
function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}
function strings(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(item => typeof item === 'string');
}
function optionalRecord(value: unknown, valid: (item: Record<string, unknown>) => boolean): boolean {
  return value === null || (record(value) && valid(value));
}

/** Read-only projection validation; class name and inventory never stand in for it. A malformed block shows nothing. */
export function readPaladinProjection(value: unknown): PaladinState | null {
  if (!record(value)) return null;
  const raw = value as unknown as PaladinState;
  const hands = raw.lay_on_hands;
  if (!hands || !whole(hands.pool_maximum, MINIMUM_POOL) || !whole(hands.pool_remaining, 0) || hands.pool_remaining > hands.pool_maximum
    || hands.poison_cost !== POISON_COST || !availability(hands.activate)
    || (raw.fighting_style !== null && typeof raw.fighting_style !== 'string')
    || !strings(raw.always_prepared) || !Array.isArray(raw.prepared_spells)
    || !raw.prepared_spells.every(spell => record(spell) && typeof spell.id === 'string' && typeof spell.castable === 'boolean')) return null;
  const smiteOk = optionalRecord(raw.divine_smite, item => availability(item.activate as FighterAvailability) && typeof item.free_cast_available === 'boolean'
    && Array.isArray(item.slot_levels) && item.slot_levels.every(level => whole(level, 1)) && (item.target_id === null || typeof item.target_id === 'string'));
  const channelOk = optionalRecord(raw.channel_divinity, item => whole(item.max_uses, 1) && whole(item.uses_remaining, 0) && Number(item.uses_remaining) <= Number(item.max_uses));
  const senseOk = optionalRecord(raw.divine_sense, item => typeof item.active === 'boolean' && Array.isArray(item.detected) && availability(item.activate as FighterAvailability));
  const sacredOk = optionalRecord(raw.sacred_weapon, item => typeof item.active === 'boolean' && whole(item.attack_bonus, 1) && availability(item.start as FighterAvailability));
  return smiteOk && channelOk && senseOk && sacredOk ? raw : null;
}

/** The typed Lay On Hands step. Null means do not send: nothing is chosen for the player and the pool bounds the number. */
export function layOnHandsStep(paladin: PaladinState, amount: string, removePoisoned: boolean): EconomyStepInput | null {
  const hands = paladin.lay_on_hands;
  const typed = amount.trim();
  const healing = Number(typed);
  if (typed !== '' && (!Number.isSafeInteger(healing) || healing < 1)) return null;
  const cost = (typed === '' ? 0 : healing) + (removePoisoned ? hands.poison_cost : 0);
  if (cost < 1 || cost > hands.pool_remaining) return null;
  return { kind: 'lay_on_hands', resource: 'bonus', ...(typed === '' ? {} : { healing_amount: healing }), ...(removePoisoned ? { remove_poisoned: true } : {}) };
}

/** The typed Divine Smite step: '' is the cast without a slot, otherwise a slot level the server lists. */
export function divineSmiteStep(paladin: PaladinState, slot: string): EconomyStepInput | null {
  const smite = paladin.divine_smite;
  if (!smite) return null;
  if (slot === '') return smite.free_cast_available ? { kind: 'divine_smite', resource: 'bonus' } : null;
  const level = Number(slot);
  return smite.slot_levels.includes(level) ? { kind: 'divine_smite', resource: 'bonus', slot_level: level } : null;
}

/** Fields an attack step carries. Sacred Weapon is offered only by the server block; a stale choice sends nothing. */
export function sacredWeaponFields(paladin: PaladinState | null, wanted: boolean, radiant: boolean): Pick<EconomyStepInput, 'sacred_weapon' | 'radiant_damage'> {
  const sacred = paladin?.sacred_weapon;
  if (!sacred) return {};
  const starting = wanted && !sacred.active && sacred.start.available;
  return { ...(starting ? { sacred_weapon: true } : {}), ...(radiant && (starting || sacred.active) ? { radiant_damage: true } : {}) };
}
