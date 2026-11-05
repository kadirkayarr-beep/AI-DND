import { AsiChoicePicker } from './asi-choice-picker';
import { sourceAsiChoice, asiChoiceLabel } from '@/lib/asi-choices';
import { availableStartingSpells, type StartingDraft, type Metadata } from '@/lib/sorcerer-starting-creation';
import { updateLimitedSelection } from '@/lib/character-catalog-normalizer';

export function ProgressionEffectsNotice({ effects }: { effects?: string[] }) {
  if (!effects?.length) return null;
  return <aside className="cc-progression-notice" aria-label="Henüz uygulanmayan özellikler">
    Bu seviyedeki {effects.length} özellik henüz oyunda tam işlemiyor.
  </aside>;
}

/** Draft-only numbers must not impersonate the final server projection at higher starts. */
export function StartingDerivedValue({ level, value, fromLevel = 4 }: { level: number; value: string | number | null | undefined; fromLevel?: number }) {
  return level >= fromLevel ? <span className="cc-deferred-hp">Oluşturulduğunda sunucu hesaplayacak</span> : <span>{value}</span>;
}

export function StartingHitPoints({ level, hitPoints }: { level: number; hitPoints: number }) {
  return level > 1 ? <span className="cc-deferred-hp">Oluşturulduğunda sunucu hesaplayacak</span> : <span>{hitPoints}</span>;
}

export function StartingLevelControl({ draft, metadata, onChange, onRetry, disabled = false }: {
  draft: StartingDraft; metadata?: Metadata; onChange: (level: 1 | 2 | 3 | 4 | 5) => void; onRetry: () => void; disabled?: boolean;
}) {
  const unavailable = draft.startingLevel > 1 && !metadata?.supported_starting_levels.includes(draft.startingLevel);
  return <div className="cc-sub-section">
    <label>Başlangıç seviyesi
      <select value={draft.startingLevel} disabled={disabled} onChange={event => {
        const level = Number(event.target.value);
        if (level === 1 || ((level === 2 || level === 3 || level === 4 || level === 5) && metadata?.supported_starting_levels.includes(level))) onChange(level);
      }}>
        {(metadata?.supported_starting_levels ?? [1]).map(level => <option key={level} value={level}>{level}</option>)}
        {unavailable && <option value={draft.startingLevel} disabled>{draft.startingLevel} — kullanılamıyor</option>}
      </select>
    </label>
    {unavailable && <p role="status">Seviye seçenekleri yüklenemedi. Seçimleriniz korunuyor; yeniden deneyin veya açıkça seviye 1 seçin.</p>}
    {(!metadata || unavailable) && <button type="button" disabled={disabled} onClick={onRetry}>Yeniden dene</button>}
  </div>;
}

