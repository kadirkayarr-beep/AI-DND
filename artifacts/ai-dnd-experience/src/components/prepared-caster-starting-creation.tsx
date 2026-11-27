import type { StartingDraft } from '@/lib/sorcerer-starting-creation';
import { asiChoiceLabel, sourceAsiChoice } from '@/lib/asi-choices';
import { updateLimitedSelection } from '@/lib/character-catalog-normalizer';
import { availableBookSpells, availableCasterCantrips, casterOptions, isCasterStartClass, pruneCasterDraft, type CasterStarting } from '@/lib/prepared-caster-starting-creation';
import { spellLabel } from '@/lib/spell-names';
import { AsiChoicePicker } from './asi-choice-picker';
import { ProgressionEffectsNotice } from './sorcerer-starting-creation';

// Wizard and Cleric starts 2-5: the Wizard adds two spellbook spells at every level, both pick a subclass at 3 and a cantrip plus an ASI at 4.
type StartingLevel = 1 | 2 | 3 | 4 | 5;
type BookField = 'level2Prepared' | 'level3Prepared' | 'level4Prepared' | 'level5Prepared';
type Common = { characterClass: string; sources?: CasterStarting; draft: StartingDraft; disabled?: boolean };
const TR_CLASS = { Wizard: 'Büyücü', Cleric: 'Rahip' } as const;
const BOOK_FIELDS: Record<2 | 3 | 4 | 5, BookField> = { 2: 'level2Prepared', 3: 'level3Prepared', 4: 'level4Prepared', 5: 'level5Prepared' };

export function PreparedCasterStartingLevelControl({ characterClass, sources, draft, onChange, onRetry, disabled = false }: Common & { onChange: (level: StartingLevel) => void; onRetry: () => void }) {
  if (!isCasterStartClass(characterClass)) return null;
  const metadata = casterOptions(characterClass, sources);
  const unavailable = draft.startingLevel > 1 && !metadata;
  return <div className="cc-sub-section">
    <label>Başlangıç seviyesi <select data-testid={`${characterClass.toLowerCase()}-starting-level`} value={draft.startingLevel} disabled={disabled} onChange={event => {
      const level = Number(event.target.value);
      // A level is offered only by the live catalog; nothing is inferred from the class name.
      if (level === 1 || (metadata && (level === 2 || level === 3 || level === 4 || level === 5) && metadata.supported_starting_levels.includes(level))) onChange(level as StartingLevel);
    }}>{(metadata?.supported_starting_levels ?? [1]).map(level => <option key={level} value={level}>{level}</option>)}
      {unavailable && <option value={draft.startingLevel} disabled>{draft.startingLevel} — kullanılamıyor</option>}
    </select></label>
    {unavailable && <p role="status">Seçili {TR_CLASS[characterClass]} seviyesi doğrulanamıyor. Yeniden deneyin veya açıkça seviye 1 seçin; seçim otomatik düşürülmez.</p>}
    {!metadata && <button type="button" disabled={disabled} onClick={onRetry}>Yeniden dene</button>}
  </div>;
}

