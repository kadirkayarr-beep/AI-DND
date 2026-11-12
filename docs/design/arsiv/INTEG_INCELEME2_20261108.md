# INTEG İNCELEME 2 (yalnız düzeltme commit'i `8c2a0569`, taban `3f15e639`)

## Özet
- BLOCKER: YOK (0). Para, kayıt, Geri Al veya tekrar oynatmayı bozan, ya da onaysız para hareketi açan bir yol bulamadım.
- Sayılar: BLOCKER 0, SHOULD-FIX 1, NOTE 5.
- S1-S4 kodda söylenen şeyi yapıyor; gerçek çağrı yolları (`_sleep_after_walk`, `_record_spoken_coin_response`, `_economic_projection`, `_front_step` typed dalı) izlendi. Yeni kelime listesi/regex yok.
- Tek gerçek eksik: raporun "D0 imzalı eski kartların özeti değişmedi" iddiası D0 için doğru değil (güvenli başarısızlık: kart bayatlar, para ödenmez).
- Sınır: yalnız okuma yaptım; testleri koşmadım. Raporun "kırmızı koşu 8 FAIL / yeşil" beyanı `doğrulanamadı` (kodu okuyarak testlerin kırmızı olacağını mantıkla doğruladım, koşmadım).

## Bulgular

### 1. SHOULD-FIX — D0 imzalı açık kartların özeti birleşmede değişti; rapordaki "değişmedi" iddiası D0 için yanlış
- Yer: `ai-dnd/economic_actions.py:427-437` (`context_digest`); karşılaştırma: `git show 3f15e639^2:ai-dnd/economic_actions.py` satır 383-388.
- D0 kolu `person["coin_response"]` anahtarını HER kart için, değer `None` olsa bile yazıyordu; mal kartında da `tip_response: None`. D1 kolu ve şimdiki kod anahtarı yalnız yanıt varsa yazıyor. `canonical_json` anahtarın varlığına duyarlı, yani D0 derlemesinin imzaladığı açık bir kart yeni kodda `_still_holds` içinde `context_digest(...) != offer.context_digest` olur ve "Teklif değişti; yeni kart gerekir. Hiçbir şey ödenmedi." döner.
- Senaryo: D0 derlemesiyle bir oda/hediye/bahşiş kartı açık kalmış bir kayıt yüklenir, oyuncu onaylar, kart bayat sayılır. Para kaybı/çifte ödeme yok (güvenli başarısız); yalnız kart yeniden açılmalı.
- Bu davranış `3f15e639` birleşmesinden geliyor, S2 düzeltmesi onu bozmadı; ama commit/rapor "iki kolun imzalı kartlarıyla uyumlu" diyor ve bunu pinleyen test yok. D0 derlemesiyle yazılmış gerçek kayıt olup olmadığı `doğrulanamadı`; yoksa NOTE seviyesinde.
- Öneri: ya raporu düzelt ("yalnız D1 imzalı kartlar uyumlu; D0 imzalı açık kart bir kez bayatlar"), ya da D0 derlemesi hiç dışarı çıkmadıysa bunu yazıp kapat. Gerçek D0 kaydı varsa: eski özet biçimini (null anahtarlı) kabul eden ikinci bir karşılaştırma ekle. Her iki durumda "imzalı eski kart" için bir test (D1 biçimi + D0 biçimi) ekle.

