/** Decode only public_inventory's terminal item identity, never the item itself. */
export function inventoryDisplay(label: string): { name: string; equipped: boolean } {
  const suffix = ' (kuşanılmış)';
  const equipped = label.endsWith(suffix);
  const text = equipped ? label.slice(0, -suffix.length) : label;
  const start = text.lastIndexOf(' [');
  if (start < 1 || !text.endsWith(']')) return { name: label, equipped: false };
  const id = text.slice(start + 2, -1);
  if (!(id.startsWith('item_') && id.length > 5 && !id.includes('[') && !id.includes(']') && !id.includes(' ')) && id !== 'kimlik doğrulanmamış') {
    return { name: label, equipped: false };
  }
  return { name: text.slice(0, start), equipped };
}
