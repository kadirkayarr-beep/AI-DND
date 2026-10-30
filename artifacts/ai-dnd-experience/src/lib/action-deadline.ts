// One absolute, monotonic deadline per action (R07). The token read, the mutation, the undo and the reconciliation
// all draw from the SAME budget; a sub-step that retries never gets a fresh one. Running out is an UNKNOWN outcome:
// the draft and the ActionKey stay, nothing is rolled back and no new action is sent on the player's behalf.
//
// DEFAULT_ACTION_DEADLINE_MS is a technical starting value (a bound so nothing waits forever), not a performance target
// or a hardware guarantee. Real calibration belongs to a later task.

export const DEFAULT_ACTION_DEADLINE_MS = 45000;

export type DeadlineClock = {
  now: () => number;
  setTimer: (callback: () => void, ms: number) => unknown;
  clearTimer: (timer: unknown) => void;
};

export function monotonicNow(): number {
  return typeof performance !== "undefined" ? performance.now() : Date.now();
}

const realClock: DeadlineClock = {
  now: monotonicNow,
  setTimer: (callback, ms) => setTimeout(callback, ms),
  clearTimer: (timer) => clearTimeout(timer as ReturnType<typeof setTimeout>),
};

/** The unknown outcome of an action whose budget ran out; the server may or may not have committed it. */
export class ActionDeadlineError extends Error {
  readonly outcome = "unknown" as const;
  constructor() {
    super("Action deadline expired; the outcome is unknown.");
    this.name = "ActionDeadlineError";
  }
}

let configuredBudgetMs = DEFAULT_ACTION_DEADLINE_MS;

/** Test seam for disposable fixture pages only: the shipped app never calls it. */
export function setActionDeadlineBudget(budgetMs: number): void {
  configuredBudgetMs = budgetMs;
}

export function startDeadline(budgetMs: number = configuredBudgetMs, clock: Pick<DeadlineClock, "now"> = realClock): number {
  return clock.now() + budgetMs;
}

export function remainingMs(deadline: number, now: number): number {
  return Math.max(0, deadline - now);
}

/** What a sub-step may use: its own cap, but never more than what is left of the shared deadline. */
export function stepBudgetMs(deadline: number, now: number, stepCapMs: number): number {
  return Math.min(stepCapMs, remainingMs(deadline, now));
}

/**
 * Runs `work` against the deadline. At expiry the work is told to stop (abort) AND the result is rejected with
 * ActionDeadlineError, so a transport that ignores the signal cannot keep the action waiting; its late reply is dropped.
 */
export function runWithDeadline<T>(
  deadline: number,
  work: (signal: AbortSignal) => Promise<T>,
  clock: DeadlineClock = realClock,
): Promise<T> {
  const controller = new AbortController();
  return new Promise<T>((resolve, reject) => {
    let finished = false;
    const left = remainingMs(deadline, clock.now());
    const expire = () => {
      if (finished) return;
      finished = true;
      controller.abort();
      reject(new ActionDeadlineError());
    };
    const timer = clock.setTimer(expire, left);
    if (left === 0) {
      clock.clearTimer(timer);
      expire();
      return;
    }
    const settle = async () => {
      try {
        const value = await work(controller.signal);
        if (finished) return;
        finished = true;
        clock.clearTimer(timer);
        resolve(value);
      } catch (error) {
        if (finished) return;
        finished = true;
        clock.clearTimer(timer);
        reject(error);
      }
    };
    void settle();
  });
}

type OperationLike = { signal: AbortSignal; isCurrent: () => boolean; close: () => void };

/** An operation whose signal also aborts when the shared deadline passes, so every step of the action inherits it. */
export function withActionDeadline<T extends OperationLike>(
  operation: T, deadline: number, clock: DeadlineClock = realClock,
): T & { deadlineExpired: () => boolean } {
  const controller = new AbortController();
  let fired = false;
  const abort = () => controller.abort();
  if (operation.signal.aborted) controller.abort();
  else operation.signal.addEventListener("abort", abort, { once: true });
  // The timer itself records that the deadline (not the owner) ended the action; no clock arithmetic is re-derived later.
  const timer = clock.setTimer(() => { fired = true; abort(); }, remainingMs(deadline, clock.now()));
  return {
    ...operation,
    signal: controller.signal,
    deadlineExpired: () => fired,
    close: () => {
      clock.clearTimer(timer);
      operation.signal.removeEventListener("abort", abort);
      operation.close();
    },
  };
}
