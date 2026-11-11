# D0 + D1 birleştirme raporu (2026-11-08)

**Özet (Kadir için):**
1. Birleştirme bitti ve yerelde commitlendi: `3f15e639`, dal `task/d0-d1-integration-20261108` (push yok). Dokuz çakışan dosya çözüldü, API istemcisi codegen ile yeniden üretildi, bütün odaklı Python grupları ve web testleri yeşil (sayılar aşağıda).
2. Senin kararın uygulandı: "üstü kalsın"da toplam 5 de, yalnız mal 4 de onaylanabilir; açık 5'lik kart doğrudan 4'lük alımı engellemez. Bu karar için yazdığım test D0 davranışıyla KIRMIZI (3 test düştü), birleşmiş kodda YEŞİL.
3. D0 ve D1 aynı yerde iki ayrı tasarım yapmıştı (para niyeti okuması, sözlü kabul/ret, oda kelimesi, say-modu okuması). Hepsini birleştirdim ama birkaçında bir tarafı seçmek zorunda kaldım; hepsi "Açık kararlar"da. Para güvenliği açısından hep daha az kart açan / daha az para oynatan tarafı seçtim.
4. Senin karar vermen gerekenler: (a) say-modunda model okuması hangi satırlarda yapılsın, (b) oda kelimesiyle kart açma (okuma varken kapalı), (c) D0'ın ayrı `coin_response` alanı kaldırıldı (D1'in `coin_answer` alanı onun işini görüyor), (d) aynı "üstü kalsın" için hem D1 paneli hem D0 kartı görünüyor (tarayıcıda bakılmadı).
5. Doğrulanmayanlar: gerçek tarayıcı, gerçek model, tüm test paketi, gerçek kayıt göçü.

---

## 1. Çakışan dosyalar ve her parçanın çözümü

### ai-dnd/shop_trade.py (3 parça)
- Parça 1 (`pending_confirmation` / `npc_declined`): D1'in `goods:<key>` ret kontrolü kaldı. D0'ın "açık bağlı kart varsa doğrudan satışı reddet" kontrolü ve `pending_confirmation` fonksiyonu **kaldırıldı** (sahip kararı). Doğrudan alımı koruyan şey zaten teklif numarası: alım `seq`'i artırır, açık kartın bağı (`binding_matches`) bayatlar, kart onaylansa hiçbir şey kesmez.
- Parça 2 (teklifi kurma): kayıtlı kart varsa (D0 `stored_offer`) o kartın kendisi kullanılır; yoksa D1'in `tender`/`counter_purchase_offer(..., tip_cp)` yolu.
- Parça 3 (dönüş): `_commit_sale` artık `(anlatı, resolution)` döndürür (D0 imzası); D1'in bahşişli/bahşişsiz/`TIP_KEPT` metinleri aynen korundu. Kayıtlı kartta anlatı `resolution.public_summary`.
- Ek (çakışma işaretsiz ama anlamca gerekliydi): D1'in "onaylanan toplam ya mal+bahşiş ya yalnız mal" mantığı ve `net_debit != confirmed_total` kontrolü kayıtlı kart için atlanıyor; çünkü kart kendi satırlarını `resolve_offer` ile çözer (reddedilen bahşiş satırı kesilmez, mal kesilir; D0'ın kısmi bahşiş reddi davranışı). Aksi halde bağlı kartın onayı hep `price_changed` olurdu.

### ai-dnd/economic_actions.py (1 parça, `derive_acceptance`)
D1'in sözlü ret blokları (`declined`, `_tip_declined`, `tip_off`) ile D0'ın `coin_responses` yanıtı (`refuse` / `npc_consent_required`, bahşiş satırı yanıtı) birlikte duruyor. Satır kararı: D1'in reddettiği bahşiş satırı `npc_declined`; değilse D0'ın yanıt kararı.
- Çakışmasız ek: D0 `context_digest`'e `coin_response`/`tip_response` alanını her zaman `None` olarak yazıyordu; bu D1 döneminde saklanmış açık kartların özetini bozup onayda bayat yapardı. Artık alan yalnız kişi gerçekten yanıt verdiyse yazılıyor. (`offer_from_record` için aday dosyadaki `counter_binding: null` kırpma kodu gerekmedi: birleşmiş `EconomicOffer`'da alan varsayılan `None` ile var, eski kayıtlar ve D0 kayıtları zaten okunuyor; bağsız kartların `confirmation_digest` biçimi D0'ın "eski kart aynı özet" kuralıyla aynı.)

