/** Guard against stale generated API types used by the RPG frontend. */
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { test } from 'node:test';

const root = path.resolve(process.cwd(), '../..');
const contractPath = path.join(root, 'lib/api-spec/openapi.yaml');
const schemasPath = path.join(root, 'lib/api-client-react/src/generated/api.schemas.ts');
const operationsPath = path.join(root, 'lib/api-client-react/src/generated/api.ts');

function interfaceBlock(source, name) {
  const start = source.indexOf(`export interface ${name} {`);
  assert.ok(start >= 0, `Missing generated ${name}`);
  const end = source.indexOf('\n}', start);
  assert.ok(end > start, `Unclosed generated ${name}`);
  return source.slice(start, end);
}

test('generated API includes the canonical state and combat contract', async () => {
  const [contract, schemas, operations] = await Promise.all([
    readFile(contractPath, 'utf8'),
    readFile(schemasPath, 'utf8'),
    readFile(operationsPath, 'utf8'),
  ]);
  const state = interfaceBlock(schemas, 'GameState');
  const combat = interfaceBlock(schemas, 'GameCombat');
  const turn = interfaceBlock(schemas, 'GameTurnInput');

  for (const field of ['exploration', 'spellcasting', 'campaign_time', 'adventure']) {
    assert.match(contract, new RegExp(`^\\s+${field}:`, 'm'));
    assert.match(state, new RegExp(`^\\s+${field}(?:\\?)?:`, 'm'));
  }
  assert.match(combat, /^\s+action_economy\?:/m);
  assert.match(turn, /^\s+interaction_mode\?:/m);
  assert.match(operations, /export const useDeleteCampaign\s*=/);
});

test('generated API carries the read-only counter quote and the trade refusal reason', async () => {
  const [contract, schemas, operations] = await Promise.all([
    readFile(contractPath, 'utf8'),
    readFile(schemasPath, 'utf8'),
    readFile(operationsPath, 'utf8'),
  ]);
  assert.match(contract, /^\s+operationId: getGameSessionShop$/m);
  const counter = interfaceBlock(schemas, 'ShopCounterResponse');
  for (const field of ['vendor', 'lines', 'purse', 'seq', 'status', 'reason']) {
    assert.match(counter, new RegExp(`^\\s+${field}(?:\\?)?:`, 'm'));
  }
  for (const field of ['key', 'label', 'unit_cp', 'stock', 'discount_cp']) {
    assert.match(interfaceBlock(schemas, 'ShopCounterLine'), new RegExp(`^\\s+${field}:`, 'm'));
  }
  for (const field of ['total_cp', 'gp', 'sp', 'cp']) {
    assert.match(interfaceBlock(schemas, 'ShopCounterPurse'), new RegExp(`^\\s+${field}:`, 'm'));
  }
  assert.match(interfaceBlock(schemas, 'TurnOutcome'), /^\s+reason\?:/m);
  assert.match(operations, /export const getGameSessionShop\s*=/);
  // A quote is a read: no generated mutation may exist for it.
  assert.doesNotMatch(operations, /useApplyGameSessionShop|postGameSessionShop/);
});
