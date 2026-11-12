// Plan part L (decision 15): Turkish spell and item names. The table is content/names/tr_names.json, the
// same file the narrator prompt and the player-text parsers read (ai-dnd/tr_names.py). Ids stay English
// everywhere; this only changes what is displayed. A name without an entry is shown as it is.
import table from '../../../../content/names/tr_names.json' with { type: 'json' };

type Kind = 'spells' | 'items';
const names = table as unknown as Record<Kind, Record<string, string>>;
const KINDS: readonly Kind[] = ['spells', 'items'];

export function hasTrName(id: string, kind?: Kind): boolean {
  return (kind ? [kind] : KINDS).some(k => Boolean(names[k][id]));
}

export function trName(id: string, kind?: Kind): string {
  for (const k of kind ? [kind] : KINDS) {
    const found = names[k][id];
    if (found) return found;
  }
  return id;
}

/** `lang` for a displayed name: nothing when it is Turkish, "en" when the original is shown. */
export function nameLang(id: string, kind?: Kind): 'en' | undefined {
  return hasTrName(id, kind) ? undefined : 'en';
}
