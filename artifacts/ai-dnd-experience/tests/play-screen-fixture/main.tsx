/**
 * UI fixture only. Fixed responses stay in this page.
 * Spell lists and the active combat target are supplied display data.
 * This is not a backend, save, or resume proof, and it is not the signed-in app.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createRoot } from "react-dom/client";
import { setAuthTokenGetter } from "@workspace/api-client-react/custom-fetch";
import GameBrowser from "@/pages/game-browser";
import { AppearanceProvider } from "@/components/appearance-provider";
import "@/index.css";

const CAMPAIGN_ID = "fixture-campaign";
const SESSION_ID = "fixture-session";
const cacheFailureFixture = new URLSearchParams(window.location.search).get("cache") === "blocked";
const combatFixture = new URLSearchParams(window.location.search).get("combat") === "1";
const emptyStateFixture = new URLSearchParams(window.location.search).get("empty-state") === "1";
if (new URLSearchParams(window.location.search).get("touch") === "1") {
  Object.defineProperty(navigator, "maxTouchPoints", { configurable: true, value: 1 });
}
let fixtureHp = 12;
// UI slice 3: a preparing caster (Wizard/Cleric) and its preparation window, only with ?caster=wizard|cleric.
const casterParam = new URLSearchParams(window.location.search).get("caster");
const casterClass = casterParam === "wizard" ? "Wizard" : casterParam === "cleric" ? "Cleric" : null;
const STANDING = ["creation", "migration", "level_up"];
const prepFixture = {
  reason: new URLSearchParams(window.location.search).get("prep") ?? "long_rest",
  open: true,
  limit: 4,
  candidates: casterClass === "Cleric"
    ? ["Bless", "Cure Wounds", "Healing Word", "Guiding Bolt", "Shield of Faith", "Command", "Aid"]
    : ["Magic Missile", "Shield", "Sleep", "Mage Armor", "Detect Magic", "Misty Step"],
  prepared: casterClass === "Cleric" ? ["Bless"] : ["Magic Missile"],
  refuseNext: null as string | null,
};
// ?levelup=1 with a caster: an earned level 2 waiting for its Wizard/Cleric choices (server offer shape, api/main.py).
const levelUpFixture = casterClass !== null && new URLSearchParams(window.location.search).get("levelup") === "1";
const levelUpPreview = () => ({
  session_id: "fixture-session", campaign_id: "fixture-campaign", revision: 3, status: "ready", reason: null, class_name: casterClass,
  from_level: 1, target_level: 2, choices_required: casterClass === "Wizard" ? { spellbook_spells: 2 } : {},
  capacity: { cantrips: 3, prepared_spells: 5, slots: { 1: 3 } },
  spellbook_spell_ids: casterClass === "Wizard" ? ["Shield", "Sleep", "Mage Armor", "Detect Magic", "Misty Step"] : null,
  effects_supported: ["Spellcasting"], effects_pending: ["Arcane Recovery pending"],
});
const prepView = () => ({
  session_id: "fixture-session", supported: true, blocked_reason: null, class_name: casterClass, open: prepFixture.open,
  reason: prepFixture.open ? prepFixture.reason : null, limit: prepFixture.limit, candidates: prepFixture.candidates,
  prepared: [...prepFixture.prepared], spellbook: casterClass === "Wizard" ? prepFixture.candidates : null,
});

// This override is scoped to this disposable fixture page, never the app.
if (cacheFailureFixture) {
  Storage.prototype.setItem = () => {
    throw new DOMException("Synthetic fixture quota failure", "QuotaExceededError");
  };
}

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
    npcs: emptyStateFixture ? [] : [{ id: "npc-marek", name: "Marek", role: "Hancı", appearance: "Eşikte bekliyor." }],
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
    class: casterClass ?? "rogue",
    strength: 10, dexterity: 14, constitution: 12, intelligence: 11, wisdom: 13, charisma: 10,
    proficient_skills: ["Stealth"],
    expertise_skills: [],
    level: levelUpFixture ? 2 : 1,
    ...(levelUpFixture ? { progression_level: 1 } : {}),
    proficiency_bonus: 2,
    max_hp: 12,
    current_hp: fixtureHp,
    armor_class: 13,
    cantrips: [],
    spells: [],
    spell_slots_remaining: {},
    xp: 0,
  },
  spellcasting: {
    cantrips: ["Fire Bolt"],
    prepared: casterClass ? [...prepFixture.prepared] : ["Magic Missile"],
    slots: { "1": 2 },
    slot_turn: ["fixture-slot-marker", 2, 1],
  },
  inventory: ["Kısa kılıç"],
  npcs: emptyStateFixture ? [] : [{
    id: "npc-marek", name: "Marek", role: "Hancı", location: "courtyard",
    appearance: "Eşikte bekliyor.", relationship: null,
    max_hp: null, current_hp: null, armor_class: null, combat_status: null,
  }],
  shops: [],
  features: [],
  doors: [],
  combat: {
    active: combatFixture,
    status: combatFixture ? "active" : "inactive",
    round: emptyStateFixture ? 0 : 1,
    initiative_order: ["player", "npc-guard"],
    current_turn_index: 0,
    current_actor_id: "player",
    turn_owner: "player",
    participants: ["player", "npc-guard"],
    participant_records: [
      {
        id: "player",
        kind: "player",
        name: "Riven",
        current_hp: fixtureHp,
        max_hp: 12,
        armor_class: 13,
        status: "active",
        primary_action_available: true,
        is_current_actor: true,
      },
      {
        id: "npc-guard",
        kind: "npc",
        name: "Avlu muhafızı",
        current_hp: 9,
        max_hp: 11,
        armor_class: 12,
        status: "active",
        primary_action_available: true,
        is_current_actor: false,
      },
    ],
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
const apiRequests: { path: string; method: string }[] = [];

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
  apiRequests.push({ path, method: init?.method ?? "GET" });
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
    if (cacheFailureFixture) fixtureHp = Math.max(1, fixtureHp - 1);
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
  if (levelUpFixture && path === `/api/game/sessions/${SESSION_ID}/level-up` && (!init?.method || init.method === "GET")) return json(levelUpPreview());
  if (casterClass && path === `/api/game/sessions/${SESSION_ID}/spellcasting/prepare` && (!init?.method || init.method === "GET")) return json(prepView());
  if (casterClass && path === `/api/game/sessions/${SESSION_ID}/spellcasting/prepare` && init?.method === "POST") {
    const body = JSON.parse(String(init.body ?? "{}")) as { prepared?: string[]; action_id?: string; close?: boolean };
    (window as FixtureWindow).__playFixture.lastPrepare = body;
    const refuse = (code: string) => json({ detail: { code, message: "engine text" } }, 409);
    if (prepFixture.refuseNext) { const code = prepFixture.refuseNext; prepFixture.refuseNext = null; return refuse(code); }
    if (!prepFixture.open) return refuse("prepare_window_closed");
    const requested = body.prepared ?? prepFixture.prepared;
    if (prepFixture.reason === "level_up" && prepFixture.prepared.some((id) => !requested.includes(id))) return refuse("prepare_level_up_additive_only");
    const result = (status: string, extra = {}) => ({ status, prepared: [...requested], dropped: [], limit: prepFixture.limit, excess: 0, open: prepFixture.open, message: "engine text", ...extra });
    if (requested.length > prepFixture.limit) {
      return json({ session_id: SESSION_ID, action_id: body.action_id, state: state(), result: result("too_many", { excess: requested.length - prepFixture.limit, open: true }) });
    }
    prepFixture.prepared = [...requested];
    if (STANDING.includes(prepFixture.reason)) prepFixture.open = false;
    return json({ session_id: SESSION_ID, action_id: body.action_id, state: state(), result: result("prepared", { open: prepFixture.open }) });
  }
  return json({ detail: { code: "campaign_error", message: `UI fixture has no response for ${path}` } }, 404);
};

type FixtureWindow = Window & {
  __playFixture: {
    label: "ui-fixture-not-backend";
    lastTurn: { message?: string; action_id?: string; interaction_mode?: string } | null;
    lastPrepare?: { prepared?: string[]; action_id?: string; close?: boolean } | null;
    refusePrepare?: (code: string) => void;
    holdNext: () => void;
    release: () => void;
    failNext: () => void;
    apiRequests: { path: string; method: string }[];
    stateSnapshot: () => string;
  };
};

const fixtureWindow = window as FixtureWindow;
fixtureWindow.__playFixture = {
  label: "ui-fixture-not-backend",
  lastTurn: null,
  lastPrepare: null,
  refusePrepare: (code: string) => { prepFixture.refuseNext = code; },
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
  apiRequests,
  stateSnapshot: () => {
    const current = state();
    return JSON.stringify({
      location: current.location,
      campaign_time: current.campaign_time,
      exploration: current.exploration,
      journey: current.journey,
      combat: current.combat,
      turn_index: current.turn_index,
    });
  },
};

setAuthTokenGetter(() => "fixture-ui-token");

createRoot(document.getElementById("root")!).render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <AppearanceProvider>
      <GameBrowser />
    </AppearanceProvider>
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

if (new URLSearchParams(window.location.search).get("screen") !== "opening") {
  void openPlayScreen();
}
