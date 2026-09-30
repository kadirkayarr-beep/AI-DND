# Playable Living World V1.1 — final web-client verification

**Date:** 30 September 2026  
**Release identity:** AI-DND v0.6.1-alpha, Internal Build V15  
**Previous identity:** AI-DND v0.6.0-alpha, Internal Build V14  
**Client/service:** `ai-dnd-web` solo browser client → its configured FastAPI service on port 8008  
**Model:** `qwen3:8b`  
**Final verification:** one fresh, disposable solo session; no campaign was persisted.

## Decision

All four requested V1.1 cases passed through the real solo web client in the final disposable session. The only persistent source change for this verification was a narrow route-distance classification guard and its regression test. No architecture or gameplay feature was added.

An earlier disposable diagnostic session exposed a failure in the distance case; it was not used as final evidence. After the fix, a fresh session was created and all four cases were completed in that single session.

## Verification record

### 1. Unsupported route distance has no unrelated side effects

Setup input: `Taverna'ya gidiyorum.` The public state moved to `tavern` and materialized the scene, Barmen `Elaris` (`npc_001`), `Ahşap masa` (`feature_001`), and the addressable visitor (`scene_ref_0001`). The UI narration for this setup turn was the generic fallback: `Bu konuda güvenilir bir doğrulamam yok; kesin yanıt belirsiz.`

Test input: `Taverna ile Kale arasındaki yol mesafesi kaç kilometre?`

Player-visible response: `İki yer arasındaki mesafe için güvenilir bir ölçüm kaydı yok; kesin uzaklık doğrulanamıyor.`

Before and after, the location remained `tavern`; the registered locations stayed `tavern`, `forest`, and `castle`; the NPC, named feature, scene, visitor referent, quests, and quest offers were identical. Only the turn index advanced from 1 to 2. No technical/debug wording appeared.

The next scene action succeeded:

- Input: `Ahşap masa yanına oturuyorum.`
- Response: `“Ahşap masa” yakınında uygun bir yere oturup yerleşiyorsun.`
- State: `scene.player_position.kind = seated`, `target_id = feature_001`; the browser displayed the `Ahşap masa` feature card.

**Result: PASS.**

### 2. Accepting a nonexistent job offer does not create outcomes

Before the acceptance input, `quests` and `quest_offers` were both empty. `Elaris` had a neutral relationship; the player inventory contained only `Macera çantası` and `Kılıç`.

- Targeting setup input: `Elaris kişisine yaklaşıyorum.`
- Response: `Elaris seni fark edip sana dönüyor.`
- Acceptance input: `İşe başlamaya hazırım.`
- Response: `Elaris, “Henüz sana belirli bir iş önermedim; şu an başlayabileceğin bir iş yok,” diye karşılık verir.`

After the acceptance input, quests and offers remained empty; location, NPC relationship, inventory, scene, and other compared public-state fields were unchanged. No reward or inventory change appeared.

**Result: PASS.**

### 3. Table and traveler identity continuity

At the entered `tavern` location, the real named feature was `Ahşap masa` (`feature_001`). Sitting at it succeeded as recorded in case 1.

The presented visitor had addressable alias `ziyaretçi`, referent ID `scene_ref_0001`, and description `Girişe yakın bir ziyaretçi, omzundaki çanta kayışını düzeltiyor.`

- Observation input: `ziyaretçi ne yapıyor?`
- Response: `Girişe yakın bir ziyaretçi, omzundaki çanta kayışını düzeltiyor.`
- After observation: the same referent remained `presented`; no NPC was created by observation.
- Approach input: `ziyaretçi kişisine yaklaşıyorum.`
- Response: `Aldren seni fark edip sana dönüyor.`
- After approach: the same `scene_ref_0001` was marked `promoted` and bound to `npc_002` (`Aldren`, role `Yolcu`). The promoted NPC retained the visitor's description and `tavern` location. The browser's visible people section listed both `Elaris` and `Aldren`.

The response and visible NPC card therefore refer to the same visitor, not a second or guessed person.

**Result: PASS.**

### 4. World-subject ruler question with an active NPC target

The promoted traveler was the active conversation target: the browser input `Adın ne?` received the response `Aldren, “Ben Aldren. Yolcu olarak buradayım.” diye yanıt verir.`

- World-question input: `Bu şehrin hükümdarı kim?`
- Player-visible response: `Bu yerin yöneticisinin kim olduğu konusunda güvenilir bir doğrulamam yok.`

The answer did not name or address Aldren. The location, NPC list and relationships, scene, feature, and promoted referent were unchanged; only the turn index advanced from 8 to 9.

**Result: PASS.**

## Failure reproduced and fixed

In the earlier diagnostic session, the same distance input was misclassified as a local tavern search. The UI said `Yakınlarda Ilyra Hanı adlı küçük bir han buluyorsun. Sokağa açılan kapısı kolayca fark ediliyor.` and the engine added `location_001` (`Ilyra Hanı`) beneath `tavern`.

The cause was the broad local-search matcher treating the beginning of `arasındaki` as search intent when the same question mentioned `Taverna`. Route/distance wording now takes precedence over tavern and local-venue search classification. The regression test asserts the actual input produces an unverified response without changing location, locations, NPCs, shops, features, doors, containers, scene state, quests, offers, or inventory.

## Automated verification and caveat

- `python -m unittest test_playable_living_world -v`: 23 tests passed.
- `python -m unittest discover -s api/tests -p 'test_*.py' -v`: 175 tests passed.
- `python ai-dnd/run_tests.py`: the runner reported all 18 deterministic gates passed. Its legacy `test_regression.py` output also printed a separate failure, `test_location_name_vs_character_name` (`'benim adım ne?'` expected `character_query`, received `dialogue`). That check is outside the four V1.1 cases and was not changed.

## Source checkpoint

`ai-dnd/game.py` SHA-256: `8656d9dafd8ca9c022b7bbb992958ffe233cf126afc0c62d55e0a78dbd0c8592`

The earlier Playable Living World V1 report remains unchanged as historical release evidence.