import { StepDice } from '@/components/step-dice';
import { ChevronDown } from 'lucide-react';
import { ABILITY_NAMES_TR, namedCatalogLabel, type AbilityKey } from '@/components/character-creation-shared';
import type { NormalizedCharacterCreationCatalog, NormalizedOriginFeatOption } from '@/lib/character-catalog-normalizer';

type BackgroundStepProps = {
  background: string;
  catalog: NormalizedCharacterCreationCatalog;
  setBackground: (value: string) => void;
  speciesData: any;
  originFeatOptions: NormalizedOriginFeatOption[];
  speciesBonusFeat: string;
  setSpeciesBonusFeat: (value: string) => void;
  selectedSpeciesBonusFeat: NormalizedOriginFeatOption | undefined;
  onRetryOptions: () => void;
};

export function BackgroundStep({ background, catalog, setBackground, speciesData, originFeatOptions, speciesBonusFeat, setSpeciesBonusFeat, selectedSpeciesBonusFeat, onRetryOptions }: BackgroundStepProps) {
  return (
    <section className="cc-step-panel">
          <div className="cc-step-header">
            <div className="cc-label">Adım 3</div>
            <h2 className="cc-step-title-text">Geçmişini Seç</h2>
            <StepDice label="Geçmiş için zar at" testId="button-dice-background" current={background}
              keys={Object.keys((catalog?.backgrounds ?? {}) as Record<string, unknown>)} onPick={setBackground} />
            <p className="cc-literary">Geçmişin; kazandığın 2 beceriyi, köken hünerini ve nitelik bonusu alabileceğin 3 alanı belirler.</p>
          </div>

          <div className="cc-cards-grid">
            {catalog?.backgrounds && Object.entries(catalog.backgrounds as Record<string, any>).map(([bgKey, bg]) => {
              const isSelected = background === bgKey;
              return (
                <div
                  key={bgKey}
                  className={`cc-choice-card ${isSelected ? 'selected' : ''}`}
                  onClick={() => setBackground(bgKey)}
                >
                  <div className="cc-card-top">
                    <span className="cc-card-title">{bg.name_tr ?? bgKey}</span>
                    <span className="cc-badge cc-badge-gold">Hüner: {bg.origin_feat ? namedCatalogLabel(catalog?.origin_feats, bg.origin_feat) : ''}</span>
                  </div>
                  <p className="cc-card-desc">{bg.desc}</p>
                  <div className="cc-card-features">
                    <span className="cc-feature-tag">Beceriler: {(bg.skills as string[] | undefined)?.map((skill: string) => namedCatalogLabel(catalog?.skills, skill)).join(', ')}</span>
                    <span className="cc-feature-tag">Araç: {bg.tool}</span>
                    <span className="cc-feature-tag">
                      Bonus Alanları: {bg.ability_bonuses_options?.map((k: AbilityKey) => ABILITY_NAMES_TR[k]?.short).join(' / ')}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
          {Number(speciesData?.origin_feat_bonus_count) > 0 && (
            <div className="cc-sub-section" data-testid="section-species-bonus-feat">
              <div className="cc-sub-header">
                <span className="cc-label">İnsan Tür Hüneri</span>
                <small>Geçmiş hünerinden farklı bir 1. seviye Başlangıç Hüneri seç.</small>
              </div>
              {originFeatOptions.length > 0 ? (
                <>
                  <label className="cc-form-group" htmlFor="select-species-bonus-feat">
                    <span className="cc-label">Ek Başlangıç Hüneri</span>
                    <div className="cc-select-wrap">
                      <select
                        id="select-species-bonus-feat"
                        data-testid="select-species-bonus-feat"
                        value={speciesBonusFeat}
                        onChange={(event) => setSpeciesBonusFeat(event.target.value)}
                        aria-describedby={
                          selectedSpeciesBonusFeat?.description
                            ? 'species-bonus-feat-description'
                            : undefined
                        }
                      >
                        <option value="">Bir hüner seç...</option>
                        {originFeatOptions.map((feat) => (
                          <option key={feat.id} value={feat.id}>{feat.label}</option>
                        ))}
                      </select>
                      <ChevronDown size={16} aria-hidden="true" />
                    </div>
                  </label>
                  {selectedSpeciesBonusFeat?.description && (
                    <p id="species-bonus-feat-description" className="cc-card-desc">
                      {selectedSpeciesBonusFeat.description}
                    </p>
                  )}
                </>
              ) : (
                <div className="cc-inline-notice" data-testid="status-origin-feats-unavailable">
                  Başlangıç hünerleri kataloğu yüklenemedi.
                  <button
                    type="button"
                    className="text-button"
                    data-testid="button-retry-origin-feats"
                    onClick={onRetryOptions}
                  >
                    Yeniden dene
                  </button>
                </div>
              )}
            </div>
          )}
        </section>
  );
}
