import { useState } from 'react';
import { RotateCcw } from 'lucide-react';

/**
 * LR00-P7 small undo control for the last completed turn, with an explicit
 * confirmation. Disabled while a turn or an undo is in flight.
 */
export function LastTurnBar({
  summary,
  canUndo,
  busy,
  onUndo,
}: {
  summary: string | null;
  canUndo: boolean;
  busy: boolean;
  onUndo: () => void;
}) {
  const [confirming, setConfirming] = useState(false);
  if (!summary && !canUndo) return null;
  return (
    <div className="last-turn-bar mt-2 flex flex-wrap items-center gap-2 text-sm" data-testid="last-turn-bar">
      {summary && <span className="text-[#a99a80]" data-testid="text-turn-outcome">Sonuç: {summary}</span>}
      {canUndo && !confirming && (
        <button
          type="button"
          className="dnd-button secondary"
          style={{ minHeight: 32, minWidth: 32, padding: '0 10px' }}
          aria-label="Son turu geri al"
          title="Son turu geri al"
          disabled={busy}
          onClick={() => setConfirming(true)}
          data-testid="button-undo-last-turn"
        >
          <RotateCcw size={14} aria-hidden="true" />
        </button>
      )}
      {canUndo && confirming && (
        <span role="group" aria-label="Geri alma onayı" className="flex items-center gap-2" data-testid="confirm-undo">
          <span>Bu tur ve sonuçları geri alınacak.</span>
          <button type="button" className="dnd-button" disabled={busy} data-testid="button-confirm-undo"
            onClick={() => { setConfirming(false); onUndo(); }}>Geri al</button>
          <button type="button" className="dnd-button secondary" data-testid="button-cancel-undo"
            onClick={() => setConfirming(false)}>Vazgeç</button>
        </span>
      )}
    </div>
  );
}
