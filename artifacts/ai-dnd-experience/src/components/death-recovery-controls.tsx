import { useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { getGetGameSessionStateQueryKey, usePlayGameTurn } from '@workspace/api-client-react';
import type { GameState } from '@workspace/api-client-react';

/** Requests passive time only. All rolls, recovery and returned state are server-owned. */
export function DeathRecoveryControls({ state, sessionId }: { state: GameState; sessionId: string }) {
  const queryClient = useQueryClient();
  const [pending, setPending] = useState<{ action_id: string; message: string } | null>(null);
  useEffect(() => { setPending(null); }, [sessionId]);
  const turn = usePlayGameTurn({
    mutation: {
      onSuccess: result => {
        queryClient.setQueryData(getGetGameSessionStateQueryKey(sessionId), result.state);
        setPending(null);
      },
    },
  });
  if (state.character.current_hp !== 0 || state.death_state.status === 'dead') return null;
  const message = state.combat.active ? 'Ölüm kurtarmasını bekliyorum.' : '1 saat bekle.';
  return <div className="mt-3">
    <button type="button" className="dnd-button secondary" disabled={turn.isPending}
      data-testid="button-death-wait" onClick={() => {
        const request = pending ?? { message, action_id: crypto.randomUUID() };
        setPending(request);
        turn.mutate({ sessionId, data: request });
      }}>
      {turn.isPending ? 'Zaman geçiyor…' : state.combat.active ? 'Durumun çözülmesini bekle' : 'Bir saat geçmesini bekle'}
    </button>
    {turn.isError && <p role="alert">Bekleyiş tamamlanamadı. Aynı bekleyişi yeniden deneyebilirsin.</p>}
  </div>;
}