export function runningQuestCount(state: {
  quests?: { status: string }[];
  campaign_adventures?: { active?: unknown[] } | null;
}): number {
  return (state.quests ?? []).filter((quest) => (
    quest.status === 'accepted' || quest.status === 'active'
  )).length + (state.campaign_adventures?.active?.length ?? 0);
}
