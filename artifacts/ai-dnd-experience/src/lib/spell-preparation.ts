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

/** D-039: an old save's Wizard with no spellbook chooses it once; the server sends the options and its own offer. */
export function choosingBook(view: SpellPrepareViewResponse): boolean {
  return !view.supported && view.blocked_reason === 'spellbook_missing' && (view.suggested_spellbook?.length ?? 0) > 0
    && (view.spellbook_options?.length ?? 0) > 0;
}

/** How many spells the book takes: the size of the server's offer (six at level 1, PHB 2024). */
export function bookSize(view: SpellPrepareViewResponse): number {
  return choosingBook(view) ? view.suggested_spellbook?.length ?? 0 : 0;
}

/** What the player starts from: the server's offer while choosing a book, otherwise the saved list. */
export function initialDraft(view: SpellPrepareViewResponse): string[] {
  return choosingBook(view) ? [...(view.suggested_spellbook ?? [])] : [...view.prepared];
}

/** The spells the player may tick: the book options while choosing a book, otherwise the window's candidates. */
function selectable(view: SpellPrepareViewResponse): readonly string[] {
  return choosingBook(view) ? view.spellbook_options ?? [] : view.candidates;
}

/** Why the window is open or closed, in plain Turkish; never a reason the engine did not give. */
export function windowReasonText(view: SpellPrepareViewResponse, combatActive: boolean): string {
  if (choosingBook(view)) {
    return `Büyü kitabın kayıtta yok: bu eski kayıt büyü seçimlerini taşımıyor. Kitabına ${bookSize(view)} birinci seviye Wizard büyüsü seç. `
      + 'Önerilen büyüler işaretli; istediğini değiştirebilirsin. Bu seçim bir kez yapılır ve Geri Al ile geri alınamaz. '
      + (combatActive
        ? 'Çatışma sürerken kaydedersen hazırlık penceresi açılmaz; uzun dinlenmeyi bitirince ya da yeni bir seviyeye geçince açılır.'
        : 'Kitabı kaydedince hazırlık penceresi açılır.');
  }
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
  if (choosingBook(view)) return [...selectable(view)];
  return [...view.candidates, ...view.prepared.filter(id => !view.candidates.includes(id))];
}

export function toggleSpell(view: SpellPrepareViewResponse, draft: readonly string[], id: string): string[] {
  if (choosingBook(view)) {
    if (draft.includes(id)) return draft.filter(spell => spell !== id);
    return draft.length >= bookSize(view) || !selectable(view).includes(id) ? [...draft] : [...draft, id];
  }
  if (!view.open || !view.supported) return [...draft];
  if (draft.includes(id)) return lockedSpells(view).has(id) ? [...draft] : draft.filter(spell => spell !== id);
  if (draft.length >= view.limit || !view.candidates.includes(id)) return [...draft];
  return [...draft, id];
}

export type PrepareBody = { prepared: string[] } | { spellbook: string[] };

/** The body for `spellcasting/prepare`, or null while the list cannot be sent as it is. */
export function prepareRequest(view: SpellPrepareViewResponse, draft: readonly string[]): PrepareBody | null {
  if (choosingBook(view)) {
    const ok = draft.length === bookSize(view) && new Set(draft).size === draft.length && draft.every(id => selectable(view).includes(id));
    return ok ? { spellbook: [...draft] } : null;
  }
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
  if (result.status === 'spellbook_saved') return 'Büyü kitabın kaydedildi. Şimdi hazırlık listeni seç.';
  if (result.status === 'too_many') {
    return `En çok ${result.limit} büyü hazırlayabilirsin; ${result.excess} fazlası var. Hangisini bırakıyorsun? Liste kaydedilmedi.`;
  }
  const empty = result.limit - result.prepared.length;
  return `Hazırlanan büyüler: ${result.prepared.length ? result.prepared.map(label).join(', ') : 'yok'}.${empty > 0 ? ` ${empty} boş yerin kaldı.` : ''}`;
}

