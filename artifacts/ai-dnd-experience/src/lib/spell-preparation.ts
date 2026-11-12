import type { SpellPrepareDropped, SpellPrepareResult, SpellPrepareViewResponse } from '@workspace/api-client-react';

/** The classes that prepare from a window (engine `spell_scope.PREPARING`); other casters never see this screen. */
export const PREPARING_CLASSES: readonly string[] = ['Wizard', 'Cleric'];

export function preparesSpells(state: { character?: { class?: string | null } | null; spellcasting?: unknown } | null | undefined): boolean {
  return !!state?.spellcasting && PREPARING_CLASSES.includes(state.character?.class ?? '');
}

const OPEN_REASON: Record<string, string> = {
  creation: 'Karakterin yeni yaratıldı: ilk hazırlık listeni seç. Pencere, ilk kaydettiğin listeye kadar açık kalır.',
  migration: 'Eski kaydın yeni büyü kurallarına taşındı: hazırlık listeni bir kez seç. Pencere, ilk kaydettiğin listeye kadar açık kalır.',
  long_rest: 'Uzun dinlenmeyi bitirdin: hazırlık listeni değiştirebilirsin. Zaman ilerleyince ya da çatışma başlayınca pencere kapanır.',
  level_up: 'Yeni seviyeye geçtin ve hazırlık sınırın büyüdü. Bu pencerede yalnız büyü ekleyebilirsin; hazırladığın büyüleri değiştirmek için uzun dinlenme gerekir. Pencere, ilk kaydettiğin listeye kadar açık kalır.',
};

export const WINDOW_SHORT: Record<string, string> = {
  creation: 'Açık · yaratım', migration: 'Açık · kayıt taşındı', long_rest: 'Açık · uzun dinlenme', level_up: 'Açık · yeni seviye',
};

/** Why the window is open or closed, in plain Turkish; never a reason the engine did not give. */
export function windowReasonText(view: SpellPrepareViewResponse, combatActive: boolean): string {
  if (!view.supported) {
    return view.blocked_reason === 'spellbook_missing'
      ? 'Büyü kitabın kayıtta yok; bu eski kayıt büyü seçimlerini taşımıyor. Büyü hazırlanamaz.'
      : 'Bu sınıf büyü hazırlamaz.';
  }
  if (view.open) return OPEN_REASON[view.reason ?? ''] ?? 'Hazırlık penceresi açık.';
  if (combatActive) return 'Çatışma sürerken büyü hazırlanamaz.';
  return 'Hazırlık penceresi kapalı. Uzun dinlenmeyi bitirince ya da yeni bir seviyeye geçince yeniden açılır.';
}

/** In a level step's window the list only grows: what was prepared before cannot be taken out. */
export function lockedSpells(view: SpellPrepareViewResponse): ReadonlySet<string> {
  return new Set(view.open && view.reason === 'level_up' ? view.prepared : []);
}

/** Candidates first (server order), then any prepared spell the server did not list, so nothing silently disappears. */
export function spellChoices(view: SpellPrepareViewResponse): string[] {
  return [...view.candidates, ...view.prepared.filter(id => !view.candidates.includes(id))];
}

export function toggleSpell(view: SpellPrepareViewResponse, draft: readonly string[], id: string): string[] {
  if (!view.open || !view.supported) return [...draft];
  if (draft.includes(id)) return lockedSpells(view).has(id) ? [...draft] : draft.filter(spell => spell !== id);
  if (draft.length >= view.limit || !view.candidates.includes(id)) return [...draft];
  return [...draft, id];
}

/** The body for `spellcasting/prepare`, or null while the list cannot be sent as it is. */
export function prepareRequest(view: SpellPrepareViewResponse, draft: readonly string[]): { prepared: string[] } | null {
  if (!view.open || !view.supported || draft.length > view.limit || new Set(draft).size !== draft.length) return null;
  if (!draft.every(id => view.candidates.includes(id))) return null;
  for (const id of lockedSpells(view)) if (!draft.includes(id)) return null;
  return { prepared: [...draft] };
}

const DROPPED: Record<string, string> = {
  duplicate: 'iki kez seçildi', cantrip: 'hile (cantrip) hazırlanmaz', not_in_spellbook: 'büyü kitabında yok', not_on_class_list: 'sınıf listesinde yok',
};

export function droppedText(dropped: readonly SpellPrepareDropped[], label: (id: string) => string): string | null {
  if (!dropped.length) return null;
  return `Listeye alınmayanlar: ${dropped.map(item => `${label(item.spell_id)} (${DROPPED[item.reason] ?? 'geçersiz'})`).join(', ')}.`;
}

/** Our own sentence from the result fields (D-070: the server message carries English ids). */
export function resultText(result: SpellPrepareResult, label: (id: string) => string): string {
  if (result.status === 'too_many') {
    return `En çok ${result.limit} büyü hazırlayabilirsin; ${result.excess} fazlası var. Hangisini bırakıyorsun? Liste kaydedilmedi.`;
  }
  const empty = result.limit - result.prepared.length;
  return `Hazırlanan büyüler: ${result.prepared.length ? result.prepared.map(label).join(', ') : 'yok'}.${empty > 0 ? ` ${empty} boş yerin kaldı.` : ''}`;
}

const REFUSALS: Record<string, string> = {
  prepare_window_closed: 'Hazırlık penceresi kapalı: büyü hazırlamak için uzun dinlenmeyi yeni bitirmiş ya da yeni bir seviyeye geçmiş olmalısın. Listen kaydedilmedi.',
  prepare_spellbook_missing: 'Büyü kitabın kayıtta yok; bu eski kayıt büyü seçimlerini taşımıyor. Listen kaydedilmedi.',
  prepare_not_supported: 'Bu sınıf büyü hazırlamaz. Listen kaydedilmedi.',
  prepare_unavailable: 'Kayıtlı büyü durumu okunamadı. Listen kaydedilmedi.',
  prepare_level_up_additive_only: 'Yeni seviyede yalnız büyü ekleyebilirsin; hazırladığın büyüleri çıkarmak için uzun dinlenme gerekir. Listen kaydedilmedi.',
  action_id_conflict: 'Bu işlem kimliği başka bir listeyle kullanılmış. Listen kaydedilmedi; durumu yenileyip yeniden dene.',
};

export function errorStatus(error: unknown): number | undefined {
  const status = error && typeof error === 'object' ? (error as { status?: unknown }).status : undefined;
  return typeof status === 'number' ? status : undefined;
}

/** A refusal is an answer: nothing was saved. Anything else (network, 5xx) leaves the outcome unknown. */
export function isPrepareRefusal(error: unknown): boolean {
  return [400, 404, 409, 422].includes(errorStatus(error) ?? 0);
}

export function prepareRefusalText(error: unknown): string {
  const data = error && typeof error === 'object' ? (error as { data?: unknown }).data : undefined;
  const detail = data && typeof data === 'object' ? (data as { detail?: unknown }).detail : undefined;
  const code = detail && typeof detail === 'object' && !Array.isArray(detail) ? (detail as { code?: unknown }).code : undefined;
  if (typeof code === 'string' && REFUSALS[code]) return REFUSALS[code];
  if (errorStatus(error) === 422) return 'Liste geçersiz sayıldı. Listen kaydedilmedi.';
  return 'Liste kaydedilmedi. Güncel durumu yenileyip yeniden dene.';
}
