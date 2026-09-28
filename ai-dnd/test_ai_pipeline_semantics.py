"""Offline pipeline cases recovered from the shared archive, run in one session."""
import game


session = game.create_session(seed=8)
session.character["name"] = "Tester"
G = {
    "world_state": session.world_state,
    "recent_dm_narrations": session.recent_dm_narrations,
}
for name in (
    "normalize_intent",
    "validate_intent",
    "execute_intent",
    "_location_reference_in_text",
    "resolve_npc_reference",
    "_detect_query_type",
    "_handle_query",
    "is_player_world_assertion",
    "_narration_is_unsafe",
    "finalize_narration",
    "_fallback_for_action_result",
):
    G[name] = getattr(session, name)


def reset(location="tavern"):
    state = G["world_state"]
    state["location"] = location
    state["flags"] = {"turn_index": 0}
    state["npcs"] = [
        {
            "id": "npc_1", "name": "Gromm", "role": "Barmen", "location": "tavern",
            "personality": "", "appearance": "", "backstory": "", "knowledge": [], "memory": [],
        }
    ]
    state["locations"] = {
        "tavern": {"name": "Taverna", "type": "building", "description": "", "aliases": ["tavern", "taverna"]},
        "forest": {"name": "Orman", "type": "wilderness", "description": "", "aliases": ["orman", "forest"]},
        "castle": {"name": "Kale", "type": "building", "description": "", "aliases": ["kale", "castle"]},
        "town_square": {"name": "Şehir Meydanı", "type": "outdoor", "description": "", "aliases": ["şehir meydanı", "meydan"]},
    }
    state["features"] = []
    state["inventory"] = ["Kılıç"]
    state["ground_items_by_location"] = {}
    state["doors"] = []
    state["events"] = []
    G["recent_dm_narrations"].clear()


def check(condition, label):
    if not condition:
        raise AssertionError(label)


reset()
families = {
    "explore": [
        "etrafta ne var", "etrafımda ne var", "etrafımda neler var", "random ne var etrafımda",
        "çevremde neler var", "ne görüyorum", "buralar nasıl", "şöyle bi etrafa bakıyorum",
        "abi bi etrafa bakalım", "etrafa bakiyom", "etrafimda ne var", "burda ortam nasıl",
    ],
    "presence": [
        "burada kim var", "burda kimler var", "kim var burada", "etrafta kim var",
        "tavernada kimler var", "ormanda kim var", "şehir meydanında kimler var", "kim var lan burda",
    ],
    "location": ["neredeyim", "nerdeyim", "şu an neredeyim", "hangi mekandayım"],
    "travel": ["tavernaya gidiyorum", "tavernaya geçiyorum", "ormana gidiyorum", "şehir meydanına yürüyorum"],
}
for family, phrases in families.items():
    for phrase in phrases:
        reset()
        raw = {"intent": "narrative", "target": {"type": "none", "reference": ""}}
        normalized = G["normalize_intent"](raw, phrase)
        validated = G["validate_intent"](normalized, phrase)
        if family == "travel":
            check(validated["intent"] == "travel", f"travel fastpath: {phrase} => {validated}")
        elif family == "location":
            check(validated.get("query_type") == "location", f"location query: {phrase} => {validated}")
        elif family == "presence":
            check(validated.get("query_type") == "presence", f"presence query: {phrase} => {validated}")
            check(G["execute_intent"](validated, phrase)["action"] == "query", f"presence action: {phrase}")
        else:
            check(validated.get("explore_type") == "observe", f"explore: {phrase} => {validated}")
            result = G["execute_intent"](validated, phrase)
            check(result["action"] == "explore" and result["success"] is True, f"explore action: {phrase}")

extra = [
    "nerdeyim ya", "nerdeyiz", "şimdi hangi yerdeyim", "konumum neresi", "ben nerdeyim şu an",
    "burda kim var ya", "kimler var burda", "kim var lan burada", "tavernada kim var",
    "ormanda kimler bulunuyor", "meydanda kim bekliyor", "burada kimler duruyor",
    "etrafıma bi bakayım", "şöyle etrafa göz atayım", "çevreye bakıyom", "çevremde ne var",
    "etrafımda neler oluyo", "ortam nasıl burda", "buralarda ne görünüyor", "ne var çevrede",
    "tavernaya gidiyom", "tavernaya geçelim", "ormana doğru yürüyorum", "meydana gidiyorum",
    "orman tarafına geçiyorum", "kaleye doğru gidiyorum", "taverna yönüne ilerliyorum", "tavernaya varıyorum",
    "barmene selam veriyorum", "selam barmen", "barmenle konuşuyorum", "barmenle iki laf edeyim",
]
for phrase in extra:
    reset()
    intent = G["validate_intent"](G["normalize_intent"]({"intent": "unknown"}, phrase), phrase)
    check(intent["intent"] in {"travel", "query", "explore", "dialogue"}, f"variant classification: {phrase} => {intent}")

