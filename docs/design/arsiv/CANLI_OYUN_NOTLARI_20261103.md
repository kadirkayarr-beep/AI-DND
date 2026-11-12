# Canlı oyun notları — Caddo (Yarı Elf Düzenbaz), gerçek tarayıcı, 3 Kas 2026 akşam

Oynayan: Claude (Chrome eklentisiyle, Kadir'in adına). Kayıt: Caddo kampanyası (en son oynanan). Adres: http://127.0.0.1:22785/ai-dnd-experience/

## OYUN MANTIĞI (para/durum)
1. [ÖNEMLİ] "bira sipariş ediyorum" → barmen "4 bakır, tezgâha koy". Oyuncu "5 bakır veriyorum, üstü kalsın" → oyun bunu HEDİYE kartı yaptı ("Hediye — 5 bakır"), bira VERİLMEDİ. Oyuncu bunu anlayamaz. Doğru yol: "Tezgâhtan satın al" paneli (oyuncu bunu bilmiyor).
2. [ÖNEMLİ] Barmen, bira parası ödendikten sonra bile "Parayı tezgâha bırakmadan içeceği kafaya dikiyorsun" dedi → anlatı, gerçek durumu (bira ödendi) bilmiyor.
3. "az önce 5 bakır verdim" (GEÇMİŞ zaman) → oyun bunu YENİ 5 bakır teklifi yaptı + "Yarım saat geçiyor". Kart çift ödemeyi engelledi (iptal ettim), ama dil okuması yanlış.
4. [ÖNEMLİ] "bir oda tutmak istiyorum, geceyi burada geçireyim" → barmen sadece "Peki." dedi, kart açılmadı, fiyat söylenmedi. Odayı ancak üstteki "Teklif hazırla" formundan istemek çalıştı.
5. Oda kartı ve onay doğru çalıştı: 50 bakır, "50 bakır ödendi". Ama ne için ödendiği yazmıyor ("Oda tutuldu" demiyor).
6. Uyku ayrı satırla çalıştı ("odama çıkıp sabaha kadar uyuyorum" → 2 Mirtul 07:00, can dolu). Bilinçli değişiklik.
7. Para hesabı DOĞRU: 5795 − 4 (bira) − 50 (oda) = 5741 bakır = "57 altın 41 bakır". Defter tuttu.
8. "Bira" envanterde kaldı; "birayı içiyorum" dedim ama tüketilmedi.
9. Odaya çıkıp uyuduktan sonra bile "Konuşuyorsun: Bir barmen" duruyor (konuşma kipi yapışkan).
10. Konuşma sürerken "hanından çıkıyorum" → barmene söylenmiş söz sayıldı ("Bak sen."), hareket olmadı. Önce "Konuşmayı bitir" gerekti.
11. "Etkileşime geç" (en belirgin turuncu düğme) → "Şu anda buna müdahale edemiyorsun."
12. Para gösterimi tutarsız: anlatıcı "57 altın 41 bakır" (gümüş yok); tezgâh paneli "57 altın 9 gümüş 5 bakır".

## ARAYÜZ / BİÇİM
A. Hikâye alanı çok küçük: yukarıdaki form+kartlar+dikkat çubuğu ekranı yiyor, hikâye ~175-250 px'lik iç içe kaydırma kutusunda. Çift kaydırma çubuğu.
B. Kartlar sayfanın EN ÜSTÜNDE, yazı alanı EN ALTTA. Oyuncu "teklif hazır" okuyup kartı bulmak için yukarı kaydırmak zorunda. Sonuç mesajları da görünür alanda değil ("↓ Yeni yanıt" düğmesi).
C. "Teklif hazırla" formu çıplak HTML gibi: etiketler yan yana yapışık ("Kime Bir barmen Ne Hediye Tutar (bakır) Odayla ayrı bahşiş..."), giriş kutularının çerçevesi yok, onay kutusu ve "Kartı hazırla" düğmesi sıkışık.
D. Kart açılınca alttaki form aşağı ZIPLIYOR (yerleşim kayması).
E. Hikâyede "HAMLEN: /item shop_buy npc_004 bira 1 0 4" — ham komut oyuncuya gösteriliyor.
F. Etiket tutarsızlığı: "ÖNCEKİ SÖZÜN" ve "HAMLEN" aynı şey için karışık.
G. "Onaylarsan işlem denenir." — tekniksel/soğuk dil. "Hediye" etiketi bira ödemesi için yanıltıcı.
H. Geri alma düğmesi etiketsiz küçük bir ikon, yazı kutusunun altında; üzerine gelince ipucu yok. (Erişilebilirlik adı "Son turu geri al".)
I. Sayfa altında ~160 px boş koyu şerit (kap yüksekliği tüm ekranı doldurmuyor).
J. Karakter sayfası: becerilerde İNGİLİZCE ("ATHLETICS", "INTIMIDATION", "STEALTH", "SLEIGHT OF HAND"), "LVL 01", "SNEAK ATTACK: 1D6".
K. Karakter sayfası: "Sunucunun bildirdiği bekleyen veya sınırlı kapsam:" başlıklı kutuda İngilizce geliştirici notları ("Rogue equipment packages are the existing catalog lists, not yet the PHB packages", "Sneak Attack: spell attack rolls never qualify...").
L. Karakter sayfası: eşyalarda dahili kimlikler görünüyor: "Deri Zırh [item_000001]" ... "Bira [item_000006]".
M. Karakter sayfası: "Kimlik" bölümünde 4 satır "Kayıtta yok" (Köken/Görünüş/Kişilik/Geçmiş) — doldurulamayan boş alan.
N. KESE (para) karakter sayfasında hiç yok; yan menüde de yok. Para sadece "envanterimde ne var" yazınca ya da tezgâh panelinde görünüyor.
O. Yan menü (Karakter/Dünya/Kişiler/Günlük/Çatışma) çok küçük, silik yazı, çok az bilgi; aynı bilgi üstteki Karakter/Dünya modallarında tekrar.
P. Modallerin kapatma düğmesi sol üstte, kalın bir başlık şeridi (~70 px) kaydırırken içeriği kapatıyor. Modal açıkken üst çubuktaki düğmelerin yeri hafif kayıyor (yanlış düğmeye bastım).
Q. "DENEYSEL — Keşif ve yolculuk · isteğe bağlı araçlar" etiketi oyuncuya geliştirici dili gibi.
R. Başarı bildirimi (yeşil kutu) uyarı üçgeni ikonu taşıyor, ve mesaj hikâyedeki satırın aynısı (çift).
S. İptal geri bildirimi var ("Teklif iptal edildi; hiçbir şey ödenmedi.") ama hikâye kutusunun içinde, ekranda görünmüyor.
T. Üst çubuk (saat, can) sayfayla birlikte kayıp gidiyor; yazarken saat/can görünmüyor.

## EK (tur 21-22)
13. İlan panosu çalıştı ama metin "..." ile yarıda kesildi ("Geçici geçiş için ayrılması düşünülen..."); aynı ilan iki kez tekrarlandı (Kuzey Hasadı Tahılcısı).
14. "hanın kapısından çıkıp sokaktaki iki yolcuya doğru yürüyorum" → sadece çıkış yapıldı; yolculara yürüme göz ardı edildi, ek bilgi verilmedi.
15. "satıcıya yaklaşıp ne sattığını soruyorum" → satıcı kişi olarak tanınmadı; yerine daha önce vedalaştığım Beralum cevap verdi ("Ben satıcı değilim..."), konuşma kipi tekrar Beralum'a kilitlendi. Dikkat çubuğundaki "satıcı" ile oyun içi kişiler uyumsuz.
16. "Etkileşime geç" hâlâ "Şu anda buna müdahale edemiyorsun." diyor (satıcıya).

## EK 2 (tur 23-27: muhafız, kavga)
17. Muhafızla sohbet çalıştı, cevap tutarlı ("resmi bilgim yok").
18. "Yumruk atıyorum" → ~30 sn işlendi, sonra "Hamlenin sonucu belirsiz" uyarısı. "Durumu sunucudan kontrol et" ile kurtarıldı: hamle aslında işlenmişti. Kurtarma yolu iyi, ama bekleme sırasında ilerleme göstergesi yok (sadece "İŞLENİYOR"), 30 sn çok uzun. Kurtarma sonrası yazı kutusunda eski hamle metni kaldı (bayat).
19. Kavga başlayınca ekranda "SAVAŞ BAŞLADI" gibi bir bildirim yok; sadece küçük satır ("Saldırın hedefi ıskalar..."). Düşman canı gösterilmiyor. Oyuncu can yalnızca sol altta "6/9".
20. Savaş denetimleri İNGİLİZCE/karışık: "ACTİON: HAZIR", "BONUS: UYGUN YETENEK YOK", "REACTİON", "Dash · Action", "Ready · Action", "SPEED: 30 FT", "SNEAK ATTACK: 1D6".
21. "Kaçıyorum" → "Buradan sıyrılabileceğin bir çıkış göremiyorsun" (bilinen: çıkışı olmayan sahne, 3c). Kaçamama bu kadar düz yazılmış; ne yapabileceğini söylemiyor.
22. Savaşta "geri al" ikonu görünmüyor / erişilemedi.
23. "Fikir lazım mı?" açılır bölümü çok silik, fark edilmiyor.
24. Savaşta bile dikkat çubuğu "satıcı... ETKİLEŞİME GEÇ" gösteriyor (savaşta alakasız).

## EK 3 (ölüm, yenileme, geri al)
25. Muhafız kılıçla 3. darbede Caddo 0 HP oldu. "Ölüm kurtarma zarını at" düğmesi çıktı; zarlar (12, 7, 8, 3) çalıştı; 3. başarısızlıkta "Öldün" (not: son zar 3 ile iki başarısız → ölüm). Mantık iyi, anlatı güzel.
26. 0 HP iken savaş düğmeleri (Saldır, Dash, Hareket et, Ready) hâlâ tıklanabilir görünüyor, ölü/baygın durumda gri değil.
27. Ölüm sonrası ekran: "Teklif hazırla" formu, "Etkileşime geç", "Konuşuyorsun: Bir muhafız" hâlâ aktif. "Caddo öldü / Yeni karakterle başla" paneli sayfanın EN ALTINDA, yazı kutusunun üstünde; ilk bakışta görünmüyor, ölünce üstte büyük bir ekran yok.
28. Ölü karakterle hamle yazınca "Sesin karanlığa karışıyor; cevap gelmiyor." cevabı geliyor (güzel).
29. Sayfa yenileme: ana ekrana düşüyor (kampanya otomatik açılmıyor), "Maceraya devam et" → liste → Caddo. Durum eksiksiz korundu (HP 0/9, ölüm zarları).
30. Ana ekran: "Maceraya devam et" iki adım (önce liste, sonra kayıt); kayıt isimleri "Caddo — Yeni Macera" hepsi aynı kalıp.
31. Geri al: onay çubuğu ("Bu tur ve sonuçları geri alınacak. GERİ AL / VAZGEÇ") iyi; sonuç mesajı net. Ama simge etiketsiz, ve geri alma sadece son turu alıyor (ölümü geri alamadım, o başka tur).
32. Savaş kapanış kutusu "ÇATIŞMA SONA ERDİ / Çatışma sona erdi." aynı cümle iki kez.
33. Zar atış sırasında zar değerleri anlatıda gömülü; görsel zar yok.

## EK 4 — Kadir'in kendi oynayışı (2026-11-03 gece/2026-11-04, sürüm c-merge 3c733c57, Haiku sınırı hâlâ açık)
Kaynak: Kadir'in oynayış notları ve yapıştırdığı transkript (Kadir karakteri, Beşvel/Ferumel). Neden iddiaları koddan DOĞRULANMADI; ölçüm Adım 2'de.
Genel: Kadir "eğlendim" dedi (özellikle savaşta); ürün kabulü DEĞİL.

Ciddi
34. Karakter ekranında 85 altınlık C paketi seçilmesine rağmen oyuna "15 altınla" başlandı. Doğrulama (Kadir'in envanter cevabı): kese 59 altın 22 bakır = 5922 bakır; harcamalar (30+4+50+5=89) ve bulunan 11 bakır geri sayılınca gerçek başlangıç TAM 60 ALTIN. Defter kendi içinde doğru; sorun yaratma ekranındaki rakamlar (85 ve 15) ile gerçek başlangıç (60) arasında. Hata yaratma/ekran gösterimi tarafında (kaynak koddan doğrulanmadı).
35. Sohbetle bira isteğinde kart çıkmıyor; tezgâh paneli gerekti. Para verince kart çıkıyor ve onaylayınca ödeme çalışıyor ("5 bakır, üstü kalsın" → 5 bakırlık HEDİYE kartı, 4 bakırlık bira satın alma değil). Sonra anlatıcı "biramı içiyorum"u normal anlattı; birayı kartla alıp envantere girip girmediği doğrulanmadı.
36. Barmen fiyatı unutuyor: "Bira 4 bakır. Kaç tane?" üç kez, sonra "Bira dört bakır değil", sonra "Öyle bir şey demedim". Anlatıcı fiyatı doğru söylediği anlar var (bira 4 bakır, oda 5 gümüş), tutarsız. Motor fiyatı sahiplenmeli (tasarım kararı g).
37. Pazarlık: İkna zarı başarılı (17, SZ 15), barmen indirimi reddetti, oda 50 bakır kaldı. Zar sonucu etkisiz.
38. Oda parası ödendi (50 bakır), "anahtarı alıp odaya gidiyorum" → "Uzanıyorsun ama eline geçen bir şey yok." Oda/anahtar kaydı yok. Sonra "hana gidip odamda sabaha kadar uyuyorum" → uyku olmadı, yalnız "5 saat 19 dakika geçiyor".
39. Silah çelişkisi: sistem bir an "uygun silahın yok" dedi, anlatıcı kılıç savurduğunu yazdı. Envanter cevabı: Greatsword, Ağır Tatar Yayı & 20 Ok, Macera Çantası, Tabak yemek, Bira (kısa kılıç yok, ama Greatsword var). Yay vardı, yay atışı HATA DEĞİL. Açık olan: "uygun silahın yok" uyarısı Greatsword varken neden çıktı (belki "kılıç" ifadesini Greatsword'a eşlemedi); tekrar denenip doğrulanacak.
54. Tüketilen eşya envanterde kalıyor: yemek yendi, bira içildi (anlatıda), envanter hâlâ "Tabak yemek, Bira" gösteriyor. Kaynak doğrulanmadı.
56. Ok harcanmıyor: Kadir yayla en az 1 (hatırlamasına göre 2) kez ateş etti, envanter hâlâ "Ağır Tatar Yayı & 20 Ok". Başlangıç sayısı Kadir tarafından doğrulandı: 20 okla başladı, atıştan sonra hâlâ 20. Atış sayısı 1 mi 2 mi belirsiz (transkriptte tek atış var); sonuç değişmiyor. Madde 54 ile aynı aile: tüketilen/harcanan kalem envanterde azalmıyor (yemek, bira, ok). Kod: tüketim/cephane düşümü olup olmadığı doğrulanmadı.
55. Envanter adları karışık dil: "Greatsword", "Ağır Tatar Yayı & 20 Ok" (çeviri tutarsız).
40. Savaşta "Ready" → "Dövüşün ortasında bu olmuyor" (geçerli D&D eylemi); "rakibin yanına gidiyorum" → "Silahını kaldırmışken yürüyüp gidemezsin". Savaşta yersiz engel.
41. Konuşma kipi: "Konuşmayı bitir" ve yer değiştirme doğru kapattı; yalnız uyku sonrası açık kaldı (madde 4 daraltıldı).

Orta
42. "Dışarı çıkıyorum" sahne atlatıyor: odadan çıkınca Kuzey Hasadı Tahılcısı içine girildi; gece/akşam ifadesi tutarsız.
43. Boş/alakasız cümleler: "Bu sorunun peşini bırakmamaya karar veriyorsun.", "Çevrede şimdilik belirgin bir değişiklik olmuyor." (bira siparişine iki kez).
44. Dış mekânda kalıp "…karşına çıkıyor ve içeri adım atıyorsun" (Omeril İskelesi).
45. NPC repliklerinde parantezli sahne yönergesi sızıyor ("Bir barmen (… başını kaldırır): …").
46. Selam kalıbı atmosfere uymuyor: muhafız ve barmen "Aleykümselam" dedi.
47. Cinayetin dünyada karşılığı yok: Ferumel öldürüldü, hiçbir tepki (3c).
48. İş bulma döngüsü: NPC'ler oyuncuyu birbirine paslıyor; iş bulunamıyor. Seyyar satıcıdan kendiliğinden bir görev çıktı (Ferumel'e iade kapları, 14 bakır): olumlu işaret.
49. İlk dakikalarda somut olay/yön yok, oyuncu boşta.
50. Han içindeyken "Dikkatini çeken" şeridi sokak sahnesini gösteriyor ("İki yolcu, bir bankın yanında…"): bayat ipucu, hata adayı.

Arayüz
51. Panel/savaş paneli açıkken hikâye alanı 4–5 satıra daralıyor; "Teklif hazırla" formu stilsiz, kişi olan her sahnede açık.
52. Tezgâh alışverişinde ham `/__direct_shop_buy__…` komutu sohbete yansıyor (ui-labels dalı e4439bab düzeltiyor, birleşmedi).
53. Ana ekranda bitişik yazım hatası; sınıf ve geçmiş kartlarında çevrilmemiş İngilizce metin.

Olumlu / doğrulanan
- Kese hesabı tezgâhtan alışverişte doğru (yemek 30, bira 4 bakır; oda 50 bakır).
- Hız: sohbet 3–5 sn, savaş düğmeleri <1 sn, takılma yok (önceki oynayıştaki 30 sn bu kez görülmedi → nedeni Adım 2'de ölçülecek).
- Doğru NPC cevap veriyor; savaş net başladı ve taktik panel açıldı; Hareket, Dash, Action Surge, Second Wind çalıştı; ceset arama (11 bakır) çalıştı.
- Denenmedi: Geri Al, Kaydet, savaştan kaçış, ölüm, "üstü kalsın" (kendi oynayışında).

## EK 4 DÜZELTMELER (kod okumasından, 2026-11-04; salt okuma araştırması, test koşulmadı; kesinlik düzeyi parantezde)
- 34 (yaratma/başlangıç kesesi): Başlangıç kesesi = arka plan altını ×100 (yalnız Barbarian'da sınıf altını da). Diğer sınıfların "N Altın" kalemi envanterde METİN olarak kalır, ilk para işleminde (settle_coin_labels) kese'ye eklenir; yani ekran/kese başta eksik görünür, sonra sıçrar (örnek: Fighter + arka plan B: 50 + "10 Altın" = 60). 85/15 rakamlarının ekrandaki kaynağı bulunamadı. (orta)
- 35 (sohbetle bira): "bir bira alabilir miyim" iki nedenle kart açmaz: soru işareti reddedilir ve alım fiillerinde "alabilir" yok; "bir bira alayım" çalışır. "Üstü kalsın" için bahşiş ayrıştırıcı YOK: bahşiş yalnız panelden; açık teklif yokken verilen para hediye kartı olur, açık teklif varsa para üstü verilir. (yüksek)
- 38 (oda): Oda kaydı yalnız onaylanmış oda kartında yazılır (flags.inn_room); anahtar eşyası yok, "odama gidip uyuyorum" için yürüme hedefi yok, okuyan kod yok. Kart onaylandıysa uyku çalışır. (orta)
- 39 (silah): İki motor nedeni: paket C Greatsword'u kuşandırmıyor (main_hand boş → no_weapon) ve Ready'de "Kılıç" sabit aranıyor (yalnız Longsword). (orta)
- 40 (Ready ve yürüyüş): Ready için tetik ve karşılık gerekir (D&D'ye uygun); yanlış olan mesaj: İngilizce hata "Dövüşün ortasında bu olmuyor" olarak görünüyor. "Rakibin yanına gidiyorum" savaş hareketi sayılmıyor, hareket yalnız açık "N feet" ile; yürüyüş seyahat olarak reddediliyor. (yüksek)
- 54, 56 (tüketim, ok): Yemek/içecek tüketen kod yok. "20 Ok" yalnız paket metni; ok sayacı ayrı (world.ammunition), tohumlanmıyor. Yani yay atışı büyük ihtimalle motorda çözülmedi, yalnız anlatıldı. (orta)
- 42 (çıkış): Çıkış kodu doğru (üst mekân = sokak). Tahılcıya geçiş büyük ihtimalle modelin seçtiği "git" rotası. Gerçek zincir gerekir. (düşük)
- 21 (kaçış): Çıkışsız sahnede kaçış tur kaybettirir (bilinçli); sokak/başlangıç sahnelerinde çıkış verisi yok, düzeltme veri işi (3c). (yüksek)
- Gecikme: Gemini takılırsa 20 sn çağrı sınırı + 25 sn bulut yürüyüşü + Gemma ≈ 30 sn çıkar (olası, loglar okunmadı). (orta)

## EK 5 — Kadir'in 19 maddelik testi (2026-11-04, GPT'nin hazırladığı `UNWRITTEN_test_raporu.html`; Chrome üzerinden, 12 sınıfla, 30 dk kesintisiz oturum dahil; kabul DEĞİL)
Kaynak Kadir'in GPT'ye yaptırdığı rapordur; bu notlar rapor metninden alındı, ben tekrar oynamadım. Numaralar raporun 1–19 testidir (`T1`…`T19`); senaryo dosyalarında bu maddeler `100 + T` ile anılır (T3 → 103, T5 → 105, T10 → 110, T11 → 111, T15 → 115). Neden iddiaları doğrulanmadı.
GEÇTİ / sağlam: T1 kaydet-yeniden aç (3 karakterde kese, envanter, konum, can, anlatı, konuşma hedefi korundu; 30 dk sonra 215 paragraf birebir); T2 geri al (para, stok, envanter döndü; ölü barmen geri geldi, anlatı silinmedi); yetersiz bakiye (100 altın teklifi engellendi, kese eksiye inmedi, iptal para kesmedi); ölüm zarları ve ölüm ekranı; Ready düğmesi ve Hareket düğmesi; Fighter Second Wind, Barbarian Rage, Monk bonus vuruşu; Paladin Cure Wounds, Divine Smite ve geri alda yuvanın dönmesi; 8 saatlik uyku can ve yuva yeniler; Fikir lazım mı; Gözlemle.
Para (en önemli):
- T3: "bir bira, 5 bakır, üstü kalsın" bahşişi tamamlamadı, 4 bakırlık normal tezgâh açıldı (madde 35/56 ile uyumlu). YENİ: Kervancı sözle 5 bakırı REDDETTİ, ama sonra onaylanan 5 bakırlık bahşiş kartı parayı KESTİ: konuşma ile kart çelişiyor (reddedilen para ödeniyor sınıfı, C-008).
- T4: Pazarlıkta 20 bakır teklifi reddedilince oda 50 bakır; ödeme çalıştı, anahtar görünmedi, konum han kaldı, oda kaydı doğrulanamadı (madde 38). Demir'de oda 50 + 1 bakır bahşiş = 51 kesildi. "Anahtarı alıyorum" envantere anahtar eklemedi; satıcı "Kimse bana bir şey anlatmadı" dedi.
- T10/T15: YENİ ciddi: "Oda için beş gümüş ödüyorum" hamlesi, açık olan 26 bakırlık sayım işini kendiliğinden TAMAMLADI ve 26 bakır verdi; ödeme kartı Oda yerine Hediye oldu. İşlevler arası yanlış tetiklenme (para yolu).
Görev ve eşya (T15): Ferumel'e 14 bakırlık iş aynı biçimde çıkmadı; alternatif 19 bakırlık iş tamamlandı. Demir'de 12 bakırlık iade işi: Görevler 0 kaldı ama Günlük'te "Süren maceralar" altında kayıt var; "İade takımını alıyorum" ikinci bir eşya ("Iade takımını") üretti (çoğalma); günlükteki alıcıya teslim denemeleri ödülsüz kaldı, iş "Sürüyor"da takıldı; konuşmalar Ferumel ile çömlekçi arasında döndü (teslimat alıcısı yanlış/döngü).
Hafıza (T16): İKİ karakterde başarısız: kişisel bilgi (kardeş adı, hediye) 3.–16. turda söylendi, 20+ tur sonra ve kaydet/yenile sonrasında hatırlanmadı ("Öyle bir şey konuştuğumuzu anımsamıyorum…"); karakter adını hatırladı.
Seviye (T11): İKİ kazanılan savaştan sonra XP 0 kaldı (iki karakterde); seviye atlama düğmesi ve gereken XP görünmedi; seviye ilerlemesi test edilemedi. YENİ.
Tüketim (T7): Yenen yemek ve içilen bira envanterde kaldı (madde 54 doğrulandı); ok atışları gerçek atış olarak işlenmedi, mühimmat azalması doğrulanamadı ("Kısa Yay & 20 Ok").
Başlangıç parası (T9, T13): Kese sınıf altını + 50 (arka plan) olarak doğru çıktı: Fighter 10+50=60, Rogue 8+50=58, Barbarian 15+50=65, Sorcerer 28+50=78 vb. Özet ekranı çoğunlukla yalnız sınıf altınını yazıyor; Barbar ekranı 15+50'yi açıklıyor. Madde 34: hata yaratma ekranının AÇIKLAMASINDA (gösterim), kese doğru.
Kaçış (T5): Sonuç sahneye göre değişiyor, iç/dış tek başına belirlemiyor: Astrid sokakta "çıkış yok", Turgut handa "Kaçacak bir açık bulamıyorsun"; Boran dükkândan ve Demir kervan durağından/iskeleden tek hamlede kaçtı. Dünya paneli "geçit yok" yazan yerden kaçış mümkün oldu: panel kaçış olanağını güvenilir göstermiyor. (Senaryo 09 varsayımlarını etkiler: han bir üst mekâna sahip sanılıyordu.)
Savaş eylemleri (T8): "Muhafıza doğru yürüyorum" yine "öylece yürüyüp gidemezsin" (madde 40 doğrulandı). Astrid'de envanterde gürz varken Ready "uygun silahın yok" dedi (madde 39: kuşanma durumu).
Büyüler (T12): Kısmi. Sorcerer'da Disguise Self anlatıldı ama yuva azalmadı; Wizard Fire Bolt "kullanım biçimi desteklenmiyor"; Wizard ve Druid yaratımı 1. seviye büyü kullanımının açık olmadığını söylüyor; Magic Missile hedef görünür olsun diye engellendi (yakın dövüşteki barmen hedefliyken); yuva bitince genel "Dövüşün ortasında bu olmuyor" mesajı (anlaşılmaz ret). Bard, Ranger, Warlock büyü etkileri doğrulanamadı.
Sınıflar (T13): 12 sınıfla karakter yaratıldı ve oynandı; Rogue Sneak Attack paneli var, ek hasar doğrulanamadı; Ranger Hunter's Mark "Anladım", Warlock Hex "Sen bilirsin" (mekanik etki yok).
Yoldaş (T14): Beraber savaşan yoldaş doğrulanamadı; NPC'ler davetleri reddetti; bir teslimat ustası davetsiz iskeleye kadar takip etti.
Dil/arayüz (T9, T17): İngilizce beceri, eşya, sınıf açıklamaları, Action/Reaction/feet, C10/C04 gibi geliştirme notları ve ham eşya kimlikleri; satın alma hamlesi hâlâ ham `/item shop_buy …` olarak görünüyor (düzeltme `ui-labels` dalında, c-merge sürümünde yok). Geri al: ikinci kez hemen düğme yok, hamle türü yenilemede sıfırlanıyor. Ölüm sonrası düğmeler gri değil, yalnız savaş paneli kayboluyor; "Yeni karakterle başla" ana ekrana gidiyor.
Dikkatini çeken (T18): Sokakta Gözlemle ve Etkileşime geç çalıştı; dükkân nöbet değişimi ve haberci hareketinde ikisi de "müdahale edemiyorsun" dedi: sahneye göre değişiyor.
Önceliğim (okuma, öneri): 1) para/yanlış tetiklenme: reddedilen paranın kesilmesi, oda ödemesinin sayım işini bitirmesi, görev eşyası çoğalması; 2) hafıza (iki karakter, kaydetten sonra bile); 3) XP/seviye 0; 4) tüketim ve ok; 5) büyü yolu; 6) oda kaydı/anahtar, kaçış göstergesi, dil.
Eşleme: 1 → Adım 3b (para, tek sahip, doğruluk kartı); hafıza → yol haritasındaki "defter ve izler" (Adım 7), bugünkü anlatı hafızası sorunu ayrı bir erken iş olabilir; XP → 3c (eksik dünya davranışı) ya da küçük hata düzeltmesi (karar Kadir'in).
Ek bulgular (Kadir, aynı gün, GPT raporunun "alakasız hamle / çelişki" listesinden): (a) T10: "Oda için beş gümüş ödüyorum" kabul edilen sayım işini tamamladı, 26 bakır verdi VE 8 saat geçirdi; oda için Hediye kartı açıldı (saat atlaması yeni). (b) T15: "İade takımını alıyorum" ikinci eşya üretti ve adı "Iade takımını" (büyük I, ad bozulması). (c) T15: günlük iskeledeki liman işçisini gösterirken konuşmalar oyuncuyu Ferumel ile çömlekçi arasında dolaştırdı; doğru alıcıya gidince de teslim tamamlanmadı. (d) T12: yumrukla dövüşülen barmen hedefken Magic Missile "hedefin açıkça görünür olması gerekiyor" ile engellendi (sahne ile çelişki). (e) [madde 121] Tek hamlede iki karşı saldırı anlatıldı (Selim'in ilk yumruğundan sonra); metin tekrarı mı çift saldırı mı doğrulanamadı. (f) [madde 122] Savaş sırasında "Tezgâhtan satın al" düğmesi açık kalıyor; savaşta satın alma ayrıca denenmedi. KADİR KARARI (2026-11-04): savaşta satın alma reddedilir ve tezgâh paneli savaş sırasında görünmez (panel kısmı küçük arayüz turu). Senaryolar: Task 16 (18, 19, 21, 22, 23).

## EK 6 — Arayüz değerlendirmesi (Kadir, GPT raporu özeti, 2026-11-04)
Genel: Görsel atmosfer iyi (koyu tema, anlatı merkezli ekran). Asıl sorun görünüşten çok, arayüzün verdiği bilgi ile gerçekleşen sonucun uyuşmaması; oyuncu neyin gerçekten olduğunu anlamakta zorlanıyor.
İyi: ana ekran ve karakter yaratımı adım adım anlaşılır; can, konum, saat üstte kolay bulunuyor; Karakter/Dünya/Kişiler/Günlük/Çatışma panelleri açılıyor; "Fikir lazım mı?" öneriyi yazı alanına koyuyor (göndermeden düzenlenebiliyor).
Zorlayan ve eşleme (öneri):
1. Anlatı ile kartlar ayrı şey söylüyor (NPC parayı reddediyor, ödeme kartı kabul ediyor): Adım 3b (anlatıcı ve kart aynı doğruluk kartından okur; tek sahip).
2. Görev görünürlüğü: "Görevler 0" iken "Süren maceralar"da teslimat var: küçük arayüz turu (sayaç iki bölümü birleştirsin ya da tek kaynaktan okusun); görev verisi 3c ile birlikte.
3. Savaş ekranı teknik ve kalabalık (Action, Bonus, Reaction, feet, Ready, uzun açıklamalar): küçük arayüz turu (ui-labels dalı Eylem/Bonus eylem/Tepki/Hız etiketlerini zaten Türkçeleştirdi; Ready/Dash ve açıklama metinleri kaldı).
4. Ham komutlar hikâyeye sızıyor (`/item shop_buy …`, eşya kimlikleri, C10/C04 notları): ui-labels dalı shop_buy yankısını gizliyor; eşya kimlikleri ve geliştirici notları kaldı (küçük arayüz turu).
5. Hata mesajları açıklayıcı değil ("Dövüşün ortasında bu olmuyor" hangi koşulun eksik olduğunu söylemiyor): motor ret mesajları (ready_needs_trigger, hedef görünürlüğü, vb.) Türkçe ve nedenli olmalı; 3b ile birlikte ya da küçük düzeltme.
6. Geri alınan metin görünür kalıyor, gerçekleşen/iptal ayrımı zor: küçük arayüz turu (geri alınan tur soluk/üstü çizili ya da ayrı etiketli).
7. Başlangıç kesesi özeti eksik: sınıf parası gösteriliyor, geçmişten gelen 50 altın aynı özette görünmüyor (madde 34): küçük arayüz turu (özet toplamı göstermeli: sınıf + geçmiş = toplam).
Ana tema 3b için: arayüzün gösterdiği bilgi motorun gerçek sonucuyla aynı kaynaktan gelmeli.
