import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile, stat } from 'node:fs/promises';

// Plan parts D and D1: v0 graphite ouroboros (WebGL, owner-approved 2026-11-17), main-menu music, compressed assets.
const logo = await readFile('src/components/ouroboros-logo.tsx', 'utf8');
const renderer = await readFile('src/components/ouroboros-renderer.ts', 'utf8');
const music = await readFile('src/lib/menu-music.ts', 'utf8');
const button = await readFile('src/components/menu-music.tsx', 'utf8');
const shell = await readFile('src/pages/game/shell-parts.tsx', 'utf8');
const css = await readFile('src/components/unwritten-play.css', 'utf8');
const panel = await readFile('src/components/appearance-settings-panel.tsx', 'utf8');
const html = await readFile('index.html', 'utf8');

// Owner decision 2026-11-17 (behaviour kept from PR #122): the logo turns all the time while motion is on.
test('with motion on the logo loops on its own; reduced motion or effects off stop it; the loop pauses for a hidden tab, an off-screen logo and the OS reduced-motion setting', () => {
  assert.match(shell, /<OuroborosLogo \/>/);
  assert.match(logo, /export function OuroborosLogo\(/);
  assert.match(logo, /const motion = !prefersReducedMotion && effectsLevel !== 'off'/);
  assert.match(logo, /renderer\.current\?\.setRunning\(motion\)/);
  assert.match(logo, /engine\.setRunning\(motionNow\.current\)/);
  assert.match(renderer, /function shouldRun\(\) \{ return running && visible && !document\.hidden && !media\.matches/);
  assert.match(renderer, /document\.addEventListener\('visibilitychange'/);
  assert.match(renderer, /new IntersectionObserver\(/);
  assert.match(renderer, /matchMedia\('\(prefers-reduced-motion: reduce\)'\)/);
  assert.match(renderer, /if \(!shouldRun\(\)\) return;/);
  assert.match(renderer, /cancelAnimationFrame\(frame\)/);
});
test('without WebGL, on a lost context or a failed texture the static emblem stays; the small mark never starts WebGL', () => {
  assert.match(renderer, /if \(!gl \|\| !ctx\) throw new Error/);
  assert.match(renderer, /ouroboros-renderer-failed/);
  assert.match(logo, /\.catch\(\(\) => \{ if \(!disposed\) setLive\(false\); \}\)/);
  assert.match(logo, /data-renderer=\{live \? 'webgl' : 'static'\}/);
  assert.match(logo, /if \(mark \|\| !canvas\.current \|\| !dust\.current\) return undefined;/);
  assert.match(logo, /logo\/ouroboros-\$\{mark \? 'mark' : 'emblem'\}\.png/);
  assert.match(logo, /role="img"/);
  assert.match(logo, /aria-label="[^"]*yılan/);
  assert.match(logo, /image-approved-ouroboros/);
});
test('night is the same logo inverted; the ink is dark in both themes and comes from theme variables, not colour codes', () => {
  assert.match(css, /\.unwritten-ouroboros \{[^}]*color:var\(--unw-page\); filter:invert\(1\)/);
  assert.match(css, /data-unw-theme="day"\] \.unwritten-ouroboros \{ color:var\(--unw-text\); filter:none/);
  const logoRules = css.split(/\r?\n/).filter(line => line.includes('.unwritten-ouroboros')).join(' ');
  assert.ok(logoRules.length > 0);
  assert.doesNotMatch(logoRules, /#[0-9a-fA-F]{3,8}/);
  assert.doesNotMatch(logo, /resolvedTheme/);
});
test('the logo textures are plain png files (no base64 in the bundle) and the old video files are gone', async () => {
  assert.doesNotMatch(renderer, /data:image\/png;base64/);
  assert.doesNotMatch(logo, /data:image\/png;base64/);
  assert.match(renderer, /logo\/ouroboros-\$\{name\}\.png/);
  for (const name of ['skin', 'head', 'profile', 'phase', 'emblem', 'mark']) assert.ok((await stat(`public/logo/ouroboros-${name}.png`)).size > 0, name);
  for (const gone of ['ouroboros-day.mp4', 'ouroboros-night.mp4', 'ouroboros-day-still.jpg', 'ouroboros-night-still.jpg']) await assert.rejects(stat(`public/logo/${gone}`), gone);
});
test('music: autoplay attempt, first-gesture fallback, fade out on leaving, remembered through the settings store', () => {
  assert.match(music, /await el\.play\(\)/);
  for (const type of ['pointerdown', 'keydown', 'touchstart']) assert.ok(music.includes(`'${type}'`), type);
  assert.match(music, /export function stopMenuMusic/);
  assert.match(button, /return \(\) => stopMenuMusic\(\)/);
  assert.match(button, /aria-label=\{label\}/);
  assert.match(button, /setSetting\('menuMusic', !on\)/);
  assert.match(panel, /checkbox-menu-music/);
});
test('the music button sits on the home screen header and has a visible focus ring', () => {
  assert.match(shell, /<MenuMusicButton \/>/);
  assert.match(css, /\.menu-music-button:focus-visible/);
});
test('favicon is the logo ring', () => {
  assert.match(html, /rel="icon" type="image\/png"[^>]*favicon\.png/);
});
test('assets are compressed and documented', async () => {
  const limit = { 'public/logo/ouroboros-skin.png': 0.4, 'public/logo/ouroboros-head.png': 0.4, 'public/logo/ouroboros-emblem.png': 0.4, 'public/logo/ouroboros-mark.png': 0.05, 'public/audio/nordisk-ritual.mp3': 3.0, 'public/favicon.png': 0.05 };
  for (const [file, mb] of Object.entries(limit)) assert.ok((await stat(file)).size < mb * 1024 * 1024, `${file} is under ${mb} MB`);
  const notes = await readFile('public/ASSET_NOTES.md', 'utf8');
  for (const name of ['ouroboros-skin.png', 'ouroboros-head.png', 'ouroboros-emblem.png', 'ouroboros-mark.png', 'nordisk-ritual.mp3', 'favicon.png', 'ffmpeg']) assert.ok(notes.includes(name), name);
});
