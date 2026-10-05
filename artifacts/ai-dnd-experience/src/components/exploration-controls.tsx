import { Compass, DoorOpen, Footprints, MapPinned, Sparkles, TriangleAlert } from 'lucide-react';
import type { GameState } from '@workspace/api-client-react';

const PACES = [
  { id: 'slow', label: 'Temkinli' },
  { id: 'normal', label: 'Normal' },
  { id: 'fast', label: 'Hızlı' },
] as const;

const WEATHER: Record<string, string> = { clear: 'Açık', rain: 'Yağmurlu', fog: 'Sisli', snow: 'Karlı', storm: 'Fırtınalı', unknown: 'Belirsiz' };
const EXIT: Record<string, string> = { open: 'açık', closed: 'kapalı', locked: 'kilitli', blocked: 'tıkalı' };
const OBSTACLE: Record<string, string> = { active: 'etkin', detected: 'fark edildi', disarmed: 'etkisizleştirildi', bypassed: 'aşıldı', triggered: 'tetiklendi', neutralized: 'etkisiz' };

function formatDuration(seconds: number | null) {
  if (seconds === null || !Number.isFinite(seconds)) return 'süre bilinmiyor';
  const total = Math.max(0, Math.round(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  if (h && m) return `${h} sa ${m} dk`;
  if (h) return `${h} sa`;
  return `${Math.max(m, total ? 1 : 0)} dk`;
}

function formatMiles(miles: number) {
  return `${new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 1 }).format(miles)} mil`;
}

export function ExplorationControls({ state, disabled, onCommand }: { state: GameState; disabled: boolean; onCommand: (message: string) => void }) {
  const exploration = state.exploration;

  if (!exploration) {
    return (
      <section className="state-panel" data-testid="panel-exploration-optin" aria-labelledby="exploration-optin-title">
        <div className="dnd-kicker"><Compass size={12} className="mr-1 inline" /> Yeni bir olasılık</div>
        <h2 id="exploration-optin-title">Taş Patika Macerası</h2>
        <p className="subtle-text mt-3">İstersen yeni bir keşif macerasına çıkabilirsin. Bu, şimdiye dek yaşadıklarının bir parçası değil; yalnızca önünde duran bir yol.</p>
        <div className="action-suggestion-list mt-3">
          <button type="button" className="action-suggestion" disabled={disabled} onClick={() => onCommand('/explore begin')} data-testid="button-explore-begin">Taş Patika Macerası</button>
        </div>
      </section>
    );
  }

  const journeyActive = Boolean(state.journey);
  const effectivePace = state.journey?.pace ?? exploration.pace;
  const paceLabel = PACES.find((p) => p.id === effectivePace)?.label ?? effectivePace;

  return (
    <section className="state-panel" data-testid="panel-exploration" aria-labelledby="exploration-title">
      <div className="dnd-kicker"><Compass size={12} className="mr-1 inline" /> Keşif</div>
      <h2 id="exploration-title">Yol ve çevre</h2>
      <div className="data-row mt-3">
        <div className="data-row-head"><span>Hava</span><span className="status-pill" data-testid="text-exploration-weather">{WEATHER[exploration.weather] ?? 'Belirsiz'}</span></div>
        <div className="data-row-head mt-2"><span className="flex items-center gap-2"><Footprints size={14} /> Yürüyüş temposu</span><span className="status-pill" data-testid="text-exploration-pace">{paceLabel}</span></div>
      </div>
      <div className="action-suggestion-list mt-3" role="group" aria-label="Yürüyüş temposu">
        {PACES.map((p) => (
          <button type="button" key={p.id} className="action-suggestion" aria-pressed={exploration.pace === p.id} disabled={disabled || journeyActive} onClick={() => onCommand(`/travel pace ${p.id}`)} data-testid={`button-pace-${p.id}`}>{p.label}</button>
        ))}
      </div>
      {journeyActive && <div className="subtle-text mt-2" role="status">Yolculuk sürerken tempo değişmez.</div>}

      <div className="mt-4">
        <div className="dnd-kicker"><MapPinned size={11} className="mr-1 inline" /> Yollar</div>
        {exploration.routes.length ? exploration.routes.map((route) => (
          <div className="data-row mt-2" key={route.id} data-testid={`exploration-route-${route.id}`}>
            <div className="data-row-head"><span>{route.name}</span>{route.blocked && <span className="status-pill">tıkalı</span>}</div>
            <div className="data-row-meta">{formatMiles(route.distance_miles)} · {formatDuration(route.duration_seconds)}</div>
          </div>
        )) : <div className="empty-line mt-2">Görünen bir yol yok.</div>}
      </div>

      <div className="mt-4">
        <div className="dnd-kicker"><DoorOpen size={11} className="mr-1 inline" /> Çıkışlar</div>
        {exploration.exits.length ? exploration.exits.map((exit) => (
          <div className="data-row mt-2" key={exit.id} data-testid={`exploration-exit-${exit.id}`}>
            <div className="data-row-head"><span>{exit.name}</span><span className="status-pill">{EXIT[exit.state] ?? exit.state}</span></div>
          </div>
        )) : <div className="empty-line mt-2">Burada görünen bir çıkış yok.</div>}
      </div>

      {exploration.obstacles.length > 0 && (
        <div className="mt-4">
          <div className="dnd-kicker"><TriangleAlert size={11} className="mr-1 inline" /> Tehlikeler</div>
          {exploration.obstacles.map((o) => (
            <div className="data-row mt-2" key={o.id} data-testid={`exploration-obstacle-${o.id}`}>
              <div className="data-row-head"><span>{o.name}</span><span className="status-pill">{OBSTACLE[o.state] ?? o.state}</span></div>
            </div>
          ))}
        </div>
      )}

      {exploration.discoveries.length > 0 && (
        <div className="mt-4">
          <div className="dnd-kicker"><Sparkles size={11} className="mr-1 inline" /> Keşifler</div>
          {exploration.discoveries.map((d) => (
            <div className="data-row mt-2" key={d.id} data-testid={`exploration-discovery-${d.id}`}>
              <div className="data-row-head"><span>{d.name}</span></div>
              <div className="data-row-desc">{d.text}</div>
            </div>
          ))}
        </div>
      )}

      {exploration.actions.length > 0 && (
        <div className="action-suggestion-list mt-4" role="group" aria-label="Keşif eylemleri">
          {exploration.actions.map((action, index) => (
            <button type="button" key={`${action.label}-${index}`} className="action-suggestion" disabled={disabled} onClick={() => onCommand(action.message)} data-testid={`button-exploration-action-${index}`}>{action.label}</button>
          ))}
        </div>
      )}
    </section>
  );
}
