import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile, stat } from 'node:fs/promises';

// Plan parts D and D1 (simple path): themed looped logo video, main-menu music, compressed assets.
const logo = await readFile('src/components/ouroboros-logo.tsx', 'utf8');
const music = await readFile('src/lib/menu-music.ts', 'utf8');
const button = await readFile('src/components/menu-music.tsx', 'utf8');
const shell = await readFile('src/pages/game/shell-parts.tsx', 'utf8');
const css = await readFile('src/components/unwritten-play.css', 'utf8');
const panel = await readFile('src/components/appearance-settings-panel.tsx', 'utf8');
const html = await readFile('index.html', 'utf8');

// Owner decision 2026-11-17 (behaviour change): the logo turns all the time while motion is on, not only
// while something is loading. Reduced motion / effects off still show only the still (next test).
test('with motion on the logo loops on its own, whatever is loading; a hidden tab pauses it and showing the tab resumes it', () => {
  assert.match(shell, /<OuroborosLogo \/>/);
  assert.match(logo, /export function OuroborosLogo\(\) \{/);
  assert.doesNotMatch(logo, /loading=|\{ loading \}|MIN_VISIBLE_MS|shownAt/);
  assert.match(logo, /if \(!el \|\| !motion\) return undefined;/);
  assert.match(logo, /const start = \(\) => \{ if \(!document\.hidden\) void el\.play\(\)/);
  assert.match(logo, /if \(document\.hidden\) el\.pause\(\);\s*else start\(\);/);
  assert.match(logo, /\}, \[motion, resolvedTheme\]\);/);
  assert.doesNotMatch(logo, /autoPlay|autoplay/);
});
test('reduced motion or effects off: no video at all, only the still image', () => {
  assert.match(logo, /const motion = !prefersReducedMotion && effectsLevel !== 'off'/);
  assert.match(logo, /\{motion && \(\s*<video/);
  assert.match(css, /prefers-reduced-motion: reduce\) \{ \.unwritten-entry \.ouroboros-video \{ display:none/);
});
test('video pauses while the tab is hidden and the one-tag video is muted, looped, inline', () => {
  assert.match(logo, /document\.hidden/);
  assert.match(logo, /visibilitychange/);
  assert.match(logo, /\bmuted\b[\s\S]*\bloop\b[\s\S]*playsInline/);
});
test('each theme has its own video and still; day multiplies, night screens (flat opaque ground, no alpha)', () => {
  assert.match(logo, /ouroboros-\$\{resolvedTheme\}\.mp4/);
  assert.match(logo, /ouroboros-\$\{resolvedTheme\}-still\.jpg/);
  assert.match(css, /\.unwritten-entry \.ouroboros-art \{[^}]*mix-blend-mode:screen/);
  assert.match(css, /data-unw-theme="day"\] \.unwritten-entry \.ouroboros-art \{ mix-blend-mode:multiply/);
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
  const limit = { 'public/logo/ouroboros-day.mp4': 2.0, 'public/logo/ouroboros-night.mp4': 2.0, 'public/audio/nordisk-ritual.mp3': 3.0, 'public/favicon.png': 0.05 };
  for (const [file, mb] of Object.entries(limit)) assert.ok((await stat(file)).size < mb * 1024 * 1024, `${file} is under ${mb} MB`);
  const notes = await readFile('public/ASSET_NOTES.md', 'utf8');
  for (const name of ['ouroboros-day.mp4', 'ouroboros-night.mp4', 'nordisk-ritual.mp3', 'favicon.png', 'ffmpeg']) assert.ok(notes.includes(name), name);
});
