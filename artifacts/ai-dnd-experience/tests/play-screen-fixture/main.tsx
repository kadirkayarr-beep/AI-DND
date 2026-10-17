/**
 * UI fixture only. Fixed responses stay in this page.
 * This is not a backend, save, or resume proof, and it is not the signed-in app.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createRoot } from "react-dom/client";
import { setAuthTokenGetter } from "@workspace/api-client-react/custom-fetch";
import GameBrowser from "@/pages/game-browser";
import "@/index.css";

const CAMPAIGN_ID = "fixture-campaign";
const SESSION_ID = "fixture-session";

type HistoryEntry = {
  player_message: string;
  narration: string;
  created_at: string;
  skill_check_result?: {
    skill: string;
    ability: string;
    d20: number;
    ability_modifier: number;
    proficiency_modifier: number;
    total_modifier: number;
    total: number;
    dc: number;
    outcome: string;
    difficulty: string;
    proficient: boolean;
  };
};

const skill = {
  skill: "Stealth",
  ability: "dexterity",
  d20: 8,
  ability_modifier: 1,
  proficiency_modifier: 2,
  total_modifier: 3,
  total: 11,
  dc: 15,
  outcome: "failure",
  difficulty: "medium",
  proficient: true,
};

const history: HistoryEntry[] = Array.from({ length: 18 }, (_, index) => ({
  player_message: `Tur ${index + 1}: avluyu ve kilitli kapıyı inceliyorum.`,
  narration: `Tur ${index + 1}. Kapı kilitli. Taş avlu, ıslak eşik ve kapalı han kapısı olduğu gibi duruyor. Bu satır geçmişin uzunluğunu taşır.`,
  created_at: "2026-10-17T08:00:00Z",
  ...(index === 0 ? { skill_check_result: skill } : {}),
}));

const state = () => ({
  campaign_time: {
    year: 1492, month: "Mirtul", day: 12, hour: 18, minute: 40, second: 0,
    day_index: 12, calendar: "Harptos", local_convention: "Faerûn",
    time_of_day: "evening", display: "12 Mirtul 1492 DR", detail: "Akşam",
  },
  known_scheduled_events: [],
  pending_event_decisions: [],
  journey: null,
  location: "courtyard",
  scene: {
    id: "scene-fixture",
    location_id: "courtyard",
    parent_location_id: null,
    kind: "yard",
    visit_revision: 1,
    activity_revision: 1,
    last_activity: null,
    ambient_event: null,
    opening: "Avlu kapısı kapalı.",
    player_position: { location_id: "courtyard", kind: "standing", target_id: null },
    npcs: [{ id: "npc-marek", name: "Marek", role: "Hancı", appearance: "Eşikte bekliyor." }],
    features: [],
    referents: [],
  },
  conversation: { active: false, interlocutor: null },
  world: { environment: "tavern", time_of_day: "evening", weather: "clear" },
  journal: { schema_version: 1, discovered_locations: [], known_npcs: [], notable_events: [], quests: [] },
  locations: {
    courtyard: {
      id: "courtyard",
      name: "Kuzgun Hanı avlusu",
      type: "tavern",
      description: "Islak taş avlu.",
      parent_location_id: null,
      exit_location_id: null,
    },
  },
  character: {
    name: "Riven",
    race: "human",
    class: "rogue",
    strength: 10, dexterity: 14, constitution: 12, intelligence: 11, wisdom: 13, charisma: 10,
    proficient_skills: ["Stealth"],
    expertise_skills: [],
    level: 1,
    proficiency_bonus: 2,
    max_hp: 12,
    current_hp: 12,
    armor_class: 13,
    cantrips: [],
    spells: [],
    spell_slots_remaining: {},
    xp: 0,
  },
  spellcasting: null,
  inventory: ["Kısa kılıç"],
  npcs: [{
    id: "npc-marek", name: "Marek", role: "Hancı", location: "courtyard",
    appearance: "Eşikte bekliyor.", relationship: null,
    max_hp: null, current_hp: null, armor_class: null, combat_status: null,
  }],
  shops: [],
  features: [],
  doors: [],
  combat: {
    active: false,
    status: "ended",
    round: 0,
    initiative_order: [],
    current_turn_index: 0,
    current_actor_id: null,
    turn_owner: null,
    participants: [],
    participant_records: [],
    target_id: null,
    end_reason: null,
  },
  death_state: {
    mode: "NORMAL", status: "active", successes: 0, failures: 0,
    stable: false, dead: false, terminal: false, prone: false,
  },
  player_combat_status: "active",
  turn_index: history.length,
  quests: [],
  quest_offers: [],
  campaign_adventures: { rumors: [], active: [], completed: [], failed: [], timeline: [], affordances: [] },
  known_lore: [],
  known_factions: [],
});

const session = () => ({
  campaign_id: CAMPAIGN_ID,
  session_id: SESSION_ID,
  name: "UI fixture macerası",
  state: state(),
  history,
  combat_history: [],
});

let holdArmed = false;
let releaseHold: (() => void) | null = null;
let failNext = false;

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function pathOf(input: RequestInfo | URL) {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
  return new URL(raw, "http://fixture.local").pathname;
}

window.fetch = async (input, init) => {
  const path = pathOf(input);
  if (!path.startsWith("/api/")) {
    throw new Error(`UI fixture blocked a non-API request: ${path}`);
  }
  if (path === "/api/game/health") return json({ status: "ok" });
  if (path === "/api/game/campaigns" && (!init?.method || init.method === "GET")) {
    return json([{
      campaign_id: CAMPAIGN_ID,
      name: "UI fixture macerası",
      created_at: "2026-10-17T08:00:00Z",
      updated_at: "2026-10-17T08:00:00Z",
      last_played_at: "2026-10-17T08:00:00Z",
      save_version: 1,
      character_name: "Riven",
      character_race: "human",
      character_class: "rogue",
      character_level: 1,
      location: "courtyard",
    }]);
  }
  if (path === `/api/game/campaigns/${CAMPAIGN_ID}/resume` && init?.method === "POST") return json(session());
  if (path === `/api/game/campaigns/${CAMPAIGN_ID}` && (!init?.method || init.method === "GET")) return json(session());
  if (path === `/api/game/sessions/${SESSION_ID}/state`) return json(state());
  if (path === `/api/game/sessions/${SESSION_ID}/turn` && init?.method === "POST") {
    const body = JSON.parse(String(init.body ?? "{}")) as { message?: string; action_id?: string; interaction_mode?: string };
    (window as FixtureWindow).__playFixture.lastTurn = body;
    if (failNext) {
      failNext = false;
      return json({ detail: { code: "ollama_unavailable", message: "Sessiz." } }, 503);
    }
    if (holdArmed) {
      holdArmed = false;
      await new Promise<void>((resolve) => {
        releaseHold = resolve;
      });
    }
    const message = body.message ?? "";
    history.push({
      player_message: message,
      narration: `Yankı: ${message}`,
      created_at: "2026-10-17T08:05:00Z",
    });
    return json({
      session_id: SESSION_ID,
      action_id: body.action_id,
      narration: `Yankı: ${message}`,
      state: state(),
      combat_result: null,
      combat_history_entry: null,
      skill_check_result: null,
      quest_outcomes: [],
      level_up: null,
    });
  }
  return json({ detail: { code: "campaign_error", message: `UI fixture has no response for ${path}` } }, 404);
};

type FixtureWindow = Window & {
  __playFixture: {
    label: "ui-fixture-not-backend";
    lastTurn: { message?: string; action_id?: string; interaction_mode?: string } | null;
    holdNext: () => void;
    release: () => void;
    failNext: () => void;
  };
};

const fixtureWindow = window as FixtureWindow;
fixtureWindow.__playFixture = {
  label: "ui-fixture-not-backend",
  lastTurn: null,
  holdNext: () => {
    holdArmed = true;
  },
  release: () => {
    holdArmed = false;
    releaseHold?.();
    releaseHold = null;
  },
  failNext: () => {
    failNext = true;
  },
};

setAuthTokenGetter(() => "fixture-ui-token");

createRoot(document.getElementById("root")!).render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <GameBrowser />
  </QueryClientProvider>,
);

async function openPlayScreen() {
  const clickWhen = async (selector: string) => {
    for (let attempt = 0; attempt < 50; attempt += 1) {
      const node = document.querySelector<HTMLButtonElement>(selector);
      if (node && !node.disabled) {
        node.click();
        return;
      }
      await new Promise((resolve) => window.setTimeout(resolve, 100));
    }
    throw new Error(`UI fixture could not find ${selector}`);
  };
  await clickWhen('[data-testid="button-continue-session"]');
  await clickWhen(`[data-testid="button-resume-${CAMPAIGN_ID}"]`);
}

void openPlayScreen();