### ai-dnd/bold_acts.py (2 parça)
- `take_room`: D1'in para sahibi kararı (`money_owner`) önce; ardından D0'ın `requested` ve `_front_economic_none` korumaları (`server=` / `requested=` imzası korundu).
- `_with_tender` / `shop_offer`: D1'in bahşiş yardımcıları (`_decided_tip`, `drop_counter_tip`, `repair_counter_tip`, `close_declined_counter`) aynen; D0'ın "bağı artık tutmayan bağlı kartları iptal et" çağrısı `_with_tender` sonuna eklendi; `shop_offer(..., requested=False)` imzası.

### ai-dnd/front_proposal.py (1 parça + 2 ek)
- `required` listesi birleşim: `deal`, `deal_goods`, `keep_change` (D1) + `economic_intent` (D0); `keep_change` `properties` içinde iki kez yazılmıştı, tek bırakıldı. Şema, `economic_route`, `money_owner.read_deal` ve testler aynı anahtarlarla tutarlı.
- Rehber metinde D0'ın `keep_change` cümlesi çıkarıldı (D1'in 924f8a19'daki açıklaması aynı alanı zaten anlatıyor; çelişen iki talimat olmasın).
- `begin()` içinde D0'ın `_front_economic_none = True` satırı kaldırıldı: bayrak artık yalnız okuma gerçekten elde edilince (`_front_step` içinde) kuruluyor. Böylece sağlayıcı yanıt vermezse eski kelime yolu çalışmaya devam ediyor.

### ai-dnd/game.py (8 parça)
1. `_experimental_speech_note`: D1'in karar-tabanlı "para henüz sende değil" notu; D0'ın bekleyen sözlü-kabul teklifi notu yalnız karar notu yoksa ekleniyor.
2. `parse_player_intent` NPC konuşma şeması: D1'in `coin_answer_for` listesi; D0'ın ayrı `coin_response` alanı ve istem cümlesi kaldırıldı (bkz. Açık karar 3).
3. `_tell_the_coin`: önce D1'in `open_card_after_reply`'ı (kişinin sözlü reddini yazar / kararın kartını açar), sonra D0'ın bekleyen sözlü teklif sonucu. D0'ın "front varsa hiçbir şey yapma" erken dönüşü D1'in "hediye varsayılanı yok" tasarımıyla zaten aşılmıştı, taşınmadı.
4. `_front_step` girişi: D1 `said_coin` + D0 `typed_economic`; birleşik kural Açık karar 1.
5. `_front_step` okuma sonrası: önce D0 `economic_route`, yoksa D1 `said_coin` (konuşulan kişiye bağlı kalır, karar `_hand_over_coin` ile), yoksa D0 "yazılı konuşma genel rotalara girmez".
6. `_front_step` sonu: `_hand_over_coin(route, listed, reply.get("front"))` (D1); D0'ın `if not _front_economic_none` koruması bu satırı hep kapatacağı için taşınmadı.
7. D0'ın `_defer_spoken_coin_offer`, `_record_spoken_coin_response`, `_front_economic_offer` fonksiyonları + `_hand_over_coin(route, listed, front=None, *, owner_routed=False)`. `owner_routed`: D0'ın doğrulanmış amaç rotası modelden `deal` gelmediyse karar yazmaz (yapısal tahmin yok); `deal` varsa D1 kararı yazılır. Alım rotasında model `deal`'i alım dışı bir şey diyorsa hiçbir kart açılmaz.
8. `valid_speech_packet` alan kümesi: D1 alanları (`coin_answer`, `coin_answer_for`, `remember_player_line`, `witness_recall`, `price_negotiation`); `coin_response` çıkarıldı.
- Ek: D0'ın `_record_spoken_coin_response` çağrısı kişinin tek sözlü cevabını (`coin_answer`) kullanıyor: `takes` -> kabul, `declines` -> ret, başka hiçbir şey -> onaysız (kart satırı reddedilmiş, para kesilmez).

### Journey senaryoları
- `02_beer_tip.json`: D0'ın kartlı akışı + D1'in tezgâh beklentisi (`tezgah` bira 4, bahşiş 1, toplam 5) aynı adımda; onay adımından sonra D1'in `/item shop_buy barman bira 1 0 5` komutu, "kart onaylandıktan sonra ikinci satış yok" beklentisiyle (kese 95, Bira 1, barmen 5). Başlık ikisini anlatıyor.
- `16_past_tense.json`: D0'ın `economic_intent: none` adımı + D1'in `deal: paid_before` adımı, ikisi de `kart: null`, kese 100.
- `17_refused_gift_not_charged.json`: D1'in 6 adımı (yapısal ret, reddedilen bahşiş, "al" ile kalkan ret, tek onay, sonraki hediyenin reddi) korundu; ilk adıma D0'ın `economic_intent: gift` eklendi.
- `18_room_phrase_not_job.json`: iki taraf da aynı adımı düzeltiyordu (known_broken ikisinde de silinmişti); başlık birleşti, `economic_intent: room` korundu.

