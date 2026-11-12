import assert from 'node:assert/strict';
import path from 'node:path';
import { before, after, test } from 'node:test';

process.env.PORT ||= '4191';
process.env.BASE_PATH ||= '/';
delete process.env.REPL_ID;

let vite, retainCombatTarget, combatErrorMessage;
before(async () => {
  const { createServer } = await import('vite');
  vite = await createServer({
    configFile: path.join(process.cwd(), 'vite.config.ts'),
    server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent',
  });
  ({ retainCombatTarget, combatErrorMessage } =
    await vite.ssrLoadModule('/src/lib/combat-ui-contract.ts'));
});
after(async () => { await vite?.close(); });

const combat = {
  active: true,
  participant_records: [
    { id: 'enemy-a', kind: 'npc', status: 'active', current_hp: 9 },
    { id: 'enemy-b', kind: 'npc', status: 'dead', current_hp: 0 },
  ],
};

test('valid combat target survives a resolved action while combat continues', () => {
  assert.equal(retainCombatTarget('enemy-a', combat, false), true);
  assert.equal(retainCombatTarget('enemy-b', combat, false), false);
  assert.equal(retainCombatTarget('enemy-a', combat, true), false);
  assert.equal(retainCombatTarget('enemy-a', { ...combat, active: false }, false), false);
});

test('known combat API errors become specific player-facing guidance', () => {
  assert.match(combatErrorMessage({ data: { detail: { code: 'out_of_turn' } } }), /sıra sende değil/);
  assert.match(combatErrorMessage({ data: { detail: { code: 'invalid_combat_target' } } }), /hedef/);
  assert.equal(combatErrorMessage({ data: { detail: { code: 'internal_error' } } }), null);
  assert.equal(combatErrorMessage(null), null);
});

test('D-070: Concentration, Bonus Action and one-slot-per-turn refusals have Turkish guidance, not the English engine message', () => {
  const said = code => combatErrorMessage({ data: { detail: { code, message: 'The Bonus Action was already taken.' } } });
  assert.match(said('concentration_not_held'), /Konsantrasyon/);
  assert.match(said('concentration_not_held'), /sürdürdüğün bir büyü yok/);
  assert.match(said('bonus_action_spent'), /ek eylemini zaten kullandın/);
  assert.match(said('spell_slot_turn_limit'), /Bir turda yalnız bir büyü yuvası/);
  for (const code of ['concentration_not_held', 'bonus_action_spent', 'spell_slot_turn_limit']) assert.doesNotMatch(said(code), /Bonus Action|already|[A-Z][a-z]+ [a-z]+ was/);
});