### 2. NOTE — `purchase_tip:<tutar>` anahtarını üretimde yazan kod yok
- Yer: `economic_actions.py:345-346, 378, 435, 782`; `game.py:18624-18637`.
- `_spoken_coin_proposal` yalnız `gift`/`tip` amaçlı kuruluyor (`_defer_spoken_coin_offer`), bu yüzden `record_coin_response(purpose=...)` hiçbir zaman `purchase_tip` yazmıyor. "Mal kartının bahşiş satırı kendi yanıtını tutar" yalnızca okuma tarafında var (eski gün-siz tutar anahtarlarını okuyor). Pratik sonuç: bağımsız bir bahşişe verilen yanıt artık mal kartının bahşiş satırını hiç etkilemiyor; mal kartı bahşiş satırının reddi yalnız D1'in `record_decline`/`_tip_declined` yolundan gelir. Önceki davranışta (tutar eşleşirse) etkilerdi. Bu istenen S2 sonucu gibi görünüyor, ama "kendi yanıtını tutar" ifadesi boş bir yetenek. Bunu pinleyen test yok (test 1 yalnız "bağımsız bahşiş yanıtı mal bahşişini düşürmez" doğruluyor, ki bu doğru ve anlamlı).
- Para riski yok: bahşiş satırı kartta görünür ve onaysız para geçmez.
- Öneri: dokümantasyon/rapor ifadesini düzelt veya `purchase_tip` yazıcısını gerçekten ekle (ihtiyaç yoksa `_REPLY_KINDS` içinden çıkar).

### 3. NOTE — Gün alanı olmayan eski kayıtlar sonsuza dek geçerli
- Yer: `economic_actions.py:383-397`.
- Eski tutar-anahtarlı kayıt (`{"1": {"status": "refuse"}}`) günle sınırlanmıyor; yalnız `accept` temizliyor. Yani S2'nin asıl hatası (yıllanmış ret) eski kayıtlarda sürüyor; test (`test_an_old_amount_only_record_still_refuses...`) bunu bilerek pinliyor. İstenen buydu ("old records still honoured"), yalnız bilinen kalıntı olarak yaz.
- Ek: gün sınırı 23:59'da yanıtı bitirir; açık kart özetinde yanıt girdisi vardı ise kart bayatlar (güvenli). Gün sınırında açık kart davranışını pinleyen test yok.
- Para riski yok.

### 4. NOTE — S1, yürüme-yatak yolunda hâlâ eski kelime regex'ine dayanıyor; regex kaçırırsa uyku bedava
- Yer: `bold_acts.py:706-715` (`take_room`), `game.py:19465-19475` (`_sleep_after_walk`).
- Düzeltme doğru: `walk_to_bed=True` yalnız `_front_economic_none` kapısını atlıyor; `_room_asked`/`_buy`/`requested=False` çağrıları kapalı kaldı (`bold_acts.py:773` `_room_asked` hâlâ `_front_economic_none` ile kapalı). Karar yine `money_owner.current` kararına öncelik veriyor (karar varsa kelimeler okunmuyor). Kart onay ister, para oynamaz; `prepared_by_action` koruması ikinci kartı engelliyor; oda hâlâ tutulmuyorsa uyku bekliyor.
- Kalan boşluk (yeni değil, S1 kapsamı dışı): kart açılışı hâlâ `_ROOM.search(...) and _wants_the_bed(...)` regex'ine bağlı (yeni kelime listesi değil, mevcut). Oyuncu "yukarı çıkıp yatıyorum" gibi oda kelimesi içermeyen bir cümle yazarsa `take_room` None döner ve `timed_gameplay` içinde oda hakkı denetimi olmadığından uyku bedava gerçekleşir (ön okuma kapalı olsa da açık olsa da aynı). Bu S1'in anlattığı "ön okuma yüzünden" kısmı değil, ondan önceden var olan boşluk. `doğrulanamadı`: gerçek bir han sahnesinde bu cümle biçimlerinin hangisi denendi.
- Öneri (ileride): uyku, tutulan oda hakkı yoksa ve sahnede hizmet veren varsa bir oda kartı/ret istesin (kelimesiz, durum denetimi).

