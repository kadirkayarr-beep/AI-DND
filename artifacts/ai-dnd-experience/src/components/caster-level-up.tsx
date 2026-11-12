import type { ClericLevel3Choices, LevelUpApplyRequest, LevelUpPreviewResponse, WizardLevel3Choices } from '@workspace/api-client-react';
import { sourceAsiChoice, asiChoiceLabel, type AsiChoice } from '@/lib/asi-choices';
import { spellLabel } from '@/lib/spell-names';
import { AsiChoicePicker } from './asi-choice-picker';
import { ProgressionEffectsNotice } from './sorcerer-starting-creation';

type LevelUpRequest = Omit<LevelUpApplyRequest, 'action_id'>;
export type CasterDraft = { spellbookSpells?: string[]; cantrip: string; subclassId?: string; asi?: AsiChoice; confirmed: boolean };
type Shape = { spellbook: boolean; subclass: boolean; asiAndCantrip: boolean };

const BOOK_SPELLS = 2;  // PHB: two Wizard spells added to the book at each Wizard level after 1
// The generated contract's only subclass ids (approved decision 5: one subclass offered per class).
const SUBCLASS: Record<string, WizardLevel3Choices['subclass_id'] | ClericLevel3Choices['subclass_id']> = { Wizard: 'evoker', Cleric: 'life_domain' };

/** The server's exact step shape for Wizard/Cleric 2-5; anything else is not offered here. */
function shapeOf(preview: LevelUpPreviewResponse): Shape | null {
  const cls = preview.class_name ?? '';
  if (!(cls in SUBCLASS)) return null;
  const counts = preview.choices_required ?? {};
  const exact = (expected: Record<string, number>) => Object.keys(counts).length === Object.keys(expected).length
    && Object.entries(expected).every(([key, value]) => counts[key] === value);
  const book: Record<string, number> = cls === 'Wizard' ? { spellbook_spells: BOOK_SPELLS } : {};
  const level = preview.target_level;
  if ((level === 2 || level === 5) && exact(book)) return { spellbook: cls === 'Wizard', subclass: false, asiAndCantrip: false };
  if (level === 3 && exact({ ...book, subclass_id: 1 })) return { spellbook: cls === 'Wizard', subclass: true, asiAndCantrip: false };
  if (level === 4 && exact({ ...book, cantrips: 1, asi: 1 })) return { spellbook: cls === 'Wizard', subclass: false, asiAndCantrip: true };
  return null;
}

export function casterLevelUpSupported(preview: LevelUpPreviewResponse): boolean {
  return shapeOf(preview) !== null;
}

/** The request body when every pick is one the server listed and the player confirmed; null keeps the button off. */
export function casterLevelUpRequest(preview: LevelUpPreviewResponse, draft: CasterDraft): LevelUpRequest | null {
  const shape = shapeOf(preview);
  if (!shape || !draft.confirmed || !preview.campaign_id || preview.revision == null || preview.target_level == null) return null;
  const choices: Record<string, unknown> = {};
  if (shape.spellbook) {
    const picked = draft.spellbookSpells ?? [];
    if (picked.length !== BOOK_SPELLS || new Set(picked).size !== BOOK_SPELLS || !picked.every(id => preview.spellbook_spell_ids?.includes(id))) return null;
    choices.spellbook_spells = [...picked];
  }
  if (shape.subclass) {
    const id = SUBCLASS[preview.class_name ?? ''];
    if (draft.subclassId !== id || !preview.subclass_options?.some(option => option.id === id)) return null;
    choices.subclass_id = id;
  }
  if (shape.asiAndCantrip) {
    const asi = sourceAsiChoice(preview.supported_asi_choices, draft.asi, false);
    if (!draft.asi || !asi || !preview.cantrip_ids?.includes(draft.cantrip)) return null;
    choices.cantrips = [draft.cantrip];
    choices.asi = asi;
  }
  return { campaign_id: preview.campaign_id, expected_revision: preview.revision, target_level: preview.target_level,
    choices: choices as LevelUpRequest['choices'] };
}

