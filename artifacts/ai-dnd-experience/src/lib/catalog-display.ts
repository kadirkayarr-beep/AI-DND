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
