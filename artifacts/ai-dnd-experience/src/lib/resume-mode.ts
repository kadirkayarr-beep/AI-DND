import type { InteractionMode } from '@/lib/action-suggestions';

/**
 * The composer's move type when a saved game is resumed: an open conversation (the engine's own projection, closed
 * in combat) keeps "Söyle" with that person; anything else starts as "Yap". No local preference is remembered.
 */
export function resumeComposerMode(state: {
  conversation?: { active?: boolean; interlocutor?: { id?: string | null } | null } | null;
}): { mode: InteractionMode; targetId: string } {
  const conversation = state?.conversation;
  const targetId = conversation?.interlocutor?.id;
  if (conversation?.active === true && typeof targetId === 'string' && targetId.trim()) return { mode: 'say', targetId };
  return { mode: 'do', targetId: '' };
}
