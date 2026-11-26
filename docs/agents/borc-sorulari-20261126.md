# Borç soruları (2026-11-26) — Kadir için

Plan: docs/superpowers/plans/2026-11-26-borc-sifirlama-plani.md (G0.1). Her soruya harfle cevap yeterli (ör. "S1 a"). "Hepsi öneri" de yeterli. Cevaplar bu dosyaya ve deftere yazılır; bir daha sorulmaz.

Her soruya harf ile cevap yeterli (ör. "S1 a"). "Öneri" bizim seçimimiz; cevapsız soru yeniden sorulmaz, yalnız dalga raporunda "cevap bekliyor" diye görünür ve ona bağlı görev başlamaz. Yalnız senin zevkine kalan ya da "wontfix/ertele" gerektiren sorular burada; classify.json'un 13 sorusu ve planın S52'si (eski numaralarıyla S2, S18-S23, S30, S33, S37, S39, S40, S45, S52; toplam 14) ajan kararına çevrildi, Rulings bölümünde satır kimliğiyle "R-D<no>" adıyla duruyor (birden çok satırı kapsayan Ruling ilk satırın adını taşır: R-D575 = D-575, D-585, D-311, D-568, D-569; R-D078 = D-078, D-079, D-304, D-306, D-302).

| No | Satır | Görev | Soru | Seçenekler | Öneri |
|---|---|---|---|---|---|
| S1 | D-024 | G0.1 | Bilinçsiz (Unconscious) kuralı PHB s.376'dan doğrulanmadı. Sen ya da Jarvis PDF'e bakabilir misin? | a) bak, doğrula, kapat · b) doğrulanmamış diye kabul et, kapat | a (Jarvis bakar) |
| S2 | D-320 | G0.1 | Para, kayıt ve Geri Al uç noktalarının (tekrar oynatma, eşzamanlı istek, iade) güvenlik incelemesi ne zaman? | a) şimdi, Opus ile · b) oyun internete açılmadan önce | b (bugün tek kullanıcı, yerel; satır 'internete açılana kadar wontfix') |
| S3 | D-021 | G0.1 | Gerçek model İngilizce 'I shove the guard' cümlesinde kavga sorusunu her zaman açmıyor. Motor güvenli. | a) motor yedek kural eklesin · b) olduğu gibi kalsın · c) ön model değişince bakılsın | b |
| S4 | D-343 | G0.1 | Parçalar motor adlarını game.X önekiyle okuyor; game.py'de 643 yeniden dışa aktarma satırı var. Bunlar kaldırılsın mı? | a) evet, ayrı bir dilimde · b) hayır, merkez kuralı kalıcı | b (kırılma riski büyük, oyuna faydası yok) |
| S5 | D-404 | G0.1 | Bayrak açıkken kullanılamayan okumadan sonra 2 çağrı sınırı yüzünden sonuç biraz kötüleşiyor. | a) kabul et · b) okumadan sonra ek çağrıya yer bırak | a |
| S6 | D-424 | G0.1 | Küçük model oda cümlesini 'belirsiz' okursa Python'un kelime yolu oda kartını yedek olarak açsın mı? | a) evet · b) hayır, tasarım kalsın | b |
| S7 | D-327 | G0.1 | Konuşma kipindeki eski kelime yedek yolları ne olsun? | a) sonraki oynayış ve ölçümden sonra kaldır · b) kalıcı yedek olarak kalsın | b (zararsız; model düşünce oyunu ayakta tutar) |
| S8 | D-246 | G0.1 | İlan panosu ya da iş listesi olduğunda söylenti sorusu oraya yönlendirsin mi? | a) evet · b) hayır, 'söylentiler belirsiz' kalsın | b (bugün pano olup olmadığını doğrulamadım) |
| S9 | D-168 | G0.1 | Uygulama içi araç sayaç dosyasının eski kopyasını gösteriyor. Bu yalnız geliştirici aracı. | a) wontfix · b) okuyucuyu düzelt | a |
| S10 | D-149 | G0.1 | Oyuncu başına maliyet kotası gerekli mi? | a) şimdi yap · b) gerek yok · c) çok kullanıcılı yayına kadar ertele | c |
| S11 | D-307 | G0.1 | Yolda ikinci yerleşim (ör. Phandalin) ve kentler arası yolculuk yapılsın mı? | a) dilim olarak yap · b) ertele, bugünkü çıkmaz mesajı kalsın | b |
| S12 | 17 satır | G0.1 | Bu satırlar bir özellik gelmeden düzeltilemez. Her biri 'ertelendi: <özellik>' diye kapansın mı? Tetikleyici sütunu kalır; özellik gelince satır yeniden açılır. Para/kayıt/Geri Al satırları **kalın**. D-312: çok kullanıcılı barındırmada oturum sahipliği yok (özellik: çok kullanıcılı barındırma) · D-315: internete açık sürümde istek sınırı ve CORS eksik (özellik: internete açık sürüm) · D-029: yakın/uzak ayrımı konumsuz tahmin ediliyor (özellik: konum modeli) · D-022, D-025, D-026, D-014: İngilizce cümlelerde niyet/hedef okuması eksik (özellik: İngilizce dil desteği) · **D-009**: XP tablosunda olmayan CR'lı ilk canavar ödülsüz kalır (özellik: o canavarın eklenmesi) · D-169: NPC isteklilik/Influence modeli yok (özellik: Influence) · **D-271**: kalıcı ödül işareti kayıtta yok, ödül iki kez verilebilir (özellik: kalıcı ödül işareti) · D-042: Wizard/Cleric özellikleri sayfalı kaynak ve çözücü olmadan eksik (özellik: o sınıf çözücüleri) · **D-048**: müttefik NPC iyileştirme yolu yok, büyü/iksir harcanmadan sonuç çıkabilir (özellik: müttefik iyileştirme) · **D-050**: odak/malzeme bileşeni harcaması kayda yazılmıyor (özellik: bileşen kaydı) · D-058: savaşta anlatı büyüsü eylem ekonomisini atlıyor (özellik: savaş büyü eylemleri) · D-358: CI Python 3.14'e geçince yerel ile CI farkı (özellik: CI 3.14) · D-066: yoğunlaşma çözücüsü D-048'i bekliyor (özellik: yoğunlaşma çözücüsü) · **D-023**: Healer's Kit kodu oyuna bağlı değil, Geri Al sarmalı gerekiyor (özellik: stabilize eylemi + NPC müttefik ölüm kurtarışları) | a) hepsi ertelensin · b) satır satır yaz (ör. 'D-029 yap') | a (yapılan iş özelliği yarım getirir; para satırlarında bugün oyuncu o yola giremiyor — doğrulamadım, G0.1 doğrulayıcısı her biri için bunu kod okumasıyla kanıtlar) |
| S13 | D-177 | G1.3 | Motorun ayıramadığı model yanlış okumaları için yeniden tasarımdan önce küçük bir gerçek model ölçümü yapılsın mı? | a) evet, yerel gemma4-12b-dm ile (para harcanmaz) · b) evet, bulut modelle (bütçe rakamını sen ver) · c) ölçme, kurala göre düzelt | a |
| S14 | D-262 | G1.3 | 'timing' alanı gelmezse bugün 'şimdi' sayılıyor (güvensiz). Alanın gerçek modelde ne sıklıkla doğru dolduğu ölçülsün mü? (S13 ile aynı ölçüm) | a) yerel ölçüm · b) bulut ölçüm, bütçe sen · c) ölçme, alanı zorunlu yap ve eksikse sor | a |
| S15 | D-263 | G1.3 | 'evet' sonrası okuma yeniden yapılıyor ve ikinci okuma farklı çıkabilir. Ölçülsün mü? (S13 ile aynı ölçüm) | a) yerel ölçüm · b) bulut ölçüm, bütçe sen · c) ölçme, ilk okumayı sakla ve yeniden oynat | a (ölçüm ne derse desin ilk okumayı saklamayı da öneriyoruz) |
| S16 | D-260 | G1.3 | Bir satırda iki eylem ayrı zamanda olabilir ('yarın vuracağım ama şimdi içiyorum'). Okumaya eylem başına zaman alanı eklensin mi? | a) evet, eylem başına · b) hayır, karışık satırda oyuncuya kısa soru sorulsun | a |
| S17 | D-530 | G1.8 | Tur kodundaki kalan üç uzun işlev (_run_player_turn_internal, _dispatch_player_turn, _narration_safety_decision) şimdi bölünsün mü? Satır 'oynayıştan sonra' diyordu. | a) evet, bu planda, önce davranışı sabitleyen testlerle · b) bir sonraki oynayışından sonra | a |
| S18 | D-592 | G1.8 | 109 işlev F karmaşıklıkta. Bu planda üç tur işlevi bölünür ve 'yalnız küçülür' kapısı (ratchet) kurulur. Kalan işlevler için ne olsun? | a) ayrı bir planla hepsi küçültülsün (satır o plana kadar 'kısmen' kalır) · b) kalanlar wontfix: kapı onları yalnız küçültür, büyütmez (onay listesine 'gevşetme olabilir' diye girer) | b (109 işlevi bölmek haftalar sürer; oyuna faydası düşük) |
| S19 | D-425 | G2.2 | Konuşma kipinde oyuncu oda isteyince hancı konuşsun mu (bir ek model çağrısı) yoksa yalnız kart mı açılsın? | a) hancı konuşur · b) yalnız kart | a (sinematik anlatı kuralın) |
| S20 | D-419 | G2.3 | 'Satırın kalanı' ve yeniden sorulan stok cevabı için ek çağrılar NPC inisiyatifi gibi 3. çağrı istisnası alsın mı? | a) evet, bunlar için de sınır 3 · b) hayır, 2 kalsın, kaybolan cümleyi kabul et · c) oynayış kaybı gösterince karar ver | a |
| S21 | D-012 | G2.4 | Model gerçek deneyim ödülünü kendi cümlesiyle söylerse ('25 deneyim puanı kazandın') bugün reddediliyor. Tutar gerçek ödülle aynıysa izin verilsin mi? | a) aynı tutarsa izin ver, farklı tutar yine reddedilir · b) bugünkü gibi kalsın (sayıyı yalnız Python yazar) | a (sinematik anlatı; para/XP doğruluğu korunur) |
| S22 | D-498 | G2.5 | 'Dışarı, <kent> sokaklarına çıkıyorsun.' aynı oyunda tekrar tekrar yazılıyor. | a) çıkış satırını her sahnede model yazsın; Python satırı yalnız yedek ve ziyaret başına bir kez · b) yalnız ziyaret başına bir kez göster, sonra kısa çeşit | a |
| S23 | D-403 | G2.9 | Oyuncuya sayı söylenmeden 'biraz para' uzatılınca oyun ne yapsın? | a) reddet · b) tutarı sor · c) varsayılan bir tutar seç | b |
| S24 | D-451 | G2.18 | Test bulma aracı (inventory.touching_tests) içe aktarılan sınıfı yönteme göre değil ada göre çözüyor; güvenli yönde, yalnız yavaş. | a) gerekçeyle kabul et, kapat · b) şimdi düzelt | a |
| S25 | D-349 | G2.19 | Yönlendirme denetiminin (routing_audit) bilinen kör noktaları (eval/exec, string getattr, iki adımlı zincir) kapatılsın mı? | a) belgele ve kabul et (çalışma anı kimlik testi asıl riski kapsıyor) · b) kapat | a |
| S26 | D-536 | G2.24 | Makbuz sıkıştırma (compact_receipts) gerçek oyunda hiç çağrılmıyor, yalnız testler çağırıyor. | a) gerçek oyunda aç (kayıt küçülür, Geri Al'ın ulaştığı derinliği sınırlayabilir) · b) sil | b |
| S27 | D-445 | G2.25 | game.py başındaki 45 kullanılmayan içe aktarma için öneri: 44'ü kalsın (yama hedefi ya da yüzey), __main__ bloğundaki 1 'import game' silinsin (text_rules_a.py'deki eşiyle). | a) öneri kabul · b) satır satır yaz | a |
| S28 | D-490 | G2.25 | Ölü kod tablosu (docs/engine-split/olu-kod-kaniti.md) satır başına evet/hayır bekliyor. Tablodaki önerileri toplu kabul ediyor musun? | a) öneriler toplu kabul · b) tabloyu sen satır satır doldur | a |
| S29 | D-544 | G2.26 | combat_bind_allowed işlevi ölü. threat_band 'none' iken savaş bağı reddedilsin mi? | a) evet, kuralı gate.py'ye ekle ve işlevi tut · b) işlev ölü, sil | b |
| S30 | D-286 | G3.1 | İngilizce olumsuz kese cümlesi ('Not a single copper leaves your purse.') ele alınsın mı? | a) İngilizce olumsuzluğu şimdi ekle · b) İngilizce kip gelene kadar bekle (wontfix) | b |
| S31 | D-287 | G3.1 | Kazanılan zarda anlatı 10 bakır diyor, 5 bakır ödeniyor. | a) anlatıyı ödenen tutara göre yeniden yaz · b) nadir, olduğu gibi kabul et | a (para doğruluğu) |
| S32 | D-253 | G3.2 | 'Kısa Yay & 20 Ok' paketinde okların repoda fiyatı yok. | a) 20 ok için katalog fiyatı ekle (2024 kuralları: 1 GP) · b) paket satışını reddet | a |
| S33 | D-381 | G3.5 | Oyuncu 'şehrin dışına gidiyorum ve <kasabadaki biri>'ni soyuyorum' derse oyun ne yapsın? | a) o kişiye yürüsün · b) 'o kişi kasabada mı?' diye sorsun | b |
| S34 | D-310 | G3.6 | Güvenlik denetiminin değiştirdiği NPC sözlerinin model ham metni görünmüyor. Yerel oyun başlatıcısı konuşma hata ayıklama kaydını (AI_DND_SPEECH_DEBUG) varsayılan açsın mı? | a) evet, -LocalPlay'de açık · b) hayır, sonraki oyunda elle açarsın | a |
| S35 | D-589 | G4.1 | pyright (tip denetimi) kapıya girsin mi? | a) evet, yalnız küçülen taban (ratchet) olarak · b) kapı olmadan yalnız en kötü dosyaları düzelt | a |
| S36 | D-591 | G4.1 | ruff hata kalıbı kuralları B023/B904/B905 kapıya girsin mi? | a) bugünkü sayıyla taban yapıp kapıya ekle · b) yalnız kaynak koddakileri düzelt | a |
| S37 | D-600 | G4.1 | Yedi yeni araçtan hangileri CI kapısına girsin? CI süresi artabilir. | a) pip-audit, pnpm audit --prod, import-linter, pyright ratchet · b) yalnız iki audit · c) hiçbiri | a |
| S38 | D-598 | G4.3 | desloppify bazı kümeleri bilinçli tasarım yüzünden 'sorun' sayıyor (ör. game_parts tek paket olduğu için 988 bölümler arası özel içe aktarma). Bunlar 'gerekçeli yanlış alarm' diye kapansın mı? | a) evet, gerekçe satır notuna yazılır · b) hayır, hepsi düzeltilsin | a |
| S39 | D-599 | G4.2 | İki soru: (1) /docs ve /openapi rotaları barındırma kipinde kapansın mı? (2) Koddaki yaklaşık 935 'raise ValueError' GameError'a taşınsın mı? | (1) a) barındırma kipinde kapalı, yerelde açık · b) her yerde açık. (2) a) taşı · b) taşıma, yalnız yeni kod GameError kullansın | (1) a (G2.10 D-314 ile aynı iş) · (2) b (davranış ve hata metni riski) |

