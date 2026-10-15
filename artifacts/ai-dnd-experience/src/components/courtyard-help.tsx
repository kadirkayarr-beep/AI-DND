import type { GameState } from '@workspace/api-client-react';

// Existing optional server projection; absence must not invent an encounter.
type CourtyardState = GameState & { bounded_encounter?: {
  scenario_id: string; location_id: string;
  visible_opponent: { npc_id: string; distance_ft: number } | null;
} | null };

export function CourtyardHelp({ state, disabled, onDraft }: {
  state: CourtyardState; disabled: boolean; onDraft: (message: string) => void;
}) {
  const encounter = state.bounded_encounter;
  const visible = encounter?.visible_opponent;
  const npc = state.npcs.find((item) => item.id === visible?.npc_id);
  if (encounter?.scenario_id !== 'open_courtyard_commoner_v1'
    || encounter.location_id !== state.location || !visible
    || !Number.isFinite(visible.distance_ft) || visible.distance_ft < 0
    || !npc || npc.location !== state.location || !npc.name.trim()
    || npc.current_hp === null || npc.current_hp <= 0 || npc.combat_status !== 'active'
    || state.combat.active || state.character.current_hp <= 0
    || state.pending_event_decisions?.length) return null;

  return <details className="data-row mb-3" data-testid="courtyard-help">
    <summary className="cursor-pointer">Avlu karşılaşması seçenekleri</summary>
    <p>{npc.name} · {visible.distance_ft} feet uzakta</p>
    <p id="courtyard-draft-help">Seçim metin kutusuna aktarılır. Düzenleyebilir, Gönder ile uygulayabilirsin.</p>
    <button type="button" className="action-suggestion" disabled={disabled}
      aria-describedby="courtyard-draft-help" data-testid="button-courtyard-draft"
      onClick={() => onDraft('Avlu çatışmasını başlat')}>
      Çatışmayı başlatmayı seç
    </button>
  </details>;
}
