import type { EconomyStepInput, MonkState } from '@workspace/api-client-react';
import { flurryStep, readMonkProjection, type DeflectMode, type OpenHandChoice } from '@/lib/monk-projection';
export { readMonkProjection } from '@/lib/monk-projection';

const DEFLECT_LABELS: Record<DeflectMode, string> = { off: 'Kapalı', reduce: 'Hasarı azalt', redirect: 'Azalt ve 0 olursa geri yönelt (1 Focus)' };

function reasons(monk: MonkState): string[] {
  const entries = [monk.martial_arts_strike, monk.flurry_of_blows, monk.patient_defense, monk.step_of_the_wind, monk.uncanny_metabolism];
  return [...new Set(entries.flatMap(entry => entry?.reason ? [entry.reason] : []))];
}

export function MonkStatus({ monk }: { monk: unknown }) {
  const value = readMonkProjection(monk);
  if (!value) return null;
  return <div className="story-meta mt-3" data-testid="monk-status">
    <p data-testid="monk-martial-arts">Martial Arts: 1d{value.martial_arts_die}{value.martial_arts_ready ? '' : ' · koşullar sağlanmıyor'}</p>
    {value.focus && <p data-testid="monk-focus">Focus Points: {value.focus.points_remaining}/{value.focus.max_points} · Save DC {value.save_dc}</p>}
    {value.movement_bonus_ft > 0 && <p data-testid="monk-movement">Unarmored Movement: +{value.movement_bonus_ft} ft</p>}
  </div>;
}

