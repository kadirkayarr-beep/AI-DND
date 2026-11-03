// The way out of an unresolved action. The browser record is never the authority: the server's stored receipt or
// durable refusal is. A timeout, a 404/503, a missing receipt or a network error is an error or "unresolved",
// never a verdict; nothing here creates a new action id or resends a move.
import { closePending, type ActionKey } from './pending-action.ts';

export type ServerVerdict =
  | { kind: 'applied'; response: unknown }
  | { kind: 'not_applied'; code: string }
  | { kind: 'unresolved'; state: 'open' | 'unknown' | 'processing'; processing: boolean; timedOut?: boolean };

export type RecoveryCallOptions = { signal?: AbortSignal };

export type RecoveryApi = {
  status: (sessionId: string, actionId: string, options?: RecoveryCallOptions) => Promise<unknown>;
  abandon: (sessionId: string, actionId: string, options?: RecoveryCallOptions) => Promise<unknown>;
  unresolved: (sessionId: string, options?: RecoveryCallOptions) => Promise<unknown>;
};

// Bounds so a recovery never loads forever. They are defaults against an endless wait, not measured performance.
export const RECOVERY_CALL_TIMEOUT_MS = 10_000;
export const RECOVERY_AUTO_ATTEMPTS = 2;

/** One recovery call ran out of time; the server may or may not have answered. Never a verdict. */
export class RecoveryTimeoutError extends Error {
  readonly outcome = 'unknown' as const;
  constructor() { super('The recovery call timed out; the outcome is unknown.'); this.name = 'RecoveryTimeoutError'; }
}

/** The screen that asked is gone (campaign switch, unmount): the answer belongs to nobody. */
export class RecoveryAbortedError extends Error {
  constructor() { super('The recovery call was abandoned by its screen.'); this.name = 'RecoveryAbortedError'; }
}

/**
 * Runs one call with its own cap. At expiry (or when the owner's signal aborts) the call is told to stop AND the result is
 * rejected, so a transport that ignores the signal cannot keep the screen waiting; its late reply is dropped.
 */
function boundedCall<T>(work: (signal: AbortSignal) => Promise<T>, owner?: AbortSignal): Promise<T> {
  const controller = new AbortController();
  return new Promise<T>((resolve, reject) => {
    let finished = false;
    const finish = (settle: () => void) => {
      if (finished) return;
      finished = true;
      clearTimeout(timer);
      owner?.removeEventListener('abort', onOwnerAbort);
      settle();
    };
    const onOwnerAbort = () => finish(() => { controller.abort(); reject(new RecoveryAbortedError()); });
    const timer = setTimeout(() => finish(() => { controller.abort(); reject(new RecoveryTimeoutError()); }), RECOVERY_CALL_TIMEOUT_MS);
    if (owner?.aborted) { onOwnerAbort(); return; }
    owner?.addEventListener('abort', onOwnerAbort, { once: true });
    const settle = async () => {
      try {
        const value = await work(controller.signal);
        finish(() => resolve(value));
      } catch (error) {
        finish(() => reject(error));
      }
    };
    void settle();
  });
}

/** Retries only a call that timed out, up to `attempts` calls in all; errors and an aborted owner end at once. */
async function withAttempts<T>(attempts: number, work: (signal: AbortSignal) => Promise<T>, owner?: AbortSignal): Promise<T> {
  try {
    return await boundedCall(work, owner);
  } catch (error) {
    if (!(error instanceof RecoveryTimeoutError) || attempts <= 1) throw error;
    return withAttempts(attempts - 1, work, owner);
  }
}

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

/**
 * Asks the server. `abandon` is the player's explicit choice; the answer still comes only from the stored record. Errors
 * propagate. Each call is bounded: a check that times out is asked again once, then the outcome is `unknown` (never a
 * verdict, nothing closes, nothing is re-sent). An abandon is asked once. The owner's `signal` ends the wait at once.
 */
export async function askServer(
  api: RecoveryApi, mode: 'check' | 'abandon', sessionId: string, actionId: string, options?: { signal?: AbortSignal },
): Promise<ServerVerdict> {
  let body: unknown;
  try {
    body = await withAttempts(mode === 'abandon' ? 1 : RECOVERY_AUTO_ATTEMPTS, (signal) => (mode === 'abandon'
      ? api.abandon(sessionId, actionId, { signal })
      : api.status(sessionId, actionId, { signal })), options?.signal);
  } catch (error) {
    if (error instanceof RecoveryTimeoutError) return { kind: 'unresolved', state: 'unknown', processing: false, timedOut: true };
    throw error;
  }
  return readVerdict(body, actionId);
}

/** The open action of the campaign as the server records it (second tab, re-login, lost browser record), or null. */
export async function findUnresolvedOnServer(
  api: RecoveryApi, sessionId: string, options?: { signal?: AbortSignal },
): Promise<{ actionId: string; state: 'open' } | null> {
  const body = await withAttempts(RECOVERY_AUTO_ATTEMPTS, (signal) => api.unresolved(sessionId, { signal }), options?.signal) as
    { unresolved?: { action_id?: unknown; state?: unknown } | null } | null;
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

const MODEL_UNAVAILABLE_STATUS = 503;

/** The server's own short line for a move a model failed and it let go of: nothing is stuck, the player only says it again. */
export function modelRefusalLine(error: unknown): string | null {
  const failure = error as { status?: unknown; data?: { detail?: { not_applied?: unknown; message?: unknown } } } | null;
  const detail = failure?.data?.detail;
  return failure?.status === MODEL_UNAVAILABLE_STATUS && detail?.not_applied === true && typeof detail.message === 'string' ? detail.message : null;
}

/** The open action a refused request ran into, when the server said `unresolved_action`; otherwise null. */
export function unresolvedActionFrom(error: unknown): { actionId: string; code: 'unresolved_action' } | null {
  const detail = (error as { data?: { detail?: { code?: unknown; unresolved_action_id?: unknown } } } | null)?.data?.detail;
  if (detail?.code === 'unresolved_action' && typeof detail.unresolved_action_id === 'string') {
    return { actionId: detail.unresolved_action_id, code: 'unresolved_action' };
  }
  return null;
}
