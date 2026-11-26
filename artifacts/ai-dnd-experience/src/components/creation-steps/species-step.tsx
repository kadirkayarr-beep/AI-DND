import { StepDice } from '@/components/step-dice';
import { portraitStyle, SPECIES_PORTRAIT_CELLS, speciesTraitDetails } from '@/components/character-creation-shared';
import type { NormalizedCharacterCreationCatalog } from '@/lib/character-catalog-normalizer';

type SpeciesStepProps = {
  species: string;
  catalog: NormalizedCharacterCreationCatalog;
  setGiantAncestry: (value: string) => void;
  setSpecies: (value: string) => void;
  speciesData: any;
  giantAncestry: string;
  speciesPortraitSheet: string;
  halfElfPortrait: string;
};

export function SpeciesStep({ species, catalog, setGiantAncestry, setSpecies, speciesData, giantAncestry, speciesPortraitSheet, halfElfPortrait }: SpeciesStepProps) {
  return (
    <section className="cc-step-panel">
          <div className="cc-step-header">
            <div className="cc-label">Adım 1</div>
            <h2 className="cc-step-title-text">Türünü Seç</h2>
            <StepDice label="Tür için zar at" testId="button-dice-species" current={species}
              keys={Object.keys((catalog?.races ?? {}) as Record<string, unknown>)}
              onPick={key => { if (key !== species) setGiantAncestry(''); setSpecies(key); }} />
            <p className="cc-literary">Türün hareket hızını, duyularını ve doğuştan gelen ırksal özelliklerini belirler.</p>
          </div>

          <div className="cc-cards-grid cc-portrait-grid">
            {catalog?.races && Object.entries(catalog.races as Record<string, any>).map(([raceKey, rc]) => {
              const isSelected = species === raceKey;
              const isHalfElf = raceKey.trim().toLowerCase() === 'half-elf';
              return (
                <div
                  key={raceKey}
                  className={`cc-choice-card ${isSelected ? 'selected' : ''}`}
                  role="button"
                  tabIndex={0}
                  aria-pressed={isSelected}
                  onClick={() => {
                    if (raceKey !== species) setGiantAncestry('');
                    setSpecies(raceKey);
                  }}
                >
                  <span
                    className={`cc-portrait ${!isHalfElf && SPECIES_PORTRAIT_CELLS[raceKey.toLowerCase()] === undefined ? 'cc-portrait-neutral' : ''}`}
                    style={isHalfElf
                      ? { backgroundImage: `url("${halfElfPortrait}")`, backgroundSize: 'cover', backgroundPosition: 'center' }
                      : portraitStyle(speciesPortraitSheet, SPECIES_PORTRAIT_CELLS[raceKey.toLowerCase()])}
                    aria-hidden="true"
                  />
                  <div className="cc-card-top">
                    <span className="cc-card-title">{rc.name_tr ?? raceKey}</span>
                    <span className="cc-badge">{rc.speed}</span>
                  </div>
                  <p className="cc-card-desc">{rc.desc}</p>
                  <div className="cc-card-features">
                    {typeof rc.source_label_tr === 'string' && (
                      <span
                        className="cc-feature-tag"
                        title={typeof rc.source_citation === 'string' ? rc.source_citation : undefined}
                      >
                        {rc.source_label_tr}
                      </span>
                    )}
                    <span className="cc-feature-tag">Karanlık Görüşü: {rc.darkvision}</span>
                    {Array.isArray(rc.traits) && rc.traits.map((trait: unknown, index: number) => {
                      const details = speciesTraitDetails(trait);
                      if (!details) return null;
                      return (
                        <span
                          className="cc-feature-tag"
                          key={`${raceKey}-${details.name}-${index}`}
                          title={details.description ?? undefined}
                        >
                          {details.name}
                          {details.description && (
                            <span className="sr-only">. {details.description}</span>
                          )}
                        </span>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
          {species === 'Goliath' && (
            <section className="cc-sub-section" data-testid="section-giant-ancestry">
              <h3 className="cc-sub-title">Dev Atanı Seç</h3>
              <p className="cc-card-desc">
                Seçimin, Ustalık Bonusun kadar uzun dinlenmede yenilenen bir yeteneği belirler.
              </p>
              <div className="cc-cards-grid">
                {(speciesData?.giant_ancestry_options ?? []).map(
                  (option: { id: string; name_tr: string; desc: string }) => (
                    <button
                      type="button"
                      key={option.id}
                      className={`cc-choice-card ${giantAncestry === option.id ? 'selected' : ''}`}
                      role="radio"
                      aria-checked={giantAncestry === option.id}
                      onClick={() => setGiantAncestry(option.id)}
                      data-testid={`giant-ancestry-${option.id}`}
                    >
                      <span className="cc-card-title">{option.name_tr}</span>
                      <span className="cc-card-desc">{option.desc}</span>
                    </button>
                  ),
                )}
              </div>
            </section>
          )}
        </section>
  );
}
