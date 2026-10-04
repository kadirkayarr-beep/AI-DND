import type { GameState, CampaignStartOptionsResponse } from '@workspace/api-client-react';

const CLASS_LABELS: Record<string, string> = {
  Barbarian: 'Barbar', Bard: 'Ozan', Cleric: 'Rahip', Druid: 'Druid', Fighter: 'Savaşçı',
  Monk: 'Keşiş', Paladin: 'Paladin', Ranger: 'Kolcu', Rogue: 'Düzenbaz',
  Sorcerer: 'Büyücü', Warlock: 'Efsuncu', Wizard: 'Sihirbaz',
};
const SPECIES_LABELS: Record<string, string> = {
  Human: 'İnsan', Elf: 'Elf', Dwarf: 'Cüce', Halfling: 'Buçukluk', Gnome: 'Gnom',
  Orc: 'Ork', Dragonborn: 'Ejderdoğan', Tiefling: 'Tiefling', Goliath: 'Goliath',
  Aasimar: 'Aasimar', 'Half-Elf': 'Yarı Elf', 'Half-Orc': 'Yarı Ork',
};
export const classLabel = (value: string) => CLASS_LABELS[value] ?? value;
export const speciesLabel = (value: string) => SPECIES_LABELS[value] ?? value;

/** Resolve supplied identifiers only through existing canonical catalog names. */
export function campaignLocationLabel(id: string, catalog?: CampaignStartOptionsResponse) {
  for (const setting of catalog?.settings ?? []) {
    for (const region of setting.regions) {
      const location = region.starting_locations.find((location) => location.entity_id === id);
      if (location) return location.name;
    }
  }
  return 'Konum ayrıntıları macera açıldığında görünür.';
}

/** Format only the authoritative calendar. No browser clock or fallback era. */
export function campaignDateLabel(time: GameState['campaign_time']) {
  if (!time) return null;
  return `${time.day} ${time.month} ${time.year} DR · ${String(time.hour).padStart(2, '0')}:${String(time.minute).padStart(2, '0')}`;
}

/** Scene membership is supplied, never inferred from prose or visual styling. */
export function currentSceneContext(state: GameState) {
  const scene = state.scene?.location_id === state.location ? state.scene : null;
  return {
    location: state.locations[state.location],
    scene,
    people: scene?.npcs ?? state.npcs.filter((person) => person.location === state.location),
    features: scene?.features ?? state.features.filter((feature) => feature.location === state.location),
    doors: state.doors.filter((door) => door.location === state.location),
  };
}

export function playerAbilityMessage(message: string) {
  return /\b(?:Python|backend|server|engine|model|Qwen|API|receipt|rollback|RNG)\b|sunucu|motor|kanonik/i.test(message)
    ? 'Yeteneğin değerlendirildi.'
    : message;
}