### 5. NOTE — S3 yalnız bağlı (`counter_binding`) kartı gizliyor; gizli kart `prepared` olarak kalıyor
- Yer: `api/serializers.py:869-872`.
- Doğrulandı: durum değişmiyor; `reconcile_offers_after_undo` aynı kayıtları koruyor (consumed→prepared, kalan prepared korunur); Geri Al sonrası `counter_offer_v1` ve `seq` geri geldiği için `binding_matches` yeniden doğru ve kart görünür. Onay yolu zaten `_still_holds` içinde `binding_matches` ile reddediyor (`economic_actions.py:1650`, `shop_trade.confirm_bound_offer`), yani gizlenen kart onaylanamaz; Geri Al dışında çifte ödeme yolu yok. Yeni sayaç teklifi açılınca (`bold_acts.py:836-838`) bayat bağlı kart zaten iptal ediliyor.
- Küçük kalıntılar: (a) `prepared_offer` "sonuncuyu" döndürür; eski kayıtta birden fazla `prepared` kart varsa ve en sonuncusu bayat bağlı kartsa, öncekilerden geçerli olan da gizlenir (C12 "tek açık kart" ihlali olan eski kayıt gerekir; olası değil). (b) `_held_deed` (tutuklama) durumunda `binding_matches` False döndüğünden kart gizlenir; bu zaten onaylanamıyordu. (c) Gerçek tarayıcı doğrulaması yok (rapor da aynısını söylüyor); serileştirici/HTTP seviyesi test edilmiş.
- Bağlı olmayan (düz) bayat kartlar bu düzeltmenin kapsamı dışında.

### 6. NOTE — S4 typed dalı: `deal` ile `economic_intent` çelişirse `deal` kazanıyor
- Yer: `game.py:18518-18530`; `money_owner.read_deal`, `bold_acts.decided`.
- Doğrulandı: `said_coin` False olduğu için `coin_in` bu dalda 0 döner (`names_coin` ile aynı `_coin_clauses` testi), `_hand_over_coin` yalnız `_coin_decision` yazıyor (`amount==0` olduğundan `_coin_paid` kurulmuyor); sadece geçerli `room` veya listeli-malı `goods` deal'i geçiyor; `gift/tip/paid_before` ve listede olmayan mal geçmiyor (test 3 bunu pinliyor). Kart/kasa teklifi `decided()` ile açılıyor, para 0, onay gerekiyor. Şema `required` ⊆ `properties`, kopya yok, sıra değişikliği (`economic_intent` 5. alan) yalnız üretim sırası; OpenAPI sözleşmesi değişmedi (rapor).
- Sınır: model `economic_intent: none` yazıp `deal: room` yazarsa (rehberde "odayı yalnız anmak oda istemek değildir" ama `deal: room` "oda istiyor ya da onun parasını veriyor") yalnız anma cümlesinde de oda kartı açılabilir. Para kaybı yok (kart onaylanmadıkça bir şey geçmez). Gerçek modelin iki alanı nasıl dolduracağı `doğrulanamadı`.

## İstenen kontrollerin cevabı
1. Her düzeltme gerçek yolda ne diyorsa onu yapıyor (S1: `take_room` yolu; S2: yazıcı + `derive_acceptance` + `context_digest` aynı `_coin_reply`; S3: serileştirici; S4: şema + typed dal).
2. Yeni para/Geri Al/tekrar-oynatma riski: bulunmadı. Çifte ödeme yok; bedava hizmet yok (S1 yalnız kart açıyor); onaysız para hareketi yok; gün-anahtarlı yanıt gün atlayınca bayatlıyor (okuma tarafında kontrol), eski kayıtlar okunuyor; gizli kart Geri Al ile geri açılıyor (testle ve koddan doğrulandı); şema uyumlu. Özet değişimi: yalnız madde 1.
3. Testler anlamlı: S1 (kart sayısı, amaç, kasa 2400, `inn_room` boş, HP, saat), S2 (net borç 5, kasa 95/5; gün sonrası kart açılır; eski kayıt `may_refuse` ve net borç 4), S3 (kayıtlı durum `prepared`, projeksiyon None, Geri Al sonrası varlıklar eşit ve aynı `offer_id`), S4 (kart sabitleri, kasa 100, sayaç `bira`, gift-deal kullanılmaz). Eksikler: `purchase_tip` yazılan yanıt testi, hediye+bahşiş paylaşım testi (senaryo 17 kapsıyor, rapora göre), imzalı eski kart özeti testi, gün sınırında açık kart testi.
4. Yeni kelime listesi/regex: YOK. `_REPLY_KIND_OF` sabit bir tür eşlemesi.
