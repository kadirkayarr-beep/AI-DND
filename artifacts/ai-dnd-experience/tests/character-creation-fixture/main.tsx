import { createRoot } from "react-dom/client";
import type { CampaignStartOptionsResponse, CharacterCreationOptions } from "@workspace/api-client-react";
import { CharacterCreationScreen } from "@/components/character-creation-screen";
import { DEFAULT_CATALOG } from "@/lib/character-catalog-defaults";
import "@/index.css";
import "@/components/unwritten-play.css";

const options: CharacterCreationOptions = {
  races: Object.keys(DEFAULT_CATALOG.races),
  classes: Object.keys(DEFAULT_CATALOG.classes),
};
const startOptions: CampaignStartOptionsResponse = {
  settings: [{
    setting_id: "forgotten-realms",
    name: "Forgotten Realms",
    regions: [{
      region_pack_id: "sword-coast-pack",
      region_id: "sword-coast",
      name: "Kılıç Sahili",
      epoch_id: "current",
      coverage_status: "supported",
      starting_locations: [{ entity_id: "waterdeep", name: "Waterdeep" }],
    }],
  }],
};
type FixtureWindow = Window & {
  __creationFixture: {
    created: { character: unknown; campaignStart: unknown; deathMode: string } | null;
    backCount: number;
  };
};
const fixture = (window as FixtureWindow).__creationFixture = { created: null, backCount: 0 };

createRoot(document.getElementById("root")!).render(
  <CharacterCreationScreen
    options={options}
    catalog={DEFAULT_CATALOG}
    startOptions={startOptions}
    loadingOptions={false}
    loadingStartOptions={false}
    optionsError={null}
    startOptionsError={null}
    creating={false}
    notice={null}
    onBack={() => { fixture.backCount += 1; }}
    onCreate={(character, campaignStart, deathMode) => {
      fixture.created = { character, campaignStart, deathMode };
    }}
    onRetryOptions={() => {}}
    onRetryStartOptions={() => {}}
  />,
);
