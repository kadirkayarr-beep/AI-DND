/** Scripted transport only: real GameBrowser/account boundary; NOT Python HTTP E2E. Synthetic earned state. */
import { useState } from "react";
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { createRoot } from "react-dom/client";
import { getGetGameSessionStateQueryKey } from "@workspace/api-client-react";
import { setAuthTokenGetter } from "@workspace/api-client-react/custom-fetch";
import GameBrowser from "@/pages/game-browser";
import { nextAccountClient, type AccountBoundary } from "@/lib/account-session";
import { setActionDeadlineBudget } from "@/lib/action-deadline";
import "@/index.css";


let CAMPAIGN_ID = "11111111-1111-4111-8111-111111111111";
let SESSION_ID = "c06-session-a";
const AMBIENT_ID="amb-1", QUEST_ID="quest-1";
type Journal = { event_id: string; event_type: string; created_at: string; turn_index: number; summary: string; location_id: null; location_name: null; related_npc_id: null; related_item: null };
const world = { hp: 26, minute: 40, turn: 18, events: [] as Journal[], questAccepted: false, ambientOpen: false, applied: false };
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
    name: "Riven", race: "human", class: "Sorcerer", strength: 10, dexterity: 14, constitution: world.applied ? 16 : 14, intelligence: 11, wisdom: 13, charisma: 10,
    proficient_skills: ["Stealth"], expertise_skills: [], level: 4, proficiency_bonus: 2, max_hp: world.applied ? 30 : 26, current_hp: world.hp, armor_class: 13,
    cantrips: world.applied ? ["Fire Bolt", "Mage Hand", "Light", "Ray of Frost", "Shocking Grasp"] : ["Fire Bolt", "Mage Hand", "Light", "Ray of Frost"], spells: ["Magic Missile", "Shield", "Burning Hands", "Chromatic Orb", "Disguise Self", "Detect Magic", ...(world.applied ? ["Mage Armor"] : [])], spell_slots_remaining: {"1":4,"2":world.applied ? 3 : 2}, progression_level: world.applied ? 4 : 3, sorcery_points: world.applied ? 4 : 3, xp: 2700,
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

