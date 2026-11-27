const HAND_SUFFIXES = { main: ' (ana el)', off: ' (ikinci el)' } as const;

/** The hand public_inventory put on an equipped label, if any. */
export function inventoryHand(label: string): 'main' | 'off' | null {
  return label.endsWith(HAND_SUFFIXES.main) ? 'main' : label.endsWith(HAND_SUFFIXES.off) ? 'off' : null;
}

/** Decode only public_inventory's terminal item identity, never the item itself. */
export function inventoryDisplay(label: string): { name: string; equipped: boolean } {
  const suffix = ' (kuşanılmış)';
  const hand = inventoryHand(label);
  const bare = hand ? label.slice(0, -HAND_SUFFIXES[hand].length) : label;
  const equipped = bare.endsWith(suffix);
  const text = equipped ? bare.slice(0, -suffix.length) : bare;
  const start = text.lastIndexOf(' [');
  if (start < 1 || !text.endsWith(']')) return { name: label, equipped: false };
  const id = text.slice(start + 2, -1);
  if (!(id.startsWith('item_') && id.length > 5 && !id.includes('[') && !id.includes(']') && !id.includes(' ')) && id !== 'kimlik doğrulanmamış') {
    return { name: label, equipped: false };
  }
  return { name: text.slice(0, start), equipped };
}
