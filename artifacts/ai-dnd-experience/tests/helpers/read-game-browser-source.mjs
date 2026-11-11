import { readdirSync, readFileSync } from 'node:fs';

const pagesDir = new URL('../../src/pages/', import.meta.url);
const gameDir = new URL('game/', pagesDir);

/** game-browser.tsx plus the components split out of it under src/pages/game/, as one source text. */
export function readGameBrowserSource() {
  const parts = [readFileSync(new URL('game-browser.tsx', pagesDir), 'utf8')];
  for (const name of readdirSync(gameDir).filter((file) => file.endsWith('.tsx')).sort()) {
    parts.push(readFileSync(new URL(name, gameDir), 'utf8'));
  }
  return parts.join('\n');
}