Kaynak sayımı: 39 soru. 36'sı classify.json'daki 49 sahip sorusundan kalanlar; 13'ü (eski S2, S18-S23, S30, S33, S37, S39, S40, S45) ve planın eski S52'si ajan kararına (Ruling) çevrildi. S12 erteleme listesi, S16 (D-260) ve S21 (D-012) plan tarafından eklendi. D-382 S33'ün cevabını izler.

## Cevaplar

Kadir, 2026-11-26: "Hepsi öneri"

- S1: a — Jarvis PHB s.376'ya bakar, doğrular, kapatır
- S2: b — internete açılmadan önce incele (bugün wontfix)
- S3: b — olduğu gibi kalsın
- S4: b — merkez kuralı kalıcı, yeniden dışa aktarmalar kalır
- S5: a — kabul et
- S6: b — hayır, tasarım kalsın
- S7: b — kalıcı yedek olarak kalsın
- S8: b — hayır, 'söylentiler belirsiz' kalsın
- S9: a — wontfix
- S10: c — çok kullanıcılı yayına kadar ertele
- S11: b — ertele, bugünkü çıkmaz mesajı kalsın
- S12: a — 17 satırın hepsi ertelensin
- S13: a — yerel gemma4-12b-dm ölçümü
- S14: a — yerel ölçüm
- S15: a — yerel ölçüm (+ ilk okumayı saklama)
- S16: a — eylem başına zaman alanı
- S17: a — bu planda böl, önce karakterizasyon testleri
- S18: b — kalanlar wontfix, ratchet yalnız küçültür (onay listesine 'gevşetme olabilir')
- S19: a — hancı konuşur
- S20: a — 3. çağrı istisnası
- S21: a — aynı tutarsa izin ver
- S22: a — model yazsın, Python satırı yedek ve ziyaret başına bir kez
- S23: b — tutarı sor
- S24: a — gerekçeyle kabul et, kapat
- S25: a — belgele ve kabul et
- S26: b — sil
- S27: a — öneri kabul
- S28: a — öneriler toplu kabul
- S29: b — işlev ölü, sil
- S30: b — İngilizce kip gelene kadar bekle (wontfix)
- S31: a — anlatıyı ödenen tutara göre yeniden yaz
- S32: a — 20 ok için katalog fiyatı (1 GP)
- S33: b — 'o kişi kasabada mı?' diye sor
- S34: a — -LocalPlay'de AI_DND_SPEECH_DEBUG açık
- S35: a — pyright yalnız küçülen taban
- S36: a — bugünkü sayıyla taban, kapıya ekle
- S37: a — pip-audit, pnpm audit --prod, import-linter, pyright ratchet
- S38: a — gerekçeli yanlış alarm olarak kapat
- S39: (1) a — /docs ve /openapi barındırma kipinde kapalı; (2) b — ValueError taşıma, yalnız yeni kod GameError
