// Plan part D: main-menu music. One looped track, started when the home screen opens, faded out when it
// closes. Browsers may refuse to play before a gesture; then the first tap, key press or touch starts it.
// Nothing here touches the saved game.
export const MENU_MUSIC_SRC = 'audio/nordisk-ritual.mp3';
export const MENU_MUSIC_VOLUME = 0.35;
const FADE_MS = 900;

const GESTURES = ['pointerdown', 'keydown', 'touchstart'] as const;

let audio: HTMLAudioElement | null = null;
let fadeTimer: ReturnType<typeof setInterval> | null = null;
let removeGestureRetry: (() => void) | null = null;
let removeVisibility: (() => void) | null = null;

function clearFade() {
  if (fadeTimer) { clearInterval(fadeTimer); fadeTimer = null; }
}

function dropGestureRetry() {
  removeGestureRetry?.();
  removeGestureRetry = null;
}

function ensureAudio(baseUrl: string): HTMLAudioElement {
  if (!audio) {
    audio = new Audio(`${baseUrl}${MENU_MUSIC_SRC}`);
    audio.loop = true;
    audio.preload = 'auto';
  }
  return audio;
}

/** Try to start playing. Resolves true when audible, false when the browser needs a gesture first. */
export async function startMenuMusic(baseUrl: string): Promise<boolean> {
  clearFade();
  const el = ensureAudio(baseUrl);
  el.volume = MENU_MUSIC_VOLUME;
  if (!removeVisibility) {
    const onVisibility = () => {
      if (!audio) return;
      if (document.hidden) audio.pause();
      else if (removeGestureRetry === null && audio.paused && audio.currentTime > 0) void audio.play().catch(() => {});
    };
    document.addEventListener('visibilitychange', onVisibility);
    removeVisibility = () => document.removeEventListener('visibilitychange', onVisibility);
  }
  try {
    await el.play();
    dropGestureRetry();
    return true;
  } catch {
    if (!removeGestureRetry) {
      const retry = () => {
        dropGestureRetry();
        if (audio) void audio.play().catch(() => {});
      };
      for (const type of GESTURES) window.addEventListener(type, retry, { once: true, passive: true });
      removeGestureRetry = () => { for (const type of GESTURES) window.removeEventListener(type, retry); };
    }
    return false;
  }
}

/** Fade out and stop. Safe to call when nothing plays. */
export function stopMenuMusic(fadeMs: number = FADE_MS): void {
  dropGestureRetry();
  removeVisibility?.();
  removeVisibility = null;
  const el = audio;
  if (!el) return;
  clearFade();
  const steps = Math.max(1, Math.round(fadeMs / 50));
  let step = 0;
  const from = el.volume;
  fadeTimer = setInterval(() => {
    step += 1;
    el.volume = Math.max(0, from * (1 - step / steps));
    if (step >= steps) {
      clearFade();
      el.pause();
      el.currentTime = 0;
    }
  }, 50);
}
