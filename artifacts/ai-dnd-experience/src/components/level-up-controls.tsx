import { AsiChoicePicker } from './asi-choice-picker';
import { sourceAsiChoice, asiChoiceLabel, type AsiChoice } from '@/lib/asi-choices';
import { useState } from 'react';
import { getGameSessionLevelUp, type FighterLevel3Choices, type LevelUpPreviewResponse, type LevelUpApplyRequest, type RogueLevel3Choices } from '@workspace/api-client-react';
import { useActionLifetime } from '@/lib/action-reconciliation';
import { currentAccountOwner } from '@/lib/account-session';
import { ProgressionEffectsNotice } from './sorcerer-starting-creation';

export type LevelUpRequest = Omit<LevelUpApplyRequest, 'action_id'>;
type Draft = { asi?: AsiChoice; cantrip: string; preparedSpell: string; preparedSpells?: string[]; metamagic?: string[]; subclassId?: string; primalKnowledgeSkill?: string; confirmed: boolean };
const EMPTY: Draft = { cantrip: '', preparedSpell: '', confirmed: false };
type SubclassPick = (FighterLevel3Choices | RogueLevel3Choices)['subclass_id'];
const SUBCLASS_PICKS: readonly SubclassPick[] = ['champion', 'assassin'];  // the generated contract's ids: an offered id outside them cannot be sent

