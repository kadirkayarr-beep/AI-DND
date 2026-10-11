import type { CombatHistoryEntry } from '@workspace/api-client-react';
import type { CombatLogEntry } from '@/components/combat-panel';

const COMBAT_HISTORY_LIMIT = 50;

function fromServerEntry(value: unknown): CombatLogEntry | null {
  if (!value || typeof value !== 'object') return null;
  const candidate = value as Partial<CombatHistoryEntry>;
  if (
    typeof candidate.event_id !== 'string'
    || candidate.event_id.length === 0
    || !Number.isInteger(candidate.turn_index)
    || typeof candidate.result !== 'object'
    || candidate.result === null
    || !['attack', 'cast', 'death_save', 'action_economy'].includes(candidate.result.action ?? '')
  ) {
    return null;
  }
  return {
    id: candidate.event_id,
    turnIndex: candidate.turn_index as number,
    result: candidate.result,
  };
}

function fromLocalEntry(value: unknown): CombatLogEntry | null {
  if (!value || typeof value !== 'object') return null;
  const candidate = value as Partial<CombatLogEntry>;
  if (
    typeof candidate.id !== 'string'
    || candidate.id.length === 0
    || !Number.isInteger(candidate.turnIndex)
    || typeof candidate.result !== 'object'
    || candidate.result === null
    || !['attack', 'cast', 'death_save', 'action_economy'].includes(candidate.result.action ?? '')
  ) {
    return null;
  }
  return {
    id: candidate.id,
    turnIndex: candidate.turnIndex as number,
    result: candidate.result,
  };
}

export function mergeCombatHistory(
  history: readonly unknown[],
  existing: readonly CombatLogEntry[] = [],
): CombatLogEntry[] {
  const byEventId = new Map<string, CombatLogEntry>();
  for (const entry of existing) {
    const valid = fromLocalEntry(entry);
    if (valid) byEventId.set(valid.id, valid);
  }
  for (const entry of history) {
    const valid = fromServerEntry(entry);
    if (valid) byEventId.set(valid.id, valid);
  }
  return [...byEventId.values()].slice(-COMBAT_HISTORY_LIMIT);
}