/** Wizard/Cleric level step. Pure: the page sends the request (submitLevelUp) and owns its receipt. */
export function CasterLevelChoices({ preview, draft, onChange, onConfirm, onCancel, disabled = false }: {
  preview: LevelUpPreviewResponse; draft: CasterDraft; onChange: (draft: CasterDraft) => void;
  onConfirm: (request: LevelUpRequest) => void; onCancel: () => void; disabled?: boolean;
}) {
  const shape = shapeOf(preview);
  if (!shape) return <p role="status">Bu seviye seçimleri henüz desteklenmiyor.</p>;
  const request = casterLevelUpRequest(preview, draft);
  const book = draft.spellbookSpells ?? [];
  const asi = sourceAsiChoice(preview.supported_asi_choices, draft.asi, false);
  const limit = preview.capacity?.prepared_spells;
  return <fieldset disabled={disabled} data-testid="level-up-choices">
    <legend>Kazanılmış {preview.target_level}. seviye seçimleri</legend>
    <p>{preview.class_name} {preview.from_level} → {preview.target_level}. XP kazandırmaz; kazanılmış sıradaki adımı tamamlar.</p>
    <p>Desteklenen ve bekleyen kapsamı sunucu aşağıda bildirir. Tüm büyü ve sınıf özellikleri desteklenmiş değildir.</p>
    {shape.spellbook && [0, 1].map(index => <label key={index}>Büyü kitabına {index + 1}. büyü <select data-testid={`level-up-spellbook-${index + 1}`} value={book[index] ?? ''} onChange={event => {
      const selected = [book[0] ?? '', book[1] ?? '']; selected[index] = event.target.value;
      onChange({ ...draft, spellbookSpells: selected, confirmed: false });
    }}><option value="">Bir büyü seç</option>{preview.spellbook_spell_ids?.map(id => <option key={id} value={id}>{spellLabel(id)}</option>)}</select></label>)}
    {shape.subclass && <label>Alt sınıf <select data-testid="level-up-subclass" value={draft.subclassId ?? ''} onChange={event => onChange({ ...draft, subclassId: event.target.value, confirmed: false })}>
      <option value="">Alt sınıf seç</option>{preview.subclass_options?.map(option => <option key={option.id} value={option.id}>{option.name}</option>)}
    </select></label>}
    {shape.asiAndCantrip && <>
      <label>Yeni hile (cantrip) <select data-testid="level-up-cantrip" value={draft.cantrip} onChange={event => onChange({ ...draft, cantrip: event.target.value, confirmed: false })}>
        <option value="">Bir hile seç</option>{preview.cantrip_ids?.map(id => <option key={id} value={id}>{spellLabel(id)}</option>)}
      </select></label>
      <AsiChoicePicker choices={preview.supported_asi_choices} selected={asi} disabled={disabled} testId="level-up-asi-choice" onChange={choice => onChange({ ...draft, asi: choice, confirmed: false })} />
    </>}
    <p data-testid="level-up-prepare-window">Seviye uygulanınca büyü hazırlama penceresi açık olur{limit != null ? ` ve hazırlık sınırın ${limit} olur` : ''}. Yeni büyülerini oyun ekranındaki “Büyü hazırlığı” bölümünden seç (çatışma dışında). Yeni seviye penceresinde yalnız büyü ekleyebilirsin; hazırladıklarını değiştirmek için uzun dinlenme gerekir.</p>
    <label><input type="checkbox" data-testid="level-up-confirm-caster" checked={draft.confirmed} disabled={disabled}
      onChange={event => onChange({ ...draft, confirmed: event.target.checked })} /> {shape.asiAndCantrip ? `Ability Score Improvement: ${asiChoiceLabel(asi)} ve bu` : 'Bu'} seçimleri onaylıyorum.</label>
    {!!preview.effects_supported?.length && <aside data-testid="level-up-supported-effects" aria-label="Desteklenen etkiler"><strong>Bu seviyede oyunda işleyenler</strong><p>{preview.effects_supported.length} özellik</p></aside>}
    <ProgressionEffectsNotice effects={preview.effects_pending} />
    <button type="button" className="dnd-button" data-testid="button-confirm-level-up" disabled={disabled || !request} onClick={() => { if (request && !disabled) onConfirm(request); }}>Seçimleri uygula</button>
    <button type="button" className="dnd-button secondary" data-testid="button-cancel-level-up" disabled={disabled} onClick={onCancel}>Taslağı iptal et</button>
    <p>Taslağı kapatmak kazanılmış XP veya temel HP artışını geri almaz. Gönderilmiş işlemler yalnız sunucunun doğrulanmış sonucuyla kapatılır.</p>
  </fieldset>;
}
