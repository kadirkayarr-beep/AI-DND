export type GateCue = 'menu' | 'select' | 'page' | 'warn' | 'success';

const MUTE_KEY = 'ai-dnd-ui-sound-muted';
const VOLUME_KEY = 'ai-dnd-ui-sound-volume';

let context: AudioContext | null = null;
let primed = false;

function readMuted() {
  return window.localStorage.getItem(MUTE_KEY) === '1';
}

function readVolume() {
  const raw = Number(window.localStorage.getItem(VOLUME_KEY));
  if (!Number.isFinite(raw)) return 0.35;
  return Math.min(1, Math.max(0, raw));
}

export function gateSoundMuted() {
  return readMuted();
}

export function gateSoundVolume() {
  return readVolume();
}

export function setGateSoundMuted(muted: boolean) {
  window.localStorage.setItem(MUTE_KEY, muted ? '1' : '0');
}

export function setGateSoundVolume(volume: number) {
  window.localStorage.setItem(VOLUME_KEY, String(Math.min(1, Math.max(0, volume))));
}

function audio() {
  if (!context) {
    const Ctx = window.AudioContext || (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctx) return null;
    context = new Ctx();
  }
  if (context.state === 'suspended') void context.resume();
  return context;
}

export function primeGateSound() {
  primed = true;
  audio();
}

function tone(ctx: AudioContext, frequency: number, start: number, duration: number, type: OscillatorType, gain: number, filterFrequency: number) {
  const oscillator = ctx.createOscillator();
  const filter = ctx.createBiquadFilter();
  const amp = ctx.createGain();
  oscillator.type = type;
  oscillator.frequency.value = frequency;
  filter.type = 'lowpass';
  filter.frequency.value = filterFrequency;
  amp.gain.setValueAtTime(0.0001, start);
  amp.gain.exponentialRampToValueAtTime(Math.max(0.0002, gain), start + 0.02);
  amp.gain.exponentialRampToValueAtTime(0.0001, start + duration);
  oscillator.connect(filter);
  filter.connect(amp);
  amp.connect(ctx.destination);
  oscillator.start(start);
  oscillator.stop(start + duration + 0.02);
}

function rustle(ctx: AudioContext, start: number, duration: number, gain: number) {
  const length = Math.floor(ctx.sampleRate * duration);
  const buffer = ctx.createBuffer(1, length, ctx.sampleRate);
  const data = buffer.getChannelData(0);
  for (let index = 0; index < length; index += 1) data[index] = (Math.random() * 2 - 1) * (1 - index / length);
  const source = ctx.createBufferSource();
  const filter = ctx.createBiquadFilter();
  const amp = ctx.createGain();
  source.buffer = buffer;
  filter.type = 'bandpass';
  filter.frequency.value = 900;
  filter.Q.value = 0.7;
  amp.gain.setValueAtTime(gain, start);
  amp.gain.exponentialRampToValueAtTime(0.0001, start + duration);
  source.connect(filter);
  filter.connect(amp);
  amp.connect(ctx.destination);
  source.start(start);
  source.stop(start + duration);
}

export function playGateSound(cue: GateCue) {
  if (!primed || readMuted()) return;
  const ctx = audio();
  if (!ctx) return;
  const now = ctx.currentTime;
  const level = readVolume() * 0.18;
  if (cue === 'menu') {
    tone(ctx, 196, now, 0.16, 'sine', level, 700);
    rustle(ctx, now, 0.09, level * 0.45);
  } else if (cue === 'select') {
    tone(ctx, 392, now, 0.12, 'triangle', level * 0.7, 1400);
    tone(ctx, 587, now + 0.03, 0.14, 'sine', level * 0.45, 1600);
  } else if (cue === 'page') {
    rustle(ctx, now, 0.14, level * 0.55);
    tone(ctx, 247, now, 0.1, 'sine', level * 0.35, 800);
  } else if (cue === 'warn') {
    tone(ctx, 311, now, 0.12, 'sine', level * 0.55, 900);
    tone(ctx, 233, now + 0.09, 0.16, 'triangle', level * 0.4, 700);
  } else {
    tone(ctx, 262, now, 0.16, 'sine', level * 0.5, 1200);
    tone(ctx, 330, now + 0.08, 0.18, 'sine', level * 0.45, 1200);
    tone(ctx, 392, now + 0.16, 0.28, 'triangle', level * 0.4, 1400);
    rustle(ctx, now, 0.12, level * 0.25);
  }
}
