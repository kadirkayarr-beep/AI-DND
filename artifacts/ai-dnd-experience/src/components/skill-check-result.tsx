import type { SkillCheckResult } from '@workspace/api-client-react';
import './skill-check-result.css';

const ABILITY_ABBREVIATIONS: Record<SkillCheckResult['ability'], string> = {
  strength: 'STR',
  dexterity: 'DEX',
  constitution: 'CON',
  intelligence: 'INT',
  wisdom: 'WIS',
  charisma: 'CHA',
};

const OUTCOME_LABELS: Record<SkillCheckResult['outcome'], string> = {
  success: 'BAŞARILI',
  failure: 'BAŞARISIZ',
};

const DIFFICULTY_LABELS: Record<SkillCheckResult['difficulty'], string> = {
  easy: 'Kolay',
  medium: 'Orta',
  hard: 'Zor',
  very_hard: 'Çok zor',
  extreme: 'Aşırı zor',
};

function signed(value: number) {
  return value > 0 ? `+${value}` : String(value);
}

export function SkillCheckResultCard({ result }: { result: SkillCheckResult }) {
  const outcomeClass = result.outcome.includes('success') ? 'success' : 'failure';
  const rollContext = result.advantage && result.disadvantage
    ? 'Avantaj ve dezavantaj birbirini götürdü.'
    : result.d20_rolls?.length
      ? `${result.advantage ? 'Avantaj' : 'Dezavantaj'} zarları: ${result.d20_rolls.join(' ve ')}.`
      : null;
  const accessibleSummary = [
    `${result.skill}: ${OUTCOME_LABELS[result.outcome]}`,
    `D20 ${result.d20}`,
    ...(rollContext ? [rollContext] : []),
    `${ABILITY_ABBREVIATIONS[result.ability]} ${signed(result.ability_modifier)}`,
    `PROF ${signed(result.proficiency_modifier)}`,
    `toplam ${result.total}`,
    `${DIFFICULTY_LABELS[result.difficulty]}, DC ${result.dc}`,
  ].join(', ');

  return (
    <section
      className={`skill-check-result skill-check-result--${outcomeClass}`}
      aria-label={accessibleSummary}
      data-testid="skill-check-result"
    >
      <div className="skill-check-result__heading">
        <span className="skill-check-result__skill">{result.skill.toLocaleUpperCase('tr-TR')}</span>
        <span className={`skill-check-result__outcome skill-check-result__outcome--${outcomeClass}`}>
          {OUTCOME_LABELS[result.outcome]}
        </span>
      </div>
      <dl className="skill-check-result__roll">
        <div>
          <dt>D20</dt>
          <dd>{result.d20}</dd>
        </div>
        <div>
          <dt>{ABILITY_ABBREVIATIONS[result.ability]}</dt>
          <dd>{signed(result.ability_modifier)}</dd>
        </div>
        <div>
          <dt>PROF</dt>
          <dd>{signed(result.proficiency_modifier)}</dd>
        </div>
        <div className="skill-check-result__total">
          <dt>TOTAL</dt>
          <dd>{result.total}</dd>
        </div>
      </dl>
      {rollContext && <p className="skill-check-result__roll-context">{rollContext}</p>}
      <p className="skill-check-result__difficulty">
        {DIFFICULTY_LABELS[result.difficulty]} · DC {result.dc}
      </p>
    </section>
  );
}