export function LevelUpChoices({ preview, draft, onChange, onConfirm, onCancel, disabled = false }: {
  preview: LevelUpPreviewResponse; draft: Draft; onChange: (draft: Draft) => void;
  onConfirm: (request: LevelUpRequest) => void; onCancel: () => void; disabled?: boolean;
}) {
  if (preview.status !== 'ready') return <div role="status" data-testid="level-up-blocked">Seviye seçimi şu anda kullanılamıyor: {preview.reason ?? 'Desteklenmeyen ilerleme'}<button type="button" onClick={onCancel}>Kapat</button></div>;
  const counts = preview.choices_required;
  const preparedCount = counts?.prepared_spells ?? 0;
  const needsCantrip = counts?.cantrips === 1;
  const needsAsi = counts?.asi === 1;
  const exactCounts = (expected: Record<string, number>) => Object.keys(counts ?? {}).length === Object.keys(expected).length
    && Object.entries(expected).every(([key, value]) => counts?.[key] === value);
  const sorcerer = preview.class_name === 'Sorcerer';
  // Legacy4/5 previews predate class_name; early steps require the explicit server class.
  const retainedSorcerer = sorcerer || preview.class_name == null;
  const needsMetamagic = sorcerer && preview.target_level === 2 && exactCounts({ prepared_spells: 2, metamagic: 2 });
  const needsSubclass = sorcerer && preview.target_level === 3 && exactCounts({ prepared_spells: 2, subclass_id: 1 });
  // Barbarian 2 (Danger Sense/Reckless Attack) and 5 (Extra Attack/Fast Movement) have no choices: explicit confirmation of an empty object.
  const fighter = preview.class_name === 'Fighter' || preview.class_name === 'Rogue';  // the same step shapes
  const emptyChoice = (preview.class_name === 'Barbarian' || fighter) && (preview.target_level === 2 || preview.target_level === 5) && exactCounts({});
  const needsSubclassPick = fighter && preview.target_level === 3 && exactCounts({ subclass_id: 1 });
  const needsBerserker = preview.class_name === 'Barbarian' && preview.target_level === 3 && exactCounts({ subclass_id: 1, primal_knowledge_skill: 1 });
  const needsNoncasterAsi = (preview.class_name === 'Barbarian' || fighter) && preview.target_level === 4 && exactCounts({ asi: 1 }) && preview.capacity === null;
  const supported = needsNoncasterAsi || needsBerserker || needsSubclassPick || needsMetamagic || needsSubclass || emptyChoice
    || (retainedSorcerer && preview.target_level === 4 && exactCounts({ prepared_spells: 1, cantrips: 1, asi: 1 }))
    || (retainedSorcerer && preview.target_level === 5 && exactCounts({ prepared_spells: 2 }));
  if (!supported) return <p role="status">Bu seviye seçimleri henüz desteklenmiyor.</p>;
  const prepared = emptyChoice || needsBerserker || needsSubclassPick || needsNoncasterAsi ? [] : draft.preparedSpells ?? [draft.preparedSpell];
  const metamagic = draft.metamagic ?? [];
  const asi = sourceAsiChoice(preview.supported_asi_choices, draft.asi, draft.confirmed);
  const subclassPick = SUBCLASS_PICKS.find(id => id === draft.subclassId);
  const valid = !!preview.campaign_id && Number.isInteger(preview.revision)
    && (!needsAsi || (!!asi && draft.confirmed))
    && (!emptyChoice || draft.confirmed)
    && (!needsBerserker || (draft.confirmed && preview.subclass_options?.some(option => option.id === draft.subclassId) && preview.primal_knowledge_skill_options?.includes(draft.primalKnowledgeSkill ?? '')))
    && (!needsSubclassPick || (draft.confirmed && !!subclassPick && preview.subclass_options?.some(option => option.id === subclassPick)))
    && (!needsMetamagic || (metamagic.length === 2 && new Set(metamagic).size === 2 && metamagic.every(id => preview.metamagic_options?.includes(id))))
    && (!needsSubclass || !!preview.subclass_options?.some(option => option.id === draft.subclassId))
    && (!needsCantrip || preview.cantrip_ids?.includes(draft.cantrip))
    && prepared.length === preparedCount && new Set(prepared).size === preparedCount
    && prepared.every(id => preview.prepared_spell_ids?.includes(id));
  return <fieldset disabled={disabled} data-testid="level-up-choices">
    <legend>Kazanılmış {preview.target_level}. seviye seçimleri</legend>
    <p>{preview.class_name ?? 'Sorcerer'}{preview.from_level != null ? ` ${preview.from_level} → ${preview.target_level}` : ` · ${preview.target_level}. seviye`}. XP kazandırmaz; kazanılmış sıradaki adımı tamamlar.</p>
    {needsAsi && <AsiChoicePicker choices={preview.supported_asi_choices} selected={asi} disabled={disabled} testId="level-up-asi-choice" onChange={choice => onChange({ ...draft, asi: choice, confirmed: false })} />}
    {!emptyChoice && <p>Desteklenen ve bekleyen kapsamı sunucu aşağıda bildirir. Tüm büyü ve sınıf özellikleri desteklenmiş değildir.</p>}
    {emptyChoice && <p>Bu adım ek seçim gerektirmez. Yalnız aşağıda belirtilen kapsam desteklenir; tüm sınıf özellikleri uygulanmış değildir.</p>}
    {needsCantrip && <label>Yeni cantrip <select data-testid="level-up-cantrip" value={draft.cantrip} onChange={event => onChange({ ...draft, cantrip: event.target.value })}><option value="">Bir cantrip seç</option>{preview.cantrip_ids?.map(id => <option key={id} value={id}>{id}</option>)}</select></label>}
    {Array.from({ length: preparedCount }, (_, index) => <label key={index}>Yeni hazırlanmış büyü {preparedCount > 1 ? index + 1 : ''} <select data-testid={index === 0 ? 'level-up-prepared' : `level-up-prepared-${index + 1}`} value={prepared[index] ?? ''} onChange={event => {
      const selected = Array.from({ length: preparedCount }, (_, i) => i === index ? event.target.value : prepared[i] ?? '');
      onChange({ ...draft, preparedSpell: selected[0], preparedSpells: selected });
    }}><option value="">Bir büyü seç</option>{preview.prepared_spell_ids?.map(id => <option key={id} value={id}>{id}</option>)}</select></label>)}
    {needsMetamagic && <fieldset disabled={disabled}><legend>İki farklı Metamagic seçimi — desteklenen kapsam aşağıdadır</legend>
      {[0, 1].map(index => <label key={index}>Metamagic {index + 1} <select data-testid={index === 0 ? 'level-up-metamagic' : 'level-up-metamagic-2'} value={metamagic[index] ?? ''} onChange={event => {
        const selected = [metamagic[0] ?? '', metamagic[1] ?? '']; selected[index] = event.target.value;
        onChange({ ...draft, metamagic: selected });
      }}><option value="">Metamagic seç</option>{preview.metamagic_options?.map(id => <option key={id} value={id}>{id}</option>)}</select></label>)}
    </fieldset>}
    {needsSubclass && <fieldset disabled={disabled}><legend>Alt sınıf seçimi — desteklenen kapsam aşağıdadır</legend>
      {preview.subclass_options?.map(option => <label key={option.id}><input type="radio" name="level-up-subclass" value={option.id} checked={draft.subclassId === option.id} disabled={disabled}
        onChange={() => onChange({ ...draft, subclassId: option.id })} />{option.name}</label>)}
    </fieldset>}
    {needsBerserker && <>
      <label>Alt sınıf <select data-testid="level-up-subclass" value={draft.subclassId ?? ''} onChange={event => onChange({ ...draft, subclassId: event.target.value, confirmed: false })}><option value="">Alt sınıf seç</option>{preview.subclass_options?.map(option => <option key={option.id} value={option.id}>{option.name}</option>)}</select></label>
      <label>Primal Knowledge — ek beceri <select data-testid="level-up-primal-skill" value={draft.primalKnowledgeSkill ?? ''} onChange={event => onChange({ ...draft, primalKnowledgeSkill: event.target.value, confirmed: false })}><option value="">Sunucunun sunduğu yeni beceriyi seç</option>{preview.primal_knowledge_skill_options?.map(skill => <option key={skill} value={skill}>{skill}</option>)}</select></label>
      <label><input type="checkbox" data-testid="level-up-confirm-berserker" checked={draft.confirmed} disabled={disabled} onChange={event => onChange({ ...draft, confirmed: event.target.checked })} /> Alt sınıf ve ek beceri seçimlerimi onaylıyorum.</label>
    </>}
    {needsSubclassPick && <>
      <label>Alt sınıf <select data-testid="level-up-subclass" value={draft.subclassId ?? ''} onChange={event => onChange({ ...draft, subclassId: event.target.value, confirmed: false })}><option value="">Alt sınıf seç</option>{preview.subclass_options?.map(option => <option key={option.id} value={option.id}>{option.name}</option>)}</select></label>
      <label><input type="checkbox" data-testid="level-up-confirm-subclass" checked={draft.confirmed} disabled={disabled} onChange={event => onChange({ ...draft, confirmed: event.target.checked })} /> Alt sınıf seçimimi onaylıyorum.</label>
    </>}
    {emptyChoice && <label><input type="checkbox" data-testid="level-up-confirm-empty" checked={draft.confirmed} disabled={disabled}
      onChange={event => onChange({ ...draft, confirmed: event.target.checked })} /> Bu kazanılmış adımın uygulanmasını onaylıyorum.</label>}
    {needsAsi && <label><input data-testid="level-up-confirm-con" type="checkbox" disabled={disabled || !asi} checked={draft.confirmed} onChange={event => { if (!disabled && asi) onChange({ ...draft, confirmed: event.target.checked }); }} /> Ability Score Improvement: {asiChoiceLabel(asi)} seçimini onaylıyorum.</label>}
    {!!preview.effects_supported?.length && <aside data-testid="level-up-supported-effects" aria-label="Desteklenen etkiler"><strong>Sunucunun bildirdiği desteklenen kapsam</strong><ul>{preview.effects_supported.map((effect, index) => <li key={index}>{effect}</li>)}</ul></aside>}
    <ProgressionEffectsNotice effects={preview.effects_pending} />
    <button type="button" className="dnd-button" data-testid="button-confirm-level-up" disabled={disabled || !valid} onClick={() => {
      if (!valid || disabled || !preview.campaign_id || preview.revision == null || preview.target_level == null) return;
      onConfirm({ campaign_id: preview.campaign_id, expected_revision: preview.revision, target_level: preview.target_level,
        choices: emptyChoice ? {} : needsSubclassPick && subclassPick ? { subclass_id: subclassPick } : needsBerserker ? { subclass_id: draft.subclassId!, primal_knowledge_skill: draft.primalKnowledgeSkill! } : needsMetamagic ? { prepared_spells: prepared, metamagic }
          : needsSubclass ? { prepared_spells: prepared, subclass_id: draft.subclassId! }
          : needsNoncasterAsi && asi ? { asi }
          : needsAsi && asi ? { cantrips: [draft.cantrip], prepared_spells: prepared, asi } : { prepared_spells: prepared } });
    }}>Seçimleri uygula</button>
    <button type="button" className="dnd-button secondary" data-testid="button-cancel-level-up" disabled={disabled} onClick={onCancel}>Taslağı iptal et</button>
    <p>Taslağı kapatmak kazanılmış XP veya temel HP artışını geri almaz. Gönderilmiş işlemler yalnız sunucunun doğrulanmış sonucuyla kapatılır.</p>
  </fieldset>;
}

