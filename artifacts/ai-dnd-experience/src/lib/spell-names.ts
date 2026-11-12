import { DEFAULT_CATALOG } from './character-catalog-defaults';

/** A spell's Turkish catalog name for display; the English id is never changed and stays what the engine receives. */
function turkishName(catalog: unknown, id: string): string | undefined {
  const sections = catalog && typeof catalog === 'object' ? (catalog as { spells_catalog?: unknown }).spells_catalog : undefined;
  if (!sections || typeof sections !== 'object') return undefined;
  for (const section of Object.values(sections as Record<string, unknown>)) {
    if (!section || typeof section !== 'object') continue;
    for (const list of Object.values(section as Record<string, unknown>)) {
      if (!Array.isArray(list)) continue;
      for (const item of list) {
        if (!item || typeof item !== 'object') continue;
        const { id: itemId, name, name_tr: tr } = item as { id?: unknown; name?: unknown; name_tr?: unknown };
        if ((itemId === id || name === id) && typeof tr === 'string' && tr.trim()) return tr.trim();
      }
    }
  }
  return undefined;
}

/**
 * D-043: Turkish name with the English id beside it when a catalog has one ("Kutsama (Bless)"); otherwise the English id.
 * The server catalog wins over the built-in defaults.
 */
export function spellLabel(id: string, catalog?: unknown): string {
  const tr = turkishName(catalog, id) ?? turkishName(DEFAULT_CATALOG, id);
  if (!tr || tr === id) return id;
  return tr.includes(`(${id})`) ? tr : `${tr} (${id})`;
}
