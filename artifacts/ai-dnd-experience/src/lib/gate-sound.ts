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
  oscillator.frequency.setValueAtTime(frequency * 1.003, start);
  oscillator.frequency.exponentialRampToValueAtTime(frequency, start + Math.min(0.11, duration * 0.45));
  oscillator.detune.setValueAtTime(-2, start);
  oscillator.detune.linearRampToValueAtTime(1.5, start + duration);
  filter.type = 'lowpass';
  filter.frequency.setValueAtTime(filterFrequency * 1.12, start);
  filter.frequency.exponentialRampToValueAtTime(filterFrequency, start + Math.min(0.16, duration * 0.7));
  amp.gain.setValueAtTime(0.0001, start);
  amp.gain.exponentialRampToValueAtTime(Math.max(0.0002, gain), start + Math.min(0.045, duration * 0.3));
  amp.gain.setValueAtTime(Math.max(0.0002, gain * 0.72), start + duration * 0.62);
  amp.gain.exponentialRampToValueAtTime(0.0001, start + duration);
  oscillator.connect(filter);
  filter.connect(amp);
  amp.connect(ctx.destination);
  oscillator.start(start);
  oscillator.stop(start + duration + 0.02);
}

function rustle(ctx: AudioContext, start: number, duration: number, gain: number, centerFrequency = 900) {
  const length = Math.floor(ctx.sampleRate * duration);
  const buffer = ctx.createBuffer(1, length, ctx.sampleRate);
  const data = buffer.getChannelData(0);
  for (let index = 0; index < length; index += 1) data[index] = (Math.random() * 2 - 1) * (1 - index / length);
  const source = ctx.createBufferSource();
  const filter = ctx.createBiquadFilter();
  const amp = ctx.createGain();
  source.buffer = buffer;
  filter.type = 'bandpass';
  filter.frequency.setValueAtTime(centerFrequency * 1.25, start);
  filter.Q.value = 0.55;
  filter.frequency.exponentialRampToValueAtTime(centerFrequency * 0.72, start + duration);
  amp.gain.setValueAtTime(0.0001, start);
  amp.gain.exponentialRampToValueAtTime(Math.max(0.0002, gain), start + Math.min(0.025, duration * 0.3));
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
    rustle(ctx, now, 0.105, level * 0.72, 680);
    tone(ctx, 132, now + 0.018, 0.13, 'sine', level * 0.1, 360);
  } else if (cue === 'select') {
    rustle(ctx, now, 0.052, level * 0.7, 1500);
    tone(ctx, 185, now + 0.012, 0.075, 'sine', level * 0.075, 520);
  } else if (cue === 'page') {
    rustle(ctx, now, 0.16, level * 0.76, 1150);
    tone(ctx, 118, now + 0.025, 0.11, 'sine', level * 0.09, 310);
  } else if (cue === 'warn') {
    rustle(ctx, now, 0.07, level * 0.62, 520);
    rustle(ctx, now + 0.075, 0.09, level * 0.48, 430);
    tone(ctx, 104, now + 0.02, 0.14, 'sine', level * 0.08, 260);
  } else {
    rustle(ctx, now, 0.13, level * 0.7, 920);
    rustle(ctx, now + 0.025, 0.075, level * 0.24, 1850);
    tone(ctx, 146, now + 0.045, 0.18, 'sine', level * 0.09, 380);
  }
}
