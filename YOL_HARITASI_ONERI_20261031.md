# Yol haritası önerisi (2026-10-31)

## Güncel sıra (2026-11-02, Kadir onayladı; aşağıdaki tablonun 3. adımından sonrasının yerine geçer)

Onaya dahil: tur çekirdeğinin yeniden yazılması, elle yazılmış şehir omurgası, Forgotten Realms'ten kendi dünyaya geçiş. Onaya dahil DEĞİL: ayda 4 USD üstü harcama; bu sınır şimdilik geçerli, Kadir ileride artırabilir. Kadir her adımın kendisine anlayacağı dilde anlatılmasını istiyor.

Kaynak: Fable görüşü, kod izleme, çürütme denemesi, Şüpheci, Pragmatist ve Eleştirmen. Kodu çalıştıran olmadı; ölçüm yok, okuma var. Dal `task/c-series-merge`.

| # | İş | Geçme ölçüsü |
|---|---|---|
| 0 | Çalışan döngüyü bitir, kapsam büyümez | Oyun güvenli oynanır: kilitlenme yok, kayıt sorunu yok. Kusursuzluk beklenmez |
| 1 | Kadir 30 dakika oynar, sınav değil; cümleler ve ham model cevapları kaydedilir | Başlangıç listesi çıkar |
| 2 | Ölçüm: makineyle "kırık" tanımı, ikinci sayı "gerçekleşen sonuç", kayıtlı noktadan tekrar, görülmemiş cümleler, her modelde ayrı sayı, kota ölçümü. Sayıları Kadir örnekle denetler. Araç tek başına durma kuralı olamaz: Fable denemesinde ciddi kırıkların yaklaşık üçte birini kaçırdı ve kolay kandırılabiliyor. Ona davranış sınamaları eklenir (vurma cümlesi savaş başlatır, "geçiyorum" kapıdan geçirir, haberci mesaj taşır) ve her ölçümde bir oyun insan gözüyle okunur | Üçü birlikte çalışır: sayaç, davranış sınamaları, okunan oyun |
| 3a | Mevcut model okumasını aç/kapa karşılaştır. Kod taşımadan kanıt: okuma ve kayıt ayrı durur, makbuz, geri alma ve tekrar çalışır, anlatıcı yalnız olandan yazar. Kanıt küçük ama gerçek bir oyun durumunda yapılır: bir mekân, birkaç kişi, çatışan iki amaç; sonuç dayatılmaz, oyuncu reddedebilir, taraf değiştirebilir, gidebilir. Zincir: fırsatı öğren, yol seç, dünya tepki versin, sonuç kaydolsun, sonraki konuşma onun üstüne kurulsun, kapatıp açınca devam etsin. Bir dünya davranışı (haberci) baştan sona bu zincirde çalışır. Yanında serbest bir oyun da ölçülür, durum testi geçsin diye kurulmuş sahneye dönüşmesin | Beş parçalı kanıt ve oyun zinciri geçer |
| 3b | Tur çekirdeği, "anlatılan gerçektir" dahil: Python önce (savaş, ölüm, dinlenme, para, komut), sonra okuma ve doğrulama, sonra sabit olgu paketinden anlatı. Model yokken komutlar çalışır, tur harcanmaz. Geçiş eylem türü eylem türü yapılır; her geçişte eski ve yeni sonuç karşılaştırılır, eski kayıtlar yeni düzende açılır, yarıda kalan istek güvenle tekrar denenir, aynı iş iki kez para vermez. Kota biterse: kararı okuyan model güvenilir değilse oyun güvenle durur ve işlemin olup olmadığını söyler; yalnız anlatı yedek modelle sürebilir. Model tutarlılığı da burada: hangi model hangi işi yapar, Gemini kotası oyun ortasında biterse oyun nasıl davranır, model değişince okuma ve ses tutarlı kalır mı | İlk 60 turda kırık 8 veya altı, sonuç sayısı düşmez, her modelde ayrı sayı |
| 3c | Eksik dünya davranışı, yeni çekirdeğin üstünde ve kelime listesi olmadan: son oyunlarda görülenler (habercinin gerçek mesajı, nöbet olayının oyuncunun önünde yaşanması, anlatılan kişinin konuşulabilmesi gibi). Yeni özellik değil, yarım kalan davranışın tamamlanması | Davranış sınamaları geçer, sonuç sayısı artar |
| 4 | Kadir oynar | En fazla 3 kırık ve "devam ederdim" |
| 5 | Eski yönlendirme sırasını ve kelime listelerini sil, kural motorları kalır, `game.py` son olarak bölünür | Dönüş noktası sayısı düşer, kırık artmaz |
| 6 | Kendi dünya, tek sıkı şehir, elle çatışmalar, ilk 10 dakika; 3a'daki küçük durum şehir ölçeğine büyütülür. Lisans işi yeni içerik projesi olmaz: SRD 5.2.1 içindeki doğrulanmış içerik kalır, dışındakiler ilk sürümde ertelenir, yeniden tasarlanmaz; mevcut karakterlerin bağlı olduğu içerik sessizce silinmez, geçişi ayrıca belirlenir | Onaylı. Üç yeni kampanya farklı, hepsi Kadir'i 10 dakikada yakalar |
| 7 | Defter, ekranda kişi ve izler | İkinci oturumda iz kaybolmaz |
| 8 | Üç oturumluk test | Kadir ikinci oturumu kendi açar |
| 9 | Ayrı okuma ve anlatı modeli | 4 USD üstü harcama Kadir'in ayrı onayıyla |
| 10 | Beş yabancı oyuncu | Üçü devam etmek ister |
| 11 | Metin veriye, İngilizce kararı, lisans, satış | Hukuk ve fiyat |

