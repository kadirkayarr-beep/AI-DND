import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  getGetGameSessionStateQueryKey,
  useResolveSpeciesTraitAction,
} from '@workspace/api-client-react';
import type {
  GameState,
  SpeciesTraitActionInput,
} from '@workspace/api-client-react';

const ANCESTRIES = [
  { id: 'cloud', label: 'Bulut Devi' },
  { id: 'fire', label: 'Ateş Devi' },
  { id: 'frost', label: 'Ayaz Devi' },
  { id: 'hill', label: 'Tepe Devi' },
  { id: 'stone', label: 'Taş Devi' },
  { id: 'storm', label: 'Fırtına Devi' },
] as const;

const REVELATION_FORMS = [
  { id: 'heavenly_wings', label: 'Göksel Kanatlar' },
  { id: 'inner_radiance', label: 'İçsel Işıltı' },
  { id: 'necrotic_shroud', label: 'Nekrotik Örtü' },
] as const;

const TRAIT_LABELS: Record<string, string> = {
  healing_hands: 'Şifa Veren Eller',
  celestial_revelation: 'Göksel Tecelli',
  large_form: 'Büyük Biçim',
  adrenaline_rush: 'Adrenalin Patlaması',
  cloud_jaunt: 'Bulut Devi Işınlanması',
  fire_giant_ancestry: 'Ateş Devi kökeni',
  frost_giant_ancestry: 'Ayaz Devi kökeni',
  hill_giant_ancestry: 'Tepe Devi kökeni',
  stone_giant_ancestry: 'Taş Devi kökeni',
  storm_giant_ancestry: 'Fırtına Devi kökeni',
  relentless_endurance: 'Amansız Dayanıklılık',
  celestial_resistance: 'Göksel Direnç',
  inner_radiance: 'İçsel Işıltı',
};

const DAMAGE_LABELS: Record<string, string> = {
  cold: 'soğuk',
  fire: 'ateş',
  necrotic: 'nekrotik',
  radiant: 'ışık',
  thunder: 'gök gürültüsü',
};

export function speciesEffectText(effect: Record<string, unknown>): string {
  const trait = typeof effect.trait === 'string'
    ? TRAIT_LABELS[effect.trait] ?? effect.trait
    : 'Tür etkisi';
  const details: string[] = [];
  if (typeof effect.damage === 'number') {
    const damageType = typeof effect.damage_type === 'string'
      ? DAMAGE_LABELS[effect.damage_type] ?? effect.damage_type
      : '';
    details.push(`${effect.damage} ${damageType} hasarı`);
  }
  if (typeof effect.damage_reduced === 'number') {
    details.push(`${effect.damage_reduced} hasar azaltıldı`);
  }
  if (typeof effect.healing === 'number') {
    details.push(`${effect.healing} can yenilendi`);
  }
  if (typeof effect.push_ft === 'number') {
    details.push(`${effect.push_ft} fit itme`);
  }
  if (effect.knocked_prone === true) details.push('hedef yere düştü');
  if (effect.frightened === true) details.push('hedef korktu');
  if (effect.expired === true) details.push('etkisi sona erdi');
  if (effect.current_hp === 1) details.push('1 can puanında ayakta kaldı');
  return details.length ? `${trait}: ${details.join(' · ')}` : trait;
}