const REFUSALS: Record<string, string> = {
  prepare_spellbook_invalid: 'Büyü kitabına Wizard listesinden tam altı farklı birinci seviye büyü seçmelisin. Kitap kaydedilmedi.',
  prepare_spellbook_not_missing: 'Büyü kitabın zaten kayıtlı; kitap yeniden seçilmez. Bu seçim kaydedilmedi; güncel durumu yenile.',
  prepare_request_mixed: 'Büyü kitabı tek başına kaydedilir; hazırlık listesi ondan sonra seçilir. Hiçbir şey kaydedilmedi.',
  prepare_window_closed: 'Hazırlık penceresi kapalı: büyü hazırlamak için uzun dinlenmeyi yeni bitirmiş ya da yeni bir seviyeye geçmiş olmalısın. Listen kaydedilmedi.',
  prepare_spellbook_missing: 'Büyü kitabın kayıtta yok; bu eski kayıt büyü seçimlerini taşımıyor. Listen kaydedilmedi.',
  prepare_not_supported: 'Bu sınıf büyü hazırlamaz. Listen kaydedilmedi.',
  prepare_unavailable: 'Kayıtlı büyü durumu okunamadı. Listen kaydedilmedi.',
  prepare_level_up_additive_only: 'Yeni seviyede yalnız büyü ekleyebilirsin; hazırladığın büyüleri çıkarmak için uzun dinlenme gerekir. Listen kaydedilmedi.',
  action_id_conflict: 'Bu işlem kimliği başka bir listeyle kullanılmış. Listen kaydedilmedi; durumu yenileyip yeniden dene.',
  // The action WAS applied; only its stored reply was archived (never "not saved").
  action_archived: 'Bu liste zaten uygulandı; sunucu yanıtı arşivlendiği için tekrar çalıştırılmadı. Güncel durumu yenile ve kayıtlı listeni kontrol et.',
};

/** The id follows the saved window, not just the chosen list: a list saved in between must not replay an older receipt. */
export function prepareActionSignature(view: SpellPrepareViewResponse, body: PrepareBody, campaignTime: unknown): string {
  return JSON.stringify([body, view.prepared, view.reason, campaignTime ?? null]);
}

export function sameSpellList(a: readonly string[] | null | undefined, b: readonly string[] | null | undefined): boolean {
  return !!a && !!b && a.length === b.length && a.every((id, index) => b[index] === id);
}

export const UNVERIFIED_SAVE = 'Kayıtlı liste, sunucunun döndürdüğü listeyle uyuşmuyor; liste kaydedilmemiş olabilir. Durumu yenile ve kayıtlı listeni kontrol et.';

export function errorStatus(error: unknown): number | undefined {
  const status = error && typeof error === 'object' ? (error as { status?: unknown }).status : undefined;
  return typeof status === 'number' ? status : undefined;
}

/** A refusal is an answer: nothing was saved. Anything else (network, 5xx) leaves the outcome unknown. */
export function isPrepareRefusal(error: unknown): boolean {
  return [400, 404, 409, 422].includes(errorStatus(error) ?? 0);
}

function errorCode(error: unknown): unknown {
  const data = error && typeof error === 'object' ? (error as { data?: unknown }).data : undefined;
  const detail = data && typeof data === 'object' ? (data as { detail?: unknown }).detail : undefined;
  return detail && typeof detail === 'object' && !Array.isArray(detail) ? (detail as { code?: unknown }).code : undefined;
}

/** HTTP 409 action_archived: the list WAS applied, only the stored reply is gone. */
export function isActionArchived(error: unknown): boolean {
  return errorStatus(error) === 409 && errorCode(error) === 'action_archived';
}

export function prepareRefusalText(error: unknown): string {
  const code = errorCode(error);
  if (typeof code === 'string' && REFUSALS[code]) return REFUSALS[code];
  if (errorStatus(error) === 422) return 'Liste geçersiz sayıldı. Listen kaydedilmedi.';
  return 'Liste kaydedilmedi. Güncel durumu yenileyip yeniden dene.';
}
