import type { EconomyStepInput, FighterState, GameState } from '@workspace/api-client-react';
import type { InteractionMode } from '@/lib/action-suggestions';
import { readFighterProjection, tacticalMindAvailable } from '@/lib/fighter-projection';
export { readFighterProjection, tacticalMindAvailable } from '@/lib/fighter-projection';

/** The typed step for Second Wind; a Tactical Shift distance is sent only when the server says it exists. Null means do not send. */
export function secondWindStep(fighter: FighterState, shift: string): EconomyStepInput | null {
  if (shift.trim() === '') return { kind: 'second_wind', resource: 'bonus' };
  const distance = Number(shift);
  if (!fighter.second_wind.tactical_shift || !Number.isSafeInteger(distance) || distance < 1) return null;
  return { kind: 'second_wind', resource: 'bonus', distance_ft: distance };
}

export function TacticalMindControl({ state, mode, targetId, checked, blocked, onChange }: {
  state: GameState; mode: InteractionMode; targetId: string | null; checked: boolean; blocked: boolean; onChange: (checked: boolean) => void;
}) {
  const projection = readFighterProjection(state.character.fighter)?.tactical_mind;
  if (!projection) return null;
  const available = tacticalMindAvailable(state, { interaction_mode: mode, target_id: targetId });
  return <div className="story-meta" style={{ flex: '0 0 100%', minWidth: 0 }} data-testid="tactical-mind-control">
    <label><input type="checkbox" data-testid="tactical-mind-confirm" checked={available && checked} disabled={blocked || !available}
      onChange={event => { if (!blocked && available) onChange(event.target.checked); }} />{' '}
      Bu kontrol başarısız olursa Tactical Mind kullan
    </label>
    <p>Başarısız kontrole 1d10 eklenir; kullanım yalnız kontrol başarıya dönerse Second Wind havuzundan harcanır. Yalnız anlık, hedefsiz Yap kontrolleri; seçim zarı görmeden yapılır.</p>
    {!available && <p role="status" data-testid="tactical-mind-unavailable">{projection.reason ?? 'Bu hamlede seçilemez.'}</p>}
  </div>;
}

export function FighterStatus({ fighter }: { fighter: unknown }) {
  const value = readFighterProjection(fighter);
  if (!value) return null;
  return <div className="story-meta mt-3" data-testid="fighter-status">
    <p data-testid="fighter-second-wind-uses">Second Wind: {value.second_wind.uses_remaining}/{value.second_wind.max_uses} · 1d{value.second_wind.die} + {value.second_wind.level_bonus}</p>
    {value.action_surge && <p data-testid="fighter-action-surge-uses">Action Surge: {value.action_surge.uses_remaining}/{value.action_surge.max_uses}</p>}
    {value.fighting_style && <p data-testid="fighter-style">Dövüş tarzı: {value.fighting_style}</p>}
  </div>;
}

export function FighterControl({ fighter, blocked, shift, onShiftChange, onCommand }: {
  fighter: unknown; blocked: boolean; shift: string; onShiftChange: (value: string) => void;
  onCommand: (label: string, step: EconomyStepInput) => void;
}) {
  const value = readFighterProjection(fighter);
  if (!value) return null;
  const windStep = secondWindStep(value, shift);
  const windEnabled = !blocked && value.second_wind.activate.available && windStep !== null;
  const surge = value.action_surge;
  const surgeEnabled = !blocked && surge?.activate.available === true;
  return <div className="story-meta mt-3" data-testid="fighter-controls">
    <FighterStatus fighter={value} />
    {value.second_wind.tactical_shift && <label>Tactical Shift (ft, en çok Speed'in yarısı) <input aria-label="Tactical Shift mesafesi" data-testid="fighter-tactical-shift" type="number" min="1" step="1"
      className="w-16 bg-transparent border border-amber-100/20 rounded px-1" value={shift} onChange={event => onShiftChange(event.target.value)} /></label>}
    <button type="button" className="action-suggestion" data-testid="button-second-wind" disabled={!windEnabled} onClick={() => {
      if (windEnabled && windStep) onCommand('Second Wind kullanıyorum.', windStep);
    }}>Second Wind · Bonus Action</button>
    {value.second_wind.activate.reason && <p role="status">Second Wind kullanılamıyor: {value.second_wind.activate.reason}</p>}
    {surge && <button type="button" className="action-suggestion" data-testid="button-action-surge" disabled={!surgeEnabled} onClick={() => {
      if (surgeEnabled) onCommand('Action Surge kullanıyorum.', { kind: 'action_surge' });
    }}>Action Surge · ek eylem (Magic hariç)</button>}
    {surge?.activate.reason && <p role="status">Action Surge kullanılamıyor: {surge.activate.reason}</p>}
  </div>;
}
