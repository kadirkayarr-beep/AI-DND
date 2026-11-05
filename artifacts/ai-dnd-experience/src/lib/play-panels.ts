export function showsCounter(
  state: { combat?: { active?: boolean } | null },
  campaignId: string,
): boolean {
  return Boolean(campaignId) && !state.combat?.active;
}
