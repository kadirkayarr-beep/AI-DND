import type { TurnOutcome } from '@workspace/api-client-react';

const EVERYDAY: Record<string, string> = {
  knock: 'Kapıya vuruldu',
  bell: 'Çan çalındı',
  read: 'Kitaba bakıldı',
  follow: 'Takip edildi',
  perform: 'Küçük bir gösteri',
};

/** One short, player-safe line describing what the last turn resolved (LR00-P5). */
export function summarizeTurnOutcome(outcome: TurnOutcome | null | undefined): string | null {
  if (!outcome) return null;
  if (outcome.action === 'travel' && typeof outcome.place_created === 'boolean') {
    return outcome.place_created ? 'Yeni bir yer kaydedildi' : 'Bilinen bir yere dönüldü';
  }
  if (outcome.action === 'everyday_action' && outcome.kind && EVERYDAY[outcome.kind]) {
    return EVERYDAY[outcome.kind];
  }
  if (outcome.target_name && typeof outcome.found === 'boolean') {
    return outcome.found
      ? `${outcome.target_name}: bir şey göze çarptı`
      : `${outcome.target_name}: bu bakışla yeni bir şey yok`;
  }
  return null;
}