export function SpeciesTraitControls({
  state,
  sessionId,
}: {
  state: GameState;
  sessionId: string;
}) {
  const queryClient = useQueryClient();
  const [selectedForm, setSelectedForm] =
    useState<SpeciesTraitActionInput['form']>('heavenly_wings');
  const [selectedAncestry, setSelectedAncestry] =
    useState<SpeciesTraitActionInput['ancestry']>('cloud');
  const action = useResolveSpeciesTraitAction({
    mutation: {
      onSuccess: (result) => {
        queryClient.setQueryData(
          getGetGameSessionStateQueryKey(sessionId),
          result.state,
        );
      },
    },
  });

  const character = state.character;
  const traits = character.species_trait_state;
  const species = character.species ?? character.race;
  const inCombat = state.combat.active;
  const isPlayerTurn = !inCombat || (
    state.combat.current_actor_id === 'player'
    && state.combat.participant_records.find((item) => item.id === 'player')
      ?.primary_action_available === true
  );
  const notBusy = !action.isPending;
  const send = (data: SpeciesTraitActionInput) => {
    action.reset();
    action.mutate({ sessionId, data: { ...data, action_id: crypto.randomUUID() } });
  };
  const ancestryLabel = ANCESTRIES.find(
    (ancestry) => ancestry.id === character.giant_ancestry,
  )?.label;
  const currentAncestryHasAttackEffect = [
    'fire',
    'frost',
    'hill',
    'stone',
    'storm',
  ].includes(character.giant_ancestry ?? '');

  return (
    <section className="species-traits" aria-labelledby="species-traits-heading" data-testid="panel-species-traits">
      <div className="species-traits-heading">
        <div>
          <span className="combat-overline">KARAKTERİNİN KÖKENİ</span>
          <h3 id="species-traits-heading">Tür yetenekleri</h3>
        </div>
        <span className="species-traits-species">{species}</span>
      </div>

      {species === 'Aasimar' && (
        <div className="species-trait-group">
          <div className="species-trait-resource">
            Şifa Veren Eller · {traits?.healing_hands_uses_remaining ?? 0} kullanım
          </div>
          <button
            type="button"
            className="species-trait-button"
            data-testid="species-action-healing-hands"
            disabled={!notBusy || !isPlayerTurn || (traits?.healing_hands_uses_remaining ?? 0) <= 0 || character.current_hp >= character.max_hp}
            onClick={() => send({ action: 'healing_hands' })}
          >
            Şifa Veren Eller kullan
          </button>
          <div className="species-trait-control-row">
            <label className="species-trait-select-label">
              <span>Göksel Tecelli biçimi</span>
              <select
                aria-label="Göksel Tecelli biçimi"
                value={selectedForm ?? 'heavenly_wings'}
                onChange={(event) => setSelectedForm(event.target.value as SpeciesTraitActionInput['form'])}
              >
                {REVELATION_FORMS.map((form) => (
                  <option value={form.id} key={form.id}>{form.label}</option>
                ))}
              </select>
            </label>
            <button
              type="button"
              className="species-trait-button"
              data-testid="species-action-celestial-revelation"
              disabled={!notBusy || !isPlayerTurn || character.level < 3 || (traits?.celestial_revelation_uses_remaining ?? 0) <= 0 || Boolean(traits?.active_celestial_form)}
              onClick={() => send({ action: 'celestial_revelation', form: selectedForm ?? 'heavenly_wings' })}
            >
              Tecelliyi etkinleştir
            </button>
          </div>
          <div className="species-trait-resource">
            Göksel Tecelli · {traits?.celestial_revelation_uses_remaining ?? 0} kullanım
            {traits?.active_celestial_form && ` · ${traits.celestial_revelation_turns_remaining} tur etkin`}
          </div>
        </div>
      )}

      {species === 'Goliath' && (
        <div className="species-trait-group">
          {character.giant_ancestry ? (
            <>
              <div className="species-trait-resource">
                Dev Atası: {ancestryLabel ?? character.giant_ancestry} · {traits?.giant_ancestry_uses_remaining ?? 0} kullanım
              </div>
              {character.giant_ancestry === 'cloud' ? (
                <button
                  type="button"
                  className="species-trait-button"
                  data-testid="species-action-cloud-jaunt"
                  disabled={!notBusy || !isPlayerTurn || (traits?.giant_ancestry_uses_remaining ?? 0) <= 0}
                  onClick={() => send({ action: 'cloud_jaunt' })}
                >
                  Bulut Devi Işınlanması · 30 fit
                </button>
              ) : currentAncestryHasAttackEffect && (
                <button
                  type="button"
                  className="species-trait-button"
                  data-testid="species-action-arm-giant-ancestry"
                  disabled={!notBusy || (traits?.giant_ancestry_uses_remaining ?? 0) <= 0}
                  onClick={() => send({
                    action: 'arm_giant_ancestry',
                    armed: !traits?.giant_ancestry_armed,
                  })}
                >
                  {traits?.giant_ancestry_armed ? 'Dev Atası etkisini hazır beklemeden çıkar' : 'Dev Atası etkisini hazırla'}
                </button>
              )}
            </>
          ) : (
            <div className="species-trait-control-row">
              <label className="species-trait-select-label">
                <span>Dev Atası seç</span>
                <select
                  aria-label="Dev Atası seç"
                  value={selectedAncestry ?? 'cloud'}
                  onChange={(event) => setSelectedAncestry(event.target.value as SpeciesTraitActionInput['ancestry'])}
                >
                  {ANCESTRIES.map((ancestry) => (
                    <option value={ancestry.id} key={ancestry.id}>{ancestry.label}</option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                className="species-trait-button"
                data-testid="species-action-choose-giant-ancestry"
                disabled={!notBusy || inCombat}
                onClick={() => send({ action: 'choose_giant_ancestry', ancestry: selectedAncestry ?? 'cloud' })}
              >
                Seçimi kaydet
              </button>
            </div>
          )}
          <div className="species-trait-control-row">
            <button
              type="button"
              className="species-trait-button"
              data-testid="species-action-large-form"
              disabled={!notBusy || !isPlayerTurn || character.level < 5 || (traits?.large_form_uses_remaining ?? 0) <= 0}
              onClick={() => send({ action: 'large_form' })}
            >
              Büyük Biçim · {traits?.large_form_uses_remaining ?? 0} kullanım
            </button>
            {traits?.large_form_turns_remaining ? (
              <span className="species-trait-resource">{traits.large_form_turns_remaining} tur etkin</span>
            ) : null}
          </div>
        </div>
      )}

      {species === 'Orc' && (
        <div className="species-trait-group">
          <div className="species-trait-resource">
            Adrenalin Patlaması · {traits?.adrenaline_rush_uses_remaining ?? 0} kullanım
            {traits?.temporary_hit_points ? ` · ${traits.temporary_hit_points} geçici can` : ''}
          </div>
          <button
            type="button"
            className="species-trait-button"
            data-testid="species-action-adrenaline-rush"
            disabled={!notBusy || !isPlayerTurn || (traits?.adrenaline_rush_uses_remaining ?? 0) <= 0}
            onClick={() => send({ action: 'adrenaline_rush' })}
          >
            Adrenalin Patlaması kullan
          </button>
        </div>
      )}

      {(species === 'Orc' || species === 'Half-Orc') && (
        <div className="species-trait-resource">
          Amansız Dayanıklılık · {traits?.relentless_endurance_available ? 'hazır' : 'uzun dinlenmeye kadar kullanıldı'}
        </div>
      )}

      <div className="species-trait-rests">
        <button
          type="button"
          className="species-trait-button species-trait-button-secondary"
          data-testid="species-action-short-rest"
          disabled={!notBusy || inCombat}
          onClick={() => send({ action: 'short_rest' })}
        >
          Kısa dinlen · 1 saat
        </button>
        <button
          type="button"
          className="species-trait-button species-trait-button-secondary"
          data-testid="species-action-long-rest"
          disabled={!notBusy || inCombat}
          onClick={() => send({ action: 'long_rest' })}
        >
          Uzun dinlen · 8 saat
        </button>
      </div>

      {action.isPending && <p className="species-trait-feedback" role="status">Sunucu yeteneği çözüyor…</p>}
      {action.isError && (
        <p className="species-trait-feedback species-trait-feedback-error" role="alert">
          {action.error instanceof Error ? action.error.message : 'Tür yeteneği kullanılamadı.'}
        </p>
      )}
      {action.data && (
        <div className="species-trait-feedback" data-testid="species-action-result" aria-live="polite">
          <strong>{action.data.result.message}</strong>
          {Object.keys(action.data.result.effects).filter((key) => key !== 'time_result').length > 0 && (
            <details>
              <summary>Sunucunun çözdüğü etki</summary>
              <pre>{JSON.stringify(Object.fromEntries(Object.entries(action.data.result.effects).filter(([key]) => key !== 'time_result')), null, 2)}</pre>
            </details>
          )}
        </div>
      )}
    </section>
  );
}