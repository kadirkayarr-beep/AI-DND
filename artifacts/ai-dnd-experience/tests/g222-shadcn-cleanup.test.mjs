import assert from 'node:assert/strict';
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';

// G2.22: unused shadcn files and their packages are gone (D-557, D-570, D-579), the Radix toast
// system that nothing calls is gone (D-558, D-572), the book gallery stays development only (D-567).
const root = process.cwd();
const src = path.join(root, 'src');
const ui = path.join(src, 'components', 'ui');

function walk(dir) {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name);
    return statSync(full).isDirectory() ? walk(full) : [full];
  });
}
const sourceFiles = walk(src).filter((f) => /\.(tsx?|css)$/.test(f));
const read = (f) => readFileSync(f, 'utf8');
const uiNames = readdirSync(ui).map((f) => f.replace(/\.tsx$/, ''));

function importsOf(file) {
  const text = read(file);
  const found = new Set();
  for (const m of text.matchAll(/from\s+['"]([^'"]+)['"]|import\(\s*['"]([^'"]+)['"]\s*\)/g)) found.add(m[1] ?? m[2]);
  return found;
}

test('every ui file is reachable from a file outside the ui folder', () => {
  const reached = new Set();
  const take = (file) => {
    for (const spec of importsOf(file)) {
      const name = spec.startsWith('@/components/ui/') ? spec.slice('@/components/ui/'.length)
        : path.dirname(file) === ui && spec.startsWith('./') ? spec.slice(2) : null;
      if (name && uiNames.includes(name) && !reached.has(name)) {
        reached.add(name);
        take(path.join(ui, `${name}.tsx`));
      }
    }
  };
  for (const f of sourceFiles.filter((x) => path.dirname(x) !== ui)) take(f);
  assert.deepEqual(uiNames.filter((n) => !reached.has(n)).sort(), []);
});

test('every Radix package in package.json is imported by the source', () => {
  const pkg = JSON.parse(read(path.join(root, 'package.json')));
  const radix = Object.keys({ ...pkg.dependencies, ...pkg.devDependencies }).filter((n) => n.startsWith('@radix-ui/'));
  const text = sourceFiles.map(read).join('\n');
  assert.deepEqual(radix.filter((n) => !text.includes(`'${n}'`) && !text.includes(`"${n}"`)).sort(), []);
});

test('the shadcn-only packages nothing imports are gone from package.json', () => {
  const pkg = JSON.parse(read(path.join(root, 'package.json')));
  const names = Object.keys({ ...pkg.dependencies, ...pkg.devDependencies });
  const text = sourceFiles.map(read).join('\n');
  const gone = ['@hookform/resolvers', 'cmdk', 'date-fns', 'embla-carousel-react', 'framer-motion', 'input-otp',
    'react-day-picker', 'react-hook-form', 'react-icons', 'react-resizable-panels', 'recharts', 'vaul', 'zod'];
  assert.deepEqual(gone.filter((n) => names.includes(n) && !text.includes(`'${n}`) && !text.includes(`"${n}`)), []);
});

test('the unused Radix toast system is removed and sonner stays the only toast', () => {
  assert.equal(existsSync(path.join(ui, 'toast.tsx')), false);
  assert.equal(existsSync(path.join(ui, 'toaster.tsx')), false);
  assert.equal(existsSync(path.join(src, 'hooks', 'use-toast.ts')), false);
  assert.doesNotMatch(read(path.join(src, 'app-shell.tsx')), /ui\/toaster|<Toaster/);
  assert.match(read(path.join(src, 'components', 'kitap', 'kontroller.tsx')), /from '@\/components\/ui\/sonner'/);
});

test('the book gallery is only built in development', () => {
  assert.match(read(path.join(src, 'app-shell.tsx')), /import\.meta\.env\.DEV \? lazy\(\(\) => import\(["']\.\/pages\/kitap-galerisi["']\)\) : null/);
});

test('the shop controllers live in src/lib and shop-panel exports no helper only tests reach', () => {
  const moved = ['shopReasonText', 'shopOutcomeStep', 'createConfirmGate', 'createOnceGate', 'createOfferCardController',
    'prepareProposal', 'createPrepareController'];
  const panel = read(path.join(src, 'components', 'shop-panel.tsx'));
  const lib = read(path.join(src, 'lib', 'shop-controllers.ts'));
  for (const name of moved) {
    assert.doesNotMatch(panel, new RegExp(`export (function|const) ${name}\\b`), `${name} still exported by shop-panel`);
    if (name !== 'createOnceGate') assert.match(panel, new RegExp(`\\b${name}\\b`), `${name} no longer used by shop-panel`);
  }
  for (const name of moved.filter((n) => n !== 'createOnceGate')) assert.match(lib, new RegExp(`export function ${name}\\b`), name);
  assert.doesNotMatch(panel, /export type (PrepareForm|ShopCounts)\b/);
});
