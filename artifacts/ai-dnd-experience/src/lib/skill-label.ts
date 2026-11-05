import { catalogDisplayName } from './catalog-display';
import { DEFAULT_CATALOG } from './character-catalog-defaults';

/** Presentation only; the request continues to carry the original skill id. */
export function skillLabel(id: string): string {
  return catalogDisplayName(DEFAULT_CATALOG.skills, id) || id;
}