export function PreparedCasterStartingChoices({ characterClass, sources, draft, initialSpells, initialCantrips, onChange, disabled = false }: Common & {
  initialSpells: string[]; initialCantrips: string[]; onChange: (draft: StartingDraft) => void;
}) {
  const metadata = casterOptions(characterClass, sources);
  if (!isCasterStartClass(characterClass) || draft.startingLevel < 2) return null;
  const prefix = characterClass.toLowerCase();
  if (!metadata) return <p role="status">{TR_CLASS[characterClass]} seviye seçenekleri doğrulanamadı.</p>;
  const update = (next: StartingDraft) => onChange(pruneCasterDraft(characterClass, next, metadata, initialSpells, initialCantrips));
  const picks = (field: BookField | 'level4Cantrips', options: string[], count: number) => <>
    <p>{(draft[field] ?? []).length}/{count} seçildi</p>
    <div className="cc-checkbox-grid">{options.map(id => <label className="cc-checkbox-card" key={id}>
      <input type="checkbox" value={id} checked={(draft[field] ?? []).includes(id)} disabled={disabled}
        onChange={event => update({ ...draft, [field]: updateLimitedSelection(draft[field] ?? [], id, event.target.checked, count) })} />
      <span>{spellLabel(id)}</span>
    </label>)}</div>
  </>;
  const asi = draft.level4Asi ? sourceAsiChoice(metadata.level_4.supported_asi_choices, draft.level4Asi) : undefined;
  return <div className="cc-starting-choices" data-testid={`${prefix}-starting-choices`}>
    {characterClass === 'Wizard' && ([2, 3, 4, 5] as const).filter(level => level <= draft.startingLevel).map(level => <fieldset key={level} disabled={disabled} className="cc-sub-section">
      <legend>{level}. seviye büyü defterine eklenecek büyüler</legend>
      {picks(BOOK_FIELDS[level], availableBookSpells(metadata, draft, initialSpells, level), 2)}
    </fieldset>)}
    {draft.startingLevel >= 3 && <fieldset disabled={disabled} className="cc-sub-section"><legend>Alt sınıf</legend>
      {metadata.level_3.subclass_options.map(option => <label className="cc-checkbox-card" key={option.id}>
        <input type="radio" name={`${prefix}-subclass`} value={option.id} checked={draft.subclassId === option.id} disabled={disabled}
          onChange={() => update({ ...draft, subclassId: option.id })} />{option.name}
      </label>)}
    </fieldset>}
    {draft.startingLevel >= 4 && <>
      <fieldset disabled={disabled} className="cc-sub-section" data-testid={`${prefix}-level4-cantrips`}><legend>4. seviye ek cantrip</legend>
        {picks('level4Cantrips', availableCasterCantrips(metadata, initialCantrips), 1)}
      </fieldset>
      <fieldset disabled={disabled} className="cc-sub-section"><legend>4. seviye Yetenek Puanı Artışı</legend>
        <AsiChoicePicker choices={metadata.level_4.supported_asi_choices} selected={asi} disabled={disabled} testId={`${prefix}-asi-choice`}
          onChange={choice => update({ ...draft, level4Asi: choice, level4ConConfirmed: false })} />
        <label><input type="checkbox" data-testid={`${prefix}-asi-confirm`} disabled={disabled || !asi} checked={draft.level4ConConfirmed ?? false}
          onChange={event => { if (!disabled && asi) update({ ...draft, level4ConConfirmed: event.target.checked }); }} /> {asiChoiceLabel(asi)} seçimini onaylıyorum.</label>
      </fieldset>
    </>}
    <p>Seçimlerin son Oluştur onayıyla sunucuda doğrulanır. Normal başlangıç ekipmanı korunur; üst seviyeye özel ek servet ve büyülü eşya henüz uygulanmıyor.</p>
    <ProgressionEffectsNotice effects={metadata.effects_pending_by_level[String(draft.startingLevel) as '1' | '2' | '3' | '4' | '5']} />
  </div>;
}

/** Review-step text: the picks as the player made them; the server applies and validates them on the final confirmation. */
export function PreparedCasterStartingSummary({ characterClass, sources, draft }: Common) {
  const metadata = casterOptions(characterClass, sources);
  if (!isCasterStartClass(characterClass) || draft.startingLevel < 2) return null;
  const subclass = metadata?.level_3.subclass_options.find(option => option.id === draft.subclassId)?.name;
  const asi = draft.startingLevel >= 4 && draft.level4Asi ? sourceAsiChoice(metadata?.level_4.supported_asi_choices, draft.level4Asi) : undefined;
  const book = ([2, 3, 4, 5] as const).filter(level => level <= draft.startingLevel).flatMap(level => draft[BOOK_FIELDS[level]] ?? []);
  return <div className="cc-sub-section" data-testid={`${characterClass.toLowerCase()}-starting-summary`}>
    <ProgressionEffectsNotice effects={metadata?.effects_pending_by_level[String(draft.startingLevel) as '1' | '2' | '3' | '4' | '5']} />
    {characterClass === 'Wizard' && <p>Büyü defterine eklenenler: {book.map(id => spellLabel(id)).join(', ') || '—'}</p>}
    {draft.startingLevel >= 3 && <p>Alt sınıf seçimi: {subclass ?? '—'}</p>}
    {draft.startingLevel >= 4 && <p>Yeni cantrip: {(draft.level4Cantrips ?? []).map(id => spellLabel(id)).join(', ') || '—'}; Yetenek Puanı Artışı: {asiChoiceLabel(asi)} (sunucu uygular)</p>}
  </div>;
}
