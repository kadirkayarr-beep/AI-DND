# Dilim 1 ara devir — Jarvis, 2026-11-05

Güncel: J-040 ile açık pazarlık-niyeti regresyonu kapandı;297 odaklı OK. Bağımsız inceleme ve genel kapılar bekliyor; hazır değil.

Durum: uygulama ve odaklı testler ilerledi; genel kapılar, bağımsız inceleme ve oynayış bekliyor. Görev 23 kısmi; “Dilim 1 hazır” tetiği verilmedi.
Dal: task/dilim1-money-memory-20261104; çalışma kopyası C:\Users\Kadir\Desktop\AI-DND-dilim1; uç ad231081. ae815c4f tabanından 35, Jarvis devrinin 353ce7d6 ucundan 19 yerel kod commit'i. Push/merge yok; uzak uç sorgulanmadı.

Tamamlanan uygulama ve odaklı kontroller:
- Görev 12 (36 motor yarısı/38): f77df47c, 46 test OK.
- Görev 14 (54): 9b657b87, 104/63 odaklı test OK.
- Görev 15 (56/107 sayaç): 8aedb6dc, 327/258 odaklı test OK.
- Görev 10 (103): 09ef524f + 93b739e8, son 138 test OK; iki eski satın alma-ret hatası kapandı.
- Görev 17/18 (116): 9f5c6a45,4d3d269e,449e6975,8f8122ec,6ed89bc0. Dört eski continuity hatası kapandı: üç tam şema testi onaylı yedi alanı aynen ister, bir kaynak istem-sırası hatası değişmeyen testle düzeltildi. Son hafıza seçimi 151 test OK (J-032).
- Görev 20 (37): e0e2731c; zar yolu probe geçti, oda50->45, bira4->3; günde bir indirim, ertesi gün yeniden tam fiyat. 201 test OK (J-033).
- Görev 21: 8f3fad79; yükleme onarımı, kayıt tekrarları ve Geri Al. 149 test OK,174.308s (J-034).
Sayılar örtüşen odaklı seçimlerdir; toplanmaz, genel paket sonucu değildir. Son hafıza/pazarlık/kayıt proof.json sonuçları PASS, errors/failures/skipped=0; dosya/ağ/alt süreç korumaları doğrulandı.

Hafıza kapsamı: “Dilim 1: NPC başına son 40 seçilmiş söz; tam arşiv sonraki iş.” Beş kanıt: doğru dinleyen (test_npc_told ve 24 diğer NPC adımı); kalıcı kaynak (commit/replay/yeniden kayıt); yeniden açılmış kaynak (yeni SessionManager+app); son model girdisi (yeni manager testinde FACT var, undo sonrası tüm girdilerde yok); son cevap (scripted recall cevabı) geçti. Bunlar sahte modelle motor kanıtıdır; gerçek modelin doğru sözü seçip hatırlaması kanıtlanmadı.

Yolculuk: önceki genel ölçüm 14 geçti/18 bilinen kırık/0 yeni kırık tarihsel kayıttır; yeniden çalıştırılmadı. Son genel toplam ölçülmedi. 03 altı adım geçti; 24 on altı scripted adım geçti, adım12 REAL_CHAIN_ONLY; 24r dört adımın tamamı aynı nedenle koşulmadı. Beş gerçek adım başarı sayılmadı. Kaynak sayımı 19 known_broken adımı: 4,15,21,34,35,39,40,41,47,54,111,112,115,121; test sonucu değildir. 37 artık işaretli değil; genel kapı D hâlâ bekliyor.

