import type { EconomyStepInput, FighterAvailability, MonkState } from '@workspace/api-client-react';

const TECHNIQUES = ['push', 'topple'] as const;
const SMALLEST_DIE = 2;
const DEFLECT_MODES = ['off', 'reduce', 'redirect'] as const;
export type OpenHandChoice = '' | (typeof TECHNIQUES)[number];
export type DeflectMode = (typeof DEFLECT_MODES)[number];

function whole(value: unknown, minimum: number): value is number {
  return Number.isSafeInteger(value) && Number(value) >= minimum;
}
function availability(value: FighterAvailability | null | undefined): boolean {
  return !!value && typeof value.available === 'boolean' && (value.reason === null || typeof value.reason === 'string');
}
function optional(value: FighterAvailability | null | undefined): boolean {
  return value === null || availability(value);
}

/** Read-only projection validation; class name and inventory never stand in for it. A malformed block shows nothing. */
export function readMonkProjection(value: unknown): MonkState | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const raw = value as MonkState;
  const focus = raw.focus;
  if (!whole(raw.martial_arts_die, SMALLEST_DIE) || typeof raw.martial_arts_ready !== 'boolean' || !whole(raw.movement_bonus_ft, 0)
    || !Number.isSafeInteger(raw.save_dc) || !whole(raw.flurry_strikes_remaining, 0) || !availability(raw.martial_arts_strike)
    || !optional(raw.flurry_of_blows) || !optional(raw.patient_defense) || !optional(raw.step_of_the_wind)
    || !optional(raw.uncanny_metabolism) || !optional(raw.stunning_strike)) return null;
  if (focus !== null && (!focus || !whole(focus.max_points, 1) || !whole(focus.points_remaining, 0) || focus.points_remaining > focus.max_points)) return null;
  if (raw.deflect_mode !== null && !DEFLECT_MODES.includes(raw.deflect_mode as DeflectMode)) return null;
  if (!Array.isArray(raw.open_hand_techniques) || !raw.open_hand_techniques.every(item => TECHNIQUES.includes(item))) return null;
  return raw;
}

/** A Flurry attack with the technique the server offers; a technique it does not offer is never sent. */
export function flurryStep(monk: MonkState, kind: 'flurry_of_blows' | 'flurry_strike', targetId: string, technique: OpenHandChoice): EconomyStepInput {
  const offered = technique && monk.open_hand_techniques.includes(technique);
  return { kind, target_id: targetId, ...(offered ? { open_hand_technique: technique } : {}) };
}
