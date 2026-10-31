import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { getGetGameSessionStateQueryKey, usePlayGameTurn } from '@workspace/api-client-react';
import type { GameState } from '@workspace/api-client-react';
import { currentAuthEpoch } from '@workspace/api-client-react/custom-fetch';
import { currentAccountOwner } from '@/lib/account-session';
import {
  closePending,
  createIntentKey,
  readPending,
  resumePending,
  unresolvedElsewhere,
  type CancelEvidence,
} from '@/lib/pending-action';

const ROLL_THE_SAVE = 'Ölüm kurtarma zarımı atıyorum.';
const WAIT_AN_HOUR = '1 saat bekle.';
const PASS_THE_TURN = 'Bekliyorum.';
const LAST_CALL = 'Karanlığa son bir kez sesleniyorum.';
const HTTP_UNPROCESSABLE = 422;

type StoredMove = NonNullable<ReturnType<typeof readPending>>;

// The wait lives in the same owner+campaign slot as every play move, so it is durable across a reload and
// every other mutation of the campaign sees it. It is told apart by its recorded kind, never by its text.
function isWait(stored: StoredMove | null): stored is StoredMove {
  return stored !== null && stored.kind === 'death_wait';
}

function cancelEvidence(error: unknown, stored: StoredMove): CancelEvidence | undefined {
  const detail = (error as { data?: { detail?: { not_applied?: unknown; code?: unknown } }; status?: number } | null)?.data?.detail;
  if (detail?.not_applied === true && typeof detail.code === 'string') return { kind: 'server_not_applied', code: detail.code };
  const status = (error as { status?: number } | null)?.status;
  if (status === HTTP_UNPROCESSABLE && typeof stored.request.message === 'string') return { kind: 'server_rejected', status };
  return undefined;
}

/** The one thing a body on the ground can still ask for, by death state. Null when nothing is left. */
function nextMove(state: GameState): { message: string; label: string } | null {
  const death = state.death_state;
  if (death?.status === 'dead') {
    return death.last_call_open ? { message: LAST_CALL, label: 'Karanlığa son bir kez seslen' } : null;
  }
  if (state.character.current_hp !== 0 || !death) return null;
  if (death.status !== 'stable') return { message: ROLL_THE_SAVE, label: 'Ölüm kurtarma zarını at' };
  return state.combat.active
    ? { message: PASS_THE_TURN, label: 'Turun geçsin' }
    : { message: WAIT_AN_HOUR, label: 'Bir saat geçmesini bekle' };
}

function buttonLabel(resumable: boolean, running: boolean, label: string): string {
  if (running) return 'Zaman geçiyor…';
  if (resumable) return 'Bekleyişin durumunu kontrol et';
  return label;
}

/**
 * Asks for the next death move only: all rolls, recovery and returned state are server-owned.
 * With onSend the move goes through the play turn, so its story lands in the transcript.
 */
export function DeathRecoveryControls({ state, sessionId, campaignId, onSend, sending }: {
  state: GameState;
  sessionId: string;
  campaignId?: string;
  onSend?: (message: string) => void;
  sending?: boolean;
}) {
  const queryClient = useQueryClient();
  const [blocked, setBlocked] = useState(false);
  const owner = currentAccountOwner() ?? 'local';
  const scope = campaignId || sessionId;
  const turn = usePlayGameTurn();
  const move = nextMove(state);
  if (move === null) return null;
  const { message, label } = move;
  const resumable = isWait(readPending(owner, scope));
  const send = () => {
    if (onSend) {
      onSend(message);
      return;
    }
    // Owner and scope are read at click time and bound, with the sent id, to this call's callbacks.
    const sendOwner = currentAccountOwner() ?? 'local';
    const sendScope = campaignId || sessionId;
    const stored = readPending(sendOwner, sendScope);
    // A different unresolved move (or a species action) is never resumed or overtaken by this button.
    if ((stored && !isWait(stored)) || (!stored && unresolvedElsewhere(sendOwner, sendScope))) {
      setBlocked(true);
      return;
    }
    try {
      const request = stored ? stored.request : { message };
      const key = stored ? resumePending(stored.key, currentAuthEpoch()).key : createIntentKey(sendOwner, sendScope, request, 'death_wait');
      const epoch = currentAuthEpoch();
      // Only the slot entry with exactly the id this call sent may be closed by this call's answer.
      const sameMove = () => {
        const current = readPending(sendOwner, sendScope);
        return current !== null && current.key.actionId === key.actionId ? current : null;
      };
      setBlocked(false);
      turn.mutate({ sessionId, data: { ...request, action_id: key.actionId } as { message: string; action_id: string } }, {
        onSuccess: () => {
          // An answer from an old auth epoch changes nothing: the wait stays pending and a retry replays its receipt.
          if (currentAuthEpoch() !== epoch) return;
          const current = sameMove();
          if (current) closePending(current.key, 'confirmed');
          // Re-read the authoritative state instead of writing the receipt's (possibly older) copy into the cache.
          void queryClient.invalidateQueries({ queryKey: getGetGameSessionStateQueryKey(sessionId) });
        },
        // Only the server's own "never applied" answer closes the wait; anything else keeps it for a retry of the same id.
        onError: (error: unknown) => {
          if (currentAuthEpoch() !== epoch) return;
          const current = sameMove();
          const evidence = current ? cancelEvidence(error, current) : undefined;
          if (current && evidence) closePending(current.key, 'cancelled', evidence);
        },
      });
    } catch {
      setBlocked(true);
    }
  };
  return <div className="mt-3">
    <button type="button" className="dnd-button secondary" disabled={turn.isPending || sending}
      data-testid="button-death-wait" onClick={send}>
      {buttonLabel(resumable, turn.isPending, label)}
    </button>
    {blocked && <p role="alert" data-testid="death-wait-blocked">Önceki hamle henüz doğrulanamadı. Önce onun sonucunu doğrula; bekleyiş bundan sonra gönderilir.</p>}
    {resumable && !turn.isPending && <p role="status">Bekleyişin sonucu henüz doğrulanamadı. Aynı bekleyiş aynı kimlikle yeniden denenir; ikinci kez uygulanmaz.</p>}
  </div>;
}

/** The end of a character, said plainly, with what is still possible. */
export function DeathEndNotice({ state, onNewAdventure }: { state: GameState; onNewAdventure: () => void }) {
  const death = state.death_state;
  if (death?.status !== 'dead') return null;
  return <div className="data-row mt-3" role="status" data-testid="death-end-notice">
    <strong>{state.character.name} öldü.</strong>
    <p className="data-row-desc">
      {death.terminal
        ? 'Bu kampanya burada kapandı.'
        : death.last_call_open
          ? 'Karanlığa son bir kez seslenebilirsin; duyan olur mu, kimse bilemez.'
          : 'Karanlıktan ses gelmiyor.'}
      {' '}Yeni bir karakterle yeni bir maceraya başlayabilirsin.
    </p>
    <button type="button" className="dnd-button secondary mt-3" data-testid="button-death-new-adventure" onClick={onNewAdventure}>
      Yeni karakterle başla
    </button>
  </div>;
}
