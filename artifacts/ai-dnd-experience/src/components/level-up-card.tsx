import type { LevelUpResult } from '@workspace/api-client-react';

/**
 * The turn raised the character's level. The server already applied it; this card says so and leads to the
 * existing choice screen (LevelUpControls, `level-up-choices`) when there is something to choose.
 */
export function LevelUpCard({ levelUp, onClose }: { levelUp: LevelUpResult | null; onClose: () => void }) {
  if (!levelUp || levelUp.new_level <= levelUp.previous_level) return null;
  const goToChoices = () => {
    const target = document.querySelector('[data-testid="level-up-choices"], [data-testid="level-up-controls"]');
    if (target instanceof HTMLElement) { target.scrollIntoView({ block: 'center' }); target.focus?.(); }
  };
  return (
    <div className="level-up-card" role="status" data-testid="level-up-card">
      <strong>Seviye {levelUp.new_level}'e ulaştın.</strong>
      <span>{levelUp.hit_points_gained > 0 ? `+${levelUp.hit_points_gained} azami can. ` : ''}Seçimlerin varsa aşağıda seni bekliyor.</span>
      <div className="level-up-card-actions">
        <button type="button" className="action-suggestion" data-testid="button-level-up-goto-choices" onClick={goToChoices}>Seçimlere git</button>
        <button type="button" className="action-suggestion" data-testid="button-level-up-card-close" onClick={onClose}>Kapat</button>
      </div>
    </div>
  );
}