reset()
for phrase, target in [("tavernaya gidiyorum", "tavern"), ("ormana gidiyorum", "forest")]:
    intent = {"intent": "travel", "target": {"type": "location", "reference": target}, "completion": "completed"}
    validated = G["validate_intent"](intent, phrase)
    check(validated["intent"] == "travel", f"grounded travel target rejected: {phrase} {validated}")
bad = G["validate_intent"](
    {"intent": "travel", "target": {"type": "location", "reference": "tavern"}},
    "neverwinter şehir kapılarından içeri giriyorum",
)
check(bad["intent"] != "travel", f"hallucinated target accepted: {bad}")
check(G["_location_reference_in_text"]("tavernaya gidiyorum") == "tavern", "tavern suffix grounding")
check(G["_location_reference_in_text"]("tavernanın dışında duruyorum") == "tavern", "tavern possessive suffix grounding")

reset()
for form in ("barmen", "barmene", "barmenle", "barmenden"):
    found = G["resolve_npc_reference"](f"{form} ile konuşuyorum")
    check(found["status"] == "found" and found["npc"]["id"] == "npc_1", f"NPC role suffix {form}: {found}")
check(G["resolve_npc_reference"]("tüccarla konuşuyorum")["status"] == "none", "unregistered role created/resolved")

identity_phrases = (
    "adın ne", "senin adın ne", "ismin ne", "senin ismin ne",
    "kimsin", "sen kimsin", "adin ne", "senin adin ne",
)
reset()
canonical_npc = G["world_state"]["npcs"][0]
for phrase in identity_phrases:
    check(G["_detect_query_type"](phrase, canonical_npc) == "npc_identity", f"NPC identity not recognized: {phrase}")
before_npcs = len(G["world_state"]["npcs"])
for phrase in identity_phrases:
    check(G["_detect_query_type"](phrase, None) != "npc_identity", f"NPC identity invented without target: {phrase}")
    G["resolve_npc_reference"](phrase)
check(len(G["world_state"]["npcs"]) == before_npcs, "identity question created an NPC")

# A name, location, and NPC identity question must remain grounded in its entity.
location_cases = (
    "Taverna adı ne?", "Tavernanın adı ne?", "Taverna'nın ismi ne?",
    "buranın adı ne?", "bu mekanın adı ne?", "bulunduğum yerin adı ne?",
    "hangi mekandayım", "hangi yerdeyim", "nerdeyim", "neredeyim",
)
for phrase in location_cases:
    kind = G["_detect_query_type"](phrase, canonical_npc)
    response = G["_handle_query"](phrase, kind, canonical_npc)
    check(kind == "location", f"{phrase!r} expected location, got {kind!r}")
    check(response and "Taverna" in response and "Gromm" not in response, f"{phrase!r} returned the wrong entity: {response!r}")

npc_cases = (
    "senin adın ne?", "adın ne?", "ismin ne?", "senin ismin ne?", "kimsin",
    "sen kimsin", "adin ne", "senin adin ne", "Gromm'un adı ne?", "Gromm kim?",
)
for phrase in npc_cases:
    kind = G["_detect_query_type"](phrase, canonical_npc)
    response = G["_handle_query"](phrase, kind, canonical_npc)
    check(kind == "npc_identity", f"{phrase!r} expected npc_identity, got {kind!r}")
    check(response and "Gromm" in response, f"{phrase!r} missed canonical NPC: {response!r}")
for phrase in ("Tavernada kim var?", "Tavernada kimler var?", "burada kimler var?"):
    check(G["_detect_query_type"](phrase, canonical_npc) == "presence", f"presence precedence failed: {phrase!r}")
G["world_state"]["npcs"] = []
check(G["_detect_query_type"]("senin adın ne?", None) is None, "missing NPC target invented")
check(G["resolve_npc_reference"]("senin adın ne?")["status"] == "none", "identity query fabricated an NPC")

reset("forest")
for phrase in ("tavernada kimler var", "ormanda kim var", "şehir meydanında kimler var"):
    intent = G["validate_intent"](
        G["normalize_intent"](
            {"intent": "travel", "target": {"type": "location", "reference": "tavern"}}, phrase
        ),
        phrase,
    )
    check(intent["intent"] == "query" and intent.get("query_type") == "presence", f"presence misclassified: {phrase} {intent}")
    result = G["execute_intent"](intent, phrase)
    check(G["world_state"]["location"] == "forest" and result["action"] == "query", f"presence mutated location: {phrase}")

for phrase in ("haydut görüyorum", "karşımda ejderha var", "barmenin adı Gromm", "burada on asker var"):
    check(G["is_player_world_assertion"](phrase), f"assertion not guarded: {phrase}")

