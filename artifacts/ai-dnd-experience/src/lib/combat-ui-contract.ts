/** Presentation helpers for already-resolved Python combat state. */

type CombatParticipant = {
  id: string;
  kind: string;
  status: string;
  current_hp: number;
};

export function retainCombatTarget(
  targetId: string,
  combat: { active: boolean; participant_records: CombatParticipant[] },
  combatEnded: boolean,
): boolean {
  if (!targetId || combatEnded || !combat.active) return false;
  return combat.participant_records.some(
    (participant) => participant.id === targetId
      && participant.kind === 'npc'
      && participant.status === 'active'
      && participant.current_hp > 0,
  );
}

const COMBAT_ERRORS: Record<string, string> = {
  stale_combat: 'Çatışmada sıra değişti. Güncel duruma bakıp hamleni yeniden seç.',
  invalid_combat_target: 'Bu hedef artık geçerli değil. Görünen rakiplerden birini seç.',
  no_weapon: 'Bu saldırı için uygun bir silahın yok.',
  out_of_turn: 'Henüz sıra sende değil.',
  combat_travel: 'Çatışma sürerken normal yolculuğa çıkamazsın.',
  unconfirmed_combat: 'Saldırmak için hedefini ve niyetini açıkça belirt.',
  reaction_pending: 'Önce bekleyen tepki kararını tamamla.',
};

export function combatErrorMessage(error: unknown): string | null {
  if (!error || typeof error !== 'object') return null;
  const data = (error as { data?: unknown }).data;
  if (!data || typeof data !== 'object') return null;
  const detail = (data as { detail?: unknown }).detail;
  if (!detail || typeof detail !== 'object') return null;
  const code = (detail as { code?: unknown }).code;
  return typeof code === 'string' ? COMBAT_ERRORS[code] ?? null : null;
}
