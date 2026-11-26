import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { after, before, test } from 'node:test';

process.env.PORT ||= '4181';
process.env.BASE_PATH ||= '/';

// D-578: the offline creation catalog in the browser is a hand-kept copy of the server catalog.
// The copy is shown in Turkish and metres, so names, descriptions, labels and item text are not compared.
// Every rule value it carries (dice, abilities, skill lists, pick counts, ability methods) must equal the server entry,
// so a server rule change turns this red instead of leaving a stale offline fallback.
const RULE_KEYS = {
  classes: ['hit_die', 'primary_ability', 'skill_count', 'skill_options', 'is_spellcaster', 'cantrips_count', 'spells_count'],
  backgrounds: ['abilities', 'skills'],
  skills: ['ability'],
};
const python = process.env.PYTHON || 'python';
const serverRoot = process.env.AI_DND_SERVER_ROOT || path.resolve('../../ai-dnd');
let vite, client, server;

before(async () => {
  server = JSON.parse(execFileSync(python, ['-B', '-c',
    'import json; from api.dnd_2024_rules import get_character_creation_catalog; print(json.dumps(get_character_creation_catalog(), ensure_ascii=True))'],
  { cwd: serverRoot, encoding: 'utf8', maxBuffer: 1 << 27, env: { ...process.env, PYTHONUTF8: '1' } }));
  const { createServer } = await import('vite');
  vite = await createServer({ configFile: path.resolve('vite.config.ts'), server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' });
  client = JSON.parse(JSON.stringify((await vite.ssrLoadModule('/src/lib/character-catalog-defaults.ts')).DEFAULT_CATALOG));
});
after(async () => await vite?.close());

test('defaultCatalogMatchesServer: every rule value of the offline catalog equals the server catalog', () => {
  const out = [];
  for (const id of Object.keys(client.races)) if (!(id in server.races)) out.push(`races.${id}: not a server species`);
  for (const [section, keys] of Object.entries(RULE_KEYS)) {
    for (const [id, mine] of Object.entries(client[section])) {
      const theirs = server[section]?.[id];
      if (!theirs) { out.push(`${section}.${id}: not on the server`); continue; }
      for (const key of keys) {
        const norm = (v) => JSON.stringify(key === 'skill_options' && Array.isArray(v) ? [...v].sort() : v);
        const same = (x, y) => norm(x) === norm(y);
        if (key in mine && !same(mine[key], theirs[key])) out.push(`${section}.${id}.${key}: client ${JSON.stringify(mine[key])} != server ${JSON.stringify(theirs[key])}`);
      }
    }
  }
  assert.deepEqual(out, []);
});
