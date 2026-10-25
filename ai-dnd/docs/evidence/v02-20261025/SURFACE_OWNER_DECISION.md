# Faz 4 Karar Belgesi: Masadaki İz ve Eşyanın Tek Kimlikle Devamı

Durum: **onaylandı ve uygulandı** (kullanıcı: "bunları da onaylıyorum"). Sahip: `equipment_economy.py` (`surface_items`, `feature_marks`, `place`/`mark`/`take`, `validate_world`). Kanıt: `api/tests/test_scene_surface_persistence.py` (11 test). Doğal dil ile yerleştirme yok; yalnız `/item` komutları. Aşağıdaki "Karar gereken" bölümü tarihsel kayıttır.

## Mevcut durum (kanıtlı)

- Eşya kimliği, bırakma/alma ve kayıt-yükleme zaten testli: `test_equipment_economy.test_identity_drop_take_and_equipment_cleanup`, `test_legacy_and_record_save_roundtrip`, `test_duplicate_ids_reject_without_partial_migration`.
- Sahip: `equipment_economy.containers(world)`, `move`, `execute`, `validate_world`. Yer eşyası `world_state["ground_items_by_location"][location]` içinde.
- **Eksik:** eşyayı bir masa özelliğine (feature) bağlayan ilişki ve masa üstü "iz" kaydı yok. Prose ile "masaya bıraktım" demek hiçbir şey yazmaz, yazmamalı.

## Önerilen dar genişletme (ikinci envanter yok)

`equipment_economy` yeni bir kap türü bilir: **yüzey kabı**.

```json
"surface_items": { "feature_001": ["item_0007"] },
"feature_marks": { "feature_001": [ {"mark_id": "mark_001", "text": "Kil bardağın dibinde bir halka", "turn": 12} ] }
```

- `surface_items` yalnız mevcut `item_id` taşır, kopya üretmez. `containers(world)` bunu da yield eder, böylece "tüm kaplarda item_id tam 1 kez" kuralı otomatik uygulanır.
- Hedef yüzey, `living_world.visible_features` içinde ve oyuncunun bulunduğu konumda olmalı. Gizli veya uzak yüzey: reddedilir, transfer olmaz.
- Aynı adlı iki masa farklı `feature_id` ile ayrı kalır.
- `feature_marks`: en fazla 4 iz/özellik, 120 karakter, yalnız metin. İz altın, kilit durumu veya bilgi kaynağı üretemez.
- Eski kayıt: iki alan yoksa boş kabul edilir, yükleme değişmez.
- Kayıt hatası: mevcut işlem sınırı geri alır, envanter eski haline döner.

## Gereken testler (karar sonrası, önce kırmızı)

`test_place_existing_item_moves_one_identity`, `test_surface_roundtrip_retains_item_and_mark`, `test_take_clears_surface_relation_without_cloning`, `test_hidden_remote_surface_rejected_without_transfer`, `test_same_name_tables_keep_distinct_items`, `test_failed_surface_save_restores_inventory`, `test_mark_cannot_grant_gold_unlock_or_change_lore`, `test_rejected_gift_not_presented_as_received`.

## Karar gereken

1. `surface_items` / `feature_marks` alanları bu adlarla eklensin mi?
2. İz sınırı (4 iz, 120 karakter) uygun mu?
3. Oyuncu "masaya bırak" komutu hangi sözcüklerle tanınsın (yeni sözlük mü, mevcut `/item drop` ailesine hedef mi)?

Onay gelmeden `equipment_economy.py` ve kayıt şeması değişmez.
