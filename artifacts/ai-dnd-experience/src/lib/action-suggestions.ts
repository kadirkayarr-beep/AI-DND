import type { GameState } from '@workspace/api-client-react';

export type InteractionMode = 'say' | 'do' | 'ask_dm';

export type ContextualActionSuggestion = {
  id: string;
  label: string;
  message: string;
  mode: InteractionMode;
  targetId?: string;
};

export function getTurnInteractionMetadata(
  state: Pick<GameState, 'scene' | 'combat'> | undefined,
  mode: InteractionMode,
  conversationTargetId: string,
  combatTargetId: string,
  hasStructuredAction = false,
): { interaction_mode: InteractionMode; target_id: string | null } {
  const effectiveMode = state?.combat.active || hasStructuredAction ? 'do' : mode;
  const presentConversationTarget = state?.scene?.npcs.some(
    (npc) => npc.id === conversationTargetId,
  );
  return {
    interaction_mode: effectiveMode,
    target_id: effectiveMode === 'say'
      ? (presentConversationTarget ? conversationTargetId : null)
      : state?.combat.active ? (combatTargetId || null) : null,
  };
}

const MAX_SUGGESTIONS = 4;

function placesJustNamed(state: GameState, recentText: string) {
  const here = state.location;
  const folded = recentText.toLocaleLowerCase('tr-TR');
  return Object.entries(state.locations ?? {}).filter(([id, place]) => (
    id !== here
    && typeof place?.name === 'string'
    && place.name.trim().length > 0
    && folded.includes(place.name.toLocaleLowerCase('tr-TR'))
  ));
}

/**
 * Ideas built only from what the state already shows, with no model call.
 * A closed door is offered as an attempt, so a lock the player has not tested
 * stays unsaid.
 */
export function getContextualActionSuggestions(
  state: GameState,
  recentText = '',
): ContextualActionSuggestion[] {
  if (state.combat.active) {
    if (state.combat.current_actor_id !== 'player') return [];
    return state.combat.participant_records
      .filter((participant) => participant.kind === 'npc'
        && participant.status === 'active'
        && participant.current_hp > 0)
      .slice(0, MAX_SUGGESTIONS)
      .map((target) => ({
        id: `attack-${target.id}`,
        label: `Saldır: ${target.name}`,
        message: `${target.name} adlı hedefe saldırıyorum.`,
        mode: 'do',
        targetId: target.id,
      }));
  }

  const suggestions: ContextualActionSuggestion[] = [];
  const interlocutor = state.conversation?.active ? state.conversation.interlocutor : null;
  if (interlocutor) {
    suggestions.push({
      id: `ask-${interlocutor.id}`,
      label: `${interlocutor.name}: burayı sor`,
      message: 'Burada neler oluyor?',
      mode: 'say',
      targetId: interlocutor.id,
    });
  }
  for (const [id, place] of placesJustNamed(state, recentText).slice(0, 1)) {
    suggestions.push({
      id: `place-${id}`,
      label: `Git: ${place.name}`,
      message: `${place.name} tarafına gidiyorum.`,
      mode: 'do',
    });
  }
  const doors = (state.doors ?? []).filter((door) => door.location === state.location && !door.open);
  for (const door of doors.slice(0, 1)) {
    suggestions.push({
      id: `door-${door.id}`,
      label: `Dene: ${door.name}`,
      message: doors.length === 1 ? 'Kapıyı açmaya çalışıyorum.' : `${door.name}: açmaya çalışıyorum.`,
      mode: 'do',
    });
  }
  const sceneNpcs = (state.scene?.npcs ?? []).filter(
    (npc) => typeof npc.name === 'string' && npc.name.trim().length > 0 && npc.id !== interlocutor?.id,
  );
  for (const npc of sceneNpcs.slice(0, 2)) {
    suggestions.push({
      id: `talk-${npc.id}`,
      label: `${npc.name} ile konuş`,
      message: `${npc.name} ile konuşmak istiyorum.`,
      mode: 'say',
      targetId: npc.id,
    });
  }
  if (suggestions.length === 0) {
    suggestions.push({
      id: 'presence',
      label: 'Yakında kimler var?',
      message: 'Burada kimler var?',
      mode: 'ask_dm',
    });
  }
  return suggestions.slice(0, MAX_SUGGESTIONS);
}
