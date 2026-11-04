# Dilim 1 ara devir — 2026-11-05

Durum: uygulama kısmen tamamlandı, genel kapılar ve oynayış bekliyor. Bu belge Görev 23'ün ara durum kaydıdır; Görev 23 bütünü tamamlanmadı ve "Dilim 1 hazır" tetiği verilmedi.

Dal: task/dilim1-money-memory-20261104. Çalışma kopyası: C:\Users\Kadir\Desktop\AI-DND-dilim1. Uç: 8aedb6dc36aca69b8cb62a21f6bf6750b890c54d. ae815c4f tabanından 19 commit; Jarvis devrinin 353ce7d6 ucundan 3 yeni yerel kod commit'i. Bu oturumlarda push ve merge yapılmadı; uzak dalın güncel ucu yeniden sorgulanmadı.

Tamamlanan Jarvis işleri:
- Görev 12 / madde 36'nın motor yarısı ve 38: ayrı salt okunur anlatıcı/NPC doğruluk kartı; f77df47c. 46 odaklı test OK.
- Görev 14 / madde 54'ün yeni front yolu: yiyecek/içecek tam ad tablosu ve tek kayıt tüketimi; 9b657b87. FOCUS 104, FINAL 63 test OK; koşular örtüşür.
- Görev 15 / madde 56 ve 107'nin sayaç yarısı: paketten bir kez cephane, kayıt/yükleme sonrası ikinci atış 18; 8aedb6dc. FINAL 327 test OK, FEATURES 258 test OK.
Bu sayılar genel paket sonucu değildir. Ayrıntı ve gerçek komutlar J-020/J-021/J-022'de. Guard dosya/ağ/alt süreç engelleri doğrulandı. Bağımsız Claude incelemesi bekliyor.

Yolculuk önce/sonra:
- Önce: defterdeki Task 1 tarihsel ölçümü 14 geçti, 18 bilinen kırık, 0 yeni kırık; 7 adım yalnız gerçek zincirde. Bu oturumda yeniden ölçülmedi.
- Sonra: genel yolculuk paketi çalıştırılmadı; yeni toplam ve "0 yeni kırık" sonucu yok. Yalnız 03 adım 4, 26, 04b'nin ilk iki adımı, 28 ve 04 adım 3 ilgili odaklı testlerde geçti.
- Kaynak dosyalarının salt okunur sayımı: 20 adımda known_broken var. Bu, test sonucu değildir ve başlangıç çalışma kapsamıyla doğrudan karşılaştırılmaz. Kalan kimlikler: 4, 15, 21, 34, 35, 37, 39, 40, 41, 47, 54, 111, 112, 115, 121.
- 35 eski yedek yolda (01 adım 3), 54 eski yedek yolda (04 adım 1/2) kalıyor. 37 (03 adım 2) Görev 20 yapılmadığı için doğrulanmadı; ürün kapsamından çıkarıldığına karar verilmedi.
- Gerçek zincir çalıştırılmadı. 107'nin model yönlendirme yarısı ve 36'nın gerçek zincir yarısı doğrulanmadı. İstem boyu (Görev 22 Step 3b) ölçülmedi.

Hafıza 116: Görev 17, 18 ve 21 uygulanmadı. "NPC başına son 40 seçilmiş söz; tam arşiv sonraki iş" planlanan kapsamdır, mevcut ürüne ilişkin başarı iddiası değildir. Beş kanıtın durumu ayrı ayrı: doğru dinleyen — bekliyor; kalıcı kaynak — bekliyor; yeniden açılmış kaynak — bekliyor; son model girdisi — bekliyor; son cevap — bekliyor.

Engeller ve sıra:
- Görev 11: panel için Kadir'in evet kararı D1-R1'de var. Eksik olan izin değildir. slot.sh node ek hedef argümanı iletmez; slot_web.sh check tam tsc/test:c06/test:standard çalıştırır. Odaklı web RED/GREEN yolu yok. Planın yuva 3 komutu da son kullanıcı talimatındaki dilim1=yuva2 sınırıyla uyumsuz. Başka yuva veya korumasız test denenmedi. Görev 11 başlamadı; "üstü kalsın" panel ana yolu tamamlanmadı.
- En küçük çözüm: araç sahibinin yuva 2 içinde tek hedef dosyasını çalıştıran, izinli hedeflerle sınırlı bir web test yolu sağlaması. Bu rapor slot.sh/slot_web.sh değiştirme izni değildir; bu betikler değiştirilmedi.
- Görev 17: plan remember_player_line şema alanını Görev 10'a bağlar; game.py içinde alan henüz yok. Son doğrudan talimat nedeniyle Görev 10 öne çekilmedi, alanı ayırmak için plan genişletilmedi. Görev 18, 17'ye bağlı. Riskli sıra değişikliği yapılmadı.
- Görev 23: HANDOFF §4b, genel kapılar beklerken devir belgesi yazılmasına açıkça izin verir. Bu izin, eksik uygulamayı tamamlanmış sayma veya "Dilim 1 hazır" bildirimine dönüştürülmedi.
- Para/kayıt/Geri Al görevleri 10, 20, 21 ve Dilim 0 Görev 5 sona bırakılmaya devam ediyor. Tamamlandı diye işaretlenmedi.
- Yan etki maddeleri 2 ve 12 için ayrı kapanış kanıtı bu ara devirde yok; ilgili kapsam ve bütünleşik testler bekliyor.

Ürünü yalnız Kadir kabul eder; 30 dakikalık oynayış bekliyor.

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