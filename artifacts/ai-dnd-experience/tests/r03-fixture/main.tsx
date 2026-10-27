/**
 * Disposable page for the R03 browser check. It mounts the REAL GameBrowser inside the real account-boundary helpers
 * (nextAccountClient / createAccountQueryClient, the same ones ClerkApiSession uses); only the API is a scripted fetch.
 * The scripted "server" has one mutable world (hp, minute, journal) and can hold a reply while the world moves on, so a
 * late reply carries the state as it was when the server processed it. Not a backend and not the signed-in shell.
 */
import { useState } from "react";
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { createRoot } from "react-dom/client";
import { getGetGameSessionStateQueryKey } from "@workspace/api-client-react";
import { setAuthTokenGetter } from "@workspace/api-client-react/custom-fetch";
import GameBrowser from "@/pages/game-browser";
import { nextAccountClient, type AccountBoundary } from "@/lib/account-session";
import "@/index.css";

const CAMPAIGN_ID = "r03-campaign";
const SESSION_ID = "r03-session";
const AMBIENT_ID = "amb-1";
const QUEST_ID = "quest-1";

type Journal = { event_id: string; event_type: string; created_at: string; turn_index: number; summary: string; location_id: null; location_name: null; related_npc_id: null; related_item: null };
const world = { hp: 12, minute: 40, turn: 18, events: [] as Journal[], questAccepted: false, ambientOpen: true };
const history: { player_message: string; narration: string; created_at: string }[] = [];

const state = () => ({
  campaign_time: { year: 1492, month: "Mirtul", day: 12, hour: 18, minute: world.minute, second: 0, day_index: 12, calendar: "Harptos", local_convention: "Faerûn", time_of_day: "evening", display: `12 Mirtul 1492 DR 18:${world.minute}`, detail: "Akşam" },
  known_scheduled_events: [], pending_event_decisions: [], journey: null, location: "courtyard",
  scene: {
    id: "scene-r03", location_id: "courtyard", parent_location_id: null, kind: "yard", visit_revision: 1, activity_revision: 1, last_activity: null,
    ambient_event: world.ambientOpen ? { event_id: "e1", instance_id: AMBIENT_ID, variation_id: "v1", event_type: "BLUE", repeat_group: "g", count: 1 } : null,
    opening: "Avlu kapısı kapalı.", player_position: { location_id: "courtyard", kind: "standing", target_id: null },
    npcs: [], features: [],
    referents: world.ambientOpen ? [{ id: "r1", event_instance_id: AMBIENT_ID, kind: "movement", description: "Bir gölge kıpırdıyor", source_turn: null, lifecycle: "presented", promoted_npc_id: null }] : [],
  },
  conversation: { active: false, interlocutor: null },
  world: { environment: "tavern", time_of_day: "evening", weather: "clear" },
  journal: { schema_version: 1, discovered_locations: [], known_npcs: [], notable_events: world.events.map((event) => ({ ...event })), quests: [] },
  locations: { courtyard: { id: "courtyard", name: "Kuzgun Hanı avlusu", type: "tavern", description: "Islak taş avlu.", parent_location_id: null, exit_location_id: null } },
  character: {
    name: "Riven", race: "human", class: "rogue", strength: 10, dexterity: 14, constitution: 12, intelligence: 11, wisdom: 13, charisma: 10,
    proficient_skills: ["Stealth"], expertise_skills: [], level: 1, proficiency_bonus: 2, max_hp: 12, current_hp: world.hp, armor_class: 13,
    cantrips: [], spells: [], spell_slots_remaining: {}, xp: 0,
  },
  spellcasting: null, inventory: ["Kısa kılıç"], npcs: [], shops: [], features: [], doors: [],
  combat: { active: false, status: "inactive", round: 0, initiative_order: [], current_turn_index: 0, current_actor_id: null, turn_owner: null, participants: [], participant_records: [], target_id: null, end_reason: null },
  death_state: { mode: "NORMAL", status: "active", successes: 0, failures: 0, stable: false, dead: false, terminal: false, prone: false },
  player_combat_status: "active",
  turn_index: world.turn,
  quests: world.questAccepted ? [{ quest_id: QUEST_ID, title: "Kayıp mühür", description: "Mührü bul.", status: "active", giver_npc_id: null, objectives: [] }] : [],
  quest_offers: world.questAccepted ? [] : [{ quest_id: QUEST_ID, title: "Kayıp mühür", description: "Mührü bul.", giver_npc_id: null, objectives: [] }],
  campaign_adventures: { rumors: [], active: [], completed: [], failed: [], timeline: [], affordances: [] },
  known_lore: [], known_factions: [],
});

// Every world-changing command costs 1 hp, advances the clock one minute and writes one journal event (fixture simplification).
function spendTurn(label: string) {
  world.hp -= 1; world.minute += 1; world.turn += 1;
  world.events.push({ event_id: `ev-${world.turn}`, event_type: "adventure_event", created_at: "2026-10-27T08:05:00Z", turn_index: world.turn, summary: `${label} (${world.turn})`, location_id: null, location_name: null, related_npc_id: null, related_item: null });
}

const session = () => ({ campaign_id: CAMPAIGN_ID, session_id: SESSION_ID, name: "R03 macerası", state: state(), history, combat_history: [] });

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
const pathOf = (input: RequestInfo | URL) => new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://fixture.local").pathname;

type Held = { release: () => void; poison: Partial<{ hp: number; minute: number }>; armed: boolean; promise: Promise<void> };
const holds = new Map<string, Held>();
const stateReads = { count: 0 };
const log: string[] = [];

