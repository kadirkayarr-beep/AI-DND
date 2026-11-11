# AI DND adım 0 para eşya ve kayıt güvenliği tasarımı — V3

**Tarih:** 3 Kasım 2026, Türkiye saati  
**Temel:** Jarvis'in `AI_DND_ADIM0_TASARIM_20261103.md` belgesi (Kadir onaylı 16 karar). Aşağıdaki gövde o belgedir; V3 değişiklikleri bu ilk bölümdedir ve çelişki halinde bu bölüm geçerlidir.  
**Hazırlayan:** Jarvis (temel), Claude (V3 değişiklikleri)  
**Okuyucu ve ürün sahibi:** Kadir  
**Durum:** Kadir V3 değişikliklerini sohbette onayladı ("Onaylıyorum bu haliyle", 2026-11-03). Yazılı belge incelemesi bekleniyor. Uygulama başlamadı. Bu belge kod veya test sonucu değildir.

## V3 değişiklikleri (Kadir onaylı, 2026-11-03)

**Kadir'in bugünkü kararları**
- K1. Uygulayıcı Claude'dur (Codex değil). Ayrı worktree `C:\Users\Kadir\Desktop\AI-DND-step0`, dal `task/step0-money`, taban `6ee9b370`. c-merge'e doğrudan yazılmaz. Korumalı test yuvası 2.
- K2. "Yeni reddeden validator ekleme" kuralı esnedi (Kadir: "Yap, esnet"). Dayanaksız para/eşya sonucu durdurulabilir; yaratıcı oyuncu denemesi sistem hatası gibi engellenmez; yeni kelime listesi yine yasak. Bu karar NIGHT_BRIEF ve hafıza kaydına işlenir.
- K3. Teslim: B1, A, C ve kalan kapsam ayrı kanıt paketleridir; c-merge'e birleştirme yalnız hepsi bitip tam test geçince ve Kadir onayıyla, tek seferde. Yarım iş oyuna girmez. Ardından Kadir'in 30 dakikalık oyunu.
- K4. İnceleme: Jarvis yoktur. Her görevden sonra bağımsız bir inceleme ajanı (yazar olmayan) görevi tasarıma ve plana karşı denetler; büyük teslimlerde ayrıca bütünleşik inceleme.
- K5. Değerli eşyada kart: Para değeri olan (fiyatı `equipment_economy.price(item)` katalog kaydından veya `shop_trade` fiyat tablosundan 0'dan büyük çözülen) ya da oyuncunun takılı/kuşanılmış eşyasını vermek küçük bir onay kartı ister. Sıradan, değersiz eşya kartsız kalır. Bu, 9. kararı değerli eşya için değiştirir. Kart para kartıyla aynı teklif/onay yolunu kullanır.

**Açık kapatmaları**
- D1. Mal ve oda fiyatını yalnız sunucu belirler (dükkân kaydı, oda fiyatı). İstemciden gelen fiyat/tutar mal ve oda için yok sayılır; uyuşmazlık açıklama sonucudur. Oyuncunun girdiği tutar yalnız hediye/bahşiş ve açık verilen para (tender) içindir.
- D2. İzinli geri alma, tüketilmiş teklifi yeniden "hazırlandı" durumuna döndürebilir. Yeni bir onay o zaman bir kez ödeme yapar; net sonuç tek ödemedir ve bu çift harcama sayılmaz. Eski action'ın tekrarı ödeme yapmaz. Tüketilmiş/iptal teklif kayıtları sınırlı tutulur; kayıt sonsuz büyümez.
- D3. Canlı oyunda sahte model ayarı yoktur ve bu çalışmada yazılmaz. Kart ve panel akışları gerçek tarayıcıda modelsiz denetlenir; sohbetten kart açılan akışlar Python sahte-model testleriyle sınanır.
- D4. Oda tutmanın bilinen üç girişi (`game.py` `_sleep_after_walk` → `bold_acts.take_room`; `bold_acts._room_asked`; `bold_acts._buy`) ve `_hand_over_coin`/`_tell_the_coin` aynı geçişte yeni yola bağlanır; eski doğrudan yazma o commit'te kapanır.
- D5. Oda bedeli bugünkü politikadaki gibi kimseye gitmez (sink). Hancıya gelir yazılmaz; `take_room` açıklamasındaki çelişki düzeltilir.
- D6. Gerçek tarayıcı kontrolünü Claude, uygulama içi tarayıcıda, yeni geçici kampanya veritabanıyla ve modelsiz yapar.

## Amaç ve başarı ölçüsü

Doğal Türkçe oyun korunurken para ve eşya yalnız doğrulanmış niyet ve motor sonucuyla değişmeli. Bağlantı kesilmesi, yeniden gönderme veya anlatım hatası aynı işlemi tekrar uygulamamalı.

Bu çalışma oyunun eğlenceli olduğunu kanıtlamaz. Adım 0'ın güvenlik engellerini kaldırmayı hedefler. Kayıt kaybı, yanlış para, bozuk geri alma veya anahtar sızıntısı tek kez görülse bile ilgili geçiş durur. Yeşil testler ve ajan oyunu ürün kabulü değildir; ürün kabulü yalnız Kadir'dedir.

## Kanıt ve sürüm sınırı

- Jarvis'in önceki bağımsız incelemesi `fa5066091c907251f053f6ae3ea4057314e17061` noktasındaki statik kod okumalarına dayanır. O incelemede ürün, model veya test çalıştırılmadı; çalışma ağacı atomik bir görüntü olarak alınmadı.
- Claude, talimat ve araç düzenlemelerinden sonra `1a5d147d` noktasını, kalıcı `Desktop\AI-DND-TOOLS` klasörünü ve 61 geçen testi raporladı. Bunlar bu tasarım hazırlanırken bağımsız doğrulanmadı.
- Reddedilen paranın kesilmesi ve oda ile birlikte ödeme sorunları Claude'un ayrı kanıt çalışmasında raporlandı. Jarvis'in koşullu kayıt riskleri aynı kanıt düzeyinde değildir.
- Uygulama planı hazırlanırken güncel başlangıç noktası ve ilgili dosyalar salt okunur doğrulanmalı. Eski satır numaraları güncel kodun kanıtı sayılamaz.

## Kapsam

**A ailesi:** Para ve eşya değişiminin tek yetkili yolu, teklif kartı, NPC kabul veya reddi, birleşik ödeme, tekrar güvenliği, gerçek işlem makbuzu, tur içi geçici durumun temizliği.

**B ailesi:** Koşullu kayıt ve geri alma risklerinin önce kanıtlanması; kanıtlanan açıkların kapatılması. Görev kabul veya iptali sonrası kayıt, yanıt hazırlama aralığı, geri alma doğrulaması, iş kapanışının yarım kalması, kurtarma isteğinin süresi ve kurtarma sonrası panel tutarlılığı bu kapsamdadır.

**C ailesi:** Kaçışın mevcut hareket kısıtlarına uyması ve gerçekleşmeyen konum değişikliğini iddia etmemesi.

**Küçük sözleşme düzeltmesi:** Gerçek oyun durumunun döndürdüğü `bounded_encounter` alanının açık API şemasında doğru tür, bulunabilirlik ve boş değer davranışıyla temsil edilmesi.

**Kapsam dışı:** Bütün tur çekirdeğinin yeniden yazılması, haberci ve dünya olayı teslimi, yeni sınıf veya büyü, içerik üretimi, yeni model zinciri, bütçe altyapısı, açık cinsel içerik, gerçek kullanıcı kayıtlarını değiştirmek, yayın, push veya merge. Parayı yere bırakma gibi yeni bir mekanik bu çalışmaya eklenmez. Bunun bulunmaması, böyle bir isteğin gizlice NPC'ye hediye sayılmasına izin vermez.

## Karar özeti

1. Para işlemi sohbetten veya panelden hazırlanır; küçük karttan onaylanır.
2. Kart onayı oyuncunun aktarımı denemesine izin verir; NPC'nin kabul edeceğini garanti etmez.
3. NPC reddederse aktarım yapılmaz. Anlatım kaydedilen sonuca uyar.
4. Bedel ve bahşiş ayrı satırlardır. İşlemler arasındaki oyuncu koşulu korunur.
5. Onay anında tutar, alıcı, mal veya hizmet, stok, erişim ve yeterli bakiye yeniden doğrulanır.
6. İşlemi etkileyen değişiklik sessizce uygulanmaz; kart yenilenir. İlgisiz bir değişiklik gereksiz tekrar onayı doğurmaz.
7. Aynı işlem kimliğinin tekrar gönderilmesi ikinci ödeme veya ikinci eşya üretmez.
8. Motor yaratıcı denemeyi değil, dayanaksız sonuç önerisini durdurur. Anlamı değiştiren otomatik onarım yapılmaz.
9. Para dışındaki açık eşya eylemleri ek kart istemez; kaynak, sahiplik ve aktarım koşulları kontrol edilir.
10. Kart açmak veya iptal etmek tek başına para, eşya ya da oyun zamanı değiştirmez.
11. İşlem önce doğrulanır, sonra kaydedilir, en son anlatılır.
12. Makbuz; fiyat, verilen para, para üstü, alıcı, mal veya hizmet ve önceki/sonraki durumla birlikte doğrulanır.
13. Kayıt sonucu belirsizse yeni durum değişiklikleri durur. Kurtarma denemesi süreli olur; belirsizlik başarı veya başarısızlık diye sunulmaz.
14. Kaçış mevcut hareket kurallarına uyar; gerçekleşmeyen yer değişikliği anlatılmaz.
15. Koşullu risk önce izole kanıtla sınanır. Kanıtlanmayan bulgu olmuş hata diye sunulmaz.
16. Son teslim sürümü kendi test kanıtını taşır; önceki sürümün yeşil sonucu sonraki düzeltmeyi doğrulamaz.

## Para ve eşya akışı

### Niyeti anlama

Oyuncu doğal cümlesini yazar. Model yalnız bir işlem önerisi çıkarabilir. Öneri oyuncunun eylemi, hedefi, miktarı ve koşulları ile eşleşmelidir. Fiyat sormak satın alma değildir; “vermiyorum” aktarma değildir; bir ihtimali konuşmak işlem emri değildir. Kişi veya miktar gerçekten belirsizse tek kısa açıklama sorusu sorulur. Yeni kelime listeleriyle her örneğe ayrı yol eklenmez.

Güvenilir öneri yoksa işlem yapılmaz; oyun içi başarısızlık uydurulmadan açıklama veya mevcut panel yolu sunulur.

### Teklif kartı

Küçük kart sohbet alanını kaplamaz; yalnız öğrenilmiş kişi etiketi ve oyuncunun erişebildiği bilgiler kullanılır. Gizli isim veya NPC kabul gerekçesi sızdırılmaz. Kart şunları gösterir:

- Kime ödeme yapılacağı ve ne alınacağı.
- Miktar/adet, birim fiyat, bedel ve ayrı bahşiş.
- Toplam veya koşula bağlı tutar; reddedilebilen yan kalem açıkça belirtilir.
- Varsa oyuncunun bağımlılık koşulu.
- Onay ve iptal seçenekleri.

Kartın arkasında kampanya, oyuncu, karşı taraf, kaynak teklif, mal veya hizmet, koşullar ve sürüm ile bağlı tekil bir teklif bulunur. Ekrandaki metin, tutar veya NPC adı tek başına işlem yetkisi değildir. İstemciden gelen değiştirilmiş fiyat veya alıcı kabul edilmez.

Önceden kabul edilmiş işin hak edilen ücreti tekrar onay istemez; aynı ekonomik kayıt yolundan olay kimliği ve hak ediş kanıtıyla geçer.

### NPC kabulü ve ret

Motor kabul koşulunu sonuç kaydından önce belirler. NPC karakteri gerekiyorsa modelin yapılandırılmış önerisiyle ifade edilebilir; ancak serbest anlatıdaki “alıyorum” veya “almıyorum” kelimesi doğrudan para yetkisi taşımaz. Önerinin NPC, teklif, bilgi ve dünya durumu ile ilişkisi doğrulanır. Kabul durumu çözülemiyorsa aktarım yapılmaz; kabul edilmiş gibi anlatılmaz.

Kaydedilmiş ret, aynı isteğin tekrarında yeniden değerlendirilmez. Yeni pazarlık yeni eylemdir. Kart iptali veya görüntüleme NPC reddi sayılmaz.

### Birleşik işlemler

Örnek: oda 50 bakır, bahşiş 5 bakır. Bu sayılar yalnız davranış örneğidir, oyun fiyatı değildir.

- İkisi kabul edilirse oda hakkı ve toplam 55 bakır aktarım birlikte kaydedilir.
- Oda mümkün, bahşiş reddedilmişse kartta gösterilmiş bağımlılık kuralına göre oda alınır ve yalnız 50 bakır kesilir. Bahşiş ret sonucu ayrıca görünür.
- Oda alınamıyorsa ona bağlı bahşiş kendiliğinden gitmez.
- Oyuncu “Bahşişi kabul etmezsen oda da tutmam” demişse bahşiş reddi bütün paketin gerçekleşmemesi sonucunu doğurur.
- Oyuncunun onaylamadığı başka mal, alıcı, fiyat veya bağımlılık sonradan yerine konmaz.

**Koşullu kısmi sonuç, yarım veritabanı kaydı değildir.** Önce hangi alt işlemlerin gerçekleşeceği belirlenir; sonra ortaya çıkan sonuç paketi tek bütün olarak kaydedilir. Yazma sırasında hata olursa paket yarım kalamaz. Bir iş ücretinin kazanılması ve ayrıca bahşiş verilmesi de bağımsız hak ediş ile oyuncunun ödeme niyetini birbirine karıştırmaz.

### Tek yetkili kayıt

Para ve eşya değişiklikleri için açık sahiplik sınırı vardır. Eski metin eşleştiriciler, model yorumlayıcıları ve NPC konuşması tüketicileri öneri verebilir; kendi başlarına bakiyeye veya envantere yazamazlar. Bu sınır A kapsamındaki ekonomik değişimler ve sıradan eşya alma/verme yolları içindir. Savaşta tüketim gibi mevcut kural işlemlerinin sahipliği korunur; bütün envanter veya tur motoru yeniden yazılmaz.

Kaydedilen sonuç; işlem kimliği, onaylanan teklif, kaynak ve alıcı, önceki/sonraki bakiyeler, verilen ve dönen para, eşya kimliği/adedi, stok veya hizmet hakkı, ret gerekçesi ve ilgili oyun zamanını bağlar. Makbuz yalnız anlatımın tekrarından türetilmez. Yanlış anlatım ve yanlış kese aynı sayıyı söylese bile bağımsız fiyat ve aktarım denetimi bunu yakalayabilmelidir.

Tekrar anahtarı yalnız tarayıcıdaki düğmeye bağlı değildir. Aynı kayıtlı işlem kimliği yeniden gelirse kaydedilmiş sonuç döner. Aynı kimlikle farklı içerik gelirse işlem reddedilir. Farklı kimlikli iki eşzamanlı istek de aynı stok, bakiye veya tekil teklif üzerinde birbirinden habersiz tamamlanamaz.

### Para dışındaki eşyalar

Oyuncunun açık alma veya verme cümlesi ek kart gerektirmez. Motor eşyanın gerçek kaynağını, mevcut sahibini, erişilebilirliğini, adetini ve aktarım koşullarını doğrular. Alıcının reddi mümkünse reddedilen eşya oyuncuda kalır. Satın alma bu yoldan ücretsiz aktarıma dönüşmez.

Anlatıda geçen eşya tek başına yeni envanter nesnesi üretmez. Mevcut dünyada tanımlı bir nesne veya motor tarafından doğrulanmış bir üretim/ödül kaynağı gerekir. Aynı nesne tekrar alınamaz ve “vermiyorum” aktarım oluşturmaz.

### Zaman ve diğer sonuçlar

Kartı açıp kapatmak oyun zamanı tüketmez. Karttan önce gerçekleşmiş konuşma, yolculuk veya bağımsız dünya olayı kart iptal edildi diye geri alınmaz. Gerçekleşen alışveriş veya hizmetin zaman maliyeti mevcut oyun kuralı tarafından bir kez uygulanır. Onay beklerken duvar saati yüzünden dünya ilerlemez; mevcut kampanya zamanı politikası korunur. Oyuncu bu sırada başka bir oyun eylemi yaparsa teklifin geçerliliği yeniden değerlendirilir.

## Kayıt güvenliği ve anlatım

### Sonucun dört durumu

1. **Hazırlandı:** Teklif var, henüz ekonomik değişiklik yok.
2. **Kesinleşti:** Kayıt başarıyla tamamlandı; anlatım bu sonuçtan üretilir.
3. **Gerçekleşmedi:** İşlem güvenle reddedildi veya kayıt öncesi tamamen geri alındı; nedeni açıkça gösterilir.
4. **Belirsiz:** Kayıt tamamlanmış olabilir, fakat sonuç henüz doğrulanamadı.

Belirsiz durumda yeni değişiklikler engellenir. Sonuç kontrolü sınırlı süre ve deneme sayısıyla yapılır; bitmeyen yükleme görüntüsü bırakılmaz. Sonuç kesinleşmezse kullanıcıya tekrar kontrol seçeneği ve anlaşılır durum gösterilir. “Bulunamadı” cevabı güvenilir biçimde işlemin kaydedilmediğini göstermiyorsa yeniden ödeme başlatmak için yeterli değildir. Okuma veya kurtarma hatası kayıt silme gerekçesi olamaz.

Kayıt kesinleşmiş, anlatım üretimi başarısız olmuşsa kullanıcı en azından gerçekleşen işlemin kısa, motor kaynaklı özetini görebilir. Serbest anlatımı yenilemek ekonomik işlemi yeniden çalıştırmaz.

### Kayıt ve geri alma sınırı

Görev kabul/iptal yolları ve ekonomik işlemler, kayıt öncesi geri alınabilir hata ile kayıt sonrası belirsizliği ayırmalıdır. Veritabanına yazılmış bir sonuçtan sonra bellek görüntüsünü körlemesine eski hale döndürmek yasaktır. Kayıt kesin değilse kampanya güvenli duruma alınır ve kanıtla uzlaştırılır.

Geri alma yalnız para veya HP'yi değil, geri alınan eylemin etkilediği bütün durumu geri getirmelidir: eşya ve stok, hizmet/iş durumu, oyun zamanı, ilgili makbuz ve diğer nedensel alanlar. Rastgele sayı durumu, konuşma geçmişi ve bekleyen kazanımlar snapshot sözleşmesine dahilse geri alma doğrulaması da bunları kapsar. Geri alma hakkı genişletilmez. Geri alınmış işlemin eski kimliği yeniden gelirse işlem tekrar uygulanmaz; eski başarılı sonuç güncelmiş gibi sunulmaz. Tarihsel kimlik korunarak geri alınmış durum ve güncel kayıt gösterilir.

İş kapanışı birden fazla etki uyguluyorsa “kapandı” işareti etkilerin sessizce yarım kalmasına yol açamaz. İlgili risk önce hata enjeksiyonuyla kanıtlanır; çözüm ya bütün sonucu atomik kaydeder ya da kalan etkileri açık, tekrar güvenli şekilde izler. Hata yutulup başarı bildirilmez.

Kurtarmadan sonra kese, envanter, son tur, tezgâh kartı ve geri alma hedefi aynı doğrulanmış durumu göstermelidir. Eski kartın bekleme işareti sonsuza kadar kalamaz.

## Kaçış ve API sözleşmesi

Kaçış, mevcut hareket ve durum kurallarını kullanır. Hızı sıfırlayan koşulda başarılı bir zar, tek başına yasak hareketi mümkün kılamaz. Mevcut kuralların izin verdiği durumdan kurtulma eylemi varsa o ayrı değerlendirilir; oyuncunun kaçma isteği doğrudan farklı bir eyleme çevrilmez.

Gidilecek yerin geçerliliği ve hareketin gerçekten gerçekleşmesi sonuç kaydından önce kontrol edilir. Aynı yerde çatışmadan çıkmak mevcut kurallarda mümkünse, sonuç “yer değiştirdi” değil gerçek savaş/konum sonucu olarak anlatılır. Geçersiz yol yüzünden çatışma yanlışlıkla bitirilemez. Bu çalışma bütün savaş veya D&D kurallarını yeniden tasarlamaz.

`bounded_encounter` düzeltmesi gerçek serializer çıktısı ile açık GameState şemasını eşleştirir. Yalnız sahte oturumla geçen sözleşme testi yeterli değildir; gerçek oturum türünün alanı üreten yolu da doğrulanır. Alanın varlığı, yokluğu ve boş değeri üretim davranışına göre tek sözleşmede belirtilir.

## Kanıt ve kabul tasarımı

Aşağıdaki sınamalar henüz çalıştırılmadı. Uygulama planı bunları gerçek dosyalar ve korumalı komutlarla eşleştirecek.

| Alan | Gerekli kanıt |
|---|---|
| Fiyat sorusu | Kart veya bilgi olabilir; para ve eşya değişmez |
| Alışveriş | Anlaşılan fiyat, verilen para, doğru para üstü, mal ve stok aynı sonuca uyar |
| Ret | NPC reddeder; kese, alıcı ve eşya değişmez; anlatım ret kaydıyla tutarlıdır |
| Oda ve bahşiş | Kabul, yalnız bahşiş reddi, oda bulunmaması ve açık koşullu ret ayrı sınanır |
| Yanlış alıcı | Sokaktaki eski NPC veya önceki konuşma ödeme hedefi olamaz |
| İş ücreti ve bahşiş | Hak ediş bir kez ödenir; bağımsız bahşiş doğru alıcıya bir kez gider |
| Eski teklif | Fiyat, alıcı, stok veya hizmet değişince sessiz yerine koyma yapılmaz |
| Tekrar | Çift tıklama, zaman aşımı, yeniden gönderme ve yeniden açma aynı sonucu korur |
| Yarış | İki istek aynı son malı veya bakiyeyi birbirinden habersiz tüketemez |
| Eşya niyeti | Verme, vermeme, fiyat sorma, varsayım ve gerçek hediye birbirinden ayrılır |
| Kaynak | Sadece anlatılmış eşya kaynak olmadan çantaya girmez; var olan alınabilir nesne alınır |
| Özgürlük | Geçerli yaratıcı deneme sistem hatası gibi engellenmez; başarılı sonuç uydurulmaz |
| Kayıt aralığı | Kayıt öncesi, kayıt sırasında ve kayıt sonrasındaki hatalar ayrı sınanır |
| Geri alma | Gerçek kapsamındaki tüm nedensel durum, tekrar kimliği ve son tur tutarlıdır |
| Kurtarma | Yavaş/cevapsız sonuç kontrolü süreli sonlanır; belirsiz kayıtla yeni değişiklik yapılmaz |
| Panel | Kurtarma sonrası kese, son tur ve kart aynı durumdadır |
| Kaçış | Hız sıfır, geçersiz çıkış, geçerli çıkış ve hareket olmadan sonuç ayrı sınanır |
| Şema | Gerçek oturum çıktısı GameState sözleşmesine uyar |

Her kanıt; başlangıç ve sonuç durumunu, ilgili tarafları, işlem kimliğini, makbuzu, NPC cümlesini ve test edilen sürümü içerir. Önceki kanıt ile yeni sürümün sonucu karıştırılmaz. Hedefli testler düzeltme boyunca kullanılır; son aday tam testle değerlendirilir. Tam testten sonra değişen kod için etkilenen kanıtlar yenilenir; eski yeşil sonuç yeni adayın tamamına mal edilmez.

Uygulama sırasında yalnız izole aday, geçici kampanya veritabanı ve sahte model kullanılır. Gerçek model çağrısı, harcama, gerçek kayıt veya anahtar okuma bu tasarımın uygulama izni değildir. Gerçek model oyunu için sonraki aşamanın açık kapsamı ve bütçesi ayrıca geçerlidir.

## İlerleme kapıları

- Bu belge üzerinde Kadir'in yazılı tasarım incelemesi tamamlanır.
- Ardından Superpowers Writing Plans ile dosya ve test düzeyinde uygulama planı hazırlanır. Güncel talimatlar ve başlangıç noktası önce salt okunur doğrulanır.
- Yazılı plan ve çalışma yöntemi Kadir tarafından onaylanmadan ürün kodu veya test çalıştırma başlamaz.
- A, B ve C ayrı kanıt paketleri olarak yürütülür. Kayıt güvenliği kritikse sırf aile sırası nedeniyle ertelenmez; ekonomik teslim için gerekli B kanıtı A'nın geçiş şartıdır.
- Eski bir yazma yolu, yerine geçen davranış kanıtlanmadan silinmez. Aynı etkinin hem eski hem yeni yoldan yazılmasına izin verilmez.
- Her teslimde kanıtlanan, kanıtlanmayan, açık kalan ve kapsam dışı olanlar ayrı yazılır. Test sayısı tek başına geçiş şartı değildir.
- Son adayın bağımsız incelemesi ve para defterli oyun değerlendirmesi tamamlanır. Çalışma dalına birleştirme yalnız Kadir'in onayıyla yapılır.
- Adım 0 güvenlik ölçüleri sağlandıktan sonra Kadir'in 30 dakikalık oyunu gelir; bu tasarımın başarısı oyunun eğlence kabulü yerine geçmez.

## Tasarım denetimi

Belge onaylanan kararlarla karşılaştırıldı. Koşullu sonuç ile atomik kayıt, kart iptali ile önceki dünya sonuçları, NPC kabulü ile oyuncu onayı ve tekrar uygulama ile kayıtlı sonucu yeniden alma ayrımları kontrol edildi.

Bu denetim yalnız belgenin tutarlılığına yöneliktir. Güncel kaynak kodun bu tasarımı sağladığı, herhangi bir testin geçtiği veya hataların kapandığı iddia edilmez.
