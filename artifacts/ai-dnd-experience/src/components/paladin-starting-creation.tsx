import type { PaladinStartingCreationOptions } from '@workspace/api-client-react';
import type { StartingDraft } from '@/lib/sorcerer-starting-creation';
import { asiChoiceLabel, sourceAsiChoice } from '@/lib/asi-choices';
import { AsiChoicePicker } from './asi-choice-picker';
import { ProgressionEffectsNotice } from './sorcerer-starting-creation';

const LEVEL_TWO = 2;
const LEVEL_THREE = 3;
const LEVEL_FOUR = 4;
const LEVEL_FIVE = 5;
const BLESSED_WARRIOR = 'Blessed Warrior';
const SELECTABLE_LEVELS = [LEVEL_TWO, LEVEL_THREE, LEVEL_FOUR, LEVEL_FIVE] as const;
type StartingLevel = 1 | typeof LEVEL_TWO | typeof LEVEL_THREE | typeof LEVEL_FOUR | typeof LEVEL_FIVE;

export function PaladinStartingLevelControl({ draft, metadata, onChange, onRetry, disabled = false }: {
  draft: StartingDraft; metadata?: PaladinStartingCreationOptions; onChange: (level: StartingLevel) => void;
  onRetry: () => void; disabled?: boolean;
}) {
  const unavailable = draft.startingLevel > 1 && !metadata;
  return <div className="cc-sub-section">
    <label>Başlangıç seviyesi <select data-testid="paladin-starting-level" value={draft.startingLevel} disabled={disabled} onChange={event => {
      const level = Number(event.target.value);
      // A level is offered only by the live catalog; nothing is inferred from the class name.
      if (level === 1) onChange(1);
      else {
        const advertised = SELECTABLE_LEVELS.find(candidate => candidate === level);
        if (advertised && metadata?.supported_starting_levels.includes(advertised)) onChange(advertised);
      }
    }}>{(metadata?.supported_starting_levels ?? [1]).map(level => <option key={level} value={level}>{level}</option>)}
      {unavailable && <option value={draft.startingLevel} disabled>{draft.startingLevel} — kullanılamıyor</option>}
    </select></label>
    {unavailable && <p role="status">Seçili Paladin seviyesi doğrulanamıyor. Yeniden deneyin veya açıkça seviye 1 seçin; seçim otomatik düşürülmez.</p>}
    {!metadata && <button type="button" disabled={disabled} onClick={onRetry}>Yeniden dene</button>}
    {SELECTABLE_LEVELS.some(level => level === draft.startingLevel) && metadata && <PaladinStartingScope metadata={metadata} level={draft.startingLevel} />}
  </div>;
}

function SpellPick({ level, value, ids, disabled, onChange }: { level: number; value: string; ids: string[] | undefined; disabled: boolean; onChange: (id: string) => void }) {
  return <label>{level}. seviye hazır büyü <select data-testid={`paladin-prepared-${level}`} value={value} disabled={disabled} onChange={event => onChange(event.target.value)}>
    <option value="">Seçin</option>
    {ids?.map(id => <option key={id} value={id}>{id}</option>)}
  </select></label>;
}

