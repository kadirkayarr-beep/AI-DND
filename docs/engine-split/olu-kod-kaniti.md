# Ölü kod kanıtı (game.py bölmesi, spec §10, T7.2)

Hiçbir şey Kadir'in 'evet'i olmadan silinmez (spec §10). Silme ayrı küçük bir PR'dır.

Dürüst beklenti (spec §10): kazanç onlarca satırdır; bölmenin asıl kazancı bu değil.

Varsayılan öneri: 5 işlevin hepsi ve başlık içe aktarmalarının hepsi kalsın. 'öneri' sütunu yalnız dört koşulun tutup tutmadığını söyler; silmek her satır için senin ayrı 'evet'ini ister.
(Neden: toplam 44 satır, 3 tanesi sabitleme testleriyle çağrılıyor, 5 tanesi parti dosyalarında duruyor; bu yüzden bir silme, güçlü incelemeli bir PR ve üç ayrı onay ister.)

Ölçüm: `P6BASE` = `234947b0` (Plan 6'nın başladığı `origin/main`), taze `git archive` kopyası. Ham kanıt dosyaları Plan 6 defter klasöründe (`.superpowers/sdd/2026-11-21-game-py-bolme-plan-6/`, depoya girmez): `p6t5-dead.out` (koşul 1, 3 ve 5), `p6t5-cond2.out` (koşul 2), `p6t5-vulture.out` (koşul 4), `p6t5-ruff.out` (F401 sayımı), `task-5-report.md` (dinamik erişim yerlerinin tek tek kararı).

Dört koşul:
1. Tanımı dışında hiçbir yerde adı geçmiyor. Sayılmayanlar (bölmenin kendi defteri, §24 satır 8 "gevşetme olabilir"): tanım satırı, `game.py`'nin yeniden dışa vurum satırı, `api/tests/engine_split_locks/*`, `scripts/engine_split/batches/*`, `docs/superpowers/`, `docs/engine-split/`, `docs/agents/debt-register.md`, `docs/agents/onay-listesi-*`. Bölmenin sabitleme testlerindeki (`test_engine_parts_pilot`, `test_engine_surface`) anılma ayrı yazılır, gizlenmez. UTF-16 ile yazılmış 5 eski günlük de okundu (0 anılma); okunamayan dosya 0.
2. Gövdesinden hiçbir satır çalışmadı: `P6BASE` üzerindeki dört tam paketin (bayrak kapalı 2, açık 2) ham çalışan satır kayıtları. Bayrak kapalı ikinci pakette bu adlarla ilgisi olmayan bir test bir kez kırıldı (D-484, testin kendi zamanlama yarışı, ana dalda düzeltildi); o paketin çalışan satırları yine okundu, çünkü fazladan çalışma yalnız satır ekleyebilir.
3. Dinamik erişim yok: ad dizesi kurulup `getattr`/`setattr` ile ulaşılan her yer tek tek bakıldı.
4. vulture 2.14 (`--min-confidence 0`) adı kullanılmıyor diye listeliyor.

## İşlevler

| ad | dosya | satır (`P6BASE`) | ne yapıyordu | kanıt (koşul 1-4) | son dokunan commit (bölmeden önce) | silinecek testler | öneri |
|---|---|---|---|---|---|---|---|
| `_filter_unsupported_lore_paragraphs` | `ai-dnd/game_parts/lore.py` | 10-22 (13 satır) | Anlatıyı paragraflara böler, desteklenmeyen bir bilgi (lore) iddiası taşıyan paragrafları atar, kalanı yeniden birleştirir. | 1 ✓ (dışarıda 0 anılma; `p6t5-dead.out`) · 2 ✓ (dört tam pakette gövdeden 0 satır çalıştı; yalnız `def` satırı içe aktarmada çalışıyor; `p6t5-cond2.out`) · 3 ✓ · 4 ✓ (`lore.py:10` %60; `p6t5-vulture.out`) | `7deff2cb` 2026-09-29 Refactor game logic and update API endpoints | yok (defterden ad düşer: `batches/lore.txt`, `surface.json`, `game.py` yeniden dışa vurum satırı) | sil |
| `_existing_local_tavern` | `ai-dnd/game_parts/places.py` | 898-910 (13 satır) | Oturumun dünyasında verilen yerin altındaki ilk hanı (tavern) bulur; yoksa hiçbir şey döndürmez. | 1 ✓ (dışarıda 0 anılma) · 2 ✓ (dört pakette gövdeden 0 satır) · 3 ✓ · 4 ✓ (`places.py:898` %60) | `3f50ee68` 2026-10-16 fix(ai-dnd): checkpoint door knock and building inspection | yok (defterden ad düşer: `batches/places-1.txt`, `surface.json`, yeniden dışa vurum satırı) | sil |
| `analyze_player_action` | `ai-dnd/game_parts/intent.py` | 684-693 (10 satır) | Eski "eylem çözümleyici" giriş noktasının uyumluluk sarmalayıcısı: niyeti okur; gizlenme, algı, inceleme, arama ya da kapıysa "beceri sınaması", değilse "anlatı" der. | 1 yalnız bölme sabitleme testi (`test_engine_parts_pilot`, 2 anılma) · 2 2 ✗ (gövde satırları 690-692 dört pakette de çalıştı; çağıran yalnız sabitleme testi) · 3 ✓ · 4 ✗ (vulture listelemiyor: test çağırıyor) | `4b52964d` 2026-10-05 Detach nested combat snapshots and regress result stability across campaign turns | `test_engine_parts_pilot.IntentPart.test_a_rebound_validate_intent_reaches_a_moved_caller` | sil (yalnız sabitleme testiyle birlikte) |
| `update_world_state_from_player` | `ai-dnd/game_parts/intent.py` | 1792-1796 (5 satır) | Uyumluluk sarmalayıcısı: oyuncu cümlesinden niyeti okur ve merkezi çözücüyle (`execute_intent`) yürütür. | 1 yalnız bölme sabitleme testi (2 anılma) · 2 2 ✗ (gövde satırları 1794-1796 dört pakette de çalıştı; çağıran yalnız sabitleme testi) · 3 ✓ · 4 ✗ (vulture listelemiyor) | `4b52964d` 2026-10-05 (aynı) | `test_engine_parts_pilot.IntentPart.test_a_rebound_execute_intent_reaches_its_moved_caller` | sil (yalnız sabitleme testiyle birlikte) |
| `is_dialogue_or_emotion` | `ai-dnd/game_parts/intent.py` | 17-19 (3 satır) | Sıradan konuşmayı, soruyu ve duyguyu beceri sınamasının dışında tutmak için `is_npc_dialogue_input`'a sorar. | 1 yalnız bölme sabitleme testi (2 anılma) · 2 2 ✗ (gövde satırı 19 dört pakette de çalıştı; çağıran yalnız sabitleme testi) · 3 ✓ · 4 ✗ (vulture listelemiyor) | `4b52964d` 2026-10-05 (aynı) | bütün test silinmez: `test_engine_parts_pilot.IntentPart.test_intent_helpers_answer_as_before` içinde bu adı çağıran iki satır silinir | sil (yalnız sabitleme testiyle birlikte) |

Sabitleme testi ne demek: bölme sırasında taşınan işlevin taşındıktan sonra da aynı cevabı verdiğini kanıtlayan test. Bu üç işlevi oyunda hiçbir yol çağırmıyor; onları çalıştıran tek şey bu testler. Koşul 2 ve 4 bu yüzden tutmuyor.

Kadir'in "evet"i bir satırın adını ve yalnız o satırda yazılı testleri kapsar.

Durum (2026-11-22): Kadir sohbette "10. sil" dedi. Denetleyicinin kararı: bu cevap yalnız iki satırı kapsar: `_filter_unsupported_lore_paragraphs` ve `_existing_local_tavern` (dört koşul da tutuyor). Kapsamadıkları Kadir'e geri döner ve her biri ayrı "evet" ister: üç niyet satırı (`analyze_player_action`, `update_world_state_from_player`, `is_dialogue_or_emotion`; öneri "sil (yalnız sabitleme testiyle birlikte)"), başlık içe aktarma tablosundaki `game` satırı (öneri "sil"; "10. sil" bu tablo yazılmadan önce verildi), her yama hedefi ve her yeniden dışa vurum satırı. Silme Görev 8'de, oynayıştan sonra yapılır; push, PR ve birleştirme ayrıca onay ister. Güncelleme (task/temizlik-2-20261124): üç niyet satırı (`analyze_player_action`, `update_world_state_from_player`, `is_dialogue_or_emotion`) bu dalda silindi (ledger Ruling).

## Kullanılmayan başlık içe aktarmaları (`game.py`)

643 yeniden dışa vurum satırı: silinmez (yüzey).

`game.py`'nin hiç okumadığı 45 başlık içe aktarması (ruff F401 toplamı 688 = 643 + 45). "yama hedefi": testler `game.<ad>` yamalıyor (`engine_split_locks/patch_census.json`), silmek için "evet" seçeneği yok. "yüzey kaydı": ad `engine_split_locks/surface.json` içinde, yani `game.<ad>` herkese açık yüzeyin parçası. "dış okuyucu": `game.py` dışında `game.<ad>` okuyan yer sayısı (koşul 1'in taraması ve dışlamaları).

