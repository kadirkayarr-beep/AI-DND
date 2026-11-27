import equipment_economy
import game
import money_owner
import re


# Someone else's purse, pocket, wallet, bag or money (third person: "kesesi", "cebinde", "çantasını"), never the
# player's own ("kesem", "cebimde", "çantamda").
_SOMEONE_ELSES_PURSE = re.compile(
    r"\b(?:kesesi\w*|cebi(?:ni|nde|nden|n)?|cuzdani(?:ni|nda|ndan|n)?|cantasi\w*|parasi\w*)\b")

_SHOP_ECONOMY_PATTERN = re.compile(
    r"\b(?:prices?|pricing|costs?|gold|coins?|copper|silver|gp|stock|"
    r"inventory|buy|buys|buying|purchase|sell|sells|selling|for sale|"
    r"transaction|transactions|fiyat(?:lar|ı|lari|lari)?|altın|gümüş|bakır|"
    r"stok|satın al|satış|satışlar|alım|takas|envanter)\b",
    re.IGNORECASE,
)

_SHOP_TRANSACTION_REQUEST_PATTERN = re.compile(
    r"\b(?:prices?|pricing|costs?|buy|buys|buying|purchase|sell|sells|"
    r"selling|for sale|stock|transaction|transactions|fiyat(?:lar|ı|lari)?|"
    r"ücret(?:ler|i)?|altın|gümüş|bakır|stok|satın al|satış|alım|takas)\b",
    re.IGNORECASE,
)

_SHOP_ENTITY_QUERY_PATTERN = re.compile(
    r"\b(?:shop(?:keeper)?s?|store(?:front)?s?|stalls?|merchant|trader|"
    r"vendor|trading post|d[uü]k?k[aâ]n|ma[gğ]aza|tezg[aâ]h|"
    r"t[uü]ccar|sat[iı]c[iı]|esnaf)\b",
    re.IGNORECASE,
)

def _is_shopkeeper_role(role):
    if not isinstance(role, str):
        return False
    return bool(re.search(
        r"\b(?:shopkeeper|shop\s+keeper|merchant|trader|vendor|"
        r"shop\s+owner|store\s+owner|tüccar|tüccar|satıcı|satici|"
        r"dükkan\s+sahibi|dukkan\s+sahibi)\b",
        role.casefold(),
    ))

def _runs_a_shop(world_state, npc):
    """This person keeps a shop or the ready counter: by her shop, her role, the counter or her tag."""
    import shop_trade
    if not isinstance(npc, dict):
        return False
    tags = npc.get("tags", [])
    return bool(
        npc.get("shop_id")
        or game._is_shopkeeper_role(npc.get("role"))
        or shop_trade.is_vendor(world_state, npc)  # a Barmen who runs the ready counter
        or (isinstance(tags, list) and any(isinstance(tag, str) and tag.casefold() == "shopkeeper" for tag in tags))
    )

def _campaign_has_shopkeeper():
    world_state = game._session().world_state
    for npc in world_state.get("npcs", []):
        if not isinstance(npc, dict):
            continue
        tags = npc.get("tags", [])
        if (
            npc.get("shop_id")
            or (isinstance(tags, list) and any(
                isinstance(tag, str) and tag.casefold() == "shopkeeper"
                for tag in tags
            ))
            or game._is_shopkeeper_role(npc.get("role"))
        ):
            return True
    return False

def _explicit_campaign_shop_request(player_input):
    if not isinstance(player_input, str):
        return False
    text = player_input.casefold()
    if re.search(
        r"\b(?:don't|dont|do not|never|not|no need to|açma|kurma|"
        r"oluşturma|ekleme|bulma|arama)\b",
        text,
    ):
        return False
    entity = (
        r"(?:shop(?:keeper)?s?|store(?:front)?s?|stall|stalls|merchant|"
        r"trader|vendor|trading post|d[uü]k?k[aâ]n|ma[gğ]aza|"
        r"tezg[aâ]h|t[uü]ccar|sat[iı]c[iı]|esnaf)"
    )
    create_action = (
        r"(?:create|open|set\s+up|establish|build|add|start|make|kur\w*|aç(?!ık|il|ıl)\w*|oluştur\w*|ekle\w*|"
        r"inşa\s+et\w*|istiyorum)"
    )
    return bool(
        re.search(rf"\b{create_action}\b.{{0,64}}\b{entity}\b", text)
        or re.search(rf"\b{entity}\b.{{0,64}}\b{create_action}\b", text)
    )

def _shop_economy_request(player_input):
    return isinstance(player_input, str) and bool(
        _SHOP_TRANSACTION_REQUEST_PATTERN.search(player_input)
    )

