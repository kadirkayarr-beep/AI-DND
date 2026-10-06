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

export function getContextualActionSuggestions(
  state: GameState,
): ContextualActionSuggestion[] {
  const suggestions: ContextualActionSuggestion[] = [
    {
      id: 'observe',
      label: 'Çevreyi gözlemle',
      message: 'Çevreyi gözlemliyorum.',
      mode: 'do',
    },
  ];
  const sceneNpcs = (state.scene?.npcs ?? []).filter(
    (npc) => typeof npc.name === 'string' && npc.name.trim().length > 0,
  );

  if (state.combat.active) {
    const hasSword = state.inventory.some((item) =>
      item.toLocaleLowerCase('tr-TR').includes('kılıç'),
    );
    if (state.combat.current_actor_id === 'player' && hasSword) {
      const activeTargets = state.combat.participant_records.filter(
        (participant) => participant.kind === 'npc'
          && participant.status === 'active'
          && participant.current_hp > 0,
      );
      for (const target of activeTargets.slice(0, 2)) {
        suggestions.push({
          id: `attack-${target.id}`,
          label: `Saldır: ${target.name}`,
          message: `${target.name} adlı hedefe kılıcımla saldırıyorum.`,
          mode: 'do',
          targetId: target.id,
        });
      }
    }
  } else if (sceneNpcs.length > 0) {
    for (const npc of sceneNpcs.slice(0, 2)) {
      suggestions.push({
        id: `talk-${npc.id}`,
        label: `${npc.name} ile konuş`,
        message: `${npc.name} ile konuşmak istiyorum.`,
        mode: 'say',
        targetId: npc.id,
      });
    }
  } else {
    suggestions.push({
      id: 'presence',
      label: 'Yakında kimler var?',
      message: 'Burada kimler var?',
      mode: 'ask_dm',
    });
  }

  if (state.inventory.length > 0) {
    suggestions.push({
      id: 'inventory',
      label: 'Envanterimi gözden geçir',
      message: 'Envanterimde neler var?',
      mode: 'ask_dm',
    });
  }

  return suggestions.slice(0, 4);
}
