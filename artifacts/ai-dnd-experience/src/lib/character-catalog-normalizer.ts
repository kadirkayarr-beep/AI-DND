type CatalogRecord = Record<string, any>;

export type NormalizedSpellOption = CatalogRecord & { id: string };

export type NormalizedCharacterCreationCatalog = CatalogRecord & {
  backgrounds: Record<string, CatalogRecord & {
    ability_bonuses_options: string[];
    origin_feat?: string;
  }>;
  spells_catalog: Record<string, CatalogRecord & {
    cantrips: NormalizedSpellOption[];
    level_1: NormalizedSpellOption[];
  }>;
};

function asRecord(value: unknown): CatalogRecord {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as CatalogRecord
    : {};
}

function nonEmptyString(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value : undefined;
}

function stringArray(value: unknown): string[] | undefined {
  return Array.isArray(value) && value.every((item) => typeof item === 'string')
    ? value
    : undefined;
}

function normalizeSpellOptions(value: unknown): NormalizedSpellOption[] {
  if (!Array.isArray(value)) return [];

  return value.flatMap((item) => {
    const spell = asRecord(item);
    const id = nonEmptyString(spell.id) ?? nonEmptyString(spell.name);
    return id ? [{ ...spell, id }] : [];
  });
}

export function normalizeCharacterCreationCatalog(
  value: unknown,
): NormalizedCharacterCreationCatalog {
  const raw = asRecord(value);
  const backgrounds = Object.fromEntries(
    Object.entries(asRecord(raw.backgrounds)).map(([key, value]) => {
      const background = asRecord(value);
      const allowedAbilities =
        stringArray(background.ability_bonuses_options) ??
        stringArray(background.abilities) ??
        [];
      const originFeat =
        nonEmptyString(background.origin_feat) ??
        nonEmptyString(background.feat);

      return [
        key,
        {
          ...background,
          ability_bonuses_options: allowedAbilities,
          ...(originFeat ? { origin_feat: originFeat } : {}),
        },
      ];
    }),
  );

  const spellsCatalog = Object.fromEntries(
    Object.entries(asRecord(raw.spells_catalog)).map(([className, value]) => {
      const spellLists = asRecord(value);
      const levelOneOptions = Array.isArray(spellLists.level_1)
        ? spellLists.level_1
        : spellLists.spells_level_1;

      return [
        className,
        {
          ...spellLists,
          cantrips: normalizeSpellOptions(spellLists.cantrips),
          level_1: normalizeSpellOptions(levelOneOptions),
        },
      ];
    }),
  );

  return {
    ...raw,
    backgrounds,
    spells_catalog: spellsCatalog,
  } as NormalizedCharacterCreationCatalog;
}

export function getSpellOptionId(option: unknown): string | null {
  const spell = asRecord(option);
  return nonEmptyString(spell.id) ?? nonEmptyString(spell.name) ?? null;
}

export function updateLimitedSelection(
  selected: string[],
  optionId: string,
  checked: boolean,
  limit: number,
): string[] {
  if (!checked) return selected.filter((id) => id !== optionId);
  if (selected.includes(optionId) || selected.length >= limit) return selected;
  return [...selected, optionId];
}

export function getRequiredSkillCount(skillCount: unknown, species: string): number {
  const baseCount =
    typeof skillCount === 'number' && Number.isFinite(skillCount)
      ? Math.max(0, Math.floor(skillCount))
      : 2;
  return baseCount + (species === 'Human' ? 1 : 0);
}

export function getClassSkillOptions(
  classOptions: unknown,
  skillsCatalog: unknown,
  species: string,
): string[] {
  const options = Array.isArray(classOptions)
    ? classOptions.filter((skill): skill is string => typeof skill === 'string')
    : [];

  if (species !== 'Human') return [...new Set(options)];

  return [...new Set([...options, ...Object.keys(asRecord(skillsCatalog))])];
}