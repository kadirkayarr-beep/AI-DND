import type { GameState } from '@workspace/api-client-react';

const SHORT_REST = 'Bir saat kısa dinleniyorum.';
const LONG_REST = '8 saat uyuyarak uzun dinlenme yapıyorum.';

/**
 * Short and long rest as buttons. They send the same words a player may type, so the engine path is unchanged
 * and the typed phrase keeps working. Hidden in combat and while the character is down or dead.
 */
export function RestControls({ state, onSend, sending }: {
  state: GameState;
  onSend: (message: string) => void;
  sending?: boolean;
}) {
  if (state.combat.active || state.character.current_hp <= 0 || state.death_state?.status === 'dead') return null;
  return (
    <div className="rest-controls" role="group" aria-label="Dinlenme" data-testid="rest-controls">
      <button type="button" className="action-suggestion" disabled={sending} data-testid="button-rest-short" onClick={() => onSend(SHORT_REST)}>Kısa dinlenme</button>
      <button type="button" className="action-suggestion" disabled={sending} data-testid="button-rest-long" onClick={() => onSend(LONG_REST)}>Uzun dinlenme</button>
    </div>
  );
}
