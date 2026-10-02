type RecordValue = Record<string, any>;

export type EquipmentRules = {
  armor_class: Record<string, {
    base_ac: number;
    dexterity_mode: 'none' | 'full' | 'capped';
    max_dexterity_bonus?: number;
  }>;
  armor_name_aliases: Record<string, string>;
  shield_item_tokens: string[];
};

export const DEFAULT_EQUIPMENT_RULES: EquipmentRules = {
  armor_class: {
    'Chain Mail': { base_ac: 16, dexterity_mode: 'none' },
    'Scale Mail': {
      base_ac: 14,
      dexterity_mode: 'capped',
      max_dexterity_bonus: 2,
    },
    'Leather Armor': { base_ac: 11, dexterity_mode: 'full' },
  },
  armor_name_aliases: {
    'Zincir Zırh': 'Chain Mail',
    'Chain Mail': 'Chain Mail',
    'Pul Zırh': 'Scale Mail',
    'Scale Mail': 'Scale Mail',
    'Deri Zırh': 'Leather Armor',
    'Leather Armor': 'Leather Armor',
  },
  shield_item_tokens: ['kalkan', 'shield'],
};

function asRecord(value: unknown): RecordValue {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as RecordValue
    : {};
}

function asStringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string')
    : [];
}

function modifier(score: unknown): number {
  const value = typeof score === 'number' && Number.isFinite(score) ? score : 10;
  return Math.floor((value - 10) / 2);
}

function canonicalFeatName(feat: unknown): string | null {
  if (typeof feat !== 'string' || !feat.trim()) return null;
  return feat.split('(', 1)[0].trim();
}

export function calculateCharacterPreviewStats(input: {
  characterClass: string;
  classData?: unknown;
  speciesData?: unknown;
  backgroundData?: unknown;
  abilityScores: Record<string, number>;
  equipmentPackage?: string;
  backgroundEquipmentOption?: string;
  fightingStyle?: string;
  speciesBonusFeat?: string;
  originFeats?: unknown;
  equipmentRules?: unknown;
}): { hp: number; ac: number; hasShield: boolean; equippedArmor: string | null } {
  const classData = asRecord(input.classData);
  const speciesData = asRecord(input.speciesData);
  const backgroundData = asRecord(input.backgroundData);
  const packages = Array.isArray(classData.equipment_packages)
    ? classData.equipment_packages
    : [];
  const selectedPackage = asRecord(
    packages.find((item: unknown) => asRecord(item).id === input.equipmentPackage),
  );
  const classItems = asStringList(selectedPackage.items);
  const backgroundItems =
    input.backgroundEquipmentOption === 'A'
      ? asStringList(backgroundData.equipment)
      : [];
  const equipmentText = [...classItems, ...backgroundItems].join(' ').toLowerCase();

  const suppliedRules = asRecord(input.equipmentRules);
  const suppliedArmorRules = asRecord(suppliedRules.armor_class);
  const suppliedAliases = asRecord(suppliedRules.armor_name_aliases);
  const armorRules =
    Object.keys(suppliedArmorRules).length > 0
      ? suppliedArmorRules
      : DEFAULT_EQUIPMENT_RULES.armor_class;
  const armorAliases =
    Object.keys(suppliedAliases).length > 0
      ? suppliedAliases
      : DEFAULT_EQUIPMENT_RULES.armor_name_aliases;
  const shieldTokens =
    asStringList(suppliedRules.shield_item_tokens).length > 0
      ? asStringList(suppliedRules.shield_item_tokens)
      : DEFAULT_EQUIPMENT_RULES.shield_item_tokens;

  const matchedArmorAlias = Object.keys(armorAliases).find((alias) =>
    equipmentText.includes(alias.toLowerCase()),
  );
  const equippedArmor = matchedArmorAlias
    ? String(armorAliases[matchedArmorAlias])
    : null;
  const armorRule = asRecord(equippedArmor ? armorRules[equippedArmor] : undefined);
  const armorWorn = Object.keys(armorRule).length > 0;

  const dexterityModifier = modifier(input.abilityScores.dexterity);
  const constitutionModifier = modifier(input.abilityScores.constitution);
  const wisdomModifier = modifier(input.abilityScores.wisdom);

  let ac = 10 + dexterityModifier;
  if (armorWorn) {
    ac = Number(armorRule.base_ac);
    if (armorRule.dexterity_mode === 'full') {
      ac += dexterityModifier;
    } else if (armorRule.dexterity_mode === 'capped') {
      ac += Math.min(
        Number(armorRule.max_dexterity_bonus),
        dexterityModifier,
      );
    }
  } else if (input.characterClass === 'Barbarian') {
    ac = 10 + dexterityModifier + constitutionModifier;
  } else if (input.characterClass === 'Monk') {
    ac = 10 + dexterityModifier + wisdomModifier;
  }

  const hasShield = shieldTokens.some((token) =>
    equipmentText.includes(token.toLowerCase()),
  );
  if (hasShield) ac += 2;
  if (input.fightingStyle === 'Defense' && armorWorn) ac += 1;

  const featCatalog = asRecord(input.originFeats);
  const featNames = new Set(
    [backgroundData.origin_feat, input.speciesBonusFeat]
      .map(canonicalFeatName)
      .filter((feat): feat is string => Boolean(feat)),
  );
  const featHpBonus = [...featNames].reduce(
    (total, feat) => total + Number(asRecord(featCatalog[feat]).hp_bonus ?? 0),
    0,
  );
  const hitDie =
    typeof classData.hit_die === 'number' && Number.isFinite(classData.hit_die)
      ? classData.hit_die
      : 10;
  const speciesHpBonus = Number(speciesData.hp_bonus ?? 0);
  const hp = Math.max(
    1,
    hitDie + constitutionModifier + speciesHpBonus + featHpBonus,
  );

  return { hp, ac, hasShield, equippedArmor };
}