Kadir'in 2026-11-02 kararları:
- Sıfır tolerans: kayıt kaybı, yanlış para, bozuk geri alma ve anahtar sızıntısı tek seferde bile o adımı geçirmez, kırık sayısına karışmaz.
- 3a gerçek karar noktasıdır: geçmezse 3b başlamaz. 8 kırık yalnız ara eşiktir, ürün kabulü değildir.
- Eski yol, yerini alan davranış kanıtlanmadan silinmez. Beş yabancı oyuncu daha geniş denemeye geçiş işaretidir, satış kanıtı değildir.
- Neverwinter katalogları arşivde kalır; yalnız isimsiz genel iş kalıpları özgün dünyaya uyarlanabilir.
- 6. adımdan önce, para harcamadan, kullanılabilir kural ve içerik envanteri çıkarılır. Hukuk ve satış 11. adımda kalır.
- 4 USD, yalnız Haiku'nun aylık sınırıdır. Haiku'ya giden tüm çağrılar buna dahildir.
- Kırıklar türüne göre ağırlıklı okunur: oyuncunun kararının yok sayılması, hitap hatasından ağırdır. "En fazla 3 kırık" ölçüsünde süre, anlamlı deneme sayısı ve eylem türleri belirtilir; kolay konuşmalarla sayı düşürülmez. Başarısız bir deneme hata değildir, anlaşılmaması hatadır. (Jarvis önerisi, Kadir 2026-11-02 onayladı; 3a, 3b ve 6. satırlardaki ekler de öyle.)
- Para önce (Kadir 2026-11-02, "Başla onay veriyorum"): Adım 0 para güvenliği olmadan kapanmaz. 3a'nın para kısmı öne alınır ve alışveriş paneliyle yapılır: sohbet serbest, satın alma küçük bir panelde, tam bedel tek işlemde, para ve mal birlikte, çift onay ikinci ödeme yaratmaz, fiyat sormak satın almak değildir, NPC işlemden sonra konuşur. Dört eski para yazıcısı fiyatlı mal için susturulur. İş ücreti, hediye, rüşvet, ceza, hırsızlık, oda ve satış açık kalır. Kadir'in 30 dakikası bu bitip para dahil sıfır tolerans hatası görülmeyince gelir.
- Adım 0'dan sonra yama döngüsü yok. Çekirdek gelene kadar yalnız sıfır tolerans hataları ve bizim yarattığımız gerilemeler düzeltilir.
- Superpowers ve ECC becerileri aktif kullanılır: yeni hata çıkınca önce sistematik hata ayıklama (kök neden, sonra düzeltme), testler önce yazılır, "bitti" demeden doğrulanır, büyük değişiklikte plan ve bağımsız inceleme yapılır. Kadir 2026-11-02 istedi.

3b başlamadan yazılacaklar: tek anlık görüntü okumadan önce alınır; model bütçesi dört tüketiciyi sayar (okuma, yedek çağrı, olay üretimi, anlatı); anlatıcının yer önerisi kayıt aşamasına taşınır; yazılı istekler kendi yolunda kalır. Duruş: 3a geçmezse veya iki döngüde sayı düşmezse yeniden konuşulur. "18 sahipten 3'e" artık üç aşama demektir; kural motorları silinmez.

