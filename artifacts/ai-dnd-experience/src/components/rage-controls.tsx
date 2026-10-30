import type { CombatActionInput, RageState, RageAvailability } from '@workspace/api-client-react';
type Availability = RageAvailability;
type Rage = RageState;
/** Read-only finite projection validation; never infer adoption from class, armor or inventory. */
export function readRageProjection(value: unknown): Rage | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const raw = value as Rage;
  const availability = (item: Availability) => !!item && typeof item.available === 'boolean' && (item.reason === null || typeof item.reason === 'string');
  if (!Number.isSafeInteger(raw.max_uses) || raw.max_uses < 1 || !Number.isSafeInteger(raw.uses_remaining) || raw.uses_remaining < 0 || raw.uses_remaining > raw.max_uses
    || typeof raw.active !== 'boolean' || !availability(raw.activate) || !availability(raw.extend)
    || (raw.active ? !Number.isSafeInteger(raw.remaining_seconds) || Number(raw.remaining_seconds) < 0 : raw.remaining_seconds !== null)) return null;
  return raw;
}

export function RageStatus({ rage }: { rage: unknown }) {
  const value = readRageProjection(rage);
  if (!value) return null;
  return <div className="story-meta mt-3" data-testid="rage-status">
    <p data-testid="rage-uses">Rage kullanımı: {value.uses_remaining}/{value.max_uses}</p>
    <p data-testid={value.active ? 'rage-active' : 'rage-inactive'}>{value.active ? 'Rage etkin' : 'Rage etkin değil'}</p>
    {value.active && <p data-testid="rage-duration">Sunucunun bildirdiği kalan süre: {value.remaining_seconds} saniye. Bu bir canlı geri sayım değildir.</p>}
    <p>Sunucunun doğruladığı Barbarian Rage durumu desteklenir; tüm sınıf özellikleri uygulanmış değildir. Etkinlik, gerçek tur ve zaman ilerlemesinde sunucuda değerlendirilir; çatışma bitişi tek başına Rage'i bitirmez.</p>
  </div>;
}

export function RageControl({ rage, confirmed, onChange, blocked, onCommand }: {
  rage: unknown; confirmed: boolean; onChange: (confirmed: boolean) => void; blocked: boolean;
  onCommand: (message: string, command: CombatActionInput) => void;
}) {
  const value = readRageProjection(rage);
  if (!value) return null;
  const kind = value.active ? 'extend_rage' : 'activate_rage';
  const availability = value.active ? value.extend : value.activate;
  const enabled = !blocked && availability.available;
  return <div className="story-meta mt-3" data-testid="rage-controls">
    <RageStatus rage={value} />
    <label><input type="checkbox" data-testid="rage-confirm" checked={confirmed} disabled={!enabled} onChange={event => { if (enabled) onChange(event.target.checked); }} />
      {value.active ? ' Bu tur Rage süresini Bonus Action ile uzatmayı onaylıyorum.' : ' Rage başlatmak için 1 kullanım ve Bonus Action harcamayı onaylıyorum.'}</label>
    <button type="button" className="action-suggestion" data-testid={value.active ? 'button-extend-rage' : 'button-activate-rage'} disabled={!enabled || !confirmed} onClick={() => {
      if (!enabled || !confirmed) return;
      onCommand(value.active ? 'Rage süresini uzatıyorum.' : 'Rage başlatıyorum.', { steps: [{ kind, resource: 'bonus' }] });
    }}>{value.active ? 'Rage uzat' : 'Rage başlat'} · Bonus Action</button>
    {availability.reason && <p role="status">Rage kullanılamıyor: {availability.reason}</p>}
    <p>Bu uygulamada başlatma ve elle uzatma yalnız kendi çatışma turunda desteklenir. Bu bir PHB dış-çatışma yasağı değildir.</p>
  </div>;
}