Kalanlar:
- Görev 11 panel onayı var; güvenli odaklı Node yolu yok. slot.sh node hedef aktarmıyor, slot_web tam kontrol ve farklı izolasyon kullanıyor. Koruma değiştirilmedi; “üstü kalsın” panel ana yolu tamamlanmadı.
- Ara kapılar13/16/19, Görev20 kapıD ve bütün dal Görev22, tam MONEY, tarayıcı, gerçek süreç restart ve gerçek model koşuları ertelendi. 35/54 eski yedek yol işaretleri kalıyor; 107 yönlendirme ve 36 gerçek zincir yarısı doğrulanmadı.
- Görev22 Step3b istem boyu ölçüldü; aşağıdaki J-036 tablosuna bak. Yan etki2/12 için ayrı bütünleşik kapanış kanıtı yok.
- Para/kayıt/Geri Al Görev10/20/21: İNCELEME BEKLİYOR (sıfır tolerans). Dilim0 Görev5 de bağımsız inceleme bekler. Önceki para dosyası kapsam kararı kullanıcı talimatıyla çözüldü; yeniden karar bekleyen engel olarak gösterilmez.
- Ürünü yalnız Kadir kabul eder; 30 dakikalık oynayış bekliyor.

## Eski test yeniden yazımları — tek yerde kayıt

Aşağıdaki Görev 7–9 satırları mevcut görev defterinden aynen alınmıştır; bu oturumun yeni değişiklikleri değildir. Bağımsız yeniden denetim iddiası yoktur.
Task 7: rewrite (D9): test_economic_dialogue.py::test_refused_gift_does_not_debit (name kept). Old: `_coin_paid` alone opened a gift card attempt (refused by the patched refuses). New: the test also sets the money owner's gift decision (new helper HandedCoin.hold_out). Expectation unchanged (no debit, no card, refusal line). Reason: coin with no decision never becomes a gift (design §3a, D29).

Task 7: rewrite (D9): test_economic_dialogue.py::test_tip_is_not_swallowed_by_currency_flag (name kept). Old: `_coin_paid` alone -> gift card. New: + gift decision. Expectation unchanged (gift card guest 5, source action turn-tip, purse same). Reason: as above.

Task 7: rewrite (D9): test_economic_dialogue.py::test_handed_coin_without_order_opens_gift_card_no_debit (name kept). Old: `_coin_paid` alone -> gift card. New: + gift decision. Expectation unchanged. Reason: as above.

Task 7: rewrite (D9): test_economic_dialogue.py::test_unconfirmed_coin_prompt_never_says_taken (name kept). Old: the speech note read `_coin_paid`. New: it reads the decision; the test sets gift(guest 5), unclear(nobody 5), gift(barman 5), room(barman 100) with the coin. Expectations unchanged ("henüz sende değil" + "5 bakır" for guest; no "bakır uzatıyor" for others; no "artık sende" after the room line; "artık sende: Mektup" kept). Reason: plan Task 7, note read from the decision.

Task 7: rewrite (D9): test_coin_writers.py::test_a_coin_handed_with_no_order_is_a_gift (name kept). Old: `_coin_paid` alone -> gift card. New: + gift decision (helper gift_held_out). Expectation unchanged (turn moves no coin; confirm pays 5 once via pay). Reason: no silent gift.

Task 7: rewrite (NOT in the D9 list, found by the run): test_coin_writers.py::test_unconfirmed_false_proposal_changes_no_relationship_or_clock (name kept). Old: `_coin_paid` alone -> gift card, then cancelled. New: + gift decision. Expectation unchanged (one card; cancel leaves purse, relationships, clock, ledger). Reason: same root as D9 (it pinned the silent gift); D9 list missed it.

Task 7: rewrite (D9): test_carius_fifth_play.py::test_a_gold_thrown_with_keep_the_change_pays_that_gold_and_buys_no_beer (name kept). Old: no deal -> Hediye card 100 ("üstü kalsın" with no order). New: front deal "tip" -> Bahşiş card 100. Amount, purse, no purchase, pay-once and second-confirm refusal unchanged; label now also checked. Reason: design D9 / decision 12 (a tip with no open offer is a Bahşiş card, not a gift).

Task 7: rewrite (D9): test_carius_fifth_play.py::test_a_tip_after_the_beer_was_bought_still_pays (name kept). Old: no deal -> Hediye card 10. New: deal "tip" -> Bahşiş card 10. Amounts (2431 -> 2421, barman 4 -> 14) and pay-once unchanged. Reason: as above.

