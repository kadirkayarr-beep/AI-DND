import type { GameState } from '@workspace/api-client-react';
import type { InteractionMode } from '@/lib/action-suggestions';
import { readPrimalKnowledgeProjection, primalKnowledgeAvailable } from '@/lib/primal-knowledge';
export { createPrimalKnowledgeIntent, readPrimalKnowledgeProjection, primalKnowledgeAvailable } from '@/lib/primal-knowledge';

export function PrimalKnowledgeControl({ state, mode, targetId, checked, blocked, onChange }: {
  state: GameState; mode: InteractionMode; targetId: string | null; checked: boolean; blocked: boolean; onChange: (checked: boolean) => void;
}) {
  const projection = readPrimalKnowledgeProjection(state.character.primal_knowledge_check);
  if (!projection) return null;
  const available = primalKnowledgeAvailable(state, { interaction_mode: mode, target_id: targetId });
  const reason = state.combat.active ? 'Çatışmada bu kontrol yolu henüz desteklenmiyor.'
    : mode !== 'do' ? 'Yalnız Yap hamlesinde seçilebilir.'
      : targetId ? 'Hedefli hamleler bu kontrol yolunda desteklenmiyor; hedefin korunur.'
        : projection.reason === 'primal_knowledge_rage_required' ? 'Etkin Rage gerekiyor.'
          : !projection.available ? 'Sunucu bu seçimi şu anda kullanıma açmıyor.' : null;
  return <div className="story-meta" style={{ flex: '0 0 100%', minWidth: 0 }} data-testid="primal-knowledge-control">
    <label><input type="checkbox" data-testid="primal-knowledge-confirm" checked={available && checked} disabled={blocked || !available}
      aria-describedby="primal-knowledge-help" onChange={event => { if (!blocked && available) onChange(event.target.checked); }} />{' '}
      Bu hamlede Kuvvet kullan (Primal Knowledge)
    </label>
    <p id="primal-knowledge-help">{projection.skills.join(' · ')}. Yalnız anlık, hedefsiz beceri kontrolü; zaman alan arama, iz sürme ve görevler desteklenmez. Beceriyi ve zorluğu sunucu belirler; her söz bir kontrol başlatmaz. Seçim yalnız bu hamle içindir.</p>
    {reason && <p role="status" data-testid="primal-knowledge-unavailable">{reason}</p>}
  </div>;
}
