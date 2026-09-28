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
  critical_success: 'KRİTİK BAŞARI',
  success: 'BAŞARILI',
  failure: 'BAŞARISIZ',
  critical_failure: 'KRİTİK BAŞARISIZLIK',
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
  const accessibleSummary = [
    `${result.skill}: ${OUTCOME_LABELS[result.outcome]}`,
    `D20 ${result.d20}`,
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
      <p className="skill-check-result__difficulty">
        {DIFFICULTY_LABELS[result.difficulty]} · DC {result.dc}
      </p>
    </section>
  );
}