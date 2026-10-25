# Masa Yokluğu Tetikleyicisi: Tasarım

Tarih: 2026-10-25. Dal: `cursor/v02-consistent-world-20261025`. Onay: kullanıcı, "uygundur". Sözlü kararlar: değişiklik dönüşte olur; önce en eski iz, iz yoksa ilk masa eşyası; dönüşte canlı NPC yoksa hiçbir şey olmaz.

## Amaç

`mark_remove` ve `surface_item_custody` bugün yalnız `register_event` ile kuruluyor. Bu tasarım, oyuncu masalı bir mekândan ayrılınca tek gizli olayı kurar ve mekâna dönünce bir kez uygular. Yeni zamanlayıcı yok. Olay oyuncu uzaktayken dünyayı değiştirmez.

## Tetik

Konum değişimi (`game.py`, `previous_location != location_id`) ayrılınan mekân için `scheduled_events.arm_table_absence(world, previous_location)` çağırır. Bu, varıştaki mevcut `process_events` çağrısından önce olur. `game.py` kuralı bu iş akışı için kullanıcı tarafından gevşetilmiştir. Yeni kural `scheduled_events.py` içindedir. Eşya ve iz mutasyonu yalnız `equipment_economy.apply_scheduled_surface_effect` içindedir.

`arm_table_absence` olay kurmaz eğer:

- ayrılınan mekânda, o mekâna ait bir özellikte iz veya yüzey eşyası yoksa,
- o mekân için durumu `PENDING` olan bir `table_absence` olayı zaten varsa.

İkinci ayrılış ikinci olay eklemez.

## Olay

Tek etki: `{"kind": "table_absence"}`. Görünürlük `hidden`, davranış `NON_INTERRUPTIVE`, `aftermath_visible` yok, karar yok. `summary` ve `aftermath` boştur. `player_observed` yanlış kalır, `player_known_summary` boş kalır. Pencere ayrılış anındaki `elapsed_seconds` ile açılır ve 86400 saniye sonra kapanır. Süre dolunca olay uygulanmadan `EXPIRED` olur. `event_id` `absence:` artı artan bir sayıdır ve 140 karakterin altındadır.

`table_absence` gizli ve sessiz olmak zorundadır. Aksi `ValueError`. Başka bir etki türü bu yolla kurulamaz.

## Dönüşte uygulama

Oyuncu o mekâna varınca (`observation.kind == arrival` ve `location_id` olayın mekânı) pencere açıksa olay bir kez çözülür. Çözüm `window_end` beklemez. Sonuç `known` listesine ve `public_events` çıktısına girmez.

`equipment_economy.resolve_table_absence(world, location_id, event_id)`:

1. Mekândaki ilk `npc_can_act` NPC seçilir. Yoksa `False`.
2. O mekândaki özelliklerde en eski iz seçilir (`turn`, sonra `mark_id`). Varsa mevcut `mark_remove` etkisi uygulanır.
3. İz yoksa, özellik kimliği sırasındaki ilk yüzeyin ilk eşyası seçilir ve mevcut `surface_item_custody` etkisi uygulanır.
4. İkisi de yoksa `False`.

`True` ise olay `OCCURRED` olur ve `effects_applied` 1'dir. `False` ise dünya değişmez, olay `EXPIRED` olur ve bu ayrılışın hakkı biter. İkinci varış aynı olayı tekrarlamaz.

Oyuncu bilgisi, kapılar, para, yerler ve anlatı nedeni değişmez. Yalnız seçilen NPC `witnessed:<event_id>` notunu alır.

## Testler

`test_return_removes_oldest_mark_once`, `test_return_moves_first_item_when_no_mark`, `test_return_without_npc_changes_nothing`, `test_second_departure_does_not_stack`, `test_absence_cause_stays_out_of_player_knowledge`, `test_nothing_to_change_arms_no_event`.

## Doğrulama

Testler önce kırmızı yazılır. Sonra 33 kapı, `test_campaign_api` kimlik kümesi, `lr00` ve `test_scene_small_events_contract` tabanla aynı olmalıdır. Birleştirme yok. Canlı olay UNRESOLVED kalır.

## Kapsam dışı

Olasılık, rastgele NPC, birden fazla iz veya eşya, oyuncu uzaktayken mutasyon, doğal dil komutu, istem metni, `free_v1`.
