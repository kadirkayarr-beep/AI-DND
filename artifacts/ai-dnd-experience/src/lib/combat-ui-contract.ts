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
  reckless_attack_unavailable: 'Reckless Attack bu saldırıda kullanılamıyor. Güncel tur durumunu kontrol edip seçimini yeniden yap.',
  spell_out_of_range: 'Seçilen hedef büyünün menzili dışında.',
  spell_visibility_unknown: 'Büyü için hedefin açıkça görünür olması gerekiyor.',
  spell_path_blocked: 'Büyünün hedefe giden yolu kapalı.',
  spell_slot_unavailable: 'Seçilen seviyede büyü yuvası kalmadı. Başka bir yuva otomatik kullanılmadı.',
  invalid_spell_target: 'Büyü için çatışmadaki geçerli bir hedefi seç.',
  unsupported_spell_target_mode: 'Bu hedefin büyü veya savunma etkileri henüz desteklenmiyor.',
  spell_not_available: 'Bu büyü hazırlanmış veya kullanılabilir değil.',
  spell_components_unavailable: 'Büyünün gerekli söz veya el bileşenleri kullanılamıyor.',
  spell_target_required: 'Büyü için açıkça bir hedef seç.',
  unsupported_spell_mode: 'Seçilen büyü kullanım biçimi henüz desteklenmiyor.',
  unsupported_spell: 'Bu büyünün etkisi henüz desteklenmiyor.',
  unsupported_spell_damage_mode: 'Etkin büyü hasarı ek etkileri henüz desteklenmiyor.',

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
  const publicMessage = (detail as { public_message?: unknown }).public_message;
  if (typeof publicMessage === 'string' && publicMessage.trim()) return publicMessage;
  const code = (detail as { code?: unknown }).code;
  return typeof code === 'string' ? COMBAT_ERRORS[code] ?? null : null;
}
