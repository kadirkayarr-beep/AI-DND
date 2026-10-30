import type { LevelUpApplyRequest, LevelUpPreviewResponse, PaladinLevel2Choices } from '@workspace/api-client-react';
import { sourceAsiChoice, asiChoiceLabel, type AsiChoice } from '@/lib/asi-choices';
import { AsiChoicePicker } from './asi-choice-picker';
import { ProgressionEffectsNotice } from './sorcerer-starting-creation';

const BLESSED_WARRIOR = 'Blessed Warrior';
const DEVOTION = 'oath_of_devotion';
const LEVEL_TWO = 2;
const LEVEL_THREE = 3;
const LEVEL_FOUR = 4;
const LEVEL_FIVE = 5;
const CANTRIPS = 2;
export type PaladinDraft = { asi?: AsiChoice; preparedSpell: string; subclassId?: string; fightingStyle?: string; blessedCantrips?: string[]; confirmed: boolean };
type LevelUpRequest = Omit<LevelUpApplyRequest, 'action_id'>;

/** Exact server counts per step; anything else is not offered. */
function supported(preview: LevelUpPreviewResponse): boolean {
  const counts = preview.choices_required ?? {};
  const exact = (expected: Record<string, number>) => Object.keys(counts).length === Object.keys(expected).length
    && Object.entries(expected).every(([key, value]) => counts[key] === value);
  return (preview.target_level === LEVEL_TWO && exact({ prepared_spells: 1, fighting_style: 1, cantrips: CANTRIPS }))
    || (preview.target_level === LEVEL_THREE && exact({ prepared_spells: 1, subclass_id: 1 }))
    || (preview.target_level === LEVEL_FOUR && exact({ prepared_spells: 1, asi: 1 }))
    || (preview.target_level === LEVEL_FIVE && exact({ prepared_spells: 1 }));
}

/** The request body when every choice is a server-listed one and confirmed; null keeps the button off. */
export function paladinLevelUpRequest(preview: LevelUpPreviewResponse, draft: PaladinDraft): LevelUpRequest | null {
  if (!supported(preview) || !draft.confirmed || !preview.campaign_id || preview.revision == null || preview.target_level == null) return null;
  if (!preview.prepared_spell_ids?.includes(draft.preparedSpell)) return null;
  const prepared_spells = [draft.preparedSpell];
  const base = { campaign_id: preview.campaign_id, expected_revision: preview.revision, target_level: preview.target_level };
  if (preview.target_level === LEVEL_TWO) {
    const style = draft.fightingStyle ?? '';
    if (!preview.fighting_style_options?.includes(style)) return null;
    const cantrips = draft.blessedCantrips ?? [];
    const blessed = style === BLESSED_WARRIOR;
    if (blessed && (cantrips.length !== CANTRIPS || new Set(cantrips).size !== CANTRIPS || !cantrips.every(id => preview.cantrip_ids?.includes(id)))) return null;
    return { ...base, choices: { prepared_spells, fighting_style: style as PaladinLevel2Choices['fighting_style'], ...(blessed ? { cantrips } : {}) } };
  }
  if (preview.target_level === LEVEL_THREE) {
    if (!preview.subclass_options?.some(option => option.id === draft.subclassId)) return null;
    return { ...base, choices: { prepared_spells, subclass_id: DEVOTION } };
  }
  if (preview.target_level === LEVEL_FOUR) {
    const asi = sourceAsiChoice(preview.supported_asi_choices, draft.asi, draft.confirmed);
    return asi ? { ...base, choices: { prepared_spells, asi } } : null;
  }
  return { ...base, choices: { prepared_spells } };
}