const requests: {path:string; method:string; body:unknown}[] = [];
const holds = new Map<string,{promise:Promise<void>;release:()=>void}>();
const receipts = new Map<string,unknown>();
let failApply = false, failBeforeApply = false, failCanonical = false, verdict = 'applied';
let boundary: AccountBoundary | null = null;
let rerender: (identity:string)=>void = ()=>{};
let remountCampaign: ()=>void = ()=>{};
const json=(body:unknown,status=200)=>new Response(JSON.stringify(body),{status,headers:{'content-type':'application/json'}});
const session=()=>({session_id:SESSION_ID,campaign_id:CAMPAIGN_ID,name:'C06 synthetic earned fixture',state:state(),history:[],combat_history:[]});
const preview=()=>({session_id:SESSION_ID,campaign_id:CAMPAIGN_ID,revision:7,status:world.applied?'blocked':'ready',reason:world.applied?'already_applied':null,target_level:4,choices_required:{prepared_spells:1,cantrips:1,asi:1},cantrip_ids:['Shocking Grasp','Minor Illusion'],prepared_spell_ids:['Mage Armor','Web'],supported_asi_choices:[{feat:'Ability Score Improvement',increase:{constitution:2}}],capacity:{cantrips:5,prepared_spells:7,slots:{'1':4,'2':3},sorcery_points:4},effects_pending:[]});
async function reply(kind:string,body:unknown){const frozen=JSON.parse(JSON.stringify(body));const held=holds.get(kind);if(held){holds.delete(kind);await held.promise;}return json(frozen);}
const releases=new Map<string,()=>void>();
window.fetch=async(input,init)=>{
 const path=new URL(typeof input==='string'?input:input instanceof URL?input.toString():input.url,location.origin).pathname;
 const method=init?.method??'GET'; const body=init?.body?JSON.parse(String(init.body)):null;
 requests.push({path,method,body});
 if(path==='/api/game/health')return json({status:'ok'});
 if(path==='/api/game/campaigns')return json([{campaign_id:CAMPAIGN_ID,name:'C06 synthetic earned fixture',created_at:'2026-10-29T00:00:00Z',updated_at:'2026-10-29T00:00:00Z',last_played_at:'2026-10-29T00:00:00Z',save_version:7,character_name:'Riven',character_race:'human',character_class:'sorcerer',character_level:4,location:'courtyard'}]);
 if(path.endsWith('/resume'))return json(session());
 if(path===`/api/game/campaigns/${CAMPAIGN_ID}`){if(failCanonical)return json({detail:{code:'synthetic_unavailable'}},503);return reply('canonical',session());}
 if(path.endsWith('/state'))return json(state());
 if(path.endsWith('/level-up')&&method==='GET')return reply('preview',preview());
 if(path.endsWith('/level-up')&&method==='POST'){
  if(failBeforeApply){failBeforeApply=false;throw new TypeError('Synthetic transport loss before delivery');}
  let result=receipts.get(body.action_id);
  if(!result){world.applied=true;result={session_id:SESSION_ID,action_id:body.action_id,state:state(),result:{status:'applied',reason:null,changes:[],effects_pending:[]}};receipts.set(body.action_id,result);}
  if(failApply){failApply=false;throw new TypeError('Synthetic lost acknowledgement after commit');}
  return reply('apply',result);
 }
 if(path.endsWith('/actions/unresolved'))return json({unresolved:null});
 if(path.includes('/actions/')){const parts=path.split('/');const action_id=parts.at(-1)==='abandon'?parts.at(-2):parts.at(-1);return json({action_id,state:verdict,response:null,processing:false,detail:verdict==='not_applied'?{code:'abandoned',not_applied:true}:null});}
 return json({detail:{code:'fixture_missing',message:`${method} ${path}`}},404);
};
function View(){const[identity,setIdentity]=useState('owner-a:session-1');const[campaignMount,setCampaignMount]=useState(0);remountCampaign=()=>setCampaignMount(n=>n+1);rerender=setIdentity;if(boundary?.identity!==identity)boundary=nextAccountClient(boundary,identity);return <QueryClientProvider client={boundary!.client}><div key={`${identity}:${campaignMount}`}><GameBrowser/></div></QueryClientProvider>;}
const cacheView=()=>{const data=boundary?.client.getQueryData(getGetGameSessionStateQueryKey(SESSION_ID)) as ReturnType<typeof state>|undefined;return data?{hp:data.character.current_hp,con:data.character.constitution,maxHp:data.character.max_hp}:null;};
async function openPlay(){for(const selector of ['[data-testid="button-continue-session"]',`[data-testid="button-resume-${CAMPAIGN_ID}"]`]){let found=false;for(let i=0;i<100;i++){const node=document.querySelector<HTMLButtonElement>(selector);if(node&&!node.disabled){node.click();found=true;break;}await new Promise(r=>setTimeout(r,100));}if(!found)throw Error(`Missing ${selector}`);}}
(window as unknown as Record<string,unknown>).__c06={
 log:()=>requests.map(r=>`${r.method} ${r.path}`),requests:()=>requests,cache:cacheView,world:()=>({hp:world.hp,applied:world.applied}),
 pending:()=>Object.keys(sessionStorage).filter(k=>k.startsWith('ai-dnd-pending-turns:action:')).map(k=>JSON.parse(sessionStorage.getItem(k)!)),
 hold:(kind:string)=>{let release=()=>{};const promise=new Promise<void>(r=>{release=r});holds.set(kind,{promise,release});releases.set(kind,release);},release:(kind:string)=>releases.get(kind)?.(),
 loseApply:()=>{failApply=true;},loseBeforeApply:()=>{failBeforeApply=true;verdict='unknown';},failCanonical:(value:boolean)=>{failCanonical=value;},verdict:(value:string)=>{verdict=value;},
 resetWorld:()=>{world.applied=false;world.hp=26;},switchIdentity:(identity:string)=>{rerender(identity);},
 switchCampaign:()=>{CAMPAIGN_ID='22222222-2222-4222-8222-222222222222';SESSION_ID='c06-session-b';world.applied=false;world.hp=26;remountCampaign();},openPlay,
};
setAuthTokenGetter(()=>'c06-synthetic-token');createRoot(document.getElementById('root')!).render(<View/>);void openPlay();
// Visible controls for a separately labelled managed-browser check when child Chrome is unavailable.
// These operate only this scripted transport, never a real account or backend.
const toolsPanel=document.createElement('details');toolsPanel.style.cssText='position:fixed;bottom:8px;right:8px;z-index:99999;background:#fff;color:#111;padding:8px;max-width:440px;max-height:45vh;overflow:auto;font:12px monospace';
const summary=document.createElement('summary');summary.textContent='Synthetic C06 transport controls (NOT backend E2E)';toolsPanel.append(summary);
const fixture=(window as unknown as {__c06:Record<string,Function>}).__c06;
for(const [label,act] of [
 ['Lose next apply acknowledgement',()=>fixture.loseApply()],['Fail canonical reads',()=>fixture.failCanonical(true)],['Restore canonical reads',()=>fixture.failCanonical(false)],
 ['Hold preview',()=>fixture.hold('preview')],['Release preview',()=>fixture.release('preview')],['Hold apply',()=>fixture.hold('apply')],['Release apply',()=>fixture.release('apply')],
 ['Switch owner',()=>{fixture.resetWorld();fixture.switchIdentity('owner-b:session-2');void fixture.openPlay();}],
] as [string,()=>void][]){const button=document.createElement('button');button.textContent=label;button.style.cssText='display:block;margin:4px;padding:3px;border:1px solid #555';button.onclick=act;toolsPanel.append(button);}
const diagnostic=document.createElement('pre');toolsPanel.append(diagnostic);document.body.append(toolsPanel);
setInterval(()=>{diagnostic.textContent=JSON.stringify({cache:fixture.cache(),pending:fixture.pending(),requests:requests.slice(-8)},null,2);},300);