---

## 2. Çakışmasız ama anlamca düzeltilen yerler (ek dosyalar)
- `ai-dnd/money_owner.py`: kişi açıkça "alırım" (`takes`) dediğinde aynı tutarın eski D0 `coin_responses` retini de kaldırıyor; yoksa D1'in "yalnız açık alışla kalkar" kuralı D0'ın kalıcı reddiyle çelişiyordu (senaryo 17 adım 4).
- `ai-dnd/api/tests/journeys/report.py`: D0'ın üç yeni senaryosu (13b, 14b, 14c) rapor kategorisine eklendi (D1'in "her numaralı senaryo bir kategoride olmalı" testi için).
- API istemcisi: `bash slot.sh 2 AI-DND-integ codegen` -> `CODEGEN_OK`. EOL farkı yok sayılınca yalnız 4 dosya değişti (+30 satır: `undone`, `undo_note`, `undo_target_unknown` ve D1'in `ShopCounterHeld` zaten openapi'de). `openapi.yaml` ve `schemas.py` elle birleştirme gerektirmedi (otomatik birleşme iki tarafın alan birleşimiydi: ShopCounterHeld/Response + CampaignHistoryEntry bayrakları). `main.py` otomatik birleşmesini okudum: D0'ın `undo_narration`/`UNDO_HISTORY_MARKER` değişikliği D1 koduyla çakışmıyor.

---

## 3. Testler: komutlar ve çıktılar

Hepsi `bash C:\Users\Kadir\Desktop\AI-DND-TOOLS\slot.sh 2 AI-DND-integ test <ETİKET> 900 api.tests.<modül> ...` ile (tek seferde bir komut).

Son kaynak değişikliğinden SONRA alınan sonuçlar:
- `f1` (527 test, 0 hata): test_counter_tip, test_economic_decline, test_counter_keep_change, test_money_owner, test_persistence_idempotency, test_step0_commit_failures, test_roadmap_r04_commit_boundary, test_front_tip_pipeline, test_money_cards, test_coin_never_works, test_coin_writers, test_shop_counter, test_shop_counter_http, test_shop_trade, test_spoken_decline, test_past_payment, test_offer_tip_expiry, test_economic_bribe, test_economic_dialogue, test_haggle, test_haggle_review, test_haggle_speech, test_journey_runner, test_journey_schema, test_journey_reload_continuation, test_journey_room_evidence, test_dilim1_save_repair, test_http_acceptance_evidence. Çıktı: `RESULT exit=0 Ran 527 tests`.
- `d2` (517 test, 0 hata): test_front_money, test_haggle_intent, test_money_routes, test_default_npc_targeting, test_experimental_npc_dialogue, test_economic_spoken_consent, test_room_purpose_routing, test_counter_semantic_continuity, test_journey_diagnostic_audit, test_front_proposal, test_front_carries_more. Çıktı: `RESULT exit=0 Ran 517 tests`.
- `f2` (835 test): test_economic_action_gate/http, economic_contract/offer/receipt/resolution/room/undo, explicit_shop_creation, front_voice, journey_report, journeys, lr00_p7_undo, shop_quote_http, shop_trade_http, dilim0_undo_text, character_creation_2024, dilim0_start_purse/ui_sources/combat_labels, equipment_native, f10_source_corrections, roadmap_c10_starting_equipment(+_http), carius_fifth_play, item_use, lasting_consequences, npc_p2_continuity, npc_told, real_lead_fallback, review_display, step4_branches, task11_schema_export, told_claims, truth_card, witness_question_source, witness_recall, witness_review, world_keeps_its_word, handoff_prompt_measurement. Çıktı: `RESULT exit=1 Ran 835 tests`, 2 FAIL (journey_report kategori testi; world_keeps_its_word oda testi). İkisi de düzeltildi (aşağıda) ve yeniden koşuldu:
- `g1` (215 test, 0 hata): test_journey_report, test_world_keeps_its_word, test_room_routing_diagnostic, test_three_plays, test_journey_item_evidence, test_journey_real_run. Çıktı: `RESULT exit=0 Ran 215 tests`.
- Web: `bash slot.sh 2 AI-DND-integ node` -> `tsc=0`, `c06=0 pass 258 fail 0`, `std=0 pass 326 fail 0 skipped 1` (1 atlanan önceden bilinen F03 atlaması).

