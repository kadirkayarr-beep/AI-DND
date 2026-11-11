import type { EffectsLevel } from './appearance-settings.ts';

/** Most effects that may be alive at once; starting another finishes the oldest first. */
export const MAX_ACTIVE_EFFECTS = 14;
/** Extra time past durationMs before the failsafe timer disposes an effect on its own. */
export const FAILSAFE_MARGIN_MS = 400;

export type EffectSpec = {
  id?: string;
  durationMs: number;
  dispose: () => void;
};

export type EffectHandle = {
  readonly id: string;
  readonly finished: boolean;
};

export type EffectRegistryOptions = {
  now?: () => number;
  setTimer?: (fn: () => void, ms: number) => unknown;
  clearTimer?: (token: unknown) => void;
  /** Called after cancelOnHidden has disposed everything (for glue code and tests). */
  onVisibilityHidden?: () => void;
};

export type EffectRegistry = {
  start(effect: EffectSpec): EffectHandle;
  finish(handle: EffectHandle): void;
  flushAll(): void;
  leftovers(): number;
  errors(): number;
  cancelOnHidden(): void;
};

type MutableHandle = { id: string; finished: boolean };

type Entry = {
  id: string;
  spec: EffectSpec;
  timer: unknown;
  handle: MutableHandle;
};

/** Effects level as a decision: callers never branch on the level strings. */
export function shouldPlayEffects(level: EffectsLevel): boolean {
  return level !== 'off';
}

/** 0 for off, a gentle tone for low, 1 for full. */
export function effectIntensity(level: EffectsLevel): number {
  if (level === 'full') return 1;
  if (level === 'low') return 0.4;
  return 0;
}

export function createEffectRegistry(options: EffectRegistryOptions = {}): EffectRegistry {
  const setTimer = options.setTimer ?? ((fn: () => void, ms: number) => setTimeout(fn, ms));
  const clearTimer =
    options.clearTimer ?? ((token: unknown) => clearTimeout(token as ReturnType<typeof setTimeout>));
  // Map keeps insertion order, so the first value is always the oldest effect.
  const active = new Map<string, Entry>();
  let errorCount = 0;
  let autoId = 0;

  function settle(entry: Entry): void {
    if (entry.handle.finished) return;
    entry.handle.finished = true;
    if (active.get(entry.id) === entry) active.delete(entry.id);
    try {
      clearTimer(entry.timer);
    } catch {
      errorCount += 1;
    }
    try {
      entry.spec.dispose();
    } catch {
      errorCount += 1;
    }
  }

  function start(spec: EffectSpec): EffectHandle {
    const id = spec.id ?? `effect-${++autoId}`;
    const previous = active.get(id);
    if (previous) settle(previous);
    while (active.size >= MAX_ACTIVE_EFFECTS) {
      const oldest = active.values().next().value as Entry;
      settle(oldest);
    }
    const handle: MutableHandle = { id, finished: false };
    const entry: Entry = { id, spec, timer: undefined, handle };
    active.set(id, entry);
    const duration = Number.isFinite(spec.durationMs) && spec.durationMs > 0 ? spec.durationMs : 0;
    try {
      entry.timer = setTimer(() => settle(entry), duration + FAILSAFE_MARGIN_MS);
    } catch {
      // Without a failsafe timer the effect must still end: dispose now.
      errorCount += 1;
      settle(entry);
    }
    return handle;
  }

  function finish(handle: EffectHandle): void {
    const entry = active.get(handle.id);
    if (entry && entry.handle === handle) settle(entry);
  }

  function flushAll(): void {
    for (const entry of [...active.values()]) settle(entry);
  }

  return {
    start,
    finish,
    flushAll,
    leftovers: () => active.size,
    errors: () => errorCount,
    cancelOnHidden() {
      flushAll();
      try {
        options.onVisibilityHidden?.();
      } catch {
        errorCount += 1;
      }
    },
  };
}

type GuardWindow = {
  document?: {
    hidden?: boolean;
    addEventListener(type: string, fn: () => void): void;
    removeEventListener(type: string, fn: () => void): void;
  };
  addEventListener(type: string, fn: () => void): void;
  removeEventListener(type: string, fn: () => void): void;
  [key: string]: unknown;
};

function isDevBuild(): boolean {
  return Boolean((import.meta as unknown as { env?: { DEV?: boolean } }).env?.DEV);
}

/**
 * Wires visibilitychange/pagehide to cancelOnHidden and, in dev only, exposes
 * window.__effectLeftovers / __flushEffects. Safe outside a browser; returns a detach function.
 */
export function attachBrowserGuards(
  registry: EffectRegistry,
  win: GuardWindow | null | undefined = typeof window === 'undefined'
    ? undefined
    : (window as unknown as GuardWindow),
  dev: boolean = isDevBuild(),
): () => void {
  if (!win || typeof win.addEventListener !== 'function') return () => {};
  const doc = win.document;
  const onVisibility = () => {
    if (doc?.hidden) registry.cancelOnHidden();
  };
  const onPageHide = () => registry.cancelOnHidden();
  doc?.addEventListener('visibilitychange', onVisibility);
  win.addEventListener('pagehide', onPageHide);
  if (dev) {
    win.__effectLeftovers = () => registry.leftovers();
    win.__flushEffects = () => registry.flushAll();
  }
  return () => {
    doc?.removeEventListener('visibilitychange', onVisibility);
    win.removeEventListener('pagehide', onPageHide);
    if (dev) {
      delete win.__effectLeftovers;
      delete win.__flushEffects;
    }
  };
}