Task 7: rewrite (D9): test_carius_fifth_play.py::test_a_coin_handed_before_a_question_still_pays (name kept). Old: no deal -> Hediye card 100. New: deal "gift" -> Hediye card 100. Expectation unchanged. Helpers renamed: gift_card -> coin_card(out, purpose, amount) (also checks the card's label), gift_operations -> coin_operations(purpose), confirm_pays_once(..., purpose). Reason: no silent gift.

Task 7: rewrite (D9): test_world_keeps_its_word.py::test_a_coin_given_leaves_the_purse_and_the_person_has_it, ::test_the_figure_in_the_line_beats_the_figure_in_the_reading, ::test_coin_with_no_figure_is_a_small_hand_not_the_readings_number (names kept). Old: no deal -> gift card. New: the scripted reading carries deal "gift". Expectations unchanged (amounts 5, 1/30/15/100, 10; confirm pays exactly that). Reason: no silent gift.

Task 8: rewrite (D9 kind, NOT in the D9 list, found by the MONEY run): test_shop_counter.py::T13ABeerIsPaidForOnce::test_a_gold_thrown_for_a_beer_opens_the_counter_and_moves_no_coin (name kept). Old: reading {speak_to, coin_cp 100} with no deal; the words "bi bira ver" opened the counter. New: the reading also carries deal goods, deal_goods bira. Expectation unchanged (shop_offer, purse and barman same, no beer, no "kesenden çıkıyor", no "artık sende", no _handed_note). Reason: with coin held out there is always a decision and the words are not read (D29); no deal + 100 cp to a server is a structural room decision (design §3a repair rule 2).

Task 8: rewrite (same root): test_shop_counter.py::T43APlateIsPaidForOnce::test_a_plate_with_coin_counted_out_opens_the_counter_and_moves_nothing (name kept). Old: reading {attempt, coin_cp 30}, no deal; words opened the counter. New: + deal goods, deal_goods yemek. Expectation unchanged (shop_offer, purse/barman same, no plate in bag). Reason: as above (30 cp with no deal is unclear, structural).

Task 8: rewrite (same root): test_carius_fifth_play.py::OneCoinOneTruth::test_a_gold_put_down_with_a_beer_order_only_opens_the_counter (name kept). Old: reading {speak_to, coin_cp 100}, no deal. New: + deal goods, deal_goods bira, keep_change true (the line says "üstü kalsın"). Expectation unchanged (shop_offer, purse 2435, barman 0). Reason: as above (no deal + 100 cp was a room card).

Task 8: rewrite (same root): test_world_keeps_its_word.py::AnInnHasRooms::test_coin_named_with_an_order_is_not_paid_by_the_words (name kept). Old: reading {speak_to npc_veyra, coin_cp 4}, no deal. New: + deal goods, deal_goods bira. Expectation unchanged (shop_offer, purse same). Reason: as above (4 cp with no deal is unclear).

Task 8: rewrite (expectation changed by D29): test_economic_bribe.py::TheBribeCard::test_coin_to_innkeeper_under_arrest_is_not_bribe (name kept). Setup unchanged (5 cp held out to the innkeeper during an arrest, no deal, then "hancıya 5 bakır verip oda tutuyorum"). Old second half: a room card with tender None and the COIN_NOT_TENDERED note (the room words opened it). New: the bribe half is unchanged (no _bribe_held_out, one _press, no bribe card, no bribe_card_opened); then the decision is unclear (barman, 5, structural), no card at all, no COIN_NOT_TENDERED, purse 500, and the unclear note for barman in _turn_notes. Reason: 5 cp fits neither an open offer nor the room price, so the decision is unclear and the words are not read (D29: unclear opens no card and no word path).

Task 9: scenario 02_beer_tip (planned rewrite, spec §6 list): marker [35] and broken_because removed; step 2 script gains deal goods, deal_goods bira, keep_change true and now expects tezgah tip_cp 1, total_cp 5, kese 100, envanter {} (old: Bira 1, kese 95, barman 5 on the coin line itself); new step 3 /item shop_buy barman bira 1 0 5 expects tezgah null, kese 95, Bira 1, barman 5. Reason: design §3b, §11 D1 (coin moves only on the counter confirm).
Jarvis'in 353ce7d6..8aedb6dc aralığı:
- 03_room_sleep.json adım 4: beklentiler korunarak [38]/broken_because kaldırıldı; görev başlığındaki yer tutucu düzeltildi. Adım 2 [37] değişmedi.
- 04_consume.json adım 3: aynı {savas:true, cephane:{arrow:19}} beklentisiyle [56]/broken_because kaldırıldı. İlk iki [54] değişmedi.
- test_item_use.ConsumeJourneys.test_a_consume_reading_drops_the_food_and_beer_and_the_card_says_so: ad aynı; eski iki sonuç [pass,pass] hâlâ zorunlu. Yeni gerçek-zincir adımı nedeniyle toplam üç sonuç ve üçüncüde unreached + REAL_CHAIN_ONLY ayrıca zorunlu. Tüketim ve kart iddiaları korunur. Gerçek zincir başarı sayılmaz.
- test_truth_card.py/test_item_use.py başlangıçta yeni dosyalardır; 04b/26/28 yeni senaryolardır. Bu aralıkta başka eski test dosyası değiştirilmedi (git diff --name-only ile doğrulandı).

Belge doğrulaması: plan Task 11/23, HANDOFF §4b/10, görev defteri D1-R1 ve Task 1, slot.sh/slot_web.sh, git log/sayım/fark ve senaryo JSON dosyaları salt okundu. Yeni ürün testi çalıştırılmadı; yalnız belge değişikliği için yapay başarısız test üretilmedi.
Son devirden sonraki eski test değişiklikleri (J-026/J-031/J-033):
- test_experimental_npc_dialogue.test_opt_in_save_failure_rolls_back_and_retry_receipt_replays: tam şema kümesi 4'ten onaylı7 alana; rollback/replay iddiaları aynı.
- test_npc_p2_continuity içindeki üç tam şema beklentisi: mevcut dört alana coin_answer, coin_answer_for, remember_player_line eklendi; tam küme eşitliği ve yasak alanlar korunur. Follow-up testi değiştirilmedi; istem açıklamaları canlı son satırdan önceye taşındı.
- test_shop_trade ortak fixture: price_cut_day_v1=game_day eklendi; dört türeyen testte eski fiyat reddi/3cp/497 bakiye iddiaları korundu.
- 03_room_sleep: plan Görev20 gereği fiyat/kart45,kese55; seed12 aynı, known_broken37 kaldırıldı; altı adım geçti.
- Yeni testlerdeki hazırlık düzeltmeleri J-033/J-034'te kayıtlı; eski test silme/atlama yok.
Tam eski test adları (adlar değişmedi): test_continuity_first_person_switch_can_come_from_environment; test_speech_call_uses_lean_schema_and_non_greedy_sampling; test_guard_fake_client_output_conforms_to_the_requested_schema. Shop fixture: CounterTrade.test_a_changed_price_changes_nothing_and_gives_the_fresh_quote, WordsOpenTheCounter/WhatIsShownIsNotFree/TypedLane mirasları dahil.

## İstem boyu — Görev22 Step3b, J-036
Kod ucu6d791c3e (tabandan29, Jarvis devrinden13 commit); yalnız ölçüm test dosyası eklendi. 2 test OK,1.066s, JVD1PROMPTBYTES / runs/20261105T123802-JVD1PROMPTBYTES. Ürün kaynağı değişmedi.
| Örnek | Son çağrı | Tüm içerik UTF-8 bayt | Doğruluk görünümü | Hafıza görünümü |
|---|---|---:|---:|---:|
| 24 adım8 | konuşma | 6791 | 100 | 131 |
| 26 adım2 | konuşma | 5653 | 233 | 0 |
| 26 adım3 | anlatıcı | 14841 | 307 | 0 |
Diğer karşı çağrılar yapılmadı; sıfır uzunlukta çağrı değildir. NarratorInput'ın satırla birleştirdiği message içerikleri ölçüldü; protokol zarfı/token ölçümü değildir. Kısaltma işareti yok. Gerçek model token sayısı yok. Bütün dal kapısı ve hazır bildirimi hâlâ bekliyor.
Son bağımsız inceleme takibi / J-037–039: Dilim1 ucu a22ce75c (tabandan32/devirden16). Null hafıza02ee56d1 düzeltildi,37 odaklı OK. Günlü fiyat konuşma notu ve sabit tutarlı oda teklifi a22ce75c düzeltildi; son129 testte128OK/1FAIL, tüm7 yeni sınır testi OK. Tek açık FAIL d4f605a4 pazarlık-niyeti regresyonu; yazılı Task20 sözleşmesinin sosyal beceri+açık teklif koşulu ilgisiz sosyal başarıyı da indirime çeviriyor. Yeni yapısal fiyat-pazarlığı niyeti sözleşmesi kararı gerekli (J-037). Dal yeşil/hazır değil; sıfır tolerans inceleme ve uzun kapılar bekliyor. Doğrudan fazla tahsilat veya kayıt kaybı kanıtlanmadı. İstem ölçümü6d791c3e J-036'da; üç örnek için geçerli, son değişiklikten sonra tekrar ölçülmedi.
Güncel / J-040: Dilim1 uç3787a4f7 (ae815c4f tabanından34, Jarvis devrinden18 yerel commit). Onaylı açık-teklife bağlı price_negotiation sözleşmesi uygulandı; J-037 ilgisiz sosyal başarı regresyonu kapandı. 297 odaklı test OK,43.407s,runs/20261105T130500-JVD1INTENTFINAL2. Eski kayıt fixture düzeltmesi ayrı c799ad78. Sıfır tolerans bağımsız inceleme bekliyor; tam MONEY/uzun kapılar/kabul değildir. Görev23 ara raporu güncel, hazır tetiği yok. Önceki “açık niyet kararı/1FAIL” satırları tarihsel kayıttır.
İstem güncel ölçümü JVD1PROMPTCURRENT2OK:24/8speech6822(100truth/131memory),26/2speech5649(233/0),26/3narration14841(307/0) UTF8bayt. Kısaltma ve gerçek token ölçümü yok; çağrılmayan diğer kanallar yok olarak kaydedildi.
Eski-test sözleşme güncellemesi J-040: test_haggle.HaggleRules ve test_haggle_review.ReviewedPrices olumlu çağrılarına açık teklif önerisi/alınan oyuncu sözü eklendi; önceki miktar, bakiye, günlük sınır ve ret iddiaları aynı. Senaryo03 yalnız açık model niyeti script'i kazandı; seed12 ve tüm beklentiler aynı. UnrelatedSocialCheck script'i açık persuasion ve pazarlık önerisi yok durumunu sabitler; başarının fiyata etki etmemesi iddiaları aynı. test_journey_runner eski hafıza fixture'ına turn1/2 eklendi (c799ad78); hiçbir beklenti silinmedi/atlanmadı/gevşetilmedi.

Güncel / J-041: Dilim1 uçad231081 (tabandan35/devirden19). Doğal Say ve Do+seçiliNPC soru pazarlığı aynı konuşma model çağrısındaki yapısal öneriden ortak Python zar/fiyat yoluna bağlandı. 9 yeni HTTP test ve son165 odaklı test OK,28.186s,runs/20261105T132152-JVD1SAYHAGGLEFINAL. Ek model çağrısı/kelime-regex yok; gerçek model koşusu yok. J-040'ın doğal konuşma kapsamındaki boşluğu kapandı; bağımsız sıfır tolerans incelemesi ve uzun kapılar bekliyor. İstem ölçümleri önceki3787a4f7 koşusunun kanıtıdır; yeni açık-teklif konuşma istemi için ölçüm/kabul iddiası yok. Hazır/push/merge yok.