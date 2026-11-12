# D0 + D1 birleştirme: bağımsız inceleme (2026-11-08)

Kapsam: `AI-DND-integ`, birleştirme `3f15e639` (ebeveynler D1 `924f8a19`, D0 `b698cd55`). Yalnız okundu; test, komut, düzenleme yok.

**Özet**
- **BLOCKER: 0.** Para, kayıt, Undo, tekrar oynatma ve devam ettirme yollarında çift kesinti, ödemesiz mal ya da bozuk Undo izlenemedi (izlenen yollar 1. bölümde).
- **SHOULD-FIX: 5, NOTE: 8.** En önemlisi S1: ön okuma elde edildiğinde "odama gidip uyuyorum" oda kartı açmadan uyutabiliyor (D1'de uyku kartın onayını bekliyordu). S2: D0'ın `coin_responses` kaydı gün sınırsız ve yalnız tutara bağlı; meşru bir bahşişi sessizce düşürebilir (para fazla kesilmez, eksik kesilir).
- Sahibin kararı (üstü kalsın: 5 ya da yalnız 4; açık 5'lik kart doğrudan 4'ü engellemez) kodda doğru uygulanmış: `pending_confirmation` tamamen silinmiş, tek satış kuralı `seq` + `binding_matches` ile korunuyor.
- Yazarın raporundaki üç "güvenli" gerekçesine itirazım var (2. bölüm sonu).
- Çalıştırılan hiçbir şey yok; "doğrulanamadı" etiketleri izlenemeyen yerleri gösterir.

---

## 1. Izlenip güvenli bulunan yollar (kanıt: kod okuma)

1. **Açık 5'lik kart + doğrudan 4 + sonra kart onayı.** Doğrudan 4 (`/item shop_buy ... 4`) `_commit_sale` yolunda `seq`'i artırır (`shop_trade.py` ~368). Kart onayında `confirm_offer` -> `_still_holds` -> `binding_matches` (`shop_trade.py:215-230`) `opened["seq"] == binding["seq"] == seq(world)` ister; artık eşit değil -> kart `cancelled`, `_unmoved("stale")`, hiçbir şey kesilmez. `opened["turn"] == quote_turn` koşulu, aynı `seq` ile yeniden teklif açılsa da (`_open_offer` yeni `turn` yazar) eski kartı öldürür.
2. **Kart onayı + sonra doğrudan 4 ya da 5.** Onay `seq`'i artırır; doğrudan komut eski `seq` ile `offer_stale` alır. (Senaryo 02 son adım ve `test_native_purchase_after_the_total5_card_was_confirmed...` bunu kapsıyor.)
3. **Doğrudan 4 sırasında kartlı akışta tender.** `_tender` (`shop_trade.py:200`) tender=5 döndürse de `resolve_offer` yalnız kabul edilen satırı (mal 4) düşer; para üstü yalnız gösterim (S4'e bakın). Kesinti hep `net`.
4. **Reddedilen bahşiş satırı kesilmez.** Kart yolunda: `derive_acceptance` (`economic_actions.py:740-756`) ret/belirsiz yanıtta satırı `refused` yazar; onayda `resolve_offer` D1'in `_tip_declined` kontrolüyle sonradan reddi de ekler; `base_required` olduğu için yalnız mal (4) kesilir, `validate_economic_resolution` hem borç hem mal/stok deltalarını aynı makbuzda doğrular. Doğrudan yolda: `_tip` D1 reddinde 0 döner, 5 onayı `tip_unavailable` ile reddedilir.
5. **Mal ödemesiz teslim edilemez.** Kayıtlı kartta `can_pay` kontrolü atlanıyor (`shop_trade.py:337`) ama `resolve_offer` `purse < running` ve `tender > purse` ile tüm kartı reddeder; reddedilen sonuçta `_commit_sale` dünyayı değiştirmeden döner (`shop_trade.py:352-353`), mal/stok yazımına hiç ulaşılmaz. `count > stock`, `vendor_refuses`, `goods:<key>` reddi `TradeRefused` olarak kart onayında da çalışıyor; `confirm_offer` bunları `stale` + kart iptali olarak yutar (dünya dokunulmadan).
6. **Tekrar oynatma / yeniden başlatma.** Kart `flags.economic_offers` içinde saklı, `counter_binding` `EconomicOffer` varsayılanıyla (`None`) okunuyor; `confirmation_digest` yalnız bağ varsa `counter_binding` + `counter_acceptance` ekliyor (`economic_actions.py:431-440`) ve bu biçim D0'ınkiyle birebir aynı, bağsız (D1) kartlar eski biçimde kalıyor. Operasyon kimliği `offer:{action_id}`; aynı kimlik `apply_resolution`'da `operation_id_reused` verir, aynı istek ise makbuz tablosundan aynen döner.
7. **Undo.** Kart onayı: `economic_step` tüketen onayda `consumed_action_id` yazıp kontrol noktasını bu eyleme çeker; `reconcile_offers_after_undo` kartı tekrar `prepared` yapar; dünya geri yüklendiği için `seq`, stok, kese, satıcı kesesi ve `counter_offer_v1` geri gelir, `binding_matches` yine geçer (test `test_undo_restores_assets_...`). Doğrudan 4: genel tur Undo'su; kart `prepared` olarak durur ve Undo sonrası yeniden geçerli (test `test_goods_only_purchase_beside_an_open_card_undoes_and_resumes`). `_state_fingerprint` `economic_offers`'ı dışarıda bıraktığından kart iptali/hazırlığı Undo hedefini bayatlatmıyor.
8. **UI Undo hedefi.** `game-browser.tsx` ~2052-2062: `economic_prepare`, `economic_cancel` ve `reason_code in [offer_not_prepared, digest_mismatch, stale]` olan reddedilmiş onay son-tur hedefini değiştirmiyor; motor tarafında `_unmoved` tam olarak bu üç gerekçeyi tüketmiyor. Bağlı kart `TradeRefused` yolunda da `_unmoved("stale")` döndüğü için tutarlı. (Tek uyumsuzluk N2'de.)
9. **`coin_response` / `coin_answer` okuyucuları.** Depo genelinde `git grep`: konuşma şeması (`game.py:7958`), istem (`9262`), paket alan kümesi (`22042`), `money_owner.read_answer`, runner `SPEECH_SCRIPT_KEYS`, üretilmiş TS istemcisi, openapi: hepsi yalnız `coin_answer`/`coin_answer_for`. Tekil `coin_response` yalnız `context_digest` içinde bir anahtar adı olarak kalıyor; çoğul `coin_responses` tek kayıt yeri. Şema `required` listesi `economic_intent`'i de içeriyor ve `properties`'te var, `keep_change` tek kez yazılı; tutarlı.

---

## 2. Bulgular

### S1 — SHOULD-FIX (yüksek öncelik): ön okuma varken "yatağa yürüme" oda kartı açmıyor, uyku bekletilmiyor
- Yer: `bold_acts.py:705` (`take_room`: `if not requested and getattr(session, "_front_economic_none", False): return None`), çağıran `game.py:19459` (`_sleep_after_walk`), bayrak `game.py:18500`.
- Senaryo: front açık; oyuncu (do modu) "Hana gidip odama çıkıp uyuyorum". `_front_step` okuma elde edince `_front_economic_none = True` kurar (okuma `go_to`/`sit` der, `economic_intent: none`, yönergeye göre "odayı yalnız anmak oda istemek değil"). Yürüyüş biter, `_sleep_after_walk` -> `take_room(session, text)` `None` döner -> `if room is not None` bloğu atlanır -> `_SLEEPING` eşleşir -> `timed_gameplay.resolve_input` uyutur. D1'de bu satırda oda kartı açılır ve `if not room["room"]: return  # sleeping waits for a room really held` uykuyu keserdi. Sonuç: oda ücreti/hakkı hiç sorulmadan dinlenme.
- Neden test yakalamadı: senaryo `03_room_sleep.json` `front_proposal` açmıyor (kelime yolu).
- Neden blocker değil: uykunun oda hakkına başka bir yerde bağlı olup olmadığı doğrulanamadı; `timed_gameplay` oda hakkına bakmıyor, yani bu kapı yalnız D1'in `_sleep_after_walk` kapısıydı; para yanlış kesilmiyor, hizmet bedelsiz kalıyor.
- Öneri: `_sleep_after_walk` kendi çağrısında bayrağı yok saysın (örn. `take_room(..., walk_to_bed=True)` ya da `requested` semantiğiyle ayrı bir yol); ya da `_front_economic_none` yalnız `_room_asked` ve `_buy` kelime yollarını kapatsın, yatağa-yürüme yolunu değil. Kart açmak para oynatmaz (onay şart), dolayısıyla bu çağrıyı açık bırakmak güvenli.

### S2 — SHOULD-FIX: `coin_responses` yalnız tutara bağlı, süresiz, her cevapsız hediye/bahşişte `unknown` yazılıyor
- Yer: `economic_actions.py:343-367` (`record_coin_response`, `_coin_response`), `394-401` (özet), `740-756` (`derive_acceptance`), yazanlar `game.py:17989`, `game.py:22300`, `money_owner.py:311`.
- Senaryo: oyuncu barmene 1 bakır bahşiş uzatır (`economic_intent: tip`, coin 1). Barmenin konuşması kabul edilmiş modelle gelir ama `coin_answer: none` (ya da kabul edilmemiş/yedek metin) -> `coin_reply = None` -> `coin_responses["1"] = {"status": "unknown"}`. Sonra "bir bira, 5 bakır koyuyorum üstü kalsın": `prepare_keep_change` kartı bahşiş = 1; `derive_acceptance` bahşiş satırı için `str(tip_cp)` = "1" anahtarını okur -> satır `refused / npc_consent_required` -> onayda yalnız 4 kesilir, "Bahşiş geçmedi; kesende kalır". Meşru bahşiş sessizce düşer; D1 doğrudan yolu (`_tip`) `coin_responses`'a hiç bakmadığı için aynı 5'i keserdi. Reddedilmişse (`refuse`) D1'in `money_declined` kaydı oyun günü sonunda biter, `coin_responses` bitmez: ertesi gün panelden hazırlanan 1 bakırlık bahşiş/hediye hâlâ "Bu para teklifi kabul edilmedi".
- Para yönü: eksik kesinti (oyuncu lehine), fazla kesinti yok; ama "iki yüzey aynı olayı farklı sonuçlandırıyor" ve D1'in "ret yalnız açık alışla ya da yeni günle biter" kuralını D0 kaydı deliyor. Yazarın "daha katı/güvenli" gerekçesi para güvenliği için doğru, doğruluk (meşru bahşiş/hediye) için yanlış.
- Öneri: `coin_responses`'a `day` ekleyin ve `_coin_response`/özet yalnız aynı oyun gününün kaydını okusun; ya da `unknown`'ı hiç saklamayın (yalnız o turun `_spoken_coin_proposal` kartına yazın, kalıcı yazmayın). Tutar anahtarı yerine (`purpose`, `amount`) kullanın ki hediye cevabı bir mal kartının bahşiş satırını etkilemesin.

### S3 — SHOULD-FIX: doğrudan 4'ten sonra bayat kart "prepared" ve ekranda kalıyor
- Yer: `api/serializers.py:868` (`economic_actions.prepared_offer(world)` bağı kontrol etmiyor); yazarın açık karar 7'si.
- Senaryo: kart (bira 4 + bahşiş 1) açık; oyuncu panelden 4'lük alım yapar. Kart `prepared` kalır, `state.economic_offer` hâlâ "Bira 4, Bahşiş 1 = 5" gösterir ve `EconomicPrepareControls` (`game-browser.tsx:2362`: `disabled={Boolean(state.economic_offer) ...}`) kilitli kalır. Onaylamak hiçbir şey kesmez ("Teklif değişti") ama oyuncu yanıltılır. Para güvenli.
- Öneri (Undo'yu bozmadan): durumu değiştirmeyin; `_economic_projection` içinde `counter_binding` taşıyan ve `shop_trade.binding_matches(world, offer)` yanlış olan kartı yalnız gösterimden çıkarın. Kart `prepared` kaldığı için Undo `reconcile` kartı yine geri açar; ayrıca `prepare_from_turn` yeni kartta zaten eskileri iptal ediyor.

### S4 — SHOULD-FIX: `economic_intent` alanı şemanın sonunda; D1'in "para beklemez" kuralının tersi
- Yer: `front_proposal.py:127-137` (deal/keep_change "kind'dan hemen sonra" yorumu; `economic_intent` `coin_cp`'den sonra), `game.py:18517-18527` (`typed:no_economic` dalı).
- Senaryo 1: küçük model uzun nesnenin son alanlarını `none` doldurur (D1 yorumu tam bunu söylüyor). Say modunda satıcıya "bir oda tutayım" (para yok): `economic_intent: none` -> `_front_economic_none = True` -> `typed:no_economic` dalı yalnız `{"kind": "speak_to"}` döner; modelin erken yazılan `deal: room` değeri bu dalda `_hand_over_coin`'a hiç verilmez (D1'de para anılmayan say satırı okunmuyordu, yani önceki davranış da kelimesizdi; ama şimdi okuma var ve çıktısı atılıyor). Oda kartı açılmaz; oyuncuya "kart yok" sinyali verilmez.
- Neden önemli: (b) maddesi "okuma varsa kelime kapalı" dediği için meşru oda isteği sessizce kaybolabilir (para güvenli).
- Öneri: `economic_intent`'i `deal`/`keep_change` ile birlikte `kind`'dan hemen sonraya alın; `typed:no_economic` dalında `deal` geçerliyse (`room`/`goods`) `_hand_over_coin(route, listed, raw_front)` çağırın (D1 kararı, para 0, "yalnız karar kart açar").

### S5 — SHOULD-FIX (D0 tasarımı; onay gerektirir): geçersiz ekonomik niyet oyuncunun satırını yutuyor
- Yer: `front_proposal.py:160-171` (`economic_route` `kind != speak_to` ya da kişi eşleşmezse `valid=False` ile yine rota döner), `game.py:18501-18509`, `game.py:18651-18656` (`_front_economic_offer` "npc_unknown" yanıtı).
- Senaryo: do modunda "tezgâha gidip bir bira alıyorum": model `kind: go_to`, `economic_intent: purchase`. Rota geçersiz sayılır ama `economic` `None` olmadığı için `_front_step` bunu döndürür; `_front_economic_offer` "Kime vermek istediğini tam anlayamadım" der, yürüme ve alım kaybolur. Say modunda başka kişiyle ilgili cümlede de (model `person_id` olarak başka kişiyi verirse) aynı. Para oynamaz.
- Öneri: `valid=False` ise `economic_route` `None` dönsün (okuma kendi `kind`'ıyla devam etsin); yalnız bilinçli bir "yanlış alıcı" durumunda soru sorulsun.

### N1 — NOTE: `_tender` ile `tip_cp` ve `drop_counter_tip` etkileşimi iki kayıt biçiminde farklı davranıyor
- `shop_trade.py:200-212`, `bold_acts.py:~858` (`drop_counter_tip`), `prepare_keep_change` (`shop_trade.py:233`).
- Model `deal=goods` vermezse `counter_offer_v1` içinde `tip_cp` yok, `tender_cp=5` var: doğrudan 4 satışı `_tender` ile 5'i tender sayar ve "Uzattığın 5 bakırdan 1 bakır para üstü sayılıyor" yazar; `TIP_KEPT` notu çıkmaz; panel `held` göstermez (5 doğrudan yazılamaz). `deal=goods` verirse `tip_cp` var, `_tender` 5'i sayarak yok. `_tender` docstring'indeki "kept change hiçbir zaman para üstü sayılmaz" değişmezi D0 rotasında tutmuyor. Kesinti her iki durumda 4 (para doğru).
- Reddedilen bahşiş: `tip_cp` varsa `drop_counter_tip` `tender_cp`'yi 5'ten 4'e indirir -> kart `binding_matches` ile bayatlar (yeni kart gerekir); `tip_cp` yoksa kart açık kalır ve onayda bahşiş satırı düşer. Yazarın açık karar 5'i bunu yarı anlatıyor.
- Öneri: `prepare_keep_change` başarılı olunca `counter_offer_v1["tip_cp"]` yazsın (tek kayıt biçimi, panel de 5'i gösterir).

### N2 — NOTE: `confirm_offer` bağlı kolda `reason_code == "stale"` (apply_resolution'dan) tüketilmiş sayılıyor
- `shop_trade.py:352-353` + `economic_actions.py:1655-1672`. Bağsız kolda `apply_resolution` "stale" verirse kart iptal + `_unmoved`; bağlı kolda aynı sonuç `consumed` olarak yazılır (tur sayacı artar, Undo kontrol noktası kayar) ama UI `reason_code === 'stale'` olan reddedilmiş onayı "tüketmeyen" sayıp son-tur hedefini kaydırmaz -> Undo hedefi bir tur geride kalır (4xx ile "artık geri alınamıyor"). Ulaşılabilirlik: aday, `apply_resolution` canlı parmak izi ile kopya eşit olduğundan pratikte erişilemez; doğrulanamadı. Öneri: `confirm_offer`'da `resolution.reason_code == "stale"` iki kolda da aynı işlensin.

### N3 — NOTE: defter `total_cp` anlamı değişti
- `shop_trade.py:370`: `total_cp` artık `resolution.net_debit_cp` (D0), D1'de mal fiyatıydı. Bahşişli doğrudan satışta kayıt 4 yerine 5. Defterin okuyucusu yalnız testler (`test_shop_trade.py:60`, bahşişsiz); tüketen kod bulunamadı. İstenirse `base.total_cp` yazın.

### N4 — NOTE: `take_room` `None` dönebilir, `_room_reply(None)` çöker
- `game.py:18733-18734`. `take_room` para kararı varken `kind != room` ise `None` döner; `_front_economic_offer` oda kolunda `_hand_over_coin` çağrılmadığından pratikte karar `None` ama savunma yok. Bir tür `if room is None:` kısa dönüşü ekleyin (doğrulanamadı: ulaşılabilirlik).

### N5 — NOTE: artık kullanılmayan içe aktarma, bayrak temizliği
- `game.py:18613` `_defer_spoken_coin_offer` içinde `import world_reactions` kullanılmıyor.
- `front_proposal.begin` (`front_proposal.py:435-455`) `_front_economic_none`, `_front_economic_front`, `_spoken_coin_proposal` bayraklarını sıfırlamıyor; yalnız `end` ve `_clear_turn_transients` sıfırlıyor. `front_read_ahead` çalışıp tur hiç koşmazsa (API reddi) bayrak sonraki tura sızıp kelime yolunu kapatabilir. `begin` içine `= False` ekleyin (yazarın sildiği satır `= True` idi, sıfırlama değil).

### N6 — NOTE: planlayıcı "economic" okumasını tanımıyor
- `game.py:18598` `_PLANNER_STAYS_OUT` `economic` türünü içermiyor; sahne planlayıcısı (`game.py:16886`) okuması `economic` olan bir satırda yine de yürüme/oturma/bakma kararı verebilir. D0'dan geliyor, para etkisi yok. Doğrulanamadı: uygulamada tetiklenir mi.

### N7 — NOTE: D0 imzalı eski kartlar ve bozuk `coin_responses`
- D0'ın `context_digest`'i `coin_response: null` anahtarını koşulsuz yazıyordu; birleşik kod yazmıyor. D0 ile saklanmış açık bir kart onayda `_still_holds` özet uyuşmazlığıyla `stale` olur: güvenli (kapalı başarısız), para oynamaz. D1 kartları değişmedi. Ayrıca `context_digest` (`economic_actions.py:394`) `npc["coin_responses"]`'ı `.get` ile okuyor ama dict doğrulaması yok (`_coin_response` doğruluyor): bozuk bir kayıtta kart hazırlama istisna fırlatır (kayıt kaybı yok, doğrulanamadı).

### N8 — NOTE: maliyet ve Undo ayrıntıları
- Say modunda satıcıya yazılan her satır artık bir model çağrısı (`game.py:18452-18461`, `served`); yalnız para anan satır değil. Sahip kararı gerekmez ama sağlayıcı sınırı olan ücretsiz modelde gecikme/oran sınırı etkisi var.
- `_with_tender` içinde bayat bağlı kartı iptal etmek (`bold_acts.py` ~834) Undo ile geri alınmaz (`reconcile` "iptal kalır" kuralı, C11). Yeniden teklif turu Undo edilince önceki kart geri gelmez; para etkisi yok.

---

## 3. Üç yazar tercihi için hüküm

**(a) Say-modu okuması yalnız para anınca ya da satıcıya söylenince.** Yanlış para üretmez: okuma yalnız kart açar, kesinti onay ister. Meşru bir alım kaybolmaz (alım kelime yolu hâlâ açık: `game.py` say dalı `bold_acts.shop_offer`). Eksik: satıcı olmayan kişiye parasız satırdaki hediye niyeti okunmaz (para yoksa zaten hediye yok). Daha sade/güvenli çözüm gerekmiyor; maliyet N8'de. Hüküm: kabul.

**(b) Okuma varsa oda kelimesi kart açmıyor.** Para yanlışı yok, ama S1 (uyku bedelsiz) ve S4 (kaybolan oda isteği) bu tercihin doğrudan sonucu. "Daha az kart = daha güvenli" gerekçesi yanlış: kart onaysız para oynatmaz; kartı kapatmak güvenliği artırmıyor, yalnız hizmeti bedelsiz ya da erişilemez bırakıyor. Daha basit çözüm: bayrak yalnız `_room_asked`/`_buy` kelime yollarını kapatsın, `_sleep_after_walk` çağrısını kapatmasın; `economic_intent` alanını başa alın ve `typed:no_economic` dalında `deal`'i kullanın.

**(c) `coin_response` alanı kaldırıldı.** Para yönünden güvenli: `coin_answer` yalnız `takes`/`declines`/başka (onaysız); "onaysız" kartta satırı reddeder. Meşru hediye/bahşişi kaybettirebilecek tek nokta S2 (kalıcı, tutara bağlı kayıt) ve `coin_answer_for`'un yok sayılması: kişi "mal için alırım" dese de (`for: goods:bira`) bekleyen hediye için `accept` yazılır. Kart yine oyuncu onayı ister, o yüzden zarar yok. Hüküm: alanın kaldırılması doğru; `coin_responses` ömrü düzeltilmeli.

**Yazar raporuna itirazlar:** (1) "hep daha az kart açan tarafı seçtim = güvenli" S1'de tersine çalışıyor. (2) Açık karar 6 "ikisi de blokluyor, daha katı/güvenli": S2'deki gibi sessiz bahşiş kaybı ve iki yüzey farkı üretir. (3) Açık karar 7: kartı iptal etmeden gösterimden gizleme (S3) hem Undo'yu hem arayüzü korur; yazar bu üçüncü seçeneği değerlendirmemiş. Yazarın "tarayıcıda bakılmadı" notları doğru; ben de tarayıcı çalıştırmadım.

---

## 4. Doğrulanamadı
- S1'de uykunun oda hakkından bağımsız başka yolla bedelsiz olup olmadığı; gerçek modelin "gidip uyuyorum" satırını hangi `kind` ile okuduğu.
- N2, N4, N6: tetiklenme yolları.
- Gerçek tarayıcı davranışı, gerçek kayıt göçü (D0 imzalı eski kayıtlar), testlerin gerçek sonucu (hiçbiri çalıştırılmadı).
