import type { CombatActionInput, EconomyStepInput } from '@workspace/api-client-react';

type Context = {
  decisionKey: string;
  projection: unknown;
  sending: boolean;
  attackEnabled: boolean;
  continueEnabled: boolean;
  reactionEnabled: boolean;
};

/** UI consent only: eligibility and effects are exclusively server projections. */
export function createRecklessIntent() {
  let context: Context;
  let key = '';
  let selected = false;
  let submitted = false;
  let available = false;
  let active = false;
  return {
    get selected() { return selected; },
    get available() { return available; },
    get active() { return active; },
    sync(next: Context) {
      const raw = next.projection as Record<string, unknown> | null | undefined;
      const valid = !!raw && typeof raw.available === 'boolean' && typeof raw.active === 'boolean'
        && (raw.reason === null || typeof raw.reason === 'string');
      available = valid && raw!.available === true && raw!.active === false;
      active = valid && raw!.active === true;
      const nextKey = JSON.stringify([next.decisionKey, available, active, valid ? raw!.reason : null]);
      if (key !== nextKey) { selected = false; submitted = false; }
      if (context?.sending && !next.sending) submitted = false;
      if (next.sending) selected = false;
      key = nextKey;
      context = next;
    },
    choose(value: boolean) {
      selected = value === true && available && !submitted && !context.sending
        && (context.attackEnabled || context.continueEnabled || context.reactionEnabled);
    },
    submit(mode: 'attack' | 'continue' | 'reaction' | 'other', step: EconomyStepInput,
      send: (label: string, command: CombatActionInput) => void, label = '', enabled = true) {
      if (!enabled || submitted || context.sending || (mode === 'attack' && !context.attackEnabled)
        || (mode === 'continue' && !context.continueEnabled)) return;
      const optIn = available && selected && (mode === 'attack' || mode === 'continue'
        || (mode === 'reaction' && context.reactionEnabled));
      selected = false;
      submitted = true;
      // Omission preserves legacy request identity; never insert a default false.
      send(label, { steps: [{ ...step, ...(optIn ? { reckless_attack: true } : {}) }] });
    },
  };
}