export function PaladinLevelChoices({ preview, draft, onChange, onConfirm, onCancel, disabled = false }: {
  preview: LevelUpPreviewResponse; draft: PaladinDraft; onChange: (draft: PaladinDraft) => void;
  onConfirm: (request: LevelUpRequest) => void; onCancel: () => void; disabled?: boolean;
}) {
  if (!supported(preview)) return <p role="status">Bu seviye seçimleri henüz desteklenmiyor.</p>;
  const request = paladinLevelUpRequest(preview, draft);
  const cantrips = draft.blessedCantrips ?? [];
  const asi = sourceAsiChoice(preview.supported_asi_choices, draft.asi, draft.confirmed);
  return <fieldset disabled={disabled} data-testid="level-up-choices">
    <legend>Kazanılmış {preview.target_level}. seviye seçimleri</legend>
    <p>Paladin {preview.from_level} → {preview.target_level}. XP kazandırmaz; kazanılmış sıradaki adımı tamamlar.</p>
    <p>Desteklenen ve bekleyen kapsamı sunucu aşağıda bildirir. Tüm büyü ve sınıf özellikleri desteklenmiş değildir.</p>
    <label>Yeni hazır büyü <select data-testid="level-up-prepared" value={draft.preparedSpell} onChange={event => onChange({ ...draft, preparedSpell: event.target.value, confirmed: false })}>
      <option value="">Bir büyü seç</option>{preview.prepared_spell_ids?.map(id => <option key={id} value={id}>{id}</option>)}
    </select></label>
    {preview.target_level === LEVEL_TWO && <>
      <label>Fighting Style <select data-testid="level-up-style" value={draft.fightingStyle ?? ''} onChange={event => onChange({ ...draft, fightingStyle: event.target.value, blessedCantrips: [], confirmed: false })}>
        <option value="">Seç</option>{preview.fighting_style_options?.map(option => <option key={option} value={option}>{option}</option>)}
      </select></label>
      {draft.fightingStyle === BLESSED_WARRIOR && [0, 1].map(index => <label key={index}>Cleric cantrip {index + 1} <select data-testid={`level-up-cantrip-${index + 1}`} value={cantrips[index] ?? ''} onChange={event => {
        const selected = [cantrips[0] ?? '', cantrips[1] ?? '']; selected[index] = event.target.value;
        onChange({ ...draft, blessedCantrips: selected, confirmed: false });
      }}><option value="">Seç</option>{preview.cantrip_ids?.map(id => <option key={id} value={id}>{id}</option>)}</select></label>)}
    </>}
    {preview.target_level === LEVEL_THREE && <label>Alt sınıf <select data-testid="level-up-subclass" value={draft.subclassId ?? ''} onChange={event => onChange({ ...draft, subclassId: event.target.value, confirmed: false })}>
      <option value="">Alt sınıf seç</option>{preview.subclass_options?.map(option => <option key={option.id} value={option.id}>{option.name}</option>)}
    </select></label>}
    {preview.target_level === LEVEL_FOUR && <AsiChoicePicker choices={preview.supported_asi_choices} selected={asi} disabled={disabled} testId="level-up-asi-choice" onChange={choice => onChange({ ...draft, asi: choice, confirmed: false })} />}
    <label><input type="checkbox" data-testid="level-up-confirm-paladin" checked={draft.confirmed} disabled={disabled}
      onChange={event => onChange({ ...draft, confirmed: event.target.checked })} /> {preview.target_level === LEVEL_FOUR ? `Ability Score Improvement: ${asiChoiceLabel(asi)} ve` : 'Bu'} seçimleri onaylıyorum.</label>
    {!!preview.effects_supported?.length && <aside data-testid="level-up-supported-effects" aria-label="Desteklenen etkiler"><strong>Sunucunun bildirdiği desteklenen kapsam</strong><ul>{preview.effects_supported.map((effect, index) => <li key={index}>{effect}</li>)}</ul></aside>}
    <ProgressionEffectsNotice effects={preview.effects_pending} />
    <button type="button" className="dnd-button" data-testid="button-confirm-level-up" disabled={disabled || !request} onClick={() => { if (request && !disabled) onConfirm(request); }}>Seçimleri uygula</button>
    <button type="button" className="dnd-button secondary" data-testid="button-cancel-level-up" disabled={disabled} onClick={onCancel}>Taslağı iptal et</button>
    <p>Taslağı kapatmak kazanılmış XP veya temel HP artışını geri almaz. Gönderilmiş işlemler yalnız sunucunun doğrulanmış sonucuyla kapatılır.</p>
  </fieldset>;
}
