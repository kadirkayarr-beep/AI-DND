import type { GameState } from '@workspace/api-client-react';

export type ContextualActionSuggestion = {
  id: string;
  label: string;
  message: string;
};

export function getContextualActionSuggestions(
  state: GameState,
): ContextualActionSuggestion[] {
  const suggestions: ContextualActionSuggestion[] = [
    {
      id: 'observe',
      label: 'Çevreyi gözlemle',
      message: 'Çevreyi gözlemliyorum.',
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
        });
      }
    }
  } else if (sceneNpcs.length > 0) {
    for (const npc of sceneNpcs.slice(0, 2)) {
      suggestions.push({
        id: `talk-${npc.id}`,
        label: `${npc.name} ile konuş`,
        message: `${npc.name} ile konuşmak istiyorum.`,
      });
    }
  } else {
    suggestions.push({
      id: 'presence',
      label: 'Yakında kimler var?',
      message: 'Burada kimler var?',
    });
  }

  if (state.inventory.length > 0) {
    suggestions.push({
      id: 'inventory',
      label: 'Envanterimi gözden geçir',
      message: 'Envanterimde neler var?',
    });
  }

  return suggestions.slice(0, 4);
}