Kırmızı/yeşil (sahip kararı testi): önce D0 engelini geçici geri koyup (`pending_confirmation`) `api.tests.test_counter_keep_change` koştum: `red3 exit=1 Ran 30 tests`, 3 FAIL (üç yeni test). Engeli çıkarınca `green1 exit=0 Ran 30 tests`; son kodda `f1` içinde de yeşil.

Ara koşular (bilgi için, nihai değil): `t1` (66 test, 2 FAIL: D0'ın eski engel testi + D1 gün-bağlı indirim), `a1` (199 test, yeşil), `b1` (472 test, 6 FAIL: senaryo 17 birleşimi), `c1` (429 test, 7 FAIL + 2 ERROR: schema/say-modu/oda kelimesi çakışmaları), `d1` (517, kalan çakışmalar). Hepsi aşağıdaki değişikliklerle giderildi.

Çalıştırılmayanlar: tam paket; `test_journey_real_run` gerçek zincir kısmı (atlanır); D0'ın web tarafının yalnız slot web adımı koşuldu, gerçek tarayıcı yok.

---

## 4. Yeniden yazdığım / eklediğim testler (ve neden)
- `test_counter_keep_change.py`: `test_native_command_cannot_bypass_a_pending_total5_card` (D0: açık 5'lik kart doğrudan 4'ü engeller) sahip kararıyla yer değiştirdi; yerine eşit katılıkta 4 test: açık kart yalnız-mal 4'ü engellemez (tam 4 kesilir, tekrar oynatma ikinci satış değil, kart ikinci kez kesmez), geri al/yeniden aç/devam kararlı (kese, çanta, stok, teklif numarası tam geri gelir, kart yeniden 5'i bir kez keser), iki bira (8) engellenmez, kart onaylandıktan sonra doğrudan 4 ikinci satış olmaz. Ayrıca D1'in "indirim yalnız kendi oyun gününde geçerli" kuralı nedeniyle `test_same_total_after_price_drop...` fixture'ına `price_cut_day_v1` eklendi (aynı katılık).
- `test_economic_spoken_consent.py`: senaryo 17 artık D1 adımlarını da taşıdığı için D0'ın üç adımlı akışını `consent_steps` yardımcısı kuruyor (D0 beklentileri aynen); `coin_response` enjeksiyonu `coin_answer`/`coin_answer_for` oldu (alan birleştirildi).
- `test_front_money.py`: "yalnız parayı anan satır okunur" testinde parasız satır satıcı olmayan kişiye gidiyor (hâlâ okuma yok); satıcıya parasız satır için yeni test (bir okuma).
- `test_front_proposal.py` (D0 testi): konuşulan kişi satıcı yapıldı (okuma ve yan etkisizlik beklentileri aynen).
- `test_money_routes.py` (D1): "karar yokken kelime yolu değişmez" testi okuma kapalıyken koşuyor (okuma varken oda kelimesi okunmaz; Açık karar 2).
- `test_haggle_intent.py` (D1, 2 test) ve `test_world_keeps_its_word.py` (D1): oda kartı artık modelin `deal: room`'u ile açılıyor (kelime yolu yerine); asıl sınanan pazarlık/tutulan oda davranışı aynen.
- `api/tests/journeys/report.py`: kategori listesine 13b/14b/14c.

---

