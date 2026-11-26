import type { CSSProperties } from 'react';
import { classLabel } from '@/lib/campaign-presentation';

export type AbilityKey = 'strength' | 'dexterity' | 'constitution' | 'intelligence' | 'wisdom' | 'charisma';

export const ABILITY_NAMES_TR: Record<AbilityKey, { short: string; full: string }> = {
  strength: { short: 'KUV', full: 'Kuvvet' },
  dexterity: { short: 'ÇEV', full: 'Çeviklik' },
  constitution: { short: 'DAY', full: 'Dayanıklılık' },
  intelligence: { short: 'ZEK', full: 'Zekâ' },
  wisdom: { short: 'BİL', full: 'Bilgelik' },
  charisma: { short: 'KAR', full: 'Karizma' },
};

export function presentedClassName(classKey: string, nameTr?: string) {
  const shared = classLabel(classKey);
  if (shared !== classKey) return shared;
  return nameTr?.trim() || classKey;
}

export function namedCatalogLabel(catalogSection: unknown, id: string): string {
  if (!catalogSection || typeof catalogSection !== 'object') return id;
  const entry = (catalogSection as Record<string, { name_tr?: unknown }>)[id];
  return typeof entry?.name_tr === 'string' && entry.name_tr.trim() ? entry.name_tr : id;
}

export const CLASS_PORTRAIT_CELLS: Record<string, number> = {
  fighter: 0, barbarian: 1, paladin: 2, ranger: 3,
  rogue: 4, monk: 5, bard: 6, cleric: 7,
  druid: 8, sorcerer: 9, wizard: 10, warlock: 11,
};

export const SPECIES_PORTRAIT_CELLS: Record<string, number> = {
  human: 0, elf: 1, dwarf: 2, halfling: 3,
  dragonborn: 4, gnome: 5, 'half-orc': 6, tiefling: 7,
  goliath: 8, aasimar: 9, 'wood elf': 10, orc: 11,
};

export function portraitStyle(sheet: string, cell: number | undefined): CSSProperties | undefined {
  if (cell === undefined) return undefined;
  const column = cell % 4;
  const row = Math.floor(cell / 4);
  return {
    backgroundImage: `url("${sheet}")`,
    backgroundPosition: `${column * 100 / 3}% ${row * 50}%`,
  };
}

export function speciesTraitDetails(
  trait: unknown,
): { name: string; description: string | null } | null {
  if (typeof trait === 'string') {
    return trait.trim() ? { name: trait, description: null } : null;
  }
  if (!trait || typeof trait !== 'object') return null;

  const record = trait as { name?: unknown; name_tr?: unknown; desc?: unknown };
  if (typeof record.name !== 'string' || !record.name.trim()) return null;
  return {
    name: typeof record.name_tr === 'string' && record.name_tr.trim() ? record.name_tr : record.name,
    description:
      typeof record.desc === 'string' && record.desc.trim()
        ? record.desc
        : null,
  };
}