def _explicit_campaign_shop_negative_request(player_input):
    if not isinstance(player_input, str):
        return False
    text = player_input.casefold()
    has_shop = bool(_SHOP_ENTITY_QUERY_PATTERN.search(text))
    has_english_negative = bool(re.search(
        r"\b(?:never|don't|dont|do not|no need to|not)\b.{0,80}"
        r"\b(?:create|open|set\s+up|establish|build|add|start|make)\b",
        text,
    ))
    has_turkish_negative = bool(re.search(
        r"\b(?:açma|acma|kurma|oluşturma|olusturma|ekleme)\b",
        text,
    ))
    return has_shop and (has_english_negative or has_turkish_negative)

def _shop_presence_question(player_input):
    return bool(
        isinstance(player_input, str)
        and _SHOP_ENTITY_QUERY_PATTERN.search(player_input)
        and "?" in player_input
    )

def generate_shop_id():
    world_state = game._session().world_state
    number = max(1, int(world_state.get("next_shop_number", 1)))
    existing = {
        shop.get("id")
        for shop in world_state.get("shops", [])
        if isinstance(shop, dict)
    }
    while f"shop_{number:03d}" in existing:
        number += 1
    world_state["next_shop_number"] = number + 1
    return f"shop_{number:03d}"

def validate_shop_proposal(proposal):
    world_state = game._session().world_state
    if not isinstance(proposal, dict):
        return None

    name = game._clean_world_text(proposal.get("name"), 60)
    description = game._clean_world_text(proposal.get("description", ""), 200) or ""
    keeper_proposal = proposal.get("shopkeeper")
    if not name or not isinstance(keeper_proposal, dict):
        return None
    if _SHOP_ECONOMY_PATTERN.search(description):
        return None

    keeper_name = game._clean_world_text(keeper_proposal.get("name"), 40)
    if (
        not keeper_name
        or not re.fullmatch(r"[\w .’'-]+", keeper_name, flags=re.UNICODE)
        or "_" in keeper_name
        or keeper_name.casefold() == game._session().character["name"].casefold()
        or any(
            npc.get("name", "").casefold() == keeper_name.casefold()
            for npc in world_state.get("npcs", [])
            if isinstance(npc, dict)
        )
    ):
        return None

    location = world_state.get("location")
    if location not in world_state.get("locations", {}):
        return None
    local_shop_count = sum(
        1 for shop in world_state.get("shops", [])
        if isinstance(shop, dict) and shop.get("location") == location
    )
    if (
        len(world_state.get("npcs", [])) >= 60
        or len(game.active_npcs(location)) >= 6
        or len(world_state.get("shops", [])) >= 12
        or local_shop_count >= 3
    ):
        return None

    keeper_personality = game._clean_world_text(
        keeper_proposal.get("personality", ""), 180
    ) or ""
    keeper_appearance = game._clean_world_text(
        keeper_proposal.get("appearance", ""), 180
    ) or ""
    if any(
        _SHOP_ECONOMY_PATTERN.search(value)
        for value in (keeper_personality, keeper_appearance)
    ):
        return None

    return {
        "name": name,
        "description": description,
        "location": location,
        "shopkeeper": {
            "name": keeper_name,
            "personality": keeper_personality,
            "appearance": keeper_appearance,
        },
    }

def create_shop_from_proposal(proposal):
    world_state = game._session().world_state
    validated = game.validate_shop_proposal(proposal)
    if not validated:
        return None

    known = {npc.get("id") for npc in world_state["npcs"]}
    shopkeeper = game.create_npc_from_ai({
        **validated["shopkeeper"],
        "role": "Shopkeeper",
        "location": validated["location"],
    })
    if not shopkeeper:
        return None

    shop_id = game.generate_shop_id()
    shop = {
        "id": shop_id,
        "name": validated["name"],
        "description": validated["description"],
        "location": validated["location"],
        "tags": ["campaign_local", "shop"],
        "shopkeeper_id": shopkeeper["id"],
        "reality_layer": "PROCEDURAL_LOCAL_FICTION",
    }
    shopkeeper["tags"] = ["campaign_local", "shopkeeper", f"shop:{shop_id}"]
    shopkeeper["shop_id"] = shop_id
    world_state["shops"].append(shop)
    if shopkeeper["id"] not in known:  # D-317: only the owner of a shop opens with the till; a person already here keeps their purse
        world_state["currency"][shopkeeper["id"]] = equipment_economy.person_purse(world_state, shopkeeper)
    return {"shop": shop, "shopkeeper": shopkeeper}

COIN_LEFT_BEHIND = money_owner.COIN_LEFT_BEHIND
