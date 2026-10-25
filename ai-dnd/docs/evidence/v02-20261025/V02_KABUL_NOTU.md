# v0.2 Tutarlı Dünya: Kabul Notu (kısmi)

Tarih: 2026-10-25. Taban: v0.1 commit `b2ea58a`. Dal: `cursor/v02-consistent-world-20261025`.

## Hüküm: **sınırlı kazanım**. Faz 3 ve 6 kısmen, Faz 4 ve 5 karar bekliyor.

| Faz | Durum | Ne yapıldı | Belge |
|---|---|---|---|
| 3 | Nesne iddiası yarısı uygulandı, oyuncu sözü/anlatıcı alanı **K3 kararı bekliyor** | 8 test, 1 gerçek kusur düzeltildi | [PER_MODE_BINDING_DECISION.md](PER_MODE_BINDING_DECISION.md) |
| 4 | **Uygulanmadı.** Yeni kalıcı alan gerekiyor | Karar belgesi ve öneri | [SURFACE_OWNER_DECISION.md](SURFACE_OWNER_DECISION.md) |
| 5 | **Uygulanmadı.** K4 onaylı küçük olay kümesi gerekiyor, Faz 4'e bağlı | Karar belgesi ve öneri | [SMALL_CHANGE_OWNER_DECISION.md](SMALL_CHANGE_OWNER_DECISION.md) |
| 6 | Mevcut arayüzlerle uygulandı | 4 sözleşme testi, kusur bulunmadı | aşağıda |

## Üretim değişikliği (tek)

`game.py` `create_local_feature`: mevcut kayıt yeniden kullanılırken artık yalnız `living_world.visible_features` içindeyse geri verilir. Gizli özellikle aynı adlı üst düzey öneri, gizli kaydı geri vermiyordu; bu, gizli adın kayıtlı nesne sayılıp anlatıma geçmesine yol açabilirdi. Çağrı yerleri `None` dönüşünü zaten ret olarak işliyor. CRLF korundu.

## Yeni testler (26, hepsi yeşil)

- `test_scene_claim_contract` (8): reddedilen iddia ekranda/`campaign_history`/asistan mesajlarında yok, doku korunur, oyuncu iddiası olgu olmaz, kimlik yeniden kullanımı, gizli çakışma, 16 sınırı, paket bağlama.
- `test_scene_transaction_contract` (4): replay tek commit ve aynı makbuz (ikinci zar yok), aynı id farklı gövde 409 `action_id_conflict`, eşzamanlı iki istek tek commit, başka kampanya geçmişi etkilenmez.
- v0.1'den: `test_scene_truth_contract` (8), `test_scene_compound_contract` (6), yeniden koşuldu, yeşil.

Faz 6'da zaten kapsanan iki durum kopyalanmadı: kayıt öncesi hata geri alma (`test_campaign_api`, `fail_once`) ve anlatıcı hatası güvenli yedeği (`test_f04_frozen_narrator_faults`). Faz 4'te eşya kimliği, bırakma/alma ve kayıt-yükleme de zaten testli (`test_equipment_economy`).

## Doğrulama (v0.1 baseline'ı ile aynı)

- 33 günlük kapı: 32/33, tek hata önceden var olan `test_runner_inventory` (55 failure / 11 error / 2 skipped, birebir aynı). Kapı bazında fark yok (`v02-gates.jsonl`).
- `test_campaign_api`: 15 failure + 5 error, 12 benzersiz kimlik kümesi baseline ile birebir aynı.
- `test_lr00_grounded_human` 38/38, `test_lr00_p1_intent` 21/21. `test_wave3_interaction_modes` baseline'daki gibi 9 ortam hatası.

## Sınırlar

- Canlı olay UNRESOLVED (v0.1 notu geçerli). v0.2 canlı model çağrısı yapmadı.
- `free_v1` kipi, devredilen şaka/alıntı/saldırı makbuzu testleri, noktalı büyük İ ve 240/400 kesme sınırı testleri kapsam dışı (ayrıntı PER_MODE_BINDING_DECISION.md).
- v0.1'in iki açık sınırı (alıntı içi noktalama, adı verilen gizli hedef) aynen duruyor.
- Faz 7 (gerçek A–H kabulü) başlamadı: yetkili model erişimi ve Faz 4–5 sonrası aynı aday revision'ı gerekir.

## Sizden beklenenler

1. **K3:** `player_line` / `feature_refs` alanları eklensin mi?
2. **Faz 4:** `surface_items` / `feature_marks` şeması onaylanıyor mu?
3. **K4:** Faz 5 başlangıç kümesi (`mark_cleaned`, `item_custody_change`) uygun mu?
