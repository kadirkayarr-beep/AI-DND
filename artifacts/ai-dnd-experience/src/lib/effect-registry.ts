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
  key: string;
  spec: EffectSpec;
  timer: unknown;
  handle: MutableHandle;
};

/** Largest delay a platform timer accepts, minus the failsafe margin. */
const MAX_DURATION_MS = 2 ** 31 - 1 - FAILSAFE_MARGIN_MS;
/** Bounds on cascades where a dispose starts further effects. */
const MAX_CASCADE_STEPS = MAX_ACTIVE_EFFECTS * 4;
const MAX_FLUSH_PASSES = 100;

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
  // Keys are namespaced: caller ids and generated ids can never collide.
  const active = new Map<string, Entry>();
  const entryOf = new WeakMap<object, Entry>();
  let errorCount = 0;
  let autoId = 0;
  // Nesting depth of dispose calls; cap trimming only runs at depth 0 so a dispose
  // that starts effects cannot make eviction recurse without bound.
  let disposeDepth = 0;

  function settle(entry: Entry): void {
    if (entry.handle.finished) return;
    entry.handle.finished = true;
    if (active.get(entry.key) === entry) active.delete(entry.key);
    try {
      clearTimer(entry.timer);
    } catch {
      errorCount += 1;
    }
    disposeDepth += 1;
    try {
      entry.spec.dispose();
    } catch {
      errorCount += 1;
    } finally {
      disposeDepth -= 1;
    }
  }

  function trimTo(limit: number): void {
    if (disposeDepth > 0) return;
    let steps = 0;
    while (active.size > limit) {
      if (steps++ >= MAX_CASCADE_STEPS) {
        errorCount += 1;
        return;
      }
      settle(active.values().next().value as Entry);
    }
  }

  function start(spec: EffectSpec): EffectHandle {
    const generated = spec.id === undefined ? ++autoId : 0;
    const id = spec.id ?? `effect-${generated}`;
    const key = spec.id === undefined ? `auto:${generated}` : `id:${spec.id}`;
    const handle: MutableHandle = { id, finished: false };
    const entry: Entry = { key, spec, timer: undefined, handle };
    entryOf.set(handle, entry);

    // Take the slot out of the map before running any dispose, so a dispose that
    // starts an effect cannot be overwritten and orphaned by this start.
    const replaced: Entry[] = [];
    const previous = active.get(key);
    if (previous) {
      active.delete(key);
      replaced.push(previous);
    }
    trimTo(MAX_ACTIVE_EFFECTS - 1);
    const clash = active.get(key);
    if (clash) replaced.push(clash);
    active.set(key, entry);

    const duration = Number.isFinite(spec.durationMs) && spec.durationMs > 0 ? spec.durationMs : 0;
    try {
      entry.timer = setTimer(() => settle(entry), Math.min(duration, MAX_DURATION_MS) + FAILSAFE_MARGIN_MS);
    } catch {
      // Without a failsafe timer the effect must still end: dispose now.
      errorCount += 1;
      settle(entry);
    }
    // Dispose the replaced effects last; the slot is already ours.
    for (const old of replaced) settle(old);
    trimTo(MAX_ACTIVE_EFFECTS);
    return handle;
  }

  function finish(handle: EffectHandle): void {
    const entry = entryOf.get(handle);
    if (entry) settle(entry);
  }

  function flushAll(): void {
    for (let pass = 0; active.size > 0; pass += 1) {
      if (pass >= MAX_FLUSH_PASSES) {
        errorCount += 1;
        return;
      }
      for (const entry of [...active.values()]) settle(entry);
    }
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
