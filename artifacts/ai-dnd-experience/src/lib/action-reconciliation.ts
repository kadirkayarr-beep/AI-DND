import { useEffect, useRef } from 'react';
import type { QueryClient, QueryKey } from '@tanstack/react-query';
import { currentAuthEpoch } from '@workspace/api-client-react/custom-fetch';

export const RETRY_MESSAGE = 'Güncel durum doğrulanamadı. Aynı işlemi yeniden dene; kayıtlı işlem kimliği korunuyor.';
export class ReconciliationError extends Error { constructor() { super(RETRY_MESSAGE); } }

export function createActionLifetime() {
  let live = true;
  const controllers = new Set<AbortController>();
  return {
    begin() {
      if (!live) return null;
      const epoch = currentAuthEpoch();
      const controller = new AbortController();
      controllers.add(controller);
      return {
        signal: controller.signal,
        isCurrent: () => live && !controller.signal.aborted && currentAuthEpoch() === epoch,
        close: () => { controllers.delete(controller); },
      };
    },
    dispose() { live = false; for (const controller of controllers) controller.abort(); controllers.clear(); },
  };
}
export type ActionOperation = NonNullable<ReturnType<ReturnType<typeof createActionLifetime>['begin']>>;
export function useActionLifetime(scope: string) {
  const ref = useRef<ReturnType<typeof createActionLifetime> | null>(null);
  const renderedScope = useRef(scope);
  renderedScope.current = scope;
  useEffect(() => {
    const lifetime = createActionLifetime();
    ref.current = lifetime;
    return () => { lifetime.dispose(); if (ref.current === lifetime) ref.current = null; };
  }, [scope]);
  return { begin: () => {
    const operation = ref.current?.begin();
    if (!operation) return null;
    return { ...operation, isCurrent: () => renderedScope.current === scope && operation.isCurrent() };
  } };
}

// One total deadline, at most three reads; no automatic mutation retry.
export async function reconcileState<T>(client: QueryClient, key: QueryKey, operation: ActionOperation,
  read: (signal: AbortSignal) => Promise<T>, timeoutMs = 8000): Promise<T> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  operation.signal.addEventListener('abort', abort, { once: true });
  let rejectAbort: () => void = () => {};
  const cancelled = new Promise<never>((_, reject) => { rejectAbort = () => reject(new ReconciliationError()); });
  controller.signal.addEventListener('abort', rejectAbort, { once: true });
  const timer = setTimeout(abort, timeoutMs);
  try {
    if (!operation.isCurrent()) throw new ReconciliationError();
    await Promise.race([client.cancelQueries({ queryKey: key, exact: true }), cancelled]);
    for (let attempt = 0; attempt < 3; attempt++) {
      if (!operation.isCurrent()) throw new ReconciliationError();
      const updates = client.getQueryState(key)?.dataUpdateCount;
      const value = await Promise.race([read(controller.signal), cancelled]);
      if (!operation.isCurrent()) throw new ReconciliationError();
      if (client.getQueryState(key)?.dataUpdateCount === updates) return value;
    }
    throw new ReconciliationError();
  } catch { throw new ReconciliationError(); }
  finally {
    clearTimeout(timer);
    operation.signal.removeEventListener('abort', abort);
    controller.signal.removeEventListener('abort', rejectAbort);
    controller.abort();
  }
}

export function actionFingerprint(value: string) {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash = Math.imul(hash ^ value.charCodeAt(index), 16777619);
  }
  return (hash >>> 0).toString(36);
}

type CombatRequestContext = { combat_id?: string; combat_round?: number; combat_turn_index?: number };

export function stableTurnActionId(scope: string, signature: string, context: CombatRequestContext = {}) {
  const storageKey = `ai-dnd-pending-turns:${scope}`;
  const fingerprint = actionFingerprint(signature);
  try {
    const pending = JSON.parse(window.sessionStorage.getItem(storageKey) ?? '{}') as Record<string, unknown>;
    const existing = pending[fingerprint];
    if (typeof existing === 'string') return existing;
    if (!window.crypto?.randomUUID) throw new Error('Secure UUID generation is unavailable.');
    const actionId = window.crypto.randomUUID();
    pending[fingerprint] = actionId;
    window.sessionStorage.setItem(`ai-dnd-turn-context:${scope}:${actionId}`, JSON.stringify(context));
    window.sessionStorage.setItem(storageKey, JSON.stringify(pending));
    return actionId;
  } catch {
    if (!window.crypto?.randomUUID) throw new Error('Secure UUID generation is unavailable.');
    return window.crypto.randomUUID();
  }
}

export function storedTurnContext(scope: string, actionId: string): CombatRequestContext {
  try {
    return JSON.parse(window.sessionStorage.getItem(`ai-dnd-turn-context:${scope}:${actionId}`) ?? '{}');
  } catch {
    return {};
  }
}

export function clearPendingTurnAction(scope: string, actionId: string) {
  const storageKey = `ai-dnd-pending-turns:${scope}`;
  try {
    window.sessionStorage.removeItem(`ai-dnd-turn-context:${scope}:${actionId}`);
    const pending = JSON.parse(window.sessionStorage.getItem(storageKey) ?? '{}') as Record<string, unknown>;
    for (const [fingerprint, pendingId] of Object.entries(pending)) {
      if (pendingId === actionId) delete pending[fingerprint];
    }
    if (Object.keys(pending).length) {
      window.sessionStorage.setItem(storageKey, JSON.stringify(pending));
    } else {
      window.sessionStorage.removeItem(storageKey);
    }
  } catch {
    // The server receipt remains authoritative if browser storage is unavailable.
  }
}
