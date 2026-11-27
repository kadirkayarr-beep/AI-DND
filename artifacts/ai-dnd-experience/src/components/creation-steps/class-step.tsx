import { StepDice } from '@/components/step-dice';
import { StartingLevelControl } from '@/components/sorcerer-starting-creation';
import { changeStartingLevel } from '@/lib/sorcerer-starting-creation';
import { PaladinStartingLevelControl } from '@/components/paladin-starting-creation';
import { RogueStartingLevelControl, FighterStartingLevelControl, MonkStartingLevelControl } from '@/components/simple-class-starting-creation';
import { BarbarianStartingLevelControl } from '@/components/barbarian-starting-creation';
import { PreparedCasterStartingLevelControl } from '@/components/prepared-caster-starting-creation';
import type { CasterStarting } from '@/lib/prepared-caster-starting-creation';
import { classLevelingNote } from '@/lib/campaign-presentation';
import { ABILITY_NAMES_TR, presentedClassName, portraitStyle, CLASS_PORTRAIT_CELLS, type AbilityKey } from '@/components/character-creation-shared';
import type { NormalizedCharacterCreationCatalog } from '@/lib/character-catalog-normalizer';
import type { StartingDraft, Metadata } from '@/lib/sorcerer-starting-creation';
import type { PaladinStartingCreationOptions, RogueStartingCreationOptions, FighterStartingCreationOptions, MonkStartingCreationOptions, BarbarianStartingCreationOptions } from '@workspace/api-client-react';
import type { Dispatch, SetStateAction } from 'react';

type ClassStepProps = {
  characterClass: string;
  catalog: NormalizedCharacterCreationCatalog;
  setCharacterClass: (value: string) => void;
  startingDraft: StartingDraft;
  startingMetadata: Metadata | undefined;
  creating: boolean;
  onRetryOptions: () => void;
  setStartingDraft: Dispatch<SetStateAction<StartingDraft>>;
  paladinStartingMetadata: PaladinStartingCreationOptions | undefined;
  rogueStartingMetadata: RogueStartingCreationOptions | undefined;
  fighterStartingMetadata: FighterStartingCreationOptions | undefined;
  monkStartingMetadata: MonkStartingCreationOptions | undefined;
  barbarianStartingMetadata: BarbarianStartingCreationOptions | undefined;
  casterStarting: CasterStarting;
  classPortraitSheet: string;
};

export function ClassStep({ characterClass, catalog, setCharacterClass, startingDraft, startingMetadata, creating, onRetryOptions, setStartingDraft, paladinStartingMetadata, rogueStartingMetadata, fighterStartingMetadata, monkStartingMetadata, barbarianStartingMetadata, casterStarting, classPortraitSheet }: ClassStepProps) {
  return (
    <section className="cc-step-panel">
          <div className="cc-step-header">
            <div className="cc-label">Adım 2</div>
            <h2 className="cc-step-title-text">Sınıfını Seç</h2>
            <StepDice label="Sınıf için zar at" testId="button-dice-class" current={characterClass}
              keys={Object.keys((catalog?.classes ?? {}) as Record<string, unknown>)} onPick={setCharacterClass} />
            <p className="cc-literary">Sınıfın, karakterinin dövüş tarzını, can zarını ve temel yeteneklerini belirler.</p>
          </div>

          {characterClass && (
            <div className="cc-starting-level" data-testid="starting-level-block">
              {characterClass === 'Sorcerer' && <StartingLevelControl draft={startingDraft} metadata={startingMetadata}
                disabled={creating} onRetry={onRetryOptions} onChange={level => setStartingDraft(draft => changeStartingLevel(draft, level))} />}
              {characterClass === 'Paladin' && <PaladinStartingLevelControl draft={startingDraft} metadata={paladinStartingMetadata}
                disabled={creating} onRetry={onRetryOptions} onChange={level => setStartingDraft(draft => changeStartingLevel(draft, level))} />}
              {characterClass === 'Rogue' && <RogueStartingLevelControl draft={startingDraft} metadata={rogueStartingMetadata}
                disabled={creating} onRetry={onRetryOptions} onChange={level => setStartingDraft(draft => changeStartingLevel(draft, level))} />}
              {characterClass === 'Fighter' && <FighterStartingLevelControl draft={startingDraft} metadata={fighterStartingMetadata}
                disabled={creating} onRetry={onRetryOptions} onChange={level => setStartingDraft(draft => changeStartingLevel(draft, level))} />}
              {characterClass === 'Monk' && <MonkStartingLevelControl draft={startingDraft} metadata={monkStartingMetadata}
                disabled={creating} onRetry={onRetryOptions} onChange={level => setStartingDraft(draft => changeStartingLevel(draft, level))} />}
              <PreparedCasterStartingLevelControl characterClass={characterClass} sources={casterStarting} draft={startingDraft} disabled={creating} onRetry={onRetryOptions} onChange={level => setStartingDraft(draft => changeStartingLevel(draft, level))} />
              {characterClass === 'Barbarian' && <BarbarianStartingLevelControl draft={startingDraft} metadata={barbarianStartingMetadata}
                disabled={creating} onRetry={onRetryOptions} onChange={level => setStartingDraft(draft => changeStartingLevel(draft, level))} />}
            </div>
          )}

          <div className="cc-cards-grid cc-portrait-grid">
            {catalog?.classes && Object.entries(catalog.classes as Record<string, any>).map(([clsKey, cls]) => {
              const isSelected = characterClass === clsKey;
              return (
                <div
                  key={clsKey}
                  className={`cc-choice-card ${isSelected ? 'selected' : ''}`}
                  data-class-key={clsKey}
                  role="button"
                  tabIndex={0}
                  aria-pressed={isSelected}
                  onClick={() => setCharacterClass(clsKey)}
                >
                  <span
                    className={`cc-portrait ${CLASS_PORTRAIT_CELLS[clsKey.toLowerCase()] === undefined ? 'cc-portrait-neutral' : ''}`}
                    style={portraitStyle(classPortraitSheet, CLASS_PORTRAIT_CELLS[clsKey.toLowerCase()])}
                    aria-hidden="true"
                  />
                  <div className="cc-card-top">
                    <span className="cc-card-title">{presentedClassName(clsKey, cls.name_tr)}</span>
                    <span className="cc-badge">d{cls.hit_die} Can Zarı</span>
                  </div>
                  <p className="cc-card-desc">{cls.desc}</p>
                  <div className="cc-card-features">
                    <span className="cc-feature-tag">Öncelik: {ABILITY_NAMES_TR[cls.primary_ability as AbilityKey]?.short ?? cls.primary_ability}</span>
                    {classLevelingNote(clsKey) && <span className="cc-feature-tag" data-testid={`class-leveling-note-${clsKey}`}>{classLevelingNote(clsKey)}</span>}
                    {cls.features?.slice(0, 2).map((feat: string) => (
                      <span className="cc-feature-tag" key={feat}>{feat}</span>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </section>
  );
}
