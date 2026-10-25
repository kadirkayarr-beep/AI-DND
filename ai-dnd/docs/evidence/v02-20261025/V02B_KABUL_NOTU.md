# v0.2b Kabul Notu: K3, Faz 4, Faz 5

Tarih: 2026-10-25. Dal: `cursor/v02-consistent-world-20261025`. Onay: kullanıcı, "bunları da onaylıyorum" (K3, Faz 4, Faz 5/K4).

## Hüküm: **sınırlı kazanım, kod seviyesinde doğrulandı**. Canlı olay UNRESOLVED; canlı model çağrısı yapılmadı.

| Faz | Sahip | Ne yapıldı | Kanıt |
|---|---|---|---|
| 3 (K3) | `game.py` (yalnız şema + doğrulama) | `DM_RESPONSE_SCHEMA` isteğe bağlı `player_line`, `feature_refs`; `required` değişmedi. Geçersiz/gizli ref deterministik yedeğe düşer. Oyuncunun yazdığı alıntı modeli yener. Model satırı yalnız oyuncunun yazdığı metnin parçası olabilir. | `test_scene_representation_contract` (9) |
| 4 | `equipment_economy.py` | `surface_items`, `feature_marks`, `feature_mark_sequence`; `/item place`, `/item mark`, `/item take` (yüzey), `/item list` yüzeyleri gösterir; en çok 8 eşya, 4 iz, 120 karakter, tek satır yazdırılabilir metin; iz kimliği tekrar kullanılmaz; eski kayıtlar değişmeden yüklenir. | `test_scene_surface_persistence` (14) |
| 5 (K4) | `scheduled_events.py` + `equipment_economy.py` | `mark_remove` ve `surface_item_custody` etkileri; gizli, `NON_INTERRUPTIVE`, nedeni oyuncuya görünmez. Yalnız eylemci NPC'ye opak `witnessed:<id>` notu. Eylemci canlı ve olay mekânında değilse hiçbir şey değişmez. Kimlik korunur, kopya yok. | `test_scene_small_events_contract` (11) |

## Bağımsız inceleme (alt ajan, salt okuma) ve sonuç

Yüksek önemde bulgu yok. Düzeltilenler: model `player_line` değerinin korumaları aşması (artık oyuncu metninin parçası olmak zorunda); canlılık denetiminin `npc_at` ile ayrışması (tek `npc_can_act`); `witnessed:` notunun mutasyondan sonra yazılması (önce kanıtlanıyor); `/item list` yüzeyleri göstermiyordu; `mark_id` yeniden kullanımı; kontrol karakterli iz metni; kayıtta özellik mekânı denetimi ve `event_id` uzunluğu; benim çift eklediğim ölü `elif` bloğu (kaldırıldı); üç `.md` dosyasının CRLF kaybı (geri yüklendi). Boş geçen üç test sıkılaştırıldı (ikinci uygulama gerçekten izleniyor, gizli ref için kontrol testi, uydurma satır testleri).

## Doğrulama (v0.1 baseline ile aynı)

- 33 kapı: 32/33. Tek hata önceden var olan `test_runner_inventory` (55 failure / 11 error / 2 skipped, birebir aynı). `v02d-gates.jsonl`.
- `test_ai_pipeline_port` şema anahtar kümesi onaylı K3 alanlarına güncellendi; `required` kümesi ayrıca sabitlendi.
- `test_campaign_api`: 15 failure + 5 error, 12 benzersiz kimlik baseline ile birebir aynı (`v02d-campaign-api-failures.txt`).
- `lr00` 38/38 ve 21/21. `test_wave3_interaction_modes` baseline'daki 9 ortam hatası. `test_equipment_economy` 32/32, `_http` 3/3.
- `test_equipment_native::test_real_conversation_still_requires_conversation_proposal` dokunulmamış tabanda da düşüyor (önceden var).
- `git diff --check` temiz. `game.py`, `equipment_economy.py`, `scheduled_events.py` tamamen CRLF; yeni testler LF (kardeş `test_scene_*` gibi).

## Açık sınırlar

- Olayı oyun içinde kendiliğinden başlatan tetikleyici yok; yalnız sunucu tarafı `register_event`. "Oyuncu ayrıldıktan sonra" kuralı, olayın ufuk dışındayken işlenmemesi ve dönüşte ilk işlemede gerçekleşmesiyle sağlanıyor.
- NPC paketi yalnız opak `witnessed:<id>` işaretini taşır; neden içeriği kasıtlı yok, yani NPC nedeni henüz sözle anlatamaz.
- İstem metni modele `player_line`/`feature_refs` üretmesini söylemiyor; alanlar yalnız geldiğinde doğrulanır.
- Yazılmayan Faz 5 testleri: `npc_mistake_stays_attributed_not_canon`, `model_contradiction_not_reclassified_as_intentional_lie`, `secret_word_in_harmless_smalltalk_does_not_block_speech`. `incidents/*` değiştirilmedi.
- Doğal dille yerleştirme yok; yalnız `/item` komutları. `free_v1` kipi kapsam dışı. v0.1 sınırları (alıntı içi noktalama, adı verilen gizli hedef, noktalı İ) aynen duruyor.
- Faz 7 (gerçek A–H kabulü) başlamadı; yetkili model erişimi ve değişmeyen aday revision gerekir.
