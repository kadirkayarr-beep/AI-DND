import type { FighterStartingCreationOptions, MonkStartingCreationOptions, RogueStartingCreationOptions } from '@workspace/api-client-react';
import type { StartingDraft } from '@/lib/sorcerer-starting-creation';
import { asiChoiceLabel, sourceAsiChoice } from '@/lib/asi-choices';
import { AsiChoicePicker } from './asi-choice-picker';
import { ProgressionEffectsNotice } from './sorcerer-starting-creation';

// Fighter, Monk and Rogue starts share one set of controls; only the Turkish class name and the test id prefix differ.
const LEVEL_TWO = 2;
const LEVEL_THREE = 3;
const LEVEL_FOUR = 4;
const LEVEL_FIVE = 5;
const SELECTABLE_LEVELS = [LEVEL_TWO, LEVEL_THREE, LEVEL_FOUR, LEVEL_FIVE] as const;
type StartingLevel = 1 | typeof LEVEL_TWO | typeof LEVEL_THREE | typeof LEVEL_FOUR | typeof LEVEL_FIVE;
type Options = FighterStartingCreationOptions | RogueStartingCreationOptions | MonkStartingCreationOptions;

const CLASS_TEXT = {
  fighter: { prefix: 'fighter', tr: 'Savaşçı' },
  rogue: { prefix: 'rogue', tr: 'Düzenbaz' },
  monk: { prefix: 'monk', tr: 'Keşiş' },
} as const;
type Cls = keyof typeof CLASS_TEXT;

type LevelControlProps = { draft: StartingDraft; metadata?: Options; onChange: (level: StartingLevel) => void; onRetry: () => void; disabled?: boolean };
type ChoicesProps = { draft: StartingDraft; metadata?: Options; onChange: (draft: StartingDraft) => void; disabled?: boolean };

