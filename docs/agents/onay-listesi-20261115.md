# Onay listesi (Kadir kararları, 2026-11-15)

Kaynak: Kadir'in 2026-11-15 kararları, madde 16-21. Defter: `docs/agents/debt-register.md`.

## 1. PR #70 (para, D-096) içinde yeniden yazılan testler

PR #70 = `task/yuk-para-20261115`, birleşme `3576eeaf`. Dört dosyada var olan testler değişti (`ai-dnd/api/tests/` altında). Ortak neden D-096: oyuncunun verdiği hediye ya da bahşişi NPC "alırım" demediyse kart açılırsa kart yalnızca onayda reddedilebilirdi (ölü kart). Artık kart hiç açılmaz, neden o turda söylenir ("alacağını söylemedi"). Beklenti gevşemedi, yön değişti: "kart açılır, onayda reddedilir" yerine "kart açılmaz, ret nedeni söylenir, kese ve defter değişmez".

Sayı notu: Kadir'in yazdığı "13+6" sayısını depoda ve PR #70'te bulamadım. Aşağıda yardımcı işlev yoluyla etkilenenler dahil 15 test sayıyorum. "altına/altında/altından" ve "6 soyut özne" değişiklikleri PR #70'te değil, PR #80'te (D-209, D-210; bkz. bölüm 2).

Onay durumu: Bu 15 test için Kadir'in ayrı bir onay cümlesi yok. Onay bekliyor.

| Dosya | Test | Eski beklenti | Yeni beklenti | Kadir onayı |
|---|---|---|---|---|
| test_compound_line.py | `test_walk_then_pay_opens_one_card_for_the_coin` | han turunda 5 gümüş bahşiş için bir "prepared" kart açılır, `max_total_cp` 50 | kart açılmaz (`economic_offer` yok), "alacağını söylemedi" bir kez söylenir, "prepared" sayısı 0, kese aynı, barmenin `coin_responses` değeri `offer:50: unknown` | bekliyor |
| test_compound_line.py | `test_walk_then_pay_by_name_opens_the_same_card` | isimle verilen bahşiş de bir kart açar (50 cp, kese aynı) | aynı yeni beklenti (ortak denetim `assert_tip_answered_without_a_dead_card`) | bekliyor |
| test_compound_line.py | `test_walk_then_pay_by_name_after_a_comma_and_sonra` | yukarıdakiyle aynı eski beklenti | aynı yeni beklenti | bekliyor |
| test_dilim3d_money.py | `test_a_tip_named_twice_is_given_once` (`tips_once` yardımcısı) | okumada NPC sözü yok, bahşiş kartı açılır (5 cp, kese 100) | okumaya "NPC alır" (`coin_answer: takes`) eklendi; kart yine açılır, ardından onay adımı eklendi: kese 95, kart yok | bekliyor |
| test_dilim3d_money.py | `test_a_turkish_tip_named_twice_is_given_once` (`tips_once` yardımcısı) | aynı | aynı yeni beklenti | bekliyor |
| test_economic_spoken_consent.py | `test_validated_offer_without_semantic_reply_cannot_debit` | defterde bir işlem, `net_debit_cp` 0, `npc_consent_required` | defterde işlem yok, "prepared" kart yok, `coin_responses` `offer:5: unknown` | bekliyor |
| test_economic_spoken_consent.py | `test_unknown_response_cannot_authorize_debit` (`run_consent` yardımcısı) | kart açılır, onayda reddedilir | senaryo 2 adımda biter: kart yok, kese 100, metinde "alacağını söylemedi" | bekliyor |
| test_economic_spoken_consent.py | `test_model_injected_speaker_cannot_authorize_debit` (`run_consent`, `malformed`) | aynı eski beklenti | aynı yeni beklenti | bekliyor |
| test_economic_spoken_consent.py | `test_unknown_reply_opens_no_card_and_says_why` (eski ad `test_unknown_reply_card_cannot_apply_and_warns_may_refuse`) | durum "prepared", `may_refuse` doğru, çözümde `refused`/`npc_consent_required`/0 | hazırlıkta hemen `refused`/`npc_consent_required`, `offer` yok, mesajda "alacağını söylemedi", dünya durumu değişmez | bekliyor |
| test_economic_spoken_consent.py | `test_unclear_reply_still_holds_after_turn_advance` (eski ad `test_consuming_refusal_cannot_be_retried_after_turn_advance`) | iki turda kart onaylanır, ikisi de `refused`, borç 0 | iki turda da hazırlık `refused`, kart yok, kese değişmez, defterde `operations` yok | bekliyor |
| test_economic_spoken_consent.py | `test_saved_reply_survives_reload` | yeniden yüklemeden sonra kart çözülür ve reddedilir | yeniden yüklemeden sonra hazırlık doğrudan `refused`, kart yok | bekliyor |
| test_economic_spoken_consent.py | `test_deterministic_reply_cannot_silently_drop_pending_gift` | bekleyen hediye için bir kart açılır, çözümde reddedilir | kart açılmaz; sonuç `refused`/`npc_consent_required`; anlatıda "alacağını söylemedi"; bekleyen öneri temizlenir | bekliyor |
| test_room_purpose_routing.py | `test_compound_gift_mentions_room_but_stays_gift` | kişi sözü yok, hediye kartı açılır | okumaya "NPC alır" (`TAKES`) eklendi, kart yine açılır (5 cp, "Hediye") | bekliyor |
| test_room_purpose_routing.py | `test_tip_amount_comes_from_words_not_model_figure` | kişi sözü yok, bahşiş kartı 5 cp | `TAKES` eklendi, kart yine 5 cp "Bahşiş"; tutar yine sözcüklerden gelir | bekliyor |
| test_room_purpose_routing.py | `test_disabled_turn_does_not_skip_next_enabled_economic_read` | hediye okuması sözsüz | okumaya `TAKES` eklendi; denetimler aynı | bekliyor |