Adım 0'dan devreden işler (Kadir 2026-11-03 onayı): 3b'de Stunned/Incapacitated iken kaçma eylemi yapılamaz (D&D 2024: eylem yok); 3c'de çıkışı tanımlı olmayan başlangıç/sokak sahnelerine dünya verisinde çıkış yazılır (bugün oralarda kaçış tur kaybettirir). Oda kartı onayından sonra uyku ayrı satırla olur; bu bilinçli davranıştır.

Durum: Kadir 2026-10-31'de onayladı, adım 1'de bulut karşılaştırması da yapılacak. Girdi: code graph, 20 tur ölçümleri, Kadir'in 30 turluk oyunu, ECC mimar görüşü, Fable görüşü (`OYUN_GELECEK_FABLE_20261031.md`). Sayılar kod ve kayıttan okundu; süre tahminleri ölçüm değildir.

## Başarı ölçüsü

Testler değil: Kadir 30 dakika oynar, en az 2 gerçek iz bulur, birinin peşine düşer, bir seçiminin sonucunu görür ve "şimdi ne olacak?" der.

## Ana karar

Yeniden yazma yok. Kural, savaş, kayıt ve makbuz motoru kalır. Serbest yazı akışı parça parça "model önerir, Python doğrular, kaydeder" düzenine geçer. Her şikâyete yeni kalıp ekleme durur.

## Sıra

| # | İş | Geçme kanıtı |
|---|---|---|
| 0 | Açık hata paketini bitir, sessiz boş tur hatasını çöz | Kadir'in cümleleri testte, tam test temiz |
| 1 | Model denemesi: 3 NPC'ye elle bilgi ve amaç ver, 30 Türkçe tur | Kadir metni okur: "insan gibi, devam ederdim" |
| 2 | Şehir bilgisi, dünya işleri, "oraya gidiyorum" | 3 yeni kampanyada farklı yapı, en az 2 iz, varış çalışıyor |
| 3 | Kadir 30 dakika oynar | Başarı ölçüsü |
| 4 | Kabul, ret, süre dolması, başkasının işi alması, dünyanın tepkisi | Aynı başlangıç, farklı seçim, farklı dünya |
| 5 | Ön zinciri 18 sahipten 3'e indir: anlam önerisi öne gelir | Serbest yazı turlarının %85'i modele ulaşır, kalıp sayısı düşer |
| 6 | Motor defteri; compact yalnız unutma görülürse | 2 oturum sonra doğru hatırlama |
| 7 | Üç oturumluk oyun testi | Kadir ikinci oturumu kendi isteğiyle açar |
| 8 | İlk sürüm, sonra medya, mikrofon, büyü modeli, kalan sınıflar | Oyun testi geçince |

## Dondurulanlar

- Yeni sınıf, kural ve büyü işi.
- Her şikâyete yeni kalıp veya sabit satır.
- `spare_slot`, model özeti ve review çağrısı (ihtiyaç görülene kadar).
- Soylu kapısına özel zincir: dünya işi genel kalır.
- `free_v1`: şimdilik `legacy` kalır, konuşma kalitesi taşınır; adım 2 sonunda karar.
- Yalnız test sayısıyla ilerleme ölçmek.

## Yön değiştiren sonuçlar

- Adım 1 başarısızsa: model yazarlık yapamıyor. Ya bulut modeli ya elle yazılmış içerik.
- Adım 5'te yeni akış mevcut makbuz ve geri alma ile bağlanamazsa: tur çekirdeği yeniden konuşulur.
- Adım 3 iki denemede tutmazsa: yön ve mimari yeniden konuşulur.

## Satış için notlar

- Prompt caching şimdilik yok. Satışta Haiku veya Sonnet ana model olursa eklenecek.
- Karar (Kadir, 2026-11-01): Oyun 18+ sunulur. İlk sürümde "kendi anahtarını getir" yok; ileride ancak hukuk incelemesinden sonra.
- Sonraki döngü: tur başına çağrı, token ve sağlayıcı kaydı eklenecek.

## Bulut modeli

Yerel kalır. Adım 1'de isteğe bağlı karşılaştırma önerilir. Fable'ın 2026-10-06 tarihli liste fiyatlarından tahmini, ayda yaklaşık 2.400 tur için: Haiku yaklaşık 1,6 USD, önbellekli Sonnet yaklaşık 18 USD. Fiyatlar güncel doğrulanmadı.