export function LevelUpControls({ sessionId, campaignId, disabled, onConfirm }: {
  sessionId: string; campaignId: string; disabled: boolean; onConfirm: (request: LevelUpRequest) => void;
}) {
  const [preview, setPreview] = useState<LevelUpPreviewResponse | null>(null);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const lifetime = useActionLifetime(`${currentAccountOwner() ?? 'local'}:${campaignId}:${sessionId}`);
  const open = async () => {
    if (disabled || loading) return;
    const operation = lifetime.begin(); if (!operation) return;
    setLoading(true); setError(false);
    try {
      const result = await getGameSessionLevelUp(sessionId, { signal: operation.signal });
      if (!operation.isCurrent() || result.session_id !== sessionId || result.campaign_id !== campaignId) return;
      setPreview(result); setDraft(EMPTY);
    } catch { if (operation.isCurrent()) setError(true); }
    finally { if (operation.isCurrent()) setLoading(false); operation.close(); }
  };
  return <section className="dnd-card p-4" data-testid="level-up-controls" aria-label="Seviye ilerlemesi">
    <button type="button" className="dnd-button secondary" data-testid="button-open-level-up" disabled={disabled || loading} onClick={() => void open()}>{loading ? 'Seviye kontrol ediliyor…' : 'Kazanılmış seviye seçimlerini kontrol et'}</button>
    {error && <p role="alert">Seviye seçenekleri yüklenemedi. Yeniden kontrol et.</p>}
    {preview && <LevelUpChoices preview={preview} draft={draft} onChange={setDraft} disabled={disabled} onCancel={() => { setPreview(null); setDraft(EMPTY); }} onConfirm={request => { onConfirm(request); setPreview(null); setDraft(EMPTY); }} />}
  </section>;
}