Not: `run_purpose` yardımcısına yalnız isteğe bağlı `speech` bağımsız değişkeni eklendi; kendi başına beklenti değişmedi.

## 2. PR #80 (D-209, D-210) süzgeç değişiklikleri (gevşetme olabilir)

| Madde | Ne değişti | Kadir onayı |
|---|---|---|
| D-209 | para iddia süzgecinde "altına/altında/altından" artık para sayılmaz ("altın", "altını", "altınlar" sayılır). Gevşetme: "Kesenden altından üçü düşüyor" gibi nadir bir yalan cümle kalabilir; para kaydı etkilenmez. | onaylandı (2026-11-15) |
| D-210 | anlatı büyüsü iddia geçidi 6 soyut özne (seçim, karar, zafer, tercih, sıra, söz) ve "doğru" yönünde artık iddia görmez. Gevşetme: listede olmayan soyut özne yine Python satırına düşer, eşya etkilenmez. | onaylandı (2026-11-15) |

## 3. Öteki onay maddeleri

| Madde | Konu | Defter satırı | Durum |
|---|---|---|---|
| 17 | Geri Al testinde `wrong_turn` yerine `wrong_time` (`test_skill_result_pipeline_regression.py`, Geri Al durum bozma durumlarından biri; D-139 kaydı) | D-139 | onaylandı (Kadir, 2026-11-15) |
| 18 | D-094 gizlenme testleri | D-094 (kural D-171) | onaylandı (Kadir, 2026-11-15) |
| 19 | D-194: izinsiz yolda telemetri kaynağı tutulmaz | D-194 | onaylandı (Kadir, 2026-11-15) |
| 20 | D-214: "henüz motorda yok", yuva harcanmaz | D-214 | onaylandı (Kadir, 2026-11-15) |
| 21 | D-203: görev kabul edilmeden toplanan delil | D-203 | onaylanmadı. Karar: delil silinmez, saklanır, görev kabul edilince sayılır; test bu davranışa göre yazılır |
| 2 | D-166: C5 testleri eşit sıkılıkla yeniden yazılacak | D-166 | yeniden yazım yapılınca bu listeye eklenir |

Doğrulamadım: testlerin dosyalardaki şu anki hâli yerine PR #70 birleşme farkına (`git diff 3576eeaf^1 3576eeaf`) baktım; "13+6" sayısının kaynağı bulunamadı.
