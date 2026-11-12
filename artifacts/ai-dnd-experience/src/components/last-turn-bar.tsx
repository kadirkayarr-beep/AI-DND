import { useState } from 'react';
import { RotateCcw } from 'lucide-react';

/**
 * The confirmation sentence: which turn is undone and how the purse comes back (Görev 26). `purseSpentCp` is the
 * purse before the turn minus after it; null when it is not known (an old turn, a retried move), so no number is said.
 * A slash command is never quoted, as on the server.
 */
export function undoConfirmText(turnLabel: string | null | undefined, purseSpentCp: number | null | undefined): string {
  let label = (turnLabel ?? '').trim().replace(/\.$/, '');
  if (label.startsWith('/')) label = '';
  if (label.length > 120) label = `${label.slice(0, 117)}...`;
  const head = label ? `“${label}” ve sonuçları geri alınacak` : 'Bu tur ve sonuçları geri alınacak';
  if (typeof purseSpentCp !== 'number') return `${head}.`;
  if (purseSpentCp > 0) return `${head}; kesene ${purseSpentCp} bakır geri döner.`;
  if (purseSpentCp < 0) return `${head}; kesenden ${-purseSpentCp} bakır geri gider.`;
  return `${head}; kesen değişmez.`;
}

/**
 * LR00-P7 small undo control for the last completed turn, with an explicit
 * confirmation. Disabled while a turn or an undo is in flight. When there is no
 * undo to offer it says why: a fight is on (`combatActive`: there is a last turn
 * and combat is running), or the one step the engine allows was just taken
 * (`justUndone`, until the next turn reply). The engine's rules stay as they are.
 */
export function LastTurnBar({
  summary,
  canUndo,
  recoveringUndo,
  busy,
  onUndo,
  combatActive,
  justUndone,
  turnLabel,
  purseSpentCp,
}: {
  summary: string | null;
  canUndo: boolean;
  recoveringUndo: boolean;
  busy: boolean;
  onUndo: () => void;
  combatActive: boolean;
  justUndone: boolean;
  turnLabel?: string | null;
  purseSpentCp?: number | null;
}) {
  const [confirming, setConfirming] = useState(false);
  if (!summary && !canUndo && !recoveringUndo && !combatActive && !justUndone) return null;
  return (
    <div className="last-turn-bar mt-2 flex flex-wrap items-center gap-2 text-sm" data-testid="last-turn-bar">
      {summary && <span className="text-(color:--unw-text-soft)" data-testid="text-turn-outcome">Sonuç: {summary}</span>}
      {recoveringUndo && (
        <button type="button" className="dnd-button secondary" disabled={busy}
          onClick={onUndo} data-testid="button-retry-undo">
          Geri almayı yeniden dene
        </button>
      )}
      {canUndo && !confirming && !recoveringUndo && (
        <button
          type="button"
          className="dnd-button secondary"
          style={{ minHeight: 32, minWidth: 32, padding: '0 10px', gap: 6 }}
          aria-label="Son turu geri al"
          title="Son turu geri al"
          disabled={busy}
          onClick={() => setConfirming(true)}
          data-testid="button-undo-last-turn"
        >
          <RotateCcw size={14} aria-hidden="true" />Geri al
        </button>
      )}
      {combatActive && (
        <span className="text-(color:--unw-text-soft)" data-testid="text-undo-combat">Savaş sürerken son tur geri alınamaz.</span>
      )}
      {justUndone && !canUndo && !combatActive && (
        <span className="text-(color:--unw-text-soft)" data-testid="text-undo-once">Yalnız son tur geri alınır; yeni bir tur oynayınca Geri al yeniden açılır.</span>
      )}
      {canUndo && confirming && (
        <span role="group" aria-label="Geri alma onayı" className="flex items-center gap-2" data-testid="confirm-undo">
          <span data-testid="text-undo-confirm">{undoConfirmText(turnLabel, purseSpentCp)}</span>
          <button type="button" className="dnd-button" disabled={busy} data-testid="button-confirm-undo"
            onClick={() => { setConfirming(false); onUndo(); }}>Geri al</button>
          <button type="button" className="dnd-button secondary" data-testid="button-cancel-undo"
            onClick={() => setConfirming(false)}>Vazgeç</button>
        </span>
      )}
    </div>
  );
}
