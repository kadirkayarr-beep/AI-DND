// Record the view boundary used by production submit/recovery closures.
export function combatStartInjection() {
  const combatStartNotices = [];
  return { combatStartNotices, setCombatStartNotice: value => combatStartNotices.push(value) };
}