## 5. Açık kararlar (Kadir)
1. **Say-modunda model okuması.** D0: yazılı konuşma satırı hep okunur. D1: yalnız para anan satır okunur (ücretsiz). Birleşik: para anan satır VEYA satıcıya (barmen vb.) söylenen satır okunur; başka kişiye parasız satır okunmaz. Neden: ücret/gecikme artmasın, D0 satıcı özellikleri (parasız "bir bira alabilir miyim?") çalışsın. Etki: D0 test `typed_speech_reads_purpose_once...` ve D1 `say_mode_reads_only...` bu kurala göre uyarlandı. İstersen "hep oku"ya (D0) ya da "yalnız para" (D1) çevrilir; ikisi de tek satır.
2. **Oda kelimesi.** Okuma elde edildiyse oda kelimesiyle kart açılmaz, yalnız modelin `deal: room` / `economic_intent: room`'u açar (D0, daha az kart = daha güvenli). Okuma hiç yoksa (sağlayıcı yanıtsız, front kapalı) eski kelime yolu çalışır (D1). D1'in dört testi bu yüzden güncellendi.
3. **Konuşma şeması.** D0'ın `coin_response` (accept/refuse/none) alanı kaldırıldı; D1'in `coin_answer` (takes/declines/none) alanı onun işini görüyor (takes = kabul, declines = ret). Gerekçe: aynı şeyi soran iki zorunlu alan küçük modele yük, D1 testleri şemayı tam sabitliyor. D0'ın `coin_responses` kaydı ve "yanıt yoksa kart onayda para kesmez" kuralı korundu.
4. **Aynı "üstü kalsın" için iki yüzey.** Model hem `deal=goods+keep_change` hem `economic_intent=purchase` derse D1 tezgâh teklifi (panel "evet" 5) ve D0 bağlı kartı (5) birlikte açılır. İkisi aynı teklif numarasını tüketir, yani yalnız biri ödeme yapabilir (testle doğrulandı), ama arayüzde ikisinin birden nasıl göründüğü tarayıcıda bakılmadı.
5. **Kısmi bahşiş reddi.** Kart yolunda (D0) bahşiş satırı reddedilirse mal (4) kesilir; panel yolunda (D1) bahşiş reddedilmişse bahşişli toplam `tip_unavailable`, yalnız mal 4 ayrı onaylanır. İkisi de gösterilenden fazlasını almaz; aynı olayın iki yüzeyde farklı sonucu var.
6. **Kalıcı ret süresi.** D0'ın `coin_responses` reddi gün sınırsız kalıyor (yalnız açık "alırım" ya da kabul kaldırır); D1'in `money_declined` reddi gün sonunda biter. Birleşik hâlde ikisi de blokluyor (daha katı/güvenli).
7. Doğrudan alımdan sonra D0 kartı "prepared" olarak kalıyor (iptal edilmiyor, onaylanırsa bayat sayılıp hiçbir şey kesmiyor). İptal etseydim Geri Al o kartı geri açmazdı. Arayüzde bayat kart görünür mü, tarayıcıda bakılmadı.

---

## 6. Doğrulanmadı
- Gerçek tarayıcı (yalnız slot web testleri ve tsc), gerçek model/sağlayıcı (tüm sahte), tam test paketi, gerçek kayıt göçü (D0 ve D1 imzalı gerçek kayıtlar; yalnız birim düzeyinde "bağsız kart özeti aynı, bağ alanı yoksa varsayılan None").
- `graphify update .` çalıştırılmadı (bu klasörde graphify-out yok; başka klasöre dokunmamak için).
- Kod incelemesi (bağımsız) yapılmadı; `ecc:*` gözden geçirme komutları çalıştırılmadı.

---

## 7. İnceleme düzeltmeleri (commit `8c2a0569`, `3f15e639` üzerine)

Kaynak: `INTEG_INCELEME_20261108.md`. S5 ve N1-N8'e dokunulmadı (S5 sahibin kararına bırakıldı). Yeni testler: `ai-dnd/api/tests/test_integ_review_fixes.py` (10 test). Kırmızı koşu düzeltmeler geri alınmış kaynakla: `r3 exit=1 Ran 10 tests`, 8 FAIL, 0 ERROR (kalan 2 test koruma testi: yazıcı gift-deal kullanılmaz, eski tutar-anahtarlı kayıt hâlâ reddeder). Yeşil: `g2 exit=0 Ran 10 tests`.

