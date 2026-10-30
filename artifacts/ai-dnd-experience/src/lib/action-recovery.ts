// The way out of an unresolved action. The browser record is never the authority: the server's stored receipt or
// durable refusal is. A timeout, a 404/503, a missing receipt or a network error is an error or "unresolved",
// never a verdict; nothing here creates a new action id or resends a move.
import { closePending, type ActionKey } from './pending-action.ts';

export type ServerVerdict =
  | { kind: 'applied'; response: unknown }
  | { kind: 'not_applied'; code: string }
  | { kind: 'unresolved'; state: 'open' | 'unknown' | 'processing'; processing: boolean };

export type RecoveryApi = {
  status: (sessionId: string, actionId: string) => Promise<unknown>;
  abandon: (sessionId: string, actionId: string) => Promise<unknown>;
  unresolved: (sessionId: string) => Promise<unknown>;
};

const UNRESOLVED_STATES = ['open', 'unknown', 'processing'] as const;

/** Interprets one server answer about `actionId`. Anything that is not a clear, matching, durable answer stays unresolved. */
export function readVerdict(body: unknown, actionId: string): ServerVerdict {
  const answer = (body && typeof body === 'object' ? body : {}) as {
    action_id?: unknown; state?: unknown; response?: unknown; processing?: unknown; detail?: { code?: unknown; not_applied?: unknown } | null;
  };
  const unresolved = (state: 'open' | 'unknown' | 'processing'): ServerVerdict => ({
    kind: 'unresolved', state, processing: state === 'processing' || answer.processing === true,
  });
  if (answer.action_id !== actionId) return unresolved('unknown');
  if (answer.state === 'applied') return { kind: 'applied', response: answer.response ?? null };
  if (answer.state === 'not_applied') {
    const detail = answer.detail;
    if (detail && detail.not_applied === true && typeof detail.code === 'string' && detail.code) {
      return { kind: 'not_applied', code: detail.code };
    }
    return unresolved('unknown');
  }
  const state = UNRESOLVED_STATES.find((candidate) => candidate === answer.state);
  return unresolved(state ?? 'unknown');
}

/** Asks the server. `abandon` is the player's explicit choice; the answer still comes only from the stored record. Errors propagate. */
export async function askServer(
  api: RecoveryApi, mode: 'check' | 'abandon', sessionId: string, actionId: string,
): Promise<ServerVerdict> {
  const body = mode === 'abandon' ? await api.abandon(sessionId, actionId) : await api.status(sessionId, actionId);
  return readVerdict(body, actionId);
}

/** The open action of the campaign as the server records it (second tab, re-login, lost browser record), or null. */
export async function findUnresolvedOnServer(
  api: RecoveryApi, sessionId: string,
): Promise<{ actionId: string; state: 'open' } | null> {
  const body = await api.unresolved(sessionId) as { unresolved?: { action_id?: unknown; state?: unknown } | null } | null;
  const open = body?.unresolved;
  if (!open) return null;
  if (typeof open.action_id !== 'string' || open.state !== 'open') {
    throw new Error('The server answer about the unresolved action could not be read.');
  }
  return { actionId: open.action_id, state: 'open' };
}

export type SettleResult = 'confirmed' | 'cancelled' | 'kept';

/**
 * Applies a verdict to the local pending record. `applied` reconciles authoritative state first (a failing reconcile
 * rejects and the record stays); `not_applied` closes with the server's own evidence; everything else keeps the identity.
 */
export async function settlePending(
  key: ActionKey, verdict: ServerVerdict, reconcile: () => Promise<void>,
): Promise<SettleResult> {
  if (verdict.kind === 'applied') {
    await reconcile();
    closePending(key, 'confirmed');
    return 'confirmed';
  }
  if (verdict.kind === 'not_applied') {
    closePending(key, 'cancelled', { kind: 'server_not_applied', code: verdict.code });
    return 'cancelled';
  }
  return 'kept';
}

/** The open action a refused request ran into, when the server said `unresolved_action`; otherwise null. */
export function unresolvedActionFrom(error: unknown): { actionId: string; code: 'unresolved_action' } | null {
  const detail = (error as { data?: { detail?: { code?: unknown; unresolved_action_id?: unknown } } } | null)?.data?.detail;
  if (detail?.code === 'unresolved_action' && typeof detail.unresolved_action_id === 'string') {
    return { actionId: detail.unresolved_action_id, code: 'unresolved_action' };
  }
  return null;
}
