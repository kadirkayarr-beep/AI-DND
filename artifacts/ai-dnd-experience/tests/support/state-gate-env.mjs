// The vm harnesses inject the page's helpers by hand; this injects the REAL freshness gate (not a stub) for the ['state', id] cache key they use.
import { applyState, nextRevision } from '../../src/lib/state-envelope.ts';
import { ActionDeadlineError, monotonicNow, remainingMs, startDeadline, withActionDeadline } from '../../src/lib/action-deadline.ts';

export function gateInjection() {
  return {
    ActionDeadlineError, monotonicNow, remainingMs, startDeadline, withActionDeadline,
    nextRevision,
    applyGameState: (client, sessionId, state, options = {}) =>
      applyState(client, ['state', sessionId], { ownerId: 'harness-owner', campaignId: sessionId, epoch: 1 },
        options.revision ?? nextRevision(), state, { isCurrent: options.isCurrent }),
  };
}