export function MonkControl({ monk, blocked, targetId, attackEnabled, continueEnabled, technique, onTechniqueChange, onCommand }: {
  monk: unknown; blocked: boolean; targetId: string | null | undefined; attackEnabled: boolean; continueEnabled: boolean;
  technique: OpenHandChoice; onTechniqueChange: (value: OpenHandChoice) => void; onCommand: (label: string, step: EconomyStepInput) => void;
}) {
  const value = readMonkProjection(monk);
  if (!value) return null;
  const target = targetId || null;
  const can = (entry: { available: boolean } | null | undefined) => !blocked && entry?.available === true;
  const focusLeft = (value.focus?.points_remaining ?? 0) > 0;
  const strike = can(value.martial_arts_strike) && !!target;
  const flurry = can(value.flurry_of_blows) && !!target;
  const stun = !blocked && !!target && value.stunning_strike?.available === true;
  return <div className="story-meta mt-3" data-testid="monk-controls">
    <MonkStatus monk={value} />
    <div className="action-suggestion-list mt-2">
      <button type="button" className="action-suggestion" data-testid="button-martial-arts-strike" disabled={!strike} onClick={() => {
        if (strike && target) onCommand('Bonus Action ile silahsız vuruş yapıyorum.', { kind: 'martial_arts_strike', target_id: target });
      }}>Silahsız vuruş · Bonus</button>
      {value.flurry_of_blows && <button type="button" className="action-suggestion" data-testid="button-flurry" disabled={!flurry} onClick={() => {
        if (flurry && target) onCommand('Flurry of Blows kullanıyorum.', flurryStep(value, 'flurry_of_blows', target, technique));
      }}>Flurry of Blows · Bonus · 1 Focus</button>}
      {value.flurry_strikes_remaining > 0 && <button type="button" className="action-suggestion" data-testid="button-flurry-strike" disabled={blocked || !target} onClick={() => {
        if (!blocked && target) onCommand('Flurry of Blows ikinci vuruşu.', flurryStep(value, 'flurry_strike', target, technique));
      }}>Flurry ikinci vuruş</button>}
      {value.patient_defense && <button type="button" className="action-suggestion" data-testid="button-patient-defense" disabled={!can(value.patient_defense)} onClick={() => {
        if (can(value.patient_defense)) onCommand('Patient Defense kullanıyorum.', { kind: 'patient_defense' });
      }}>Patient Defense · Disengage</button>}
      {value.patient_defense && <button type="button" className="action-suggestion" data-testid="button-patient-defense-focus" disabled={!can(value.patient_defense) || !focusLeft} onClick={() => {
        if (can(value.patient_defense) && focusLeft) onCommand('Patient Defense için Focus harcıyorum.', { kind: 'patient_defense', spend_focus: true });
      }}>Patient Defense · Disengage + Dodge · 1 Focus</button>}
      {value.step_of_the_wind && <button type="button" className="action-suggestion" data-testid="button-step-of-the-wind" disabled={!can(value.step_of_the_wind)} onClick={() => {
        if (can(value.step_of_the_wind)) onCommand('Step of the Wind kullanıyorum.', { kind: 'step_of_the_wind' });
      }}>Step of the Wind · Dash</button>}
      {value.step_of_the_wind && <button type="button" className="action-suggestion" data-testid="button-step-of-the-wind-focus" disabled={!can(value.step_of_the_wind) || !focusLeft} onClick={() => {
        if (can(value.step_of_the_wind) && focusLeft) onCommand('Step of the Wind için Focus harcıyorum.', { kind: 'step_of_the_wind', spend_focus: true });
      }}>Step of the Wind · Disengage + Dash · 1 Focus</button>}
      {value.uncanny_metabolism && <button type="button" className="action-suggestion" data-testid="button-uncanny-metabolism" disabled={!can(value.uncanny_metabolism)} onClick={() => {
        if (can(value.uncanny_metabolism)) onCommand('Uncanny Metabolism kullanıyorum.', { kind: 'uncanny_metabolism' });
      }}>Uncanny Metabolism</button>}
      {value.stunning_strike && <button type="button" className="action-suggestion" data-testid="button-stunning-attack" disabled={!stun || !attackEnabled} onClick={() => {
        if (stun && attackEnabled && target) onCommand('Stunning Strike ile saldırıyorum.', { kind: 'attack', target_id: target, stunning_strike: true });
      }}>Saldır + Stunning Strike · Action</button>}
      {value.stunning_strike && continueEnabled && <button type="button" className="action-suggestion" data-testid="button-stunning-continue" disabled={!stun} onClick={() => {
        if (stun && target) onCommand('Stunning Strike ile saldırıya devam ediyorum.', { kind: 'continue_attack', target_id: target, stunning_strike: true });
      }}>Attack Action devamı + Stunning Strike</button>}
    </div>
    {value.open_hand_techniques.length > 0 && <label>Open Hand Technique <select aria-label="Open Hand Technique" data-testid="monk-technique" value={technique} disabled={blocked}
      onChange={event => { const next = value.open_hand_techniques.find(item => item === event.target.value); onTechniqueChange(next ?? ''); }}>
      <option value="">Yok</option>
      {value.open_hand_techniques.map(item => <option key={item} value={item}>{item === 'push' ? 'Push' : 'Topple'}</option>)}
    </select></label>}
    {value.deflect_mode && <label>Deflect Attacks <select aria-label="Deflect Attacks" data-testid="monk-deflect" value={value.deflect_mode} disabled={blocked}
      onChange={event => {
        const next = (Object.keys(DEFLECT_LABELS) as DeflectMode[]).find(mode => mode === event.target.value);
        if (next && next !== value.deflect_mode && !blocked) onCommand('Deflect Attacks ayarını değiştiriyorum.', { kind: 'set_deflect_attacks', deflect_mode: next });
      }}>{(Object.keys(DEFLECT_LABELS) as DeflectMode[]).map(mode => <option key={mode} value={mode}>{DEFLECT_LABELS[mode]}</option>)}</select></label>}
    {value.deflect_mode && <p>Deflect Attacks sorulmadan, ayara göre ilk uygun isabette Reaction harcar; Ready varken kullanılmaz.</p>}
    {value.stunning_strike && <p>Stunning Strike zardan önce seçilir; ıskada Focus harcanmaz.</p>}
    {reasons(value).map(reason => <p key={reason} role="status">Kullanılamıyor: {reason}</p>)}
  </div>;
}