- **S1 (yatağa yürüme):** `bold_acts.take_room(..., walk_to_bed=True)`; `game._sleep_after_walk` bunu geçiyor, böylece ön okuma `_front_economic_none` kurmuş olsa da oda kartı açılıyor ve uyku onaylı oda hakkını bekliyor. Serbest satırın oda kelimesi yolu (`requested` olmayan çağrılar, `_room_asked`, `_buy`) kapalı kaldı. Para oynamaz (kart onay ister). Test: `WalkToBedWithAReading.test_walk_then_sleep_with_a_reading_opens_the_room_card_and_waits`.
- **S2 (`coin_responses`):** yanıt artık yazıldığı oyun gününe ve teklif türüne bağlı: `offer:<tutar>` (hediye ve bahşiş kartı tek yanıt paylaşır; senaryo 17'nin "reddedilen hediye sonrası aynı bahşiş" beklentisi için) ve `purchase_tip:<tutar>` (mal kartının bahşiş satırı; bağımsız bahşişin cevapsızlığı bunu etkilemez). Gün değişince yanıt geçersiz, yazma sırasında eski günün kayıtları temizleniyor; `accept` o tutarın bütün yanıtlarını siler. Eski kayıtlar (gün alanı yok, anahtar yalnız tutar) hâlâ okunuyor ve aynı şekilde reddediyor; D0/D1 imzalı eski kartların özeti değişmedi (yalnız yanıt varsa alan yazılıyor, değer aynı sözlük). `context_digest` ve `derive_acceptance` aynı `_coin_reply` okuyucusunu kullanıyor (N7'deki bozuk kayıt `.get` riski de bu yolda doğrulanıyor). Not: gün sınırı yok sayılan tek durum eski gün alanı olmayan kayıtlar. Testler: `ASpokenReplyBelongsToOneDayAndOneKind` (3 test).
- **S3 (bayat kart gösterimi):** `api/serializers._economic_projection` bağlı kart `binding_matches` değilse kartı yalnız göstermiyor; kayıtlı durum `prepared` kalıyor. Test: `AStaleCardIsHiddenNotChanged` (doğrudan 4 sonrası projeksiyon `None`, kart `prepared`, Geri Al sonrası aynı kart hem depoda hem `state.economic_offer`'da geri).
- **S4 (`economic_intent` konumu ve typed dal):** `front_proposal.schema` içinde `economic_intent` `kind, deal, deal_goods, keep_change`'den hemen sonra; `required` aynı sırada tutarlı, rehber metinde `economic_intent` cümlesi `deal`/`keep_change` cümlelerinin hemen sonrasına taşındı. `game._front_step` `typed:no_economic` dalı model `deal` değeri `room` ya da (listedeki mal ile) `goods` ise `_hand_over_coin(route, listed, raw_front)` çağırıyor (yalnız D1 kararı, para 0). Şema sözleşmesi (openapi) değişmedi, codegen gerekmedi. Testler: `TheDealSitsNextToKind` (2), `ATypedLineKeepsAValidDeal` (3: oda, mal, hediye-deal kullanılmaz).

Koşular (son kaynak değişikliğinden sonra, `slot.sh 2 AI-DND-integ test <etiket> 900 ...`):
- `i1` 537 test, exit=0 (counter_tip, economic_decline, counter_keep_change, money_owner, persistence_idempotency, step0_commit_failures, roadmap_r04_commit_boundary, front_tip_pipeline, money_cards, coin_never_works, coin_writers, shop_counter(_http), shop_trade, spoken_decline, past_payment, offer_tip_expiry, economic_bribe, economic_dialogue, haggle(_review/_speech), journey_runner/schema/reload_continuation/room_evidence, dilim1_save_repair, http_acceptance_evidence, integ_review_fixes).
- `i2` 706 test, exit=0 (front_money, haggle_intent, money_routes, default_npc_targeting, experimental_npc_dialogue, economic_spoken_consent, room_purpose_routing, counter_semantic_continuity, journey_diagnostic_audit (senaryolar 02/03/16/17/18 dahil), front_proposal, front_carries_more, room_routing_diagnostic, three_plays, journey_item_evidence, journey_report, world_keeps_its_word).
- `i3` 659 test, exit=0 (economic_action_gate/http/contract/offer/receipt/resolution/room/undo, explicit_shop_creation, front_voice, journeys, lr00_p7_undo, shop_quote_http, shop_trade_http, dilim0_undo_text, last_play_blockers, campaign_api, lasting_consequences, item_use, truth_card, witness_recall).
- Web: `slot.sh 2 AI-DND-integ node` -> `tsc=0`, `c06=0 pass 258 fail 0`, `std=0 pass 326 fail 0 skipped 1`.
- Ara bir koşuda (`h2`) `economic_spoken_consent` üç test düştü: S2'nin ilk sürümü hediye yanıtını bahşiş kartından ayırmıştı (D0 senaryo 17 ikisinin aynı yanıtı paylaşmasını bekliyor); yanıt anahtarı `offer` olarak birleştirilip yeniden koşuldu (`i2` yeşil).

Doğrulanmadı: gerçek tarayıcı (S3'ün kartı gizlemesi yalnız serileştirici/HTTP düzeyinde), gerçek model (S4'te gerçek modelin `deal` ve `economic_intent` alanlarını nasıl dolduracağı), tam test paketi, D0 imzalı eski kayıtların gerçek göçü.
