import assert from 'node:assert/strict';
import path from 'node:path';
import { after, before, test } from 'node:test';

process.env.PORT ||= '4181';
process.env.BASE_PATH ||= '/';
delete process.env.REPL_ID;

let vite;
let summarizeTurnOutcome;

before(async () => {
  const { createServer } = await import('vite');
  vite = await createServer({
    configFile: path.join(process.cwd(), 'vite.config.ts'),
    server: { middlewareMode: true },
    appType: 'custom',
    logLevel: 'silent',
  });
  ({ summarizeTurnOutcome } = await vite.ssrLoadModule('/src/lib/turn-outcome.ts'));
});

after(async () => {
  await vite?.close();
});

test('turn outcome summary names what the receipt says, nothing more', () => {
  assert.equal(summarizeTurnOutcome(null), null);
  assert.equal(summarizeTurnOutcome({ action: 'travel', place_created: true }), 'Yeni bir yer kaydedildi');
  assert.equal(summarizeTurnOutcome({ action: 'travel', place_created: false }), 'Bilinen bir yere dönüldü');
  assert.equal(summarizeTurnOutcome({ action: 'everyday_action', kind: 'knock' }), 'Kapıya vuruldu');
  assert.equal(
    summarizeTurnOutcome({ action: 'skill_check', target_name: 'Han Kapısı', found: false }),
    'Han Kapısı: bu bakışla yeni bir şey yok',
  );
  assert.equal(summarizeTurnOutcome({ action: 'dialogue', status: 'resolved' }), null);
});
