import { classLabel } from './campaign-presentation';

/** Catalog display names never alter the identifier sent to the engine. */
export function catalogDisplayName(section: unknown, id: string): string | undefined {
  if (!section || typeof section !== 'object') return undefined;
  const item = Array.isArray(section)
    ? section.find(value => value?.id === id)
    : (section as Record<string, unknown>)[id];
  if (!item || typeof item !== 'object') return undefined;
  const name = (item as { name_tr?: unknown }).name_tr;
  return typeof name === 'string' && name.trim() ? name : undefined;
}

/** Some origin feats encode their class choice in the identifier; it remains unchanged in requests. */
export function originFeatLabel(section: unknown, id: string): string {
  const direct = catalogDisplayName(section, id);
  if (direct) return direct;
  const start = id.lastIndexOf(' (');
  if (start > 0 && id.endsWith(')')) {
    const base = catalogDisplayName(section, id.slice(0, start));
    if (base) return `${base} (${classLabel(id.slice(start + 2, -1))})`;
  }
  return id;
}

/** A stored subclass is shown only through the matching class's current catalog. */
export function subclassCatalogName(catalog: unknown, characterClass: string, subclassId?: string | null): string | undefined {
  if (!catalog || typeof catalog !== 'object' || Array.isArray(catalog) || !subclassId) return undefined;
  const section = (catalog as Record<string, { level_3?: { subclass_options?: unknown } } | undefined>)[`${characterClass.trim().toLowerCase()}_starting_creation`];
  const options = section?.level_3?.subclass_options;
  if (!Array.isArray(options)) return undefined;
  const matches = options.filter(option => option && typeof option === 'object' && !Array.isArray(option) && option.id === subclassId);
  if (matches.length !== 1) return undefined;
  const name: unknown = matches[0].name;
  return typeof name === 'string' && name.trim() ? name.trim() : undefined;
}
