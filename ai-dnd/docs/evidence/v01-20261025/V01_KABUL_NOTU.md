# v0.1 Sahne Doğruluğu: Kabul Notu

Tarih: 2026-10-25. Kaynak: `dev/ai-dnd` `2d02a5e`. Çalışma ağacı: `AI-DND-v01-scene-truth` (`cursor/v01-scene-truth-20261025`). Hiçbir şey commit veya push edilmedi.

## Hüküm: **sınırlı kazanım**

Üç gerçek kusur sentetik olarak yeniden üretildi, kırmızı testle sabitlendi ve düzeltildi. Baseline'a göre regresyon yok. Canlı olay için **"düzeltildi" iddiası yoktur**: Faz 0 sonucu UNRESOLVED kalıyor (H01–H05 kaydı ve çalışan sürecin kaynağı kanıtlanamadı, canlı modele tur gönderilmedi).

## Değişenler

| Kusur | Sahip | Düzeltme | Kanıt testi |
|---|---|---|---|
| F3: oturma, gizli/keşfedilmemiş özelliği seçip adını sızdırıyordu | `game.py` `resolve_scene_seating` (tek oturma sahibi, `living_world.visible_features` ile süzer) | Gizli özellikler aday değil. Aynı adlı birden çok yer için netleştirme sorusu, yer yoksa dürüst "oturabileceğin yer yok". | `test_hidden_seat_target_is_not_selected_or_disclosed`, `test_same_name_tables_require_clarification` |
| F4: birleşik komutta oturma adımının işleyicisi yoktu | `grounded_action._do_sit`, `HANDLERS["sit"]` | Aynı sahibi çağırır. Başarı tamamlanır. Ret `blocked` olur ve zincir durur. Önceki giriş korunur. | `test_compound_open_door_completes_entry_and_seat`, `test_compound_keeps_entry_before_missing_seat`, `test_compound_stops_at_locked_entry` |
| F2: alıntı içindeki "otur" oyuncuyu oturtuyordu | `living_world.classify_scene_action` | Oturma tespiti yalnız alıntı dışı metinde (`_text_outside_quotes`). | `test_quoted_sit_command_is_speech_not_action` |

Üretim farkı: `game.py` +54/−38 (yalnız oturma dalının çıkarılması, CRLF korundu), `grounded_action.py` +12, `living_world.py` +4/−4. Diff: `v01-production.diff`.

## Doğrulama

- Yeni testler: `test_scene_truth_contract` (8) ve `test_scene_compound_contract` (6): **14/14 geçti**. Önce kırmızıydı: hidden-seat, compound açık kapı, compound eksik yer, alıntı komutu.
- 33 günlük kapı: baseline 32/33, sonra 32/33. Tek hata `test_runner_inventory`, ikisinde de birebir 55 failure / 11 error / 2 skipped. Kapı bazında fark yok (`after-gates.jsonl`).
- `test_lr00_grounded_human` 38/38, `test_lr00_p1_intent` 21/21 (`after-extra.txt`).
- `test_campaign_api`: baseline ile aynı 15 failure + 5 error. 12 benzersiz test kimliği kümesi birebir aynı. Yeni regresyon yok.
- `test_wave3_interaction_modes`: baseline'da da 9 hata (`No server authenticator is configured`). Ortam kaynaklı, değişmedi.
- `git diff --check` temiz.
- Bağımsız inceleme (python-reviewer): blokaj yok.

## Bilinen sınırlar (kabul edilmiş, bu fazda kapatılmadı)

1. **Alıntı içi noktalama:** `Garsona 'masaya otur, lütfen' diyorum`. `affirmative_scene_intent` cümleyi virgül/noktada bölüyor, alıntı kapanmadan kalıyor ve "otur" komut sayılabiliyor. Düzeltme cümle bölme sırasını değiştirmeyi gerektirir. Bu, Wave3 konuşma mekaniğine dokunmak olur ve sahip kuralıyla yasak. Ayrı bir karar belgesiyle ele alınmalı.
2. **Adı verilen ama eşleşmeyen/gizli hedef:** `Gizli kuytuya oturuyorum` oyuncuyu ilk görünür yere oturtuyor (eski davranış, sızıntı yok). "Oyuncu bir ad verdi mi" ayrımı ayrı karar ister.
3. **İmplicit kalkma yok:** `oturup ... gidiyorum` oyuncuyu `seated` bırakarak taşıyabilir. Kapsam dışı.
4. **Zayıf test kenarları:** `test_expired_entry_reference_does_not_narrate_arrival` iki sonucu kabul ediyor. `discovered: False` ayrı bir test almadı.
5. **Canlı olay:** F5 (gözlem turunun modeli çağırması) aday, kanıtsız. Canlı kapanış için Faz 0'ın H01–H05 kaydı ve süreç kimliği gerekir.

## Sonraki adım (karar bekliyor)

v0.2 (Faz 3–6) başlamadı. Her faz önce karar belgesi ister. Commit/push için açık onay gerekir.