world = G["world_state"]
world["location"] = "tavern"
world["npcs"] = [
    {"id": "npc_1", "name": "Kasım", "role": "Hancı", "location": "tavern",
     "appearance": "", "personality": "", "backstory": "", "knowledge": [], "memory": []},
    {"id": "npc_2", "name": "Karanlık Kuyu", "role": "Geçit Gözetmeni", "location": "forest",
     "appearance": "", "personality": "", "backstory": "", "knowledge": [], "memory": []},
    {"id": "npc_3", "name": "Korucu Elric", "role": "Orman Rehberi", "location": "forest",
     "appearance": "", "personality": "", "backstory": "", "knowledge": [], "memory": []},
]
world["features"] = [
    {"location": "tavern", "name": "Gölgeli Masalar", "description": "Alçak ışıkta duran masalar."},
    {"location": "tavern", "name": "Kemerli Pencereler", "description": "Pencerelerden süzülen ışık."},
    {"location": "forest", "name": "Yabanıl Ağaçlı Yol", "description": "Ormanda uzanan dar yol."},
]
unsafe = G["_narration_is_unsafe"]
check(not unsafe("Kasım, gölgeli masaların yanında sessizce durur.", "random ne var etrafımda"), "registered NPC rejected")
check(not unsafe("Gölgeli Masalar loş ışıkta odanın kıyısında sıralanır.", "random ne var etrafımda"), "registered feature rejected")
check(not unsafe("Karanlık Kuyu'nun sesi ağaçların arasından duyulur.", "ormana bakıyorum"), "registered multiword NPC possessive rejected")
check(not unsafe("Elric, yakındaki yolu inceler.", "ormana bakıyorum"), "registered NPC name component rejected")
check(not unsafe("Serin hava ve yaprak hışırtısı çevreyi doldurur.", "şöyle bi etrafa bakalım"), "harmless atmosphere rejected")
dialogue_target = world["npcs"][0]
dialogue = {"action": "dialogue", "status": "resolved", "success": True, "state_changes": []}
check(not unsafe('Kasım sana doğru eğilir. "Bir şey mi istiyorsun?" diye sorar.', "barmenle konuşayım", dialogue_target, dialogue), "NPC question rejected as player action")
check(not unsafe("Kemal masanın yanında oturuyor.", "barmenle konuşayım", dialogue_target, dialogue), "NPC posture rejected as player sitting")
check(not unsafe("Kemal, 'Bir barmen var mı?' diye sorar.", "barmenle konuşayım", dialogue_target, dialogue), "quoted generic noun misread as NPC name")
check(unsafe('Kasım, "Bir şey mi istiyorsun?" diye sorar. Kılıcını çekersin.', "barmenle konuşayım", dialogue_target, dialogue), "extra player action hidden by NPC dialogue")

world["location"] = "forest"
travel = {"action": "travel", "status": "completed", "success": True, "new_location": "forest"}
check(not unsafe("Tester ormana girerken, yaprak sesleri onu karşılar.", "ormana gidiyorum", action_result=travel), "committed named arrival rejected")
check(not unsafe("Orman içine adım attınız; yaprak sesleri çevrede duyulur.", "ormana gidiyorum", action_result=travel), "committed step arrival rejected")
check(unsafe("Tester ormana girerken kılıcını çeker.", "ormana gidiyorum", action_result=travel), "extra player action accepted")
qwen_extra_travel = "Ormana girerken doğa koruyucusu Elric sana selam verdi. Yapraklı yolu takip ederek ileriye doğru ilerliyorsun."
check(unsafe(qwen_extra_travel, "ormana gidiyorum", action_result=travel), "uncommitted post-arrival movement accepted")
check(unsafe("Zorvax, sana doğru yaklaşır.", "ormanı gözlemliyorum"), "unregistered NPC accepted")
check(unsafe("Yerdeki sandık açılmış duruyor.", "ormana bakıyorum"), "unregistered persistent item accepted")

explore = {"action": "explore", "status": "resolved", "success": True, "state_changes": [], "explore_type": "observe"}
check(not unsafe("Ormanda serin hava ve yaprak sesleri duyulur.", "random ne var etrafımda", action_result=explore), "state-free explore prose rejected")
check(not unsafe("Yapraklı Yolun izlerini fark ediyorsun; uzaktan kuş sesleri duyuyorsun.", "şöyle bi etrafa bakalım", action_result=explore), "perceptual observation rejected")
G["recent_dm_narrations"].clear()
fallback = G["finalize_narration"]("Tester kılıcını alır ve duvarı kırar.", "ormana bakıyorum", action_result=explore)
check(bool(fallback) and "duvarı kırar" not in fallback.casefold(), "unsafe narration did not fall back")
check(unsafe("", "ormana bakıyorum", action_result=explore), "empty narration accepted")

print("PASS: 87 semantic, 24 query-grounding, and 18 narrator-safety checks")