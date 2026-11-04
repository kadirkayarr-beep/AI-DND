/** A copper total in the counter's words: "{gp} altın {sp} gümüş {cp} bakır". Not a whole, non-negative number: "—". */
export function coinText(totalCp: number): string {
  if (!Number.isInteger(totalCp) || totalCp < 0) return '—';
  return `${Math.floor(totalCp / 100)} altın ${Math.floor(totalCp % 100 / 10)} gümüş ${totalCp % 10} bakır`;
}