/** Each step's picks; nothing is chosen for the player and the server applies them on the final confirmation. */
export function PaladinStartingChoices({ draft, metadata, onChange, disabled = false }: {
  draft: StartingDraft; metadata?: PaladinStartingCreationOptions; onChange: (draft: StartingDraft) => void; disabled?: boolean;
}) {
  const two = metadata?.level_2;
  if (!two) return <p role="status">Paladin seviye 2 seçenekleri doğrulanamadı.</p>;
  const level = draft.startingLevel;
  const three = level >= LEVEL_THREE ? metadata?.level_3 : undefined;
  const four = level >= LEVEL_FOUR ? metadata?.level_4 : undefined;
  const five = level === LEVEL_FIVE ? metadata?.level_5 : undefined;
  const asi = four && draft.level4Asi ? sourceAsiChoice(four.supported_asi_choices, draft.level4Asi) : undefined;
  const cantrips = draft.paladinCantrips ?? [];
  return <div className="cc-sub-section" data-testid="paladin-start-choices">
    <SpellPick level={LEVEL_TWO} value={draft.level2Prepared[0] ?? ''} ids={two.prepared_spell_ids} disabled={disabled} onChange={id => onChange({ ...draft, level2Prepared: id ? [id] : [] })} />
    <label>Fighting Style <select data-testid="paladin-style-choice" value={draft.paladinStyle ?? ''} disabled={disabled}
      onChange={event => onChange({ ...draft, paladinStyle: event.target.value, paladinCantrips: [] })}>
      <option value="">Seçin</option>
      {two.fighting_style_options.map(option => <option key={option} value={option}>{option}</option>)}
    </select></label>
    {draft.paladinStyle === BLESSED_WARRIOR && [0, 1].map(index => <label key={index}>Cleric cantrip {index + 1} <select data-testid={`paladin-cantrip-${index + 1}`} value={cantrips[index] ?? ''} disabled={disabled} onChange={event => {
      const selected = [cantrips[0] ?? '', cantrips[1] ?? '']; selected[index] = event.target.value;
      onChange({ ...draft, paladinCantrips: selected });
    }}><option value="">Seçin</option>{two.blessed_warrior_cantrip_ids.map(id => <option key={id} value={id}>{id}</option>)}</select></label>)}
    {three && <>
      <SpellPick level={LEVEL_THREE} value={draft.level3Prepared[0] ?? ''} ids={three.prepared_spell_ids} disabled={disabled} onChange={id => onChange({ ...draft, level3Prepared: id ? [id] : [] })} />
      <label>Alt sınıf <select data-testid="paladin-subclass" value={draft.subclassId} disabled={disabled} onChange={event => onChange({ ...draft, subclassId: event.target.value })}>
        <option value="">Seçin</option>
        {three.subclass_options.map(option => <option key={option.id} value={option.id}>{option.name}</option>)}
      </select></label>
    </>}
    {level >= LEVEL_THREE && !three && <p role="status">Paladin seviye 3 seçenekleri doğrulanamadı.</p>}
    {level >= LEVEL_FOUR && !four && <p role="status">Paladin seviye 4 seçenekleri doğrulanamadı.</p>}
    {four && <fieldset disabled={disabled} className="cc-sub-section"><legend>4. seviye seçimleri</legend>
      <SpellPick level={LEVEL_FOUR} value={draft.level4Prepared?.[0] ?? ''} ids={four.prepared_spell_ids} disabled={disabled} onChange={id => onChange({ ...draft, level4Prepared: id ? [id] : [] })} />
      <AsiChoicePicker choices={four.supported_asi_choices} selected={asi} disabled={disabled} testId="paladin-asi-choice"
        onChange={choice => onChange({ ...draft, level4Asi: choice, level4ConConfirmed: false })} />
      <label><input type="checkbox" data-testid="paladin-asi-confirm" disabled={disabled || !asi} checked={draft.level4ConConfirmed ?? false}
        onChange={event => { if (!disabled && asi) onChange({ ...draft, level4ConConfirmed: event.target.checked }); }} /> {asiChoiceLabel(asi)} seçimini onaylıyorum.</label>
    </fieldset>}
    {five && <SpellPick level={LEVEL_FIVE} value={draft.level5Prepared?.[0] ?? ''} ids={five.prepared_spell_ids} disabled={disabled} onChange={id => onChange({ ...draft, level5Prepared: id ? [id] : [] })} />}
    <p>Seçimlerin son Oluştur onayıyla sunucuda doğrulanır.</p>
  </div>;
}

function scopeBlock(metadata: PaladinStartingCreationOptions | undefined, level: number) {
  const blocks = { [LEVEL_TWO]: metadata?.level_2, [LEVEL_THREE]: metadata?.level_3, [LEVEL_FOUR]: metadata?.level_4, [LEVEL_FIVE]: metadata?.level_5 };
  return blocks[level as keyof typeof blocks];
}

/** Every level's server list is cumulative, so the block of the chosen level is the whole scope. */
export function PaladinStartingScope({ metadata, level = LEVEL_TWO }: { metadata?: PaladinStartingCreationOptions; level?: number }) {
  const block = scopeBlock(metadata, level);
  if (!metadata || !block) return <p role="status">Paladin seviye {level} kapsamı doğrulanamadı.</p>;
  return <aside className="cc-progression-notice" data-testid="paladin-starting-scope">
    <strong>Paladin başlangıç seviyesi {level}</strong>
    <p>Seviye seçimini son Oluştur onayıyla uygularsın. Bu akış tüm Paladin özelliklerinin uygulandığı anlamına gelmez.</p>
    <h4>Desteklenen kapsam</h4>
    <ul>{block.effects_supported.map((effect, index) => <li key={index}>{effect}</li>)}</ul>
    <ProgressionEffectsNotice effects={block.effects_pending} />
    <p>Can ve XP sunucu tarafından oluşturulur.</p>
  </aside>;
}

/** Review-step text: the picks as the player made them; the server applies and validates them on the final confirmation. */
export function PaladinStartingSummary({ draft, metadata }: { draft: StartingDraft; metadata?: PaladinStartingCreationOptions }) {
  if (draft.startingLevel < LEVEL_TWO) return null;
  const asi = draft.startingLevel >= LEVEL_FOUR && draft.level4Asi ? sourceAsiChoice(metadata?.level_4?.supported_asi_choices, draft.level4Asi) : undefined;
  const prepared = [draft.level2Prepared[0], draft.level3Prepared[0], draft.level4Prepared?.[0], draft.level5Prepared?.[0]].filter(Boolean);
  return <>
    <PaladinStartingScope metadata={metadata} level={draft.startingLevel} />
    <div className="cc-sub-section">
      <p>Fighting Style: {draft.paladinStyle || '—'}{draft.paladinCantrips?.length ? ` (${draft.paladinCantrips.join(', ')})` : ''}</p>
      <p>Ek hazır büyüler: {prepared.join(', ') || '—'}</p>
      {draft.startingLevel >= LEVEL_THREE && <p>Alt sınıf seçimi: {metadata?.level_3?.subclass_options.find(option => option.id === draft.subclassId)?.name ?? '—'}</p>}
      {draft.startingLevel >= LEVEL_FOUR && <p>Ability Score Improvement: {asiChoiceLabel(asi)} (sunucu uygular)</p>}
    </div>
  </>;
}
