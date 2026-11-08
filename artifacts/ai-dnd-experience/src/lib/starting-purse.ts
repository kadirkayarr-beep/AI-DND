// The starting purse as the creation catalog names it. The client never reads coin out of item text:
// the server's catalog gives each class package and each background its coin (coin_gp, coin_items),
// and option B's gold (equipment_rules.background_option_b_gp).

type CatalogRecord = Record<string, unknown>;

const asRecord = (value: unknown): CatalogRecord =>
  value && typeof value === 'object' && !Array.isArray(value) ? value as CatalogRecord : {};
const gold = (value: unknown): number | null =>
  typeof value === 'number' && Number.isInteger(value) && value >= 0 ? value : null;

export type StartingPurse = { classGp: number; backgroundGp: number; totalGp: number };

/** Class package gold plus background gold (option A: the background's coin; B: the catalog's option B gold). Missing field: null. */
export function startingPurse(catalog: unknown, characterClass: string, packageId: string | undefined,
  background: string | undefined, backgroundOption: string | undefined): StartingPurse | null {
  const root = asRecord(catalog);
  const packages = asRecord(asRecord(root.classes)[characterClass]).equipment_packages;
  const pack = Array.isArray(packages) ? packages.find((item) => asRecord(item).id === packageId) : undefined;
  const classGp = gold(asRecord(pack).coin_gp);
  const backgroundGp = backgroundOption === 'A' && background
    ? gold(asRecord(asRecord(root.backgrounds)[background]).coin_gp)
    : backgroundOption === 'B' ? gold(asRecord(root.equipment_rules).background_option_b_gp) : null;
  if (classGp === null || backgroundGp === null) return null;
  return { classGp, backgroundGp, totalGp: classGp + backgroundGp };
}

/** A package's items without its coin items (the coin is the purse line). A catalog without coin_items keeps its list. */
export function packageGoods(pack: unknown): string[] {
  const { items, coin_items: coinItems } = asRecord(pack);
  const list = Array.isArray(items) ? items.filter((item): item is string => typeof item === 'string') : [];
  return Array.isArray(coinItems) ? list.filter((item) => !coinItems.includes(item)) : list;
}