function SimpleStartingLevelControl({ cls, draft, metadata, onChange, onRetry, disabled = false }: LevelControlProps & { cls: Cls }) {
  const { prefix, tr } = CLASS_TEXT[cls];
  const unavailable = draft.startingLevel > 1 && !metadata;
  return <div className="cc-sub-section">
    <label>Başlangıç seviyesi <select data-testid={`${prefix}-starting-level`} value={draft.startingLevel} disabled={disabled} onChange={event => {
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
    {unavailable && <p role="status">Seçili {tr} seviyesi doğrulanamıyor. Yeniden deneyin veya açıkça seviye 1 seçin; seçim otomatik düşürülmez.</p>}
    {!metadata && <button type="button" disabled={disabled} onClick={onRetry}>Yeniden dene</button>}
    {SELECTABLE_LEVELS.some(level => level === draft.startingLevel) && metadata && <SimpleStartingScope cls={cls} metadata={metadata} level={draft.startingLevel} />}
  </div>;
}

/** Start 3 needs the subclass, start 4/5 add the confirmed ASI; nothing is chosen for the player. */
function SimpleStartingChoices({ cls, draft, metadata, onChange, disabled = false }: ChoicesProps & { cls: Cls }) {
  const { prefix, tr } = CLASS_TEXT[cls];
  const source = metadata?.level_3;
  if (!source) return <p role="status">{tr} seviye 3 seçenekleri doğrulanamadı.</p>;
  const four = draft.startingLevel >= LEVEL_FOUR ? metadata?.level_4 : undefined;
  const asi = four && draft.level4Asi ? sourceAsiChoice(four.supported_asi_choices, draft.level4Asi) : undefined;
  return <div className="cc-sub-section" data-testid={`${prefix}-start3-choices`}>
    <label>Alt sınıf <select data-testid={`${prefix}-subclass`} value={draft.subclassId} disabled={disabled}
      onChange={event => onChange({ ...draft, subclassId: event.target.value })}>
      <option value="">Seçin</option>
      {source.subclass_options.map(option => <option key={option.id} value={option.id}>{option.name}</option>)}
    </select></label>
    {draft.startingLevel >= LEVEL_FOUR && !four && <p role="status">{tr} seviye 4 seçenekleri doğrulanamadı.</p>}
    {four && <fieldset disabled={disabled} className="cc-sub-section"><legend>4. seviye Yetenek Puanı Artışı</legend>
      <AsiChoicePicker choices={four.supported_asi_choices} selected={asi} disabled={disabled} testId={`${prefix}-asi-choice`}
        onChange={choice => onChange({ ...draft, level4Asi: choice, level4ConConfirmed: false })} />
      <label><input type="checkbox" data-testid={`${prefix}-asi-confirm`} disabled={disabled || !asi} checked={draft.level4ConConfirmed ?? false}
        onChange={event => { if (!disabled && asi) onChange({ ...draft, level4ConConfirmed: event.target.checked }); }} /> {asiChoiceLabel(asi)} seçimini onaylıyorum.</label>
    </fieldset>}
    <p>Seçimlerin son Oluştur onayıyla sunucuda doğrulanır.</p>
  </div>;
}

function scopeHeading(tr: string, level: number): string | undefined {
  return ({
    [LEVEL_TWO]: `${tr} başlangıç seviyesi 2 — ek seçim gerektirmez.`,
    [LEVEL_THREE]: `${tr} başlangıç seviyesi 3 — alt sınıf seçimi gerekir.`,
    [LEVEL_FOUR]: `${tr} başlangıç seviyesi 4 — alt sınıf ve Yetenek Puanı Artışı seçimi gerekir.`,
    [LEVEL_FIVE]: `${tr} başlangıç seviyesi 5 — alt sınıf ve 4. seviye yetenek puanı artışı seçimi gerekir; 5. seviye ek seçim istemez.`,
  } as Record<number, string>)[level];
}

function scopeBlock(metadata: Options | undefined, level: number) {
  const blocks = { [LEVEL_TWO]: metadata?.level_2, [LEVEL_THREE]: metadata?.level_3, [LEVEL_FOUR]: metadata?.level_4, [LEVEL_FIVE]: metadata?.level_5 };
  return blocks[level as keyof typeof blocks];
}

/** Every level's server list is cumulative, so the block of the chosen level is the whole scope. */
function SimpleStartingScope({ cls, metadata, level = LEVEL_TWO }: { cls: Cls; metadata?: Options; level?: number }) {
  const { prefix, tr } = CLASS_TEXT[cls];
  const block = scopeBlock(metadata, level);
  if (!metadata || !block) return <p role="status">{tr} seviye {level} kapsamı doğrulanamadı.</p>;
  return <aside className="cc-progression-notice" data-testid={`${prefix}-starting-scope`}>
    <strong>{scopeHeading(tr, level)}</strong>
    <p>Seviye seçimini son Oluştur onayıyla uygularsın. Bu akış tüm {tr} özelliklerinin uygulandığı anlamına gelmez.</p>
    <h4>Bu seviyede oyunda işleyenler</h4>
    <p>{block.effects_supported.length} özellik</p>
    <ProgressionEffectsNotice effects={block.effects_pending} />
    <p>Can ve XP sunucu tarafından oluşturulur.</p>
  </aside>;
}

/** Review-step text: the picks as the player made them; the server applies and validates them on the final confirmation. */
function SimpleStartingSummary({ cls, draft, metadata }: { cls: Cls; draft: StartingDraft; metadata?: Options }) {
  if (draft.startingLevel < LEVEL_TWO) return null;
  const asi = draft.startingLevel >= LEVEL_FOUR && draft.level4Asi ? sourceAsiChoice(metadata?.level_4?.supported_asi_choices, draft.level4Asi) : undefined;
  return <>
    <SimpleStartingScope cls={cls} metadata={metadata} level={draft.startingLevel} />
    {draft.startingLevel >= LEVEL_THREE && <div className="cc-sub-section">
      <p>Alt sınıf seçimi: {metadata?.level_3?.subclass_options.find(option => option.id === draft.subclassId)?.name ?? '—'}</p>
      {draft.startingLevel >= LEVEL_FOUR && <p>Yetenek Puanı Artışı: {asiChoiceLabel(asi)} (sunucu uygular)</p>}
    </div>}
  </>;
}

export function FighterStartingLevelControl(props: Omit<LevelControlProps, 'metadata'> & { metadata?: FighterStartingCreationOptions }) { return SimpleStartingLevelControl({ cls: 'fighter', ...props }); }
export function RogueStartingLevelControl(props: Omit<LevelControlProps, 'metadata'> & { metadata?: RogueStartingCreationOptions }) { return SimpleStartingLevelControl({ cls: 'rogue', ...props }); }
export function MonkStartingLevelControl(props: Omit<LevelControlProps, 'metadata'> & { metadata?: MonkStartingCreationOptions }) { return SimpleStartingLevelControl({ cls: 'monk', ...props }); }
export function FighterStartingChoices(props: Omit<ChoicesProps, 'metadata'> & { metadata?: FighterStartingCreationOptions }) { return SimpleStartingChoices({ cls: 'fighter', ...props }); }
export function RogueStartingChoices(props: Omit<ChoicesProps, 'metadata'> & { metadata?: RogueStartingCreationOptions }) { return SimpleStartingChoices({ cls: 'rogue', ...props }); }
export function MonkStartingChoices(props: Omit<ChoicesProps, 'metadata'> & { metadata?: MonkStartingCreationOptions }) { return SimpleStartingChoices({ cls: 'monk', ...props }); }
export function FighterStartingSummary(props: { draft: StartingDraft; metadata?: FighterStartingCreationOptions }) { return SimpleStartingSummary({ cls: 'fighter', ...props }); }
export function RogueStartingSummary(props: { draft: StartingDraft; metadata?: RogueStartingCreationOptions }) { return SimpleStartingSummary({ cls: 'rogue', ...props }); }
export function MonkStartingSummary(props: { draft: StartingDraft; metadata?: MonkStartingCreationOptions }) { return SimpleStartingSummary({ cls: 'monk', ...props }); }
