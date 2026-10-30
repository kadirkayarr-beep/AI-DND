import type { SkillCheckResult } from '@workspace/api-client-react';
import { Check, ChevronDown, Dices, X } from 'lucide-react';
import { DEFAULT_CATALOG } from '@/lib/character-catalog-defaults';
import './skill-check-result.css';

const ABILITY_ABBREVIATIONS: Partial<Record<SkillCheckResult['ability'], string>> = {
  strength: 'KUV',
  dexterity: 'ÇEV',
  constitution: 'DAY',
  intelligence: 'ZEK',
  wisdom: 'BİL',
  charisma: 'KAR',
};

const DIFFICULTY_LABELS: Partial<Record<SkillCheckResult['difficulty'], string>> = {
  easy: 'Kolay',
  medium: 'Orta',
  hard: 'Zor',
  very_hard: 'Çok zor',
  extreme: 'Aşırı zor',
};

function availableNumber(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

function signed(value: number) {
  return value > 0 ? `+${value}` : String(value);
}

export function SkillCheckResultCard({ result }: { result: SkillCheckResult }) {
  const skillCatalogEntry = DEFAULT_CATALOG.skills[result.skill] as { name_tr?: string } | undefined;
  const skillLabel = skillCatalogEntry?.name_tr ?? result.skill;
  const outcome = result.outcome === 'success'
    ? { key: 'success', label: 'Başarılı' }
    : result.outcome === 'failure'
      ? { key: 'failure', label: 'Başarısız' }
      : null;
  const d20 = availableNumber(result.d20);
  const total = availableNumber(result.total);
  const abilityModifier = availableNumber(result.ability_modifier);
  const proficiencyModifier = availableNumber(result.proficiency_modifier);
  const totalModifier = availableNumber(result.total_modifier);
  const abilityLabel = ABILITY_ABBREVIATIONS[result.ability];
  const primalKnowledge = result.check_feature === 'primal_knowledge' && result.ability === 'strength'
    && result.original_ability && ABILITY_ABBREVIATIONS[result.original_ability];
  const featureAbilityLabel = primalKnowledge ? 'Kuvvet (Primal Knowledge)' : null;
  const difficultyLabel = DIFFICULTY_LABELS[result.difficulty];
  const rolls = Array.isArray(result.d20_rolls)
    ? result.d20_rolls.map(availableNumber).filter((roll): roll is number => roll !== undefined)
    : [];
  const rollModes = [
    result.advantage === true ? 'Avantaj' : null,
    result.disadvantage === true ? 'Dezavantaj' : null,
  ].filter((mode): mode is string => mode !== null);
  const accessibleSummary = [
    skillLabel,
    ...(featureAbilityLabel ? [featureAbilityLabel, `Asıl yetenek ${primalKnowledge}`] : []),
    outcome?.label ?? 'Sonuç bilgisi yok',
    ...(d20 === undefined ? [] : [`D20 ${d20}`]),
    ...(total === undefined ? [] : [`Toplam ${total}`]),
    ...(rollModes.length ? [rollModes.join(' ve ')] : []),
    'Ayrıntı için etkinleştir',
  ].join(', ');

  return (
    <details
      className={`skill-check-result${outcome ? ` skill-check-result--${outcome.key}` : ' skill-check-result--unknown'}`}
      aria-label={`${skillLabel} zar kontrolü`}
      data-testid="skill-check-result"
    >
      <summary className="skill-check-result__summary" aria-label={accessibleSummary}>
        <span className="skill-check-result__dice-icon" aria-hidden="true"><Dices size={18} strokeWidth={1.7} /></span>
        <span className="skill-check-result__identity">
          <span className="skill-check-result__skill">{skillLabel}</span>
          <span className={`skill-check-result__outcome${outcome ? ` skill-check-result__outcome--${outcome.key}` : ''}`}>
            {outcome?.key === 'success' ? <Check size={13} aria-hidden="true" /> : outcome?.key === 'failure' ? <X size={13} aria-hidden="true" /> : null}
            {outcome?.label ?? 'Sonuç bilgisi yok'}
          </span>
        </span>
        <span className="skill-check-result__quick-result">
          {d20 !== undefined && <span>D20 <strong>{d20}</strong></span>}
          {total !== undefined && <span>Toplam <strong>{total}</strong></span>}
        </span>
        <ChevronDown className="skill-check-result__chevron" size={16} aria-hidden="true" />
      </summary>
      <div className="skill-check-result__details">
        {rolls.length > 0 && <div className="skill-check-result__dice-rolls" aria-label={`Atılan zarlar: ${rolls.join(', ')}`}>
          <span className="skill-check-result__detail-label">Atılan zarlar</span>
          <span className="skill-check-result__dice-list">
            {rolls.map((roll, index) => <span className="skill-check-result__die" key={`${roll}-${index}`}>{roll}</span>)}
          </span>
        </div>}
        {rollModes.length > 0 && <p className="skill-check-result__roll-context">{rollModes.join(' · ')}</p>}
        {featureAbilityLabel && <p className="skill-check-result__roll-context" data-testid="skill-check-primal-knowledge">{featureAbilityLabel} · Asıl yetenek: {primalKnowledge}</p>}
        {result.expertise === true && <p className="skill-check-result__roll-context">Uzmanlık</p>}
        <dl className="skill-check-result__roll">
          {d20 !== undefined && <div><dt>Kullanılan D20</dt><dd>{d20}</dd></div>}
          {abilityModifier !== undefined && abilityLabel && <div><dt>Yetenek · {featureAbilityLabel ?? abilityLabel}</dt><dd>{signed(abilityModifier)}</dd></div>}
          {proficiencyModifier !== undefined && <div><dt>Yeterlilik bonusu</dt><dd>{signed(proficiencyModifier)}</dd></div>}
          {totalModifier !== undefined && <div><dt>Toplam bonus</dt><dd>{signed(totalModifier)}</dd></div>}
          {total !== undefined && <div className="skill-check-result__total"><dt>Toplam</dt><dd>{total}</dd></div>}
          {difficultyLabel && <div><dt>Zorluk</dt><dd>{difficultyLabel}</dd></div>}
        </dl>
      </div>
    </details>
  );
}