| ad | modül | yama hedefi | yüzey kaydı | dış okuyucu | öneri |
|---|---|---|---|---|---|
| `game` | `game` | hayır | hayır | yok | sil |
| `ollama` | `ollama` | evet | evet | 374 (ör. `ai-dnd/api/ollama_adapter.py:461`) | kalsın (testler `game.ollama` yamalıyor) |
| `unicodedata` | `unicodedata` | hayır | evet | yok | kalsın (yüzey kaydı) |
| `collections` | `collections` | hayır | evet | yok | kalsın (yüzey kaydı) |
| `refusals` | `refusals` | hayır | evet | yok | kalsın (yüzey kaydı) |
| `tr_case` | `tr_case` | hayır | evet | yok | kalsın (yüzey kaydı) |
| `tr_names` | `tr_names` | hayır | evet | yok | kalsın (yüzey kaydı) |
| `hashlib` | `hashlib` | hayır | evet | yok | kalsın (yüzey kaydı) |
| `tempfile` | `tempfile` | hayır | evet | yok | kalsın (yüzey kaydı) |
| `contextlib` | `contextlib` | hayır | evet | yok | kalsın (yüzey kaydı) |
| `uuid4` | `uuid` | evet | evet | 7 (ör. `ai-dnd/api/tests/test_engine_parts_pilot.py:1285`) | kalsın (testler `game.uuid4` yamalıyor) |
| `find_quest` | `quest_catalog` | hayır | evet | yok | kalsın (yüzey kaydı) |
| `adventure_director` | `adventure.director` | hayır | evet | yok | kalsın (yüzey kaydı) |
| `incident_projection` | `incidents.projection` | hayır | evet | yok | kalsın (yüzey kaydı) |
| `local_dialogue` | `local_dialogue` | hayır | evet | 1 (ör. `ai-dnd/api/tests/test_npc_dialogue_stage_a_diagnostic.py:526`) | kalsın (yüzey kaydı; 1 dış okuyucu) |
| `local_exploration` | `local_exploration` | hayır | evet | yok | kalsın (yüzey kaydı) |
| `held_weapon` | `held_weapon` | hayır | evet | yok | kalsın (yüzey kaydı) |
| `monster_sense` | `monster_sense` | hayır | evet | yok | kalsın (yüzey kaydı) |
| `name_catalog` | `name_catalog` | hayır | evet | yok | kalsın (yüzey kaydı) |
| `campaign_time` | `campaign_time` | hayır | evet | 4 (ör. `ai-dnd/api/tests/test_roadmap_k04.py:130`) | kalsın (yüzey kaydı; 4 dış okuyucu) |
| `scheduled_events` | `scheduled_events` | hayır | evet | yok | kalsın (yüzey kaydı) |
| `timed_gameplay` | `timed_gameplay` | hayır | evet | 1 (ör. `ai-dnd/api/tests/test_combat_lifecycle.py:167`) | kalsın (yüzey kaydı; 1 dış okuyucu) |
| `combat_lifecycle` | `combat_lifecycle` | hayır | evet | 5 (ör. `ai-dnd/test_regression.py:442`) | kalsın (yüzey kaydı; 5 dış okuyucu) |
| `action_economy` | `action_economy` | hayır | evet | 4 (ör. `ai-dnd/api/serializers.py:857`) | kalsın (yüzey kaydı; 4 dış okuyucu) |
| `initiative` | `initiative` | hayır | evet | yok | kalsın (yüzey kaydı) |
| `weapon_attack` | `weapon_attack` | hayır | evet | 2 (ör. `ai-dnd/api/tests/test_dragonborn_breath.py:53`) | kalsın (yüzey kaydı; 2 dış okuyucu) |
| `effect_targeting` | `effect_targeting` | hayır | evet | yok | kalsın (yüzey kaydı) |
| `attributed_claims` | `attributed_claims` | hayır | evet | yok | kalsın (yüzey kaydı) |
| `effect_lifecycle` | `effect_lifecycle` | evet | evet | 8 (ör. `ai-dnd/api/tests/test_roadmap_k04.py:95`) | kalsın (testler `game.effect_lifecycle` yamalıyor) |
| `interaction_adventure` | `interaction_adventure` | hayır | evet | 21 (ör. `ai-dnd/api/tests/test_ai_freedom_resolution_boundary.py:159`) | kalsın (yüzey kaydı; 21 dış okuyucu) |
| `money_owner` | `money_owner` | hayır | evet | yok | kalsın (yüzey kaydı) |
| `talk_front` | `talk_front` | hayır | evet | yok | kalsın (yüzey kaydı) |
| `npc_statements` | `npc_statements` | hayır | evet | 1 (ör. `ai-dnd/api/tests/test_engine_parts_pilot.py:902`) | kalsın (yüzey kaydı; 1 dış okuyucu) |
| `WEAPONS` | `weapon_catalog` | hayır | evet | 26 (ör. `ai-dnd/api/tests/test_combat_lifecycle.py:79`) | kalsın (yüzey kaydı; 26 dış okuyucu) |
| `dataclass` | `dataclasses` | hayır | evet | yok | kalsın (yüzey kaydı) |
| `field` | `dataclasses` | hayır | evet | yok | kalsın (yüzey kaydı) |
| `Optional` | `typing` | hayır | evet | yok | kalsın (yüzey kaydı) |
| `List` | `typing` | hayır | evet | yok | kalsın (yüzey kaydı) |
| `Dict` | `typing` | hayır | evet | yok | kalsın (yüzey kaydı) |
| `get_expertise_choice_count` | `api.dnd_2024_rules` | hayır | evet | yok | kalsın (yüzey kaydı) |
| `resolution_action_scope` | `api.core_resolution` | hayır | evet | yok | kalsın (yüzey kaydı) |
| `resolve_attack_roll` | `api.core_resolution` | hayır | evet | yok | kalsın (yüzey kaydı) |
| `resolve_death_save` | `api.core_resolution` | hayır | evet | yok | kalsın (yüzey kaydı) |
| `resolve_saving_throw` | `api.core_resolution` | evet | evet | 2 (ör. `ai-dnd/api/tests/test_engine_parts_pilot.py:1514`) | kalsın (testler `game.resolve_saving_throw` yamalıyor) |
| `resolve_skill_check` | `api.core_resolution` | hayır | evet | yok | kalsın (yüzey kaydı) |

`game` satırı: `game.py` doğrudan çalıştırılınca (`if __name__ == "__main__":` bloğu) motoru `game` adıyla yükleyen satır. `game_parts/__init__.py` ve `game_parts/terminal.py` de `import game` yapıyor, bu yüzden dört koşula göre silinebilir görünüyor. Doğrulamadım: `game.py`'yi bu satır olmadan çalıştırıp denemedim.
