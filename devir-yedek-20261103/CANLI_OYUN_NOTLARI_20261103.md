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