export function StartingLevelChoices({ draft, metadata, initialSpells, initialCantrips = [], onChange, spellLabels = {}, disabled = false }: {
  draft: StartingDraft; metadata?: Metadata; initialSpells: string[]; initialCantrips?: string[]; onChange: (draft: StartingDraft) => void;
  spellLabels?: Record<string, string>; disabled?: boolean;
}) {
  if (!metadata || draft.startingLevel === 1) return null;
  const asi = sourceAsiChoice(metadata.level_4?.supported_asi_choices, draft.level4Asi, draft.level4ConConfirmed);
  const available = availableStartingSpells(metadata, initialSpells, draft, initialCantrips);
  const picks = (field: 'level2Prepared' | 'level3Prepared' | 'metamagic' | 'level4Prepared' | 'level4Cantrips' | 'level5Prepared', options: string[], count: number) => <>
    <p>{(draft[field] ?? []).length}/{count} seçildi</p>
    <div className="cc-checkbox-grid">{options.map(id => <label className="cc-checkbox-card" key={id}>
      <input type="checkbox" value={id} checked={(draft[field] ?? []).includes(id)} disabled={disabled}
        onChange={event => onChange({ ...draft, [field]: updateLimitedSelection(draft[field] ?? [], id, event.target.checked, count) })} />
      <span>{field === 'metamagic' ? id : (spellLabels[id] ?? id)}</span>
    </label>)}</div>
  </>;
  return <div className="cc-starting-choices">
    <fieldset disabled={disabled} className="cc-sub-section"><legend>2. seviye ek büyüler</legend>
      {picks('level2Prepared', available.level2, metadata.level_2.prepared_spell_count)}
    </fieldset>
    <fieldset disabled={disabled} className="cc-sub-section"><legend>Metamagic seçimleri — destek kapsamı sunucudan bildirilir</legend>
      {picks('metamagic', metadata.level_2.metamagic_options, metadata.level_2.metamagic_count)}
    </fieldset>
    {draft.startingLevel >= 3 && <>
      <fieldset disabled={disabled} className="cc-sub-section"><legend>3. seviye ek büyüler</legend>
        {picks('level3Prepared', available.level3, metadata.level_3.prepared_spell_count)}
      </fieldset>
      <fieldset disabled={disabled} className="cc-sub-section"><legend>Alt sınıf seçimi — destek kapsamı sunucudan bildirilir</legend>
        <p>{draft.subclassId ? 1 : 0}/1 seçildi</p>
        {metadata.level_3.subclass_options.map(option => <label className="cc-checkbox-card" key={option.id}>
          <input type="radio" name="starting-subclass" value={option.id} checked={draft.subclassId === option.id} disabled={disabled}
            onChange={() => onChange({ ...draft, subclassId: option.id })} />{option.name}
        </label>)}
      </fieldset>
    </>}
    {draft.startingLevel >= 4 && metadata.level_4 && <>
      <fieldset disabled={disabled} className="cc-sub-section"><legend>4. seviye ek büyü</legend>
        {picks('level4Prepared', available.level4, metadata.level_4.prepared_spell_count)}
      </fieldset>
      <fieldset disabled={disabled} className="cc-sub-section" data-testid="starting-level4-cantrips"><legend>4. seviye ek cantrip</legend>
        {picks('level4Cantrips', available.cantrips4, metadata.level_4.cantrip_count)}
      </fieldset>
      <fieldset disabled={disabled} className="cc-sub-section"><legend>4. seviye Ability Score Improvement</legend>
        <AsiChoicePicker choices={metadata.level_4.supported_asi_choices} selected={asi} disabled={disabled} testId="starting-asi-choice"
          onChange={choice => onChange({ ...draft, level4Asi: choice, level4ConConfirmed: false })} />
        <label><input type="checkbox" data-testid="starting-con-plus-two" disabled={disabled || !asi} checked={draft.level4ConConfirmed ?? false}
          onChange={event => { if (!disabled && asi) onChange({ ...draft, level4ConConfirmed: event.target.checked }); }} /> {asiChoiceLabel(asi)} seçimini onaylıyorum.</label>
      </fieldset>
    </>}
    {draft.startingLevel === 5 && metadata.level_5 && <fieldset disabled={disabled} className="cc-sub-section" data-testid="starting-level5-prepared"><legend>5. seviye ek büyüler</legend>
      {picks('level5Prepared', available.level5, metadata.level_5.prepared_spell_count)}
    </fieldset>}
    {draft.startingLevel >= 4 && <p className="cc-progression-notice" data-testid="starting-equipment-limits">Normal başlangıç ekipmanı korunur. Üst seviyeye özel ek servet ve büyülü eşya seçimi henüz uygulanmıyor.</p>}
    <ProgressionEffectsNotice effects={metadata.effects_pending_by_level[String(draft.startingLevel) as '1' | '2' | '3' | '4' | '5']} />
  </div>;
}

/** Keep unavailable initial picks visible until the player explicitly removes them. */
export function StaleInitialSpellChoices({ selectedSpells, metadata, onRemove, disabled = false }: {
  selectedSpells: string[];
  metadata?: Metadata;
  onRemove: (id: string) => void;
  disabled?: boolean;
}) {
  if (!metadata) return null;
  const stale = selectedSpells.filter(id => !metadata.level_2.prepared_spell_ids.includes(id));
  if (!stale.length) return null;
  return <div className="cc-progression-notice" role="status">
    <p>Bu başlangıç büyüleri güncel seçeneklerde yok. Yerlerine seçim yapmak için önce kaldırın.</p>
    <ul>{stale.map(id => <li key={id}>
      <span>{id}</span>{' '}
      <button type="button" disabled={disabled} onClick={() => onRemove(id)}>Kaldır: {id}</button>
    </li>)}</ul>
  </div>;
}