function arm(kind: string, poison: Held["poison"] = {}) {
  let release: () => void = () => {};
  const promise = new Promise<void>((resolve) => { release = resolve; });
  holds.set(kind, { armed: true, promise, release, poison });
}

// The server processes the request NOW and freezes the answer; a held reply is delivered later with that old copy.
async function answer(kind: string, effect: () => void, body: (frozen: ReturnType<typeof state>) => unknown) {
  const held = holds.get(kind);
  effect();
  const frozen = state();
  if (held?.armed) {
    held.armed = false;
    if (held.poison.hp !== undefined) frozen.character.current_hp = held.poison.hp;
    if (held.poison.minute !== undefined) frozen.campaign_time.minute = held.poison.minute;
    await held.promise;
  }
  return json(body(frozen));
}

window.fetch = async (input, init) => {
  const path = pathOf(input);
  const method = init?.method ?? "GET";
  log.push(`${method} ${path}`);
  if (!path.startsWith("/api/")) throw new Error(`R03 fixture blocked a non-API request: ${path}`);
  if (path === "/api/game/health") return json({ status: "ok" });
  if (path === "/api/game/campaigns" && method === "GET") {
    return json([{ campaign_id: CAMPAIGN_ID, name: "R03 macerası", created_at: "2026-10-27T08:00:00Z", updated_at: "2026-10-27T08:00:00Z", last_played_at: "2026-10-27T08:00:00Z", save_version: 1, character_name: "Riven", character_race: "human", character_class: "rogue", character_level: 1, location: "courtyard" }]);
  }
  if (path === `/api/game/campaigns/${CAMPAIGN_ID}/resume` && method === "POST") return json(session());
  if (path === `/api/game/campaigns/${CAMPAIGN_ID}` && method === "GET") return json(session());
  if (path === `/api/game/sessions/${SESSION_ID}/state`) { stateReads.count += 1; return json(state()); }
  if (path === `/api/game/sessions/${SESSION_ID}/quests/${QUEST_ID}/accept` && method === "POST") {
    return answer("quest", () => { world.questAccepted = true; spendTurn("Görev kabul edildi"); }, (frozen) => ({ session_id: SESSION_ID, state: frozen, quest: frozen.quests[0], outcome: null }));
  }
  if (path === `/api/game/sessions/${SESSION_ID}/ambient-events/${AMBIENT_ID}/actions` && method === "POST") {
    const body = JSON.parse(String(init?.body ?? "{}")) as { action_id?: string };
    return answer("ambient", () => { world.ambientOpen = false; }, (frozen) => ({
      session_id: SESSION_ID, state: frozen,
      result: { event_instance_id: AMBIENT_ID, action_id: body.action_id, status: "APPLIED", reason_code: null, transition_id: null, canonical_event_id: null },
    }));
  }
  if (path === `/api/game/sessions/${SESSION_ID}/turn` && method === "POST") {
    const body = JSON.parse(String(init?.body ?? "{}")) as { message?: string; action_id?: string };
    return answer("turn", () => { spendTurn(body.message ?? ""); history.push({ player_message: body.message ?? "", narration: `Yankı: ${body.message}`, created_at: "2026-10-27T08:05:00Z" }); }, (frozen) => ({ session_id: SESSION_ID, action_id: body.action_id, narration: `Yankı: ${body.message}`, state: frozen, combat_result: null, combat_history_entry: null, skill_check_result: null, quest_outcomes: [], level_up: null }));
  }
  return json({ detail: { code: "campaign_error", message: `R03 fixture has no response for ${method} ${path}` } }, 404);
};

let boundary: AccountBoundary | null = null;
let rerender: (identity: string) => void = () => {};

function View() {
  const [identity, setIdentity] = useState("owner-a:session-1");
  rerender = setIdentity;
  if (boundary?.identity !== identity) boundary = nextAccountClient(boundary, identity);
  // Same shape as ClerkApiSession: one client per identity, children remounted per identity.
  return (
    <QueryClientProvider client={boundary!.client}>
      <div key={identity} style={{ display: "contents" }}><GameBrowser /></div>
    </QueryClientProvider>
  );
}

const cacheView = () => {
  const client = boundary?.client as QueryClient | undefined;
  const data = client?.getQueryData(getGetGameSessionStateQueryKey(SESSION_ID)) as ReturnType<typeof state> | undefined;
  if (!data) return null;
  return { hp: data.character.current_hp, minute: data.campaign_time.minute, events: data.journal.notable_events.length, questAccepted: data.quests.length > 0, ambientOpen: data.scene.ambient_event !== null };
};

async function openPlay() {
  const clickWhen = async (selector: string) => {
    for (let attempt = 0; attempt < 80; attempt += 1) {
      const node = document.querySelector<HTMLButtonElement>(selector);
      if (node && !node.disabled) { node.click(); return; }
      await new Promise((resolve) => window.setTimeout(resolve, 100));
    }
    throw new Error(`R03 fixture could not find ${selector}`);
  };
  await clickWhen('[data-testid="button-continue-session"]');
  await clickWhen(`[data-testid="button-resume-${CAMPAIGN_ID}"]`);
}

(window as unknown as Record<string, unknown>).__r03 = {
  hold: arm,
  release: (kind: string) => holds.get(kind)?.release(),
  world: () => ({ hp: world.hp, minute: world.minute, events: world.events.length, questAccepted: world.questAccepted, ambientOpen: world.ambientOpen }),
  cache: cacheView,
  stateReads: () => stateReads.count,
  log: () => [...log],
  switchIdentity: (identity: string) => rerender(identity),
  openPlay,
};

setAuthTokenGetter(() => "r03-fixture-token");
createRoot(document.getElementById("root")!).render(<View />);
void openPlay();
