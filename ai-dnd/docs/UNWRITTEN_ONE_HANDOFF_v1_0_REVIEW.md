# UNWRITTEN — ONE HANDOFF v1.0
## Yaratıcı AI DM, kalıcı Forgotten Realms ve oynanabilir Living Realms

**Sürüm:** v1.0 REVIEW · **Tarih:** 16 Ekim 2026  
**Statü:** Sahibinin son metin incelemesine sunulan tasarım ve çalışma sözleşmesi adayı. Henüz yürürlüğe girmedi.  
**Ürün adı:** UNWRITTEN · **Gelişim programı:** Living Realms · **Yakın hedef:** LR00 Reforged  
**Kaynak inceleme noktası:** `dev/ai-dnd`, `476ba9bd148da18e24cb5dab020c116ba4907445`  
**Bu teslim:** Bir ana sözleşme. Kod değişikliği, migration, Git işlemi, dağıtım, yeni şehir aktivasyonu, tamamlanmış tasarım uygulaması veya PASS kaydı değildir.

> UNWRITTEN, önceden kodlanmış hikâyeyi farklı cümlelerle okuyan bir anlatıcı olmayacak. AI DM yeni yerel insanlar, amaçlar, çatışmalar ve sürprizler yaratacak; oyuncu kendi yolunu seçecek. Oyun bu yaratımları kabul ettiğinde onları gerçek, etkileşilebilir ve hatırlanan kampanya içeriği hâline getirecek. Kurallar, zarlar, kayıtlar ve geçmiş oyuncuya karşı değiştirilmeyecek.

## 0. Yeni gelen için hızlı başlangıç

1. Önce bu sayfadaki statüyü ve §15'teki gerçek durum tablosunu oku. LR00 veya GOLD kabul edilmiş değildir. Eski test sayıları yeni kabul değildir.
2. §1–9 ürün ve davranış sözleşmesidir. §10 arayüzü, §11–13 yol haritasını ve kanıtı, §14 güvenli çalışma düzenini tanımlar.
3. Eski bir kuralla çelişki görürsen §16'daki **koru / değiştir / emekliye ayır** kaydına bak. Burada açıkça değiştirilmeyen teknik kapılar ve güvenlik sınırları geçerliliğini korur. Belge henüz REVIEW olduğu için önerilen değişiklikler şimdiden yürürlükte sayılmaz.
4. Ürün vizyonunu yeniden onaya götürme. Kullanıcı yaratıcı AI DM, serbest giriş, Forgotten Realms, kalıcılık ve viewport odaklı oyun istedi. İncelenecek şey bu hedefi gerçekleştiren ayrıntılı sözleşmedir.
5. **Aktif iş:** v1.0 REVIEW; aktif uygulama paketi yok. **Sıradaki adım:** son metin ve kapsam incelemesi, ardından yetkili LR00-P0. **Şimdi yapılmayacaklar:** kod, Git, migration, canlı state/zar müdahalesi ve deploy.
6. Uygulama başlayacaksa yalnız §17'deki üç sınırlı görevle başla; kapsam, sahip, kaynak ve durma koşulunu kaydet. Bu belgeyi okumak uygulama izni değildir.

### 0.1 Onay neyi değiştirir?

Bu metnin açık onayı, §16'da belirtilen eski ifadelerin yerine bu sürümün tasarım hükümlerini geçirir. Onay kaydında sürüm, son dosya hash'i, tarih ve varsa istisnalar bulunur. Bu hash henüz üretilip onaylanmış değildir; inceleme düzeltmeleri sırasında değişebilir. Tarihsel belgeler silinmez ve eski kanıt yeniden yazılmaz.

Üç karar ayrıdır: **tasarım sözleşmesini kabul etmek**, **belirli paketin uygulamasını başlatmak**, **merge/promotion/dağıtım veya veri geçişi yapmak**. Kullanıcı tek mesajda bunlardan birden fazlasını açıkça yetkilendirebilir; aynı yetki tekrar tekrar sorulmaz. Tasarım onayı, bütün LR01–05 uygulamalarının veya production dağıtımının toplu izni değildir. Yetkili paket içinde rutin dosya/test ayrıntıları için yeni ürün onayı aranmaz; kapsam, veri, güvenlik veya mekanik sözleşme değişiyorsa değişiklik kaydı açılır.

### 0.2 Okuma anahtarı

- **Mevcut/doğrulanmış:** Kaynakta veya tarihli operasyon kanıtında görülmüş olan.
- **Tarihsel:** Kendi sürümünde kalır; bugünkü çalışmanın sonucu değildir.
- **Aday hüküm:** Bu REVIEW sürümünün onayla yürürlüğe girmesi önerilen davranışı.
- **Açık/BLOCKED/NOT TESTED:** Eksik kanıt veya yetki; sessiz PASS değildir.

Aşağıdaki “yapılır/yapılmaz” dili aday sözleşmenin normatif dilidir. Mevcut uygulamanın zaten böyle çalıştığı iddiası değildir. Özellikle yeni `OH1` kabul kimlikleri eski Bible'da dondurulmuş AC'ler değildir.

## 1. Yapmakta olduğumuz oyun

### 1.1 Oyuncuya verilen söz

Oyuncu kendi karakterini, Forgotten Realms içinde D&D 2024 temelli bir kampanyada oynar. Önceki başlangıç çerçevesi 1501 DR olarak korunur; başka tarih/bölge seçimi kaynak ve içerik kapsamıyla açıkça ele alınır. Bu tarih, her eski kaydın aynı tarihte olduğunun kanıtı veya erişilebilir bütün lore'un otomatik geçerli olduğu anlamına gelmez.

Oyuncunun ana aracı doğal Türkçe girişidir. “Kapıyı çalıyorum”, “Pencerenin sürgüsünü inceleyebilir miyim?”, “Neden?”, “Bu işi yaparım ama altın yerine kılıcını isterim” ayrı önceden yazılmış senaryolara muhtaç olmadan anlamlandırılmalıdır. Uygulanabilecek sonuç, karakterin gerçek imkânlarına, dünyaya ve kurallara bağlıdır. Serbestlik her isteğin başarılı olması değildir; makul bir isteğin gerçekten anlaşılması, tutarlı değerlendirilmesi ve anlamlı karşılık bulmasıdır.

AI DM yalnız atmosfer üretmez. Yerel karakterler, onların istekleri ve korkuları, çözülmemiş meseleler, ilişki gerilimleri, keşfedilebilir ayrıntılar ve gelecekte gerçekleşebilecek gelişmeler üretir. Bununla birlikte oyuncunun kararını vermez, zar sonucunu düzeltmez, geçmişi gizlice yeniden yazmaz. Oyuncu bir fırsatı reddedebilir, beklenmedik bir çözüm bulabilir, ayrılabilir veya daha sonra dönebilir. Dünya bu tercihleri hatırlar.

Her yeni kampanya aynı adı değiştirilmiş hancı ve aynı zorunlu görev değildir. Yeni kampanyada kadro, ilişkiler, amaçlar ve başlangıç gerilimi anlamlı biçimde çeşitlenir. Aynı kampanyada ise kişi aynı kişidir: tekrar karşılaşınca adı, yaşadıkları ve öğrendikleri rastgele değişmez. Canlı dünya, her dönüşte yeniden üretilen dünya demek değildir.

### 1.2 Başarı neye benzeyecek?

Oyuncu küçük bir sahnede kendi planını kurar. Sistem doğru hedefi anlar. Bir yeni kişi veya ayrıntı yaratılmışsa kabul edilir, kayda girer ve sonraki eylemde gerçekten kullanılabilir. Bir inceleme doğru bilgiyi açar; NPC yalnız kendi bildiğini söyler. Başarı ve başarısızlık farklı, kurallı sonuçlar doğurur. Oyuncu oyunu kapatıp açtığında aynı dünyaya döner. Ekranda nerede olduğunu, sonucun ne olduğunu ve bir sonraki girişimini nereye yazacağını aramak zorunda kalmaz.

Bu deneyim önce dar bir alanda kanıtlanır. Dar alan, nihai ürünün kalıcı sınırı değildir. Alan büyütmek de derinliğin yerine geçmez: yirmi yeni şehir, tek kapıdaki yanlış hedeflemeyi çözmez.

### 1.3 Yapılmayacaklar

- Yalnız seçenek kartlarından oynanan, her serbest cümleyi aynı yola zorlayan bir macera.
- D&D veya Forgotten Realms adı altında kaynak dışı mekanik ve resmî lore uydurma.
- Bütün dünyayı, bütün sınıfları ve bütün büyüleri ilk teslimde tamamlamış gibi sunma.
- Güzel metnin doğrudan HP, eşya, ödeme, konum, görev veya geçmiş yazması.
- Her NPC için sürekli çalışan model ajanı, her tur görsel/video üretimi veya erkenden multiplayer genişlemesi.
- Teknik doğruluk uğruna bütün yaratıcı içeriği reddeden; yalnız “desteklenmiyor” diyen bir ürün.
- Sunum veya logo yenilemeyi, çekirdek oyun kabulü yerine kullanma.

## 2. Otorite matrisi: kim neyi belirler?

| Alan | Öneriyi kim üretebilir? | Kabul ve kalıcılık sahibi | Yasak geçiş |
|---|---|---|---|
| Oyuncunun niyeti, sözleri ve seçimi | Oyuncu; AI yalnız yorumlar/netleştirir | Yetkili eylem hattı, oyuncunun gönderdiği kapsam | DM'nin oyuncu adına kabul, saldırı, ödeme veya yolculuk seçmesi |
| Resmî Forgotten Realms bilgisi | Kaynaklı lore hattı | Mevcut lore authority, edition/tarih/kapsam politikası | Yeni yerel hikâyeyi resmî lore diye sunma |
| D&D mekanik sonucu | Oyuncunun girişimi + yetkili kural verisi | Python resolver ve mevcut mekanik owner'lar | Modelin DC, zar, hasar veya ödülü sonuç olarak dayatması |
| Yeni kampanya-yerel kişi/ayrıntı | AI DM, yetkili içerik zarfı içinde | Mevcut dünya/olay sahiplerinin doğrulama ve kayıt yolu | Anlatıda görünmüş olmasını tek başına kabul sayma |
| NPC amacı, kişiliği, sırrı | AI DM; geçmiş ve setting ile uyumlu | Kabul edilmiş yerel profil/olgu/olay | Sonucu engellemek için gizli amacı veya sırrı geriye dönük değiştirme |
| NPC inancı ve bilgisi | Gözlem, anlatılma, kaynaklı çıkarım; yaratılmış başlangıç profili | Kişiye bağlı bilgi/hafıza yolu | Global dünya gerçeğini bütün NPC'lere kopyalama |
| Gelecek olay/plot ihtimali | AI DM | Önce öneri/plan; koşul sağlanınca yetkili olay sahibi | Planı olmuş olay gibi hafızaya yazma |
| Anlatı ve diyalog | AI DM | Çözülmüş sonuç ve kabul edilmiş içerik üzerinde anlatı doğrulama | Anlatı başarısız olunca sonucu tekrar çözme |
| UI, günlük, harita, portre | Frontend/sunum | Oyuncuya açık yetkili projeksiyon | CSS arkasında sır saklama; görüntüyü yeni oyun gerçeği sayma |
| Ürün kapsamı ve kabul | Proje sahibi | Sürümlü sözleşme ve açık karar | Araştırmacı önerisini onay veya test çıktısını insan kabulü sayma |

**Temel değişiklik:** “Python gerçeği yazar” bütün hikâyenin Python'da önceden yazılacağı anlamına gelmez. AI yaratıcı önerinin sahibidir; Python kabulün ve kalıcılığın sahibidir. Aynı şekilde “Qwen anlatır” artık yalnız edebî yeniden yazım görevini tarif etmez: yetkili yaratıcı öneri ve niyet anlama da bu rolün parçasıdır.

Doğrulayıcı, iyi bir hikâyenin tek doğru biçimini belirleyen gizli senaryo filtresi olmaz. Kimlik, kaynak, çelişki, bilgi, mekanik, şema ve izin sınırlarını uygular. Dramatik kalite ayrıca değerlendirilir. Güvenli ama yavan bir öneri geçerli olabilir; bu, deneyim kabulünü geçtiği anlamına gelmez.

### 2.1 Birbirine karıştırılmayacak olgu türleri

1. **Resmî setting olgusu:** Kaynak/provenance ve zaman kapsamı olan lore.
2. **Kabul edilmiş kampanya olgusu:** Bu kampanyada yaratılmış veya yaşanmış gerçek; resmî yayın kanonu iddiası taşımaz.
3. **Kişisel profil olgusu:** Yeni yerel NPC'nin kabul edilmiş kişiliği/yerel geçmişi; oyuncunun yaşamadığı bir olayı oyuncuya atfedemez.
4. **İnanç/iddia:** NPC'nin doğru veya yanlış bildiği, söylediği ya da çıkardığı sonuç. Söylemiş olması, içeriğinin dünya gerçeği olması değildir.
5. **Gelecek ihtimali:** Amaç, plan, tehdit, taslak olay. Gerçekleşmeden geçmişe yazılmaz.
6. **Geçici duyusal anlatım:** Mekanik sonuç veya kalıcı nesne vaat etmeyen atmosfer.
7. **Desteksiz geçmiş iddiası:** “Geçen sefer bana bunu vermiştin” gibi kanıtı olmayan iddia. Soru veya diyalog olarak işlenebilir; gerçekleşmiş olay olarak kabul edilmez.

Mevcut `VERIFIED_SETTING_FACT`, `CAMPAIGN_FACT`, `PROCEDURAL_PERSONAL_FACT`, `EPHEMERAL_SCENE_TEXTURE` ayrımları başlangıç noktasıdır. Yukarıdaki kavramsal ayrım yeni tablo adlarının peşinen onayı değildir. Mevcut veri anlamlarıyla karşılanamayan boşluk önce gösterilir. [S3]

## 3. Kampanya yaratımı ve kalıcı dünya

### 3.1 Başlangıç üretimi: sorunlar yarat, oyuncunun geleceğini yazma

Yeni kampanya üretimi şu sırayla düşünülür: yetkili setting/tarih → karakterin bilinen başlangıç durumu → izinli yerel üretim alanı → yeni kadro ve gerilim önerileri → çelişki ve yetki doğrulaması → kalıcı kimlikler → oyuncuya açık başlangıç sahnesi.

Aday üretim zarfı; mevcut bölge/konum, oluşturulabilecek varlık türleri, mevcut komşuluklar, erişim, kaynaklı setting sınırlamaları, karakter düzeyiyle ilgili izinli mekanik kapsam, ton ve içerik sınırlarını taşır. “Yaratıcı ol” tek başına veri yazma izni değildir. Zarf da yalnız üç sabit NPC kalıbı seçen bir menüye dönüşmemelidir.

LR00'da ilk dar yaratım kanıtı: yeni bir kampanya-yerel NPC, onun en az bir tutarlı amacı veya derdi, sahneye bağlı yeni bir etkileşilebilir ayrıntı ve oyuncunun kabul etmek zorunda olmadığı bir yerel mesele. Bunlar bir ürün kanıtının minimum bileşenleridir; her kampanyada tam aynı sayıda kişi/olay zorunluluğu değildir. Ödül, yeni sınıf/büyü, şehir veya üretim quest kataloğu bu küçük kesite gizlenmez. Yerel mesele, otomatik kabul edilmiş görev değildir.

NPC geçmişi oyuncuyla yaşanmamış bir tanışıklık üretmez. Resmî tanınmış kişileri yeni yerel NPC gibi serbestçe yeniden tanımlamaz. Yeni bir dükkân önerisi, otomatik ticaret mekaniklerinin açıldığı anlamına gelmez; ekonomik etkiler kendi owner ve içerik yetkisini gerektirir.

### 3.2 Yaratılan içeriğin yaşam döngüsü

**Önerildi → doğrulandı → kabul edildi ve kimliklendirildi → uygun kişiye açıldı → etkileşim/olayla değişti → gerekirse tarihsel hâle geldi.** Reddedilen öneri oyuncuya gerçekmiş gibi anlatılmaz, belleğe girmez. Aynı isteğin tekrarı ikinci kişi/nesne yaratmaz. Kabul edilmiş içerik tekrar ziyaretlerde yeniden örneklenmez.

**Buradaki içerik kabulü, onaylı üretim zarfı içinde mevcut yazılım owner’ının otomatik doğrulamasıdır; her yeni NPC veya ayrıntı için proje sahibine soru sorulmaz.** Proje sahibi kapsamı ve ürün kabulünü onaylar. Zarf dışındaki yeni mekanik/şehir/ödül yetkisi ayrı karardır.

Kavramsal kayıt gereksinimi: kampanya ve varlık kimliği; tür; ad/takma ad; konum/üst varlık; kaynak türü; oluşum olayı; gizlilik/keşif durumu; geçerli sürüm; izinli etkileşimler. Kullanıcı arayüzüne gizli bütün kayıt değil, gerekli oyuncu görünümü gider. Ad birincil kimlik değildir; aynı adlı iki kişi karışmamalıdır.

Kampanyalar arası çeşitlilik; başlangıç niyeti, kadro rolleri, motivasyon, ilişki ve çatışma bileşimlerinde ölçülür. Yalnız seed değişmesi veya ad havuzunun büyümesi yeterli kanıt değildir. Kampanya içinde kararlılık için kabul edilmiş gerçek çıktı saklanır; seed'in gelecekte aynı model sürümü ve aynı cümleyi yeniden üreteceği varsayılmaz. Eski Marek'i sırf çeşitlilik artırmak için yeniden adlandırmak yasaktır.

### 3.3 Duyusal süs ile etkileşim sözü

“Havanın serinliği taş duvarlardan hissediliyor” genellikle atmosferdir. “Pencerenin içinde açılabilir bir sürgü var”, “Tezgâhta anahtar duruyor”, “Doğudaki geçit avluya açılıyor” oyuncuya somut imkân sözü verir. Bunlar kabul edilmiş temsil ve kapsam gerektirir. Anlatı böyle bir ayrıntıyı yanlışlıkla vaat etmişse oyuncu onu sorduğunda sistem yokmuş gibi davranarak geçmiş metni örtmez; tutarsızlık kaydı ve güvenli düzeltme gerekir.

Oyuncu sıradan bir ayrıntıyı araştırdığında her defasında gizli ödül yaratılmaz. Fakat hiçbir ayrıntı sırf önceden tek tek kodlanmadı diye otomatik yok sayılmaz. Yetkili, henüz belirlenmemiş yerel boşluk varsa AI bunu mevcut gerçeklerle uyumlu doldurabilir. Sonuç mekanik çözümü veya gizemin cevabını etkileyecekse içerik, zar sonucuna bakılmadan önce belirlenir ve öneri iziyle mühürlenir. Başarısızlık gördükten sonra ipucu eklemek veya başarılı oyuncudan kaçırmak için suçluyu değiştirmek yoktur.

### 3.4 Yerler ve bağlantılar

Bölge, kalıcı konum, sahne ve etkileşilebilir nesne farklı kimlik düzeyleridir. Bir pencerenin içinde bulunduğu han, pencerenin yerine hedef olamaz. Yeni yerel ayrıntı üretme yetkisi yeni resmî şehir, keyfî uzaklık, resmî rota veya teleport yetkisi değildir.

Yolculuk izinli bir bağlantıyı veya kaynaklı yolu çözer; konum, zaman ve ilgili kaynakları tutarlı değiştirir. Geri dönüş gerçekten geçilen bağlantıya dayanır. Tek yönlü geçit mümkündür ama açık semantiğe sahiptir. Bilinmeyen yol süresi kesinmiş gibi yazılmaz. Tam rota ve yolculuk derinliği LR01'in kapsamıdır; LR00 küçük sahnesinde dahi girilen/çıkılan yer ve mevcut kapı durumu yalan söylenmez.

## 4. Doğal niyet, hedef ve bilinmeyen girişimler

### 4.1 Giriş anlama sözleşmesi

Sistem oyuncunun istediği sonucu, denediği yöntemi ve hedefini ayrı ele alır. “Kapıyı açıyorum” başarı beyanı değil girişimdir; kilit ve erişim denetlenir. “Kapıyı açtığımı söylüyorum” konuşmadır; kapı açılmaz. “Açık mı?” sorudur. “Açmıyorum” olumsuzlamadır. “Açıksa içeri bakacağım” koşulludur. Alıntı içindeki talimat otomatik eylem değildir.

Hedef çözümleme; mevcut sahne, kalıcı kimlikler, açık metin, isteğe bağlı UI hedefi ve diyalog odağını birlikte değerlendirir. Eski hedef, açık yeni cümleyi geçersiz kılamaz. Birden çok makul hedef ve önemli sonuç varsa kısa netleştirme yapılır; tek belirgin hedefte her seferinde soru sorulmaz. Netleştirme oyun zamanını veya kaynağı tüketmez.

“Neden?” yalnız son NPC adına bağlanmaz; son ilgili önerme, konu ve konuşan gerekir. “O”, “orası”, “diğeri”, “geri dönelim” için de bağlam önemlidir. Konu değişince eski açık teklif otomatik etkin eylem olmaktan çıkar. Bir kapıyı çalmak, önceki NPC teklifine yanıt sayılmaz.

### 4.2 Her ifade için yeni if/else yazmamak

Niyet kategorileri sınırlı bir alan dili olabilir: konuşma, inceleme, hareket, nesne etkileşimi, bekleme ve mevcut mekanik eylemler. Bu, oyuncunun söyleyebileceği cümlelerin kapalı listesi değildir. Model doğal ifadeyi yöntem/hedef/koşul bileşenlerine çevirir; owner'lar nesnelerin yeteneklerini ve geçerli işlemleri çözer. Yeni genel davranış ihtiyacı varsa bir hedef/yetenek sözleşmesi eklenir, tek kullanıcının tek cümlesine özel yama normal çözüm sayılmaz.

Eski deterministik yollar atılmaz; açık ve güvenilir durumda maliyet azaltabilir. Ancak bir anahtar kelime daha önce eşleşti diye yanlış geniş hedefe gitmek kabul edilemez. Bağlam ve anlam eşlemesi kaynak izinde görülebilmelidir. “Han penceresini arıyorum” cümlesinde `han` ve `ara` bulunması tek başına yeni han arama yetkisi değildir.

### 4.3 Bir mesajda birden fazla girişim

Aday varsayılan: bir gönderim, **bir mantıksal girişim** ve onun doğal, aynı kapsamlı alt adımlarıdır. “Kapıyı hafifçe çalıp içeriden ses dinliyorum” tek bileşik girişim olarak değerlendirilebilir. “Kapıyı kırıp içeri dalıyorum, sandığı açıp malları alıyorum” belirsiz ara sonuçlar, zaman ve kaynak içerir; sessizce bütünü yürütülmez.

Çözücü önce sıralamayı ve koşulları korur. Aynı kapsamda güvenle çözülebilen ilk girişim yürütülür; sonraki bağımlı girişim yeni gözlem gerektiriyorsa açıkça bekler. Birbirinden bağımsız ve önemli birkaç eylem varsa hangisinin önce yapılacağını netleştirir veya açık bir sınırlı sıra onayı ister. Hiçbir alt cümle sessizce atılmaz. Otomatik arka plan kuyruğu yoktur. Bir mesajı gizlice çok tura bölüp her parça için iki model çağrısı açmak bütçeyi aşma yolu değildir.

### 4.4 Makul ama desteklenmeyen eylem

Sıra: niyeti anla → mevcut genel resolver/yetenekle karşılanabiliyor mu bak → kurala uygun ve yetkili yerel yorum mümkün mü değerlendir → gerekirse dürüst sınır ve yakın seçenek sun. Örneğin yaratıcı dikkat dağıtma, var olan kaynaklı beceri/aksiyon çerçevesine girebiliyorsa yalnız tam cümle kataloğu yok diye reddedilmez.

Yeni mekanik gerektiren bir eylemde model gizlice ev kuralı uygulamaz. Teknik kapsam dışılığı oyun dünyasında imkânsızlık diye yansıtmaz: “Bu eylemin şu mekanik etkisi henüz desteklenmiyor” ile “Kapı şu an kilitli” ayrıdır. Kullanıcıya her defasında teknik uzun açıklama yapılmaz; hedefin anlaşıldığı ve neyin çözülebileceği kısa anlatılır.

Oyuncu fikrini değiştirirse gönderilmemiş taslak değişir; çözülmüş sonuç otomatik geri alınmaz. Oyun dışı soru ayrı niyet olarak tanınır, oyun zamanı ilerletmez ve sır açmaz. Zorunlu Say/Do/Ask DM modu gerektirmez.

## 5. AI DM'nin hikâye kurma sorumluluğu

### 5.1 Esnek plot, sabit geçmiş

DM'nin planı geleceğe ilişkin bir çalışma hipotezidir. NPC'lerin amaçları, mevcut tehditler, verilmiş sözler, cevapsız sorular ve fırsatlar tutulur. “Üçüncü turda kesin baskın olacak; oyuncu mutlaka kaçacak” türü zorunlu sahne zinciri varsayılan değildir. Yetkili zaman/olay koşulu gerçekleşirse gelişme olur; oyuncunun müdahalesi koşulları değiştirebilir.

DM oyuncuya ilgi çekici şey sunmak için inisiyatif alır. Her tur oyuncunun sormasını bekleyen pasif ansiklopedi olmaz. Fakat inisiyatif kaynak ve yetki içindedir: bir NPC konuşabilir, bir sorun görünür hâle gelebilir, kaydedilmiş tehdit ilerleyebilir. İzinli olay mekanizması olmayan bir ekonomik ceza, gizli zaman atlaması veya savaş başlangıcı sırf gerilim yaratmak için uygulanmaz.

Bir sürpriz geçmiş gerçeği bozmadığı sürece yeni anlam açabilir. Suçlunun kimliği veya ipucunun anlamı önceden kabul edilmişse oyuncunun doğru tahmini yüzünden değiştirilmez. Henüz belirlenmemiş uzak bir kişi/amaç sonraki yaratımda oluşabilir; bunun önceki bilgiyi değiştirmediği doğrulanır. Oyuncu gizemi erken çözerse oyun bunu başarı olarak karşılar, yeni bir bahaneyle başarıyı geri almaz.

### 5.2 NPC'ler: amaç, ses ve bilgi

Her önemli yerel NPC için işe yarayan küçük bir profil yeterlidir: kimlik/rol, şimdi istediği şey, çekindiği şey, konuşma tavrı, mevcut ilişkiler, bildikleri ve oyuncuyla gerçekleşmiş olayları. Bu profil ansiklopedi doldurma görevi değildir. Karakter sesi aynı kalıp cümleyi tekrarlamak değildir; değişen konuya kendi bakışıyla yanıt vermektir.

NPC bilmediğinde bilmiyorum diyebilir; tahmin edebilir, yanlış inanabilir veya yalan söyleyebilir. Bunlar ayrı anlamlar taşır. “Güvenlik yüzünden” gibi kesin neden, ilgili profil/olay/kaynak olmadan dünya gerçeği olarak uydurulmaz. Yetkili yeni yerel kişisel gerekçe yaratılabiliyorsa önce kabul edilir; mevcut nedenle çelişmez ve geçmiş oyuncu eylemi icat etmez.

A'nın gördüğü olay B'nin bilgisi değildir. Oyuncu B'ye anlattığında B bir iddia öğrenir; doğru gözlemle eşitlenmesi gerekmez. DM'nin bildiği sır oyuncuya veya bütün NPC'lere gönderilmez. Özetler kaynak olay kimliklerine dayanır; asıl olay kaydının yerini almaz. Mevcut hafıza sınırlarının dışına çıkan bilgiler gerektiğinde seçici okunur; bütün geçmişi her tur prompt'a eklemek çözüm değildir.

### 5.3 Sonuç, kısmi başarı ve kapanış

Başarısızlık anlamlı olabilir ama “fail-forward” yeni bir mekanik gibi sessizce açılmaz. Zaman kaybı, gürültü, şüphe, eşya hasarı veya kısmi keşif ancak yetkili kural/olay/eylem sözleşmesi gerçekten destekliyorsa uygulanır. Destek yoksa model dramatik bedel icat etmez. Kısmi başarı, kayıtta tanımlı sonuçtur; başarısız zarı gizli başarıya çevirmek değildir.

Hikâye yayları kapanabilir. Her cevaptan yeni bir sonsuz gizem üretmek yerine çözülen mesele görünür biçimde çözüldü sayılır; sonuçları dünyada kalır. Oyuncu başka bir meseleye geçebilir veya sakin bir etkileşime dönebilir. Dünyanın devam etmesi eski ödülü tekrar vermek veya bitmiş görevi yeniden açmak anlamına gelmez.

## 6. Mekanik çözüm, inceleme ve anlatı kalitesi

### 6.1 Kurallı özgürlük

D&D 2024 hedefi bütün kuralların bugün tamamlandığı anlamına gelmez. Her etkin mekanik için kaynak/edition, mevcut owner, desteklenen parametreler ve sonuç alanları belli olur. 2014 veya başka sistemden bir davranış sessizce 2024 diye kullanılmaz. Kaynak erişimi ve yayın/varlık hakları ayrıca korunur; ürün hedefi kullanım hakkı kanıtı değildir.

**Legacy seçeneklerin korunması:** Önceki kullanıcı tercihi olarak aktarılan Half-Elf ve Half-Orc seçenekleri korunur; otomatik olarak 2024 seçeneği diye etiketlenmez. Bu tarihsel tercihin özgün karar kaydı mevcut kaynak okumalarında doğrudan bulunmadığı için kaynak doğrulaması açık olarak tutulur; bu eksiklik seçenekleri sessizce silme veya mekaniklerini dönüştürme yetkisi değildir. Mevcut karakterler ve yaratım seçenekleri korunur; ilgili edition/kural kaynağı uygulama manifestinde doğrulanır. AI görünüş/kişilik taslakları seçilen tür ve kabul edilmiş özelliklerle uyumlu olur; portre üretimi mekanik tür dönüşümü yapmaz. Bu koruma yeni özellik paketi değildir.

Python; zar, DC, isabet, hasar, HP, koşul, sıra, aksiyon ekonomisi, slot, envanter, konum, zaman ve ödülün yetkili sahibidir. Model makul yöntem önerebilir, fakat nihai mekanik sonucunu tayin etmez. Yetkili genel beceri çözümü varsa yaratıcı yöntem onunla değerlendirilebilir; yoksa yeni kural önce kapsamlandırılır. Her soru zar gerektirmez. Otomatik açık bilgi için gereksiz check, ulaşılamayan bilgi için anlamsız check veya başarıyla ilgisiz zar gösterimi yapılmaz.

### 6.2 Sonuç makbuzu

Her çözülen girişim, anlatıdan bağımsız bir **sonuç makbuzu** taşır. Bu kavram mevcut response/event sözleşmesine eklenebilir; yeni paralel kayıt sistemi talimatı değildir. Asgari anlamlar:

- Kampanya ve mantıksal istek kimliği; başlangıç/son durum revizyonu.
- Gerçek hedef ve çözülmüş girişim; çözülmedi/netleştirme/başarı/başarısızlık gibi yetkili durum.
- Atılmış zar ve kullanılan modifier; yalnız mevcut kayıtta gerçekten bulunan ayrıntılar.
- Açılmasına izin verilen keşifler, değişen olgular ve gerçek kaynak etkileri.
- Kabul edilmiş yeni içerik kimlikleri; hangi bilgi kime açıldı.
- Anlatı kaynağı ve durumu: doğrulanmış model anlatısı, güvenli fallback veya eksik sunum.

Makbuz oyuncuya bütün DM sırlarını açmaz. DC veya gizli testin görünürlüğü mevcut kurala göre belirlenir. Geliştirici kanıtı ile oyuncu kartı aynı veri kümesi değildir.

### 6.3 “İnceleme başarılı” yeterli değildir

İnceleme sonucu hedefe ve yönteme bağlanır. Sürgü incelendiyse sürgü hakkında erişilebilir bilgi; camdan bakıldıysa görüş sınırı; iz arandıysa uygun bulgu veya açıkça sınırlı yokluk bildirilir. Her başarılı check hazine, gizli geçit veya yeni bir ipucu yaratmaz. “Bu yöntemle başka iz bulamadın” ile “Burada kesinlikle hiçbir şey yok” farklı iddialardır.

Keşif koşulları ve olası bilgi ilk çözümden önce belirlenir. İlk model çağrısında gerektiğinde koşullu bulgu adayları hazırlanır; Python kabul edilebilenleri belirler ve yetkili check sonucuna göre hangisinin açıldığını seçer. İkinci anlatı çağrısı başarısızlığı telafi etmek veya başarıyı süslemek için yeni kullanılabilir kanıt üretmez. Gerekli içerik bu bütçe içinde güvenilir üretilemiyorsa eksikliği açıkça raporlanır; sahte keşif veya gizli üçüncü çağrı ile kapatılmaz.

### 6.4 Anlatı kalitesi sözleşmesi

İyi bir yanıt dört şeyi yapar: mevcut sahneye bağlıdır; oyuncunun gerçekten denediğine cevap verir; çözülmüş sonucu anlaşılır kılar; sonraki karara alan bırakır. Her tur aynı giriş paragrafı, aynı han tarifi veya ilgisiz görev teklifi dönmez. Sabit kişi/nesne sürekliliği korunurken cümleler ve vurgu bağlama göre değişebilir.

Yanıt oyuncunun duygusunu veya kararını dikte etmez. “Korkuyla geri çekilirsin” yalnız gerçekten uygulanmış mekanik zorlamanın uygun anlatımıysa kullanılabilir; normal durumda oyuncunun iradesini yazmaz. Üslup canlı olabilir, fakat kayıt dışı hasar, sahiplik, ilişki, ödeme veya zaman akışı eklemez.

Reddedilmiş model anlatısı hafızaya, günlüğe, NPC bilgisine veya kampanya olayına yazılmaz. Fallback somut doğrulanmış sonucu taşımalıdır; yalnız “başarılı oldun” üretmesi mekanik güvenlik sağlasa da deneyim kabulü değildir. Anlatı sorunu, çözülmüş eylemi yeniden zar atarak onarma sebebi olmaz.

## 7. Model çağrısı ve bağlam bütçesi

### 7.1 İlk tasarım tercihi: toplam iki çağrı içinde yaratıcı DM

v1.0 için önerilen başlangıç, **mantıksal eylem başına toplam 0–2 model çağrısıdır**. Bu mevcut sözleşmeyle uyumludur; yaratıcılığın sonsuza dek iki çağrı içinde çözüleceği iddiası değildir. Ölçüm iki çağrının kaliteyi belirgin sınırladığını gösterirse farklı bütçe ve mimari gerekçeli v1.x değişikliği olarak teklif edilir. O zamana kadar sessiz artış yoktur.

- Açık, güvenilir deterministik giriş: sıfır yorumlama çağrısı; gerekirse bütçe içinde bir anlatı çağrısı.
- Serbest giriş: ilk çağrı niyet/hedef/koşul ve gerektiğinde sınırlı yaratıcı içerik önerisini üretir. Python doğrular ve çözer. İkinci çağrı yalnız kabul edilmiş içerik ve sonucu anlatır.
- Yeni kampanya açılışı: görünür, ayrı başlangıç işlemi olarak tanımlanır; ilk aday bütçesi yine en fazla iki çağrıdır. Bir oyuncu girişiminin içinden sahte “başlangıç/arka plan” işlemleri açılıp limit aşılmaz.
- Geri dönüş: kabul edilmiş içerik okunur; aynı kişiyi/odayı yeniden yaratma çağrısı yapılmaz.
- Reddedilmiş anlatı: ek model çağrısı yoktur. Kayıtlı sonuç ve güvenli fallback kullanılır.

Modelin yapılandırılmış JSON üretmesi doğruluğu kanıtlamaz. Şema, kimlik, bilgi, kaynak ve izin ayrı doğrulanır. Model SQL, Python kodu, serbest JSON patch veya keyfî state yolu yazmaz. Araçlı/ayrı yaratıcı hazırlık ileride değerlendirilebilir; açık uçlu agent loop başlangıç tasarımı değildir. [S8]

### 7.2 Bağlam seçimi

İlk bağlamın çekirdeği: oyuncunun tam girdisi; sahne ve geçerli hedef kimlikleri; mevcut durum; diyalog konusu ve son ilgili önerme; gerekli kaynaklı kurallar; ilgili kabul edilmiş yerel olgular; oyuncu/NPC bilgi görünümü; açık meseleler ve yakın sonuçlar. Sadece “son altı mesaj” veya bütün sohbet yığını yeterli kabul edilmez.

Bağlam seçimi gizli bilgi kapsamına göre ayrılır. DM için gerekli sır ile NPC'nin söyleyebileceği bilgi aynı alan değildir. Anlatı doğrulamasının ihtiyaç duyduğu gizli olgu oyuncuya giden API/UI paketine taşınmaz. Çok uzun geçmişte özet kullanılabilir, fakat özet geçmişi yeniden kuran otorite değildir. Kaynak olay/varlık bağlantıları korunur.

İlk ölçüm modeli, digest/quantization, Ollama sürümü, donanım, context ayarı, sıcak/soğuk çalışma, token sayıları ve çağrı süreleriyle kaydedilir. `qwen3:8b` etiketi tek başına tekrarlanabilir deney tanımı değildir. Yorumlama ile yaratıcı üretimin sampling ihtiyaçları ayrıştırılabilir; seçilen ayarlar ölçülmeden “en iyi” ilan edilmez. Mevcut parser'ın ayarları tarihsel uygulama kanıtıdır, yeni kalitenin garantisi değildir.

### 7.3 Hata ve bütçe hesabı

Çağrı sayımı mantıksal isteğin tamamını kapsar: yorumlama, yaratım, anlatı, sağlayıcıya giden retry ve varsa araç sonrası model devamı. HTTP retry, sayfa yenileme, resume veya süreç restart bütçeyi sıfırlamaz. Sağlayıcıya gerçekten ulaşmış başarısız/timeout denemeler görünür kaydedilir; belirsiz sayım dürüstçe bilinmiyor kalır. Sağlayıcıya gitmiş olabilecek belirsiz/timeout deneme, gönderilmediği kanıtlanana kadar bütçede ayrılmış bir deneme olarak tutulur; kör retry ile iki çağrı aşılmaz. Aynı girişimi tamamlayan netleştirme ve retry mesajları aynı mantıksal istek zincirinde kalır; çağrı bütçesini sıfırlamaz. Oyuncu önceki girişimi bırakıp gerçekten farklı bir girişim seçerse yeni istek kimliği ve bütçe oluşur. Aynı girişimi sırf tükenen bütçeyi aşmak için yeni kimlikle yeniden etiketlemek yasaktır. Kimlik geçişi, eski girişimin çözülme/commit durumunu korur; önceki çözülmüş etki yeniden uygulanmaz.

Devam koşusu için verilen beş yeni istek sınırı ile görünür kullanıcı girdisi sayısı, backend hata olayı veya model çağrısı sayısı değildir. Yetkilendirilmiş deneme sınırı, uygulama sayaçları, sağlayıcı hatası ve gerçek inference çağrıları ayrı incelenir. Güncel canlı oturumun gerçek model logları henüz görülmediği için teşhis açık kalır.

Ölçülecekler: doğru niyet ve hedef; kabul edilmiş yeni içeriğin kalitesi; red/fallback oranı; toplam ve kalıcı sonuca kadar süre; token/çağrı maliyeti; bağlam taşması; kullanıcı bekleme deneyimi. İlk smoke ölçümünden sonra paket için süre sınırı kararlaştırılır. Burada kanıtsız milisaniye veya p95 hedefi uydurulmaz. İki çağrı yetersizse rapor bunun hangi beceriyi ve hangi maliyeti etkilediğini gösterir; bütün sistemi sessizce daha fazla örneklemeye açmaz.

## 8. Kayıt, tekrar güvenliği ve eski kampanyalar

### 8.1 Mantıksal işlem sınırı

Aday işlem kimliği kampanya + istek kimliğine bağlıdır. Aynı kimlik ve aynı içerik, varsa kayıtlı sonucu döndürür. Aynı kimlik farklı içerikle kullanılırsa yeni hamle sayılmaz; uyuşmazlık olarak ele alınır. UI'da Gönder'i kapatmak tek başına çift harcamayı önlemez.

Model çağrısı uzun açık yazma transaction'ı içinde tutulmaz. Başlangıç revizyonu okunur; öneri hazırlanır; kısa commit öncesi hedef ve önkoşullar tekrar doğrulanır. Atomik sınır; yetkili etkiler, keşif/yaratım kayıtları, olay/makbuz ve revizyon ilerlemesinin tutarlılığıdır. Mevcut engine JSON save ile API SQLite kampanya save yolları aynı şey sayılmaz; ilgili yol açıkça test edilir.

Çakışan revizyonda eski öneri yeni dünyaya kör uygulanmaz. Henüz commit edilmemiş çözümlemenin sonucu yayımlanmaz; yeniden değerlendirme mevcut bütçe ve mekanik RNG sözleşmesi içinde mümkün değilse güvenli durur/netleştirme döner. Commit edilmiş sonuç hiçbir durumda tekrar zar atılarak değiştirilmez. Bir crash aralığında neyin atıldığı/kaydedildiği belirsizse başarı veya başarısızlık tahmin edilmez; kanıt korunur ve kurtarma durumu açık gösterilir. Bu tasarım “dağıtık sistemde evrensel exactly-once” iddiası değildir; tek mekanik etki için idempotent uygulama ve kayıt güvencesidir.

### 8.2 Arıza senaryoları

- **Çözümden önce arıza:** Oyun etkisi oluşmaz; taslak korunur, güvenli tekrar semantiği açıklanır.
- **Commit sonrası, anlatı öncesi arıza:** Kayıtlı sonuç/fallback geri gelir; zar ve kaynak yeniden işlenmez.
- **Anlatı reddi:** Sonuç geçerliliğini korur; reddedilen metin bilgiye dönüşmez.
- **Geç gelen yanıt:** Kampanya ve revizyon uyuşmuyorsa başka kampanyanın ekranına yazılmaz.
- **Restart:** Kabul edilmiş kimlik, keşif, kaynak, ilgili diyalog odağı ve RNG/olay durumu korunur.
- **Yedekten dönme:** İlgili manifest/sürümle doğrulanır; yalnız dosyanın varlığı “restore başarılı” değildir.

SQLite ayarları, foreign key davranışı ve backup yolu mevcut uygulamada doğrulanır; WAL açık diye güç kesintisine karşı her koşulda kayıpsızlık vaat edilmez. Canlı veritabanının yalnız ana dosyasını kopyalamak güvenilir backup varsayılmaz. [S9]

### 8.3 Eski save politikası

Kampanya gerçekleri yeni üretim politikasına geçerken keyfî yeniden örneklenmez. Eksik yeni alan için açık schema/version geçişi, güvenli varsayılan veya destek sınırı gerekir. Eski handa kapı kaydı yok diye geçmişte görülmüş durum sessizce değiştirilmez. Aynı zamanda yeni test fixture'ına eklenen kapı, eski canlı kampanyada zaten varmış gibi sunulmaz.

Migration gerekiyorsa önce mevcut sahip, backup/restore, idempotent geçiş, eski sürümle uyumluluk veya geri dönüş sınırı ve veri kaybı riski yazılır. Üretim verisine uygulamak ayrı yetkidir. Test kopyaları kullanıcı kampanyasının yerine geçirilmez. Kayıp geçmiş kanıtı yeni bir test çalıştırarak yeniden yaratmış gibi davranılmaz.

Kullanıcı bir tur geri alma özelliğini istedi; dar sözleşme §8.4'tedir. Bu, sınırsız geçmiş düzenleme açmaz. Metin düzeltmesi, transport retry, arıza rollback'i ve oyuncunun bilinçli undo eylemi ayrıdır. Yeniden anlatım otomatik ek model çağrısı izni değildir.

### 8.4 Bir tur geri alma: kullanıcı isteği ve önerilen teknik sözleşme

**Ürün kararı:** Kullanıcı, yanlış anlaşılmayı düzeltme yönünü kabul ederken ayrıca bir tur geri gitme özelliğini istedi. **Aşağıdaki teknik davranış adaydır:** Son metnin ve ilgili paketin uygulama onayı beklenir. Özellikle kötü zar sonrası aynı hamlenin yeniden atılıp atılmayacağı konusunda kullanıcı ayrı bir kural seçmiş sayılmaz; bu metin güvenilirlik için önerilen varsayılanı açıkça sunar.

**Kapsam:** İlk sürüm tek oyuncuda, aktif dalın son tamamlanmış oyuncu turunu geri alır. “Tur” bir sohbet balonu değildir: o oyuncu isteğine bağlı bütün yetkili etkiler, varsa alt çözüm adımları ve tetiklenen dünya olaylarıyla aynı sınırdır. Konum, zaman, HP, koşullar, slotlar, envanter, NPC bilgisi/ilişki etkisi, keşif, yaratılmış yerel varlıklar, günlük, diyalog odağı, olay kayıtlarının aktif projeksiyonu ve RNG durumu tutarlı şekilde tur öncesine döner. Bu listenin gerçek veri sahipleri paket girişinde envanterlenir; yalnız görünen alanları geri almak yeterli değildir.

**Açık oyuncu eylemi:** Kullanıcı ayrıca metin komutu yerine küçük bir geri düğmesini seçti. Son tamamlanan turun yanında küçük ↶ kontrolü bulunur; tooltip ve erişilebilir adı “Son turu geri al” olur. Görsel küçük olsa da dokunma alanı rahat, odak görünür ve klavye erişimi tamdır. İşlem sürerken veya güvenilir geri alma state'i yokken devre dışıdır; nedeni erişilebilir biçimde açıklanır. Büyük bir sayfa üstü düğme veya oyuncuya komut yazdırma gerekmez. **Kabul edilen UI yönü:** İlk tıklamada küçük “Bu tur ve sonuçları geri alınacak” onayı, “Geri al / Vazgeç” seçenekleriyle gösterilir. Kullanıcı düğme, açıklama, onay, işlem sürerken devre dışı kalma ve erişilebilir dokunma alanı yönünü de kabul etti; uygulama henüz başlamadı. Seçim hangi turu etkilediğini gösterir; yanlış anlaşılma tespiti tek başına otomatik undo başlatmaz. Tek seferlik bu seçim tekrar çalıştırıldığında ikinci tur geri alınmaz. İlk kapsam ardışık undo ile geçmişte sınırsız yürümeyi açmaz: son tur geri alınınca aynı işlem tekrar geri götürmez; yeni bir oyuncu turu tamamlanınca onun için yeniden kullanılabilir. Genel branch gezgini veya çoklu undo/redo bu paketin dışında kalır.

**Geçmişi silmek yerine dal değiştirme:** Önceki tur ve sonucu denetim/geçmiş kanıtında korunur; terkedilmiş gelecek dalı olarak işaretlenir. Aktif state ve model context yalnız seçilen yeni dalı izler; türetilmiş özetler ve önbellekler de dal/revizyon kapsamında uzlaştırılır. Eski dalın request ID'siyle gelen tekrar tarihsel sonucu referanslayabilir ama terkedilmiş etkileri aktif dala yeniden uygulayamaz. Geri alınmış olay NPC'nin bildiği, oyuncunun keşfettiği veya elde ettiği etkin gerçek gibi geri gelmez. Tarihsel test raporları, orijinal kullanıcı transkripti ve gerçek hata kanıtı silinmez. Oyuncunun zihninde gördüğü bilgiyi unutturamayacağımız açıktır; sistem bunu yeni dalın karakter/NPC bilgisi diye kullanmaz.

**Zar için önerilen varsayılan:** Geri aldıktan sonra aynı başlangıç koşullarında aynı mekanik girişim yeniden seçilirse önceki kaydedilmiş zar sonucu kullanılır; yeni şans örneklemesi yapılmaz. Sadece eşanlamlı ifade yazmak veya yeni request ID almak farklı hamle değildir. Gerçekten farklı yöntem/hedef veya değişmiş yetkili önkoşul yeni girişimdir; kendi geçerli mekanik çözümü yapılır. Eşdeğerlik yalnız metin benzerliğiyle aranmaz: aynı güvenilir tur-öncesi state, aynı normalize resolver eylemi/hedefi/parametreleri ve kayıtlı zar/makbuz kimliğiyle sınırlıdır. Evrensel bir dil eşdeğerliği veya hile tespit sistemi kurulması gerekmez. Kanıtlı eşleştirme mümkün değilse aynı sonucu veya yeni zarı tahmin ederek uygulamak yerine netleştirme/güvenli sınır gerekir.

RNG geri yükleme ile eski sonucu yeniden kullanma birlikte tutarlı olmalıdır: eşdeğer hamlede kayıtlı atış kullanılırken RNG'nin o çözümden sonraki konumu da doğru ilerletilir; sonraki hamle aynı rastgeleliği yanlışlıkla tekrar tüketmez. Farklı hamle tur öncesi RNG'den normal ilerler. Bu varsayılan her tür bilgi avantajını engellediği iddiasını taşımaz; oyuncunun bilinçli geri alma tercihi ile aynı çözüm için yeni rastgele sonuç üretimini birbirinden ayırır. Nihai politika son sözleşme onayında değiştirilebilir; bugünkü canlı zarlara geriye dönük uygulanmaz.

**İşlem ve yarış güvenliği:** Çözülmekte olan veya sonucu belirsiz oyuncu turu varken undo yoktur; önce işlem uzlaştırılır. Yeni eylemle undo aynı anda commit olamaz. Undo ayrı idempotent kontrol işlemidir, transport retry değildir. Branch/revizyon değişimi atomiktir; eski dala ait gecikmiş model yanıtı, API response veya medya sonucu aktif dalı yeniden canlandıramaz. Geri alma ücretli dış üretimi veya gönderilmiş dış işlemi kendiliğinden iptal/refund etmez; bu tür işlemlerin sınırı gösterilir. Undo için model çağrısı gerekmez. Gerçekleşmiş model çağrısı, token/kota ve maliyet kayıtları geri alınmayan denetim verisidir; terkedilmiş dalın isteği harcanmamış bir istek diye yeniden sınıflandırılmaz. Transport retry veya eşdeğer girişimin kayıtlı sonucunu yeniden kullanma önceki sayaçları sıfırlamaz ve yeni zar üretmez. Yeni dalda gerçekten farklı bir girişim kendi sınırlı bütçesine sahiptir; aynı girişimi yeniden ifade etmek iki çağrı tavanını aşma yolu değildir.

**Eski save ve rollout:** Güvenilir tur-öncesi snapshot/olay/RNG kanıtı bulunmayan geçmiş turda düğme kullanılamaz ve neden söylenir; eksik durum anlatıdan tahmin edilmez. Snapshot veya branch şeması gerekiyorsa mevcut persistence sahibinde sürümlü migration, backup/restore ve eski save testleri yapılır. Bu paket geçmiş kullanıcının kampanyasını bugün değiştirme yetkisi değildir. Geri alma özelliği hazır değilken çekirdek oyun çalışmaya devam eder; hazırmış gibi gösterilmez.

## 9. Mevcut mimariden aşamalı geçiş

Kaynak envanteri “sıfırdan motor kurmalıyız” sonucunu desteklemiyor. Oyuncu yolu Experience UI → FastAPI → Python `GameSession` → SQLite ve Ollama'dır. Node/Express/Postgres çalışma alanı kampanya API'siyle karıştırılmaz. `game.py` içinde çok sayıda owner/dispatch yolu vardır; tek bir prompt değişikliği bütün girişleri düzeltmiş sayılmaz. [S2, S3]

| Sorumluluk | Kaynakta doğrulanan başlangıç | Önerilen geliştirme; henüz mevcut işlev iddiası değil |
|---|---|---|
| Niyet/hedef ve dispatch | `game.py` parser, normalize/validate ve mevcut owner yönlendirmeleri | Anlam/hedef önceliği, bileşik girişim politikası, izlenebilir route kararı |
| Yerel dünya ve kişi yaratımı | `living_world.py` bir kez scene materialization; `validate_world_updates` izinli öneri sınırı | Kampanyaya özgü yaratıcı zarf, kalıcı kabul, genel etkileşilebilir ayrıntı |
| Kişisel diyalog | `local_dialogue.py`; `game.py` aktif kişi ve hafıza korumaları | Kişi yanında önerme/konu sürekliliği, doğru bilgi görünümü |
| Uzun süreli bağlam | `api/narrative_memory.py` | Kaynaklı seçici bağlam ve açık meselelerin ilgili turda kullanımı |
| Oyuncu bilgisi | `api/lore_authority/player_knowledge.py` | Yeni kabul edilmiş yerel içeriğin gizlilik korunarak projeksiyonu |
| Mekanik/anlatı | Mevcut beceri/kapı/combat sonuç paketleri, `narration_claims.assess` | Kullanışlı keşif alanları ve yaratıcı kabulün anlatıya taşınması |
| UI ve API | Mevcut Experience yüzeyi ve alan sözleşmeleri | Viewport kabuğu, tek giriş, görünür makbuz, isteğe bağlı 3D zar |
| Persistence | Mevcut engine save/API SQLite yolları | Yaratım, diyalog odağı ve işlem bütünlüğü için boşluk doğrulaması |

Tablodaki kavramlar yeni dosya/fonksiyon adlarının onayı değildir. Değişiklikten hemen önce güncel owner listesi ve dosya sınırları tekrar doğrulanır. Yeni modül ancak mevcut sorumluluğun gerçekten taşınması veya eksik bir alan gösterilmesiyle önerilir. İkinci narrator, journal veya persistence sistemi kurarak geçiş kolaylaştırılmaz.

Aşamalar: önce mevcut davranışın izi → dar sözleşme ve test → mevcut owner'da değişiklik → eski yollarla uyum → gerçek model/oyuncu kanıtı. Geriye dönük uyum bayrakları gerekiyorsa açık ömür ve kaldırma koşulu taşır; sonsuz çift motor bırakılmaz. `game.py` üzerinde tek entegrasyon yazarı bulunur; farklı araştırmacılar paralel okuyabilir, aynı bloklara eşzamanlı yama yapmaz.

## 10. Oyun ekranı, 3D zar ve kimlik

### 10.1 Ana düzen: sahne ve anlatı

Kullanıcının istediği ana oyun döngüsü viewport'a oturur: bulunduğu yer ve kritik durum → son oyuncu girişimi → DM anlatısı ve gerçek sonuç → tek serbest giriş. Tam geçmiş, envanter, günlük ve ayrıntılı karakter görünümü gerektiğinde açılır. Bu, bütün romanı ve bütün envanteri aynı ekrana sıkıştırmak değildir.

Önerilen A düzeni merkezde anlatı/sonuç, yardımcı alanda bilinen kişiler/nesneler/çıkışlar, üstte HP ve kritik koşullar, altta erişilebilir giriş kullanır. Sinematik B görünümü ve yoğun taktik C düzeni ilk teslimde ayrı üç uygulama yapılmaz. İleride aynı veri ve eylem yolunun sunum varyantları olabilir. Kullanıcının yerleşime olumlu geri bildirimi yön desteğidir; bütün piksel ölçülerinin uygulama kabulü değildir.

1366×768, 1920×1080 ve 360×800 CSS viewport'ları aday test ölçüleridir; kullanıcının ölçülmüş cihazı değildir. Normal masaüstü döngüsünde ana sayfa kaydırmadan eyleme erişim hedeflenir. Uzun son yanıt tek belirgin okuma alanında kayabilir; tam metin asla kesilmez. Geçmiş kendi panelinde açılır. Kullanıcı eski kısmı okurken otomatik aşağı çekilmez; yeni sonuç işareti gelir.

Dar ekranda tek sütun, sade durum şeridi, anlatı ve giriş önceliklidir. Kişi/çıkış/envanter çekmecede veya açık etiketli panelde bulunur. Klavye açılınca önce dekoratif görsel küçülür; Gönder, taslak ve sonuca erişim kaybolmaz. Zoom/büyük yazı/dar yükseklikte reflow ve sayfa kaydırma erişilebilirlik için serbesttir. “Sıfır scroll” uğruna yazı küçültülmez veya içerik kırpılmaz.

### 10.2 Tek giriş ve hedef yardımı

Say/Do/Ask DM zorunlu modları yoktur. Tek alan konuşma ve eylemi alır. İsteğe bağlı hedef çipi açıkça görünür ve kaldırılabilir; serbest metnin yerine komut kataloğu oluşturmaz. Çip ile metin çelişirse yanlış kişiye sessiz işlem yapılmaz. Öneri kartı yalnız taslağı doldurur; açık Gönder olmadan tur, seyahat, saldırı veya ödeme olmaz. Dolu taslak sessizce ezilmez.

Oyun dışı yardım isteğe bağlı, belirgin ve zamanı ilerletmeyen ikincil seçenektir; ayrı zorunlu giriş modu değildir. “Kayıtlar”, “Burada”, “Karakter” gibi açık adlar belirsiz ikon yoğunluğuna tercih edilir. Son turun kritik HP/slot kaybı veya keşfi yalnız çekmece içine saklanmaz.

### 10.3 3D zar: kullanıcı tarafından istenen yön

Zar atma gerektiğinde sahne üstünde geçici **3D zar sunumu** hedeflenir; ardından kısa, kalıcı sonuç kartına çekilir. Bu yön 16 Ekim'de kullanıcı tarafından ayrıca istenmiştir. Kütüphane, asset, animasyon süresi ve uygulama ayrıntısı henüz seçilmedi; test PASS değildir.

3D fizik motoru oyun zarını çözmez. Python'ın **bir kez** ürettiği kaydedilmiş sonucu gösterir. Animasyonu yeniden oynatmak, sayfa yenilemek veya geçmiş turu açmak yeni zar/eylem/slot tüketimi yaratmaz. İstemci animasyonu başarısız olsa da doğru metin sonucu ve oyun akışı çalışır. Eski kayıtta yalnız toplam varsa tek tek zar yüzleri uydurulmaz; toplam gösterilir, dekoratif sunum kanıt gibi kullanılmaz.

Atla, ses kapat, reduced-motion ve ekran okuyucu/metin sonucu bulunur. WebGL kullanılamıyorsa 2D/metin fallback vardır. Animasyon Gönder'i veya okunabilir sonucu gereksiz bekletmez; tamamlanmasını zorunlu tutmaz. Gizli/DC görünürlüğü normal sonuç politikasıyla aynıdır. Kritik failure veya success yalnız renk ve animasyonla anlatılmaz.

**Yerleşim:** LR00-P5'te sonuç kartı ve 3D entegrasyon sınırı hazırlanır; sınırlı 3D sunum aynı paket içinde bağımsız alt teslim olabilir. Mekanik/idempotency ve metin yolunun kabulü 3D görselin cilasını beklemez. Ürün yönü kaybolmaz: LR04 bütünleşik görsel kalite kapısında gerçek 3D, performans ve erişilebilirlik doğrulanır. 3D alt teslim tamamlanmadıysa açıkça açık kalır; “bütün istekler bitti” denmez.

### 10.4 Erişilebilirlik ve bilgi güvenliği

Klavye ile giriş/gönderim, belirgin odak, panel kapanınca doğru yere dönüş, ekran okuyucu için kısa durum bildirimleri, yeterli kontrast ve rahat dokunma alanları tasarım hedefidir. 200% metin ve 400% zoom/reflow denenir; ölçmeden WCAG uygunluğu ilan edilmez. Enter/IME davranışı yanlışlıkla hamle göndermemelidir; başlangıç önerisi Enter yeni satır, Ctrl/Cmd+Enter gönderim ve görünür Gönder düğmesidir.

Yeni yanıt odağı çalmaz; her token sesli tekrar okutulmaz. Bekleme, bağlantı belirsizliği, çözüldü-anlatı eksik ve çözülemedi ayrılır. “Sonucu kontrol et”, “aynı isteği güvenle yeniden dene” ve “yeni girişim” aynı düğme değildir. UI'da iptal görünmesi sunucu iptal semantiği olmadığı hâlde eylemi iptal etmiş gibi davranamaz.

Oyuncuya açılmamış sır HTML, tooltip, erişilebilir ad, kart sayısı, portrait metadata veya ağ yanıtıyla sızmaz. NPC kartı onun gizli amacını açmaz. Sahne görselindeki dekorların tümü mekanik vaat değildir; oyuncunun ilgilendiği ayrıntı için §3.3 geçerlidir.

### 10.5 Logo ve görsel kimlik

UNWRITTEN adı, Ouroboros ve sisli kale kapısı yönü korunur. Mevcut nihai logo asset'i bu çalışmada görülmedi; konseptin onayı, görülmemiş dosyanın kalite veya hak onayı değildir. Logo metin yer tutucusu yeni logo kabulü sayılmaz.

Replit Design ile inceltme ayrı öneri görevidir: mevcut asset görülür, okunurluk ve küçük boyut testleri yapılır; wordmark/amblem/tek renk varyantları, vektör kaynak, font ve varlık hakları değerlendirilir. Kullanıcı seçmeden mevcut kimlik değiştirilmez. BG3 sinematik kalite referansıdır; başka oyunun logosu, karakteri veya arayüz bezemesini kopyalama izni değildir.

Rakip UI incelemesinin dersi: Fables'ın metin içine yerleşen mekanik sonuçları, Runebook'un tek sütun okuma akışı, AI Realm'in açılabilir bilgi alanları ve Craft'ın sahne/portre desteği birlikte değerlendirilebilir. AI Dungeon'ın Do/Say modları burada zorunlu tasarım olarak alınmaz. İnceleme resmî ekran/rehberlerle sınırlıdır; güncel canlı kampanya veya mobil klavye/erişilebilirlik testi değildir. [S10]

### 10.6 Yeni medya önerileri: karakter üretimi, portre ve mekân atmosferi

Kullanıcının 16 Ekim'deki yeni fikirleri **ürün adaylarıdır**: mekâna uygun ses/görsel; karakter yaratırken görünüş ve kişilik için AI Generate; bunlara bağlı portre; bazı işler için ikinci AI. Yön olumlu değerlendirilir, fakat bu soru ücretli sağlayıcı, model kurulumu veya bütün özelliklerin LR00'a eklenmesi onayı değildir.

**Önerilen karakter akışı:** “Görünüş öner” ve “Kişilik öner” ayrı, isteğe bağlı taslaklar üretir. Kullanıcı düzenleyebilir, alanları kilitleyebilir, yalnız seçtiği kısmı yeniden üretebilir veya atlayabilir. Taslak onaylanmadan kayıtlı karakter gerçeğini değiştirmez. Kişilik roleplay ilhamıdır; oyuncunun ne hissedeceğini veya yapacağını zorunlu kılmaz. Kullanıcının söylemediği travma, bağlayıcı geçmiş ilişki veya mekanik yetenek otomatik karaktere eklenmez.

**Portre:** Onaylı görünüşün belirli sürümüne bağlanır; kişilik ifade/duruşa öneri verebilir. İlk kabul edilen portre referans olarak korunur. “Portreyi güncelle” açık eylemdir; her tuş vuruşunda veya her tur ücretli yeniden üretim yoktur. Eski görsel saklanır; kullanıcı yeni varyasyonu reddedebilir. Referans kullanmak yüz tutarlılığını destekler, kusursuz kimlik garantisi değildir. Görselin eklediği yara, silah, mücevher veya başka bir ayrıntı mekanik eşya/özellik oluşturmaz.

**Mekân:** Görsel kabul edilmiş ve oyuncuya açık konum/sahne bilgisiyle üretilir, konum ve kaynak sürümüne bağlı önbelleklenir. Her girişte yeniden yaratılmaz. Gece/yangın gibi yetkili değişim ayrı varyant olabilir. Resimde tesadüfen görünen pencere yeni mekanik çıkış, mesafe veya taktik görüş kanıtı değildir. Oyuncu onu sorarsa §3.3'ün tutarlılık sınırı uygulanır; gizli dünya bilgisi görsel prompt'uyla sızdırılmaz.

**Ses:** İlk öneri, kullanım hakkı doğrulanmış yağmur/rüzgâr/kalabalık/ateş gibi hazır katmanlardır. Sahne/hava gerçek veriye dayanır; bilinmeyen hava sesle kesinleştirilmez. Genel mute ve ayrı ses düzeyleri bulunur; başlangıç kullanıcı eylemiyle olur, metin deneyimi ses olmadan eksiksizdir. Her tur üretken ses çağrısı ilk çözüm değildir. Dosya/lisans/atıf/dağıtım koşulları doğrulanmadan varlık projeye alınmaz.

**İkinci AI:** Metin DM'yi değiştirmek yerine ayrı medya sağlayıcı arayüzü ve kalıcı iş kuyruğu önerilir. Ağır görsel işlem DM turunu veya karakter kaydını bekletmez. Beklerken son kabul edilmiş görsel/yer tutucu kullanılır. Yerel model GPU/bellek ve bakım maliyeti, bulut modeli ağ/veri aktarımı/kota/maliyet getirir; donanım ve bütçe görülmeden seçim veya hız sözü verilmez. Resmî Diffusers IP-Adapter ve referanslı barındırılmış düzenleme API'leri araştırma adaylarıdır, seçilmiş sağlayıcı değildir. [S11]

**İş güvenliği:** İstek kimliği, varlık/kaynak revizyonu ve sağlayıcı iş kimliği tutulur. Çift tıklama yeni ücretli iş yaratmaz; belirsiz timeout'ta önce mevcut iş uzlaştırılır. Yerel idempotency uzak sağlayıcının garantisi değildir. İptal, uzak işi veya maliyeti gerçekten iptal edebildiği ölçüde anlatılır. İptal edilmiş/eski revizyona ait geç sonuç aktif portreyi değiştiremez. Gizli API anahtarları istemciye konmaz. Sağlayıcıya veri gönderimi ve ücretli kullanım kapsamı açıkça yetkilendirilmeden başlatılmaz.

**Bütçe ayrımı:** Bunlar oyuncunun mekanik hamlesinden ayrı, açık kullanıcı başlatmalı medya/karakter taslak işlemleridir; kendi kota, tekrar ve maliyet sınırı gerekir. Oyun turundaki yaratıcı metin/DM işi “medya” adıyla §7'deki iki çağrı hesabından çıkarılmaz. Ayrı model kullanımı gizli üçüncü DM çağrısı değildir.

**Yerleşim ve kabul:** LR04 veya açık küçük ara UI dilimi adayı. Önce metin taslakları, sonra portre/mekân, sonra katmanlı ses; üretken ses ihtiyaç kanıtıyla değerlendirilebilir. LR00 önkoşulu değildir. İlgili dilim açılırsa taslak onayı, alan kilidi, referans sürekliliği, eski revizyon/geç sonuç, kota/iptal, metin fallback ve hak kontrolü kabul kapsamına girer. Yeni medya özellikleriyle bütün oyun bitti denmez.

## 11. Living Realms yol haritası ve bağımlılık sözleşmesi

### 11.1 LR ürün sırasıdır; F teknik güvenceyi taşır

LR00–LR05 oyuncuya ulaşan aşamaları anlatır. F01–F15 geçmiş teknik sözleşmedeki güvenilirlik ve içerik alanlarını tanımlar. Yeni metin bunları yalnız indekslemiyor: yaratıcı DM yetkisini açıyor, dar LR00 yaratımını tanımlıyor ve UI önceliğini güncelliyor. Aynı zamanda eski güvenlik ve kabul borçlarını isim değiştirerek yok etmiyor.

**Döngüyü önleyen açık kapsam değişikliği — OH1-SCOPE-01:** LR00-P3'teki dar kampanya-yerel üretim pilotu, yeni sözleşme ve o paketin uygulama yetkisiyle yapılabilir; bütün F05/F06/F07-EXPAND veya LR01/LR02'nin tamamlanmasını beklemez. Bu pilot F06/F07'nin tamamlandığı anlamına gelmez. Dar pilotta kimlik, kişisel amaç, sahne ayrıntısı, bilgi aktarımı ve ödülsüz yerel mesele sınanır; tam görev yaşam döngüsü, otomatik ödül, sayısal ilişki sistemi, söylenti ağı ve geniş yolculuk açılmaz. Böylece LR00'ın deneyim kapısı ilerideki fazlara bağımlı yapılarak imkânsızlaştırılmaz.

Pilot için gerekli korumalar yine vardır: yetkili mekanik çözüm, F03 kapsamında ilgili alan/kalıcılık/replay güvencesi, F04'ün niyet ve anlatı güvenliği, yerel kabul zarfı ve oyuncu bilgi sınırı. Bu korumalar pilot içinde dar biçimde uygulanır. Aynı davranışın ilerideki F06/F07 kabulünde yeniden kullanılabilmesi için kanıt kapsamı açık tutulur; bugün bütün ileri faz PASS ilan edilmez.

### 11.2 Kritik kapılar neden var ve nasıl korunuyor?

| Kapı | Koruduğu ihtiyaç | v1.0 yaklaşımı |
|---|---|---|
| F02'nin owner envanteri → F03 başlangıcı; özgül F02-AC-005 | Yanlış katmanda state/alan değişikliği yapmamak | Koru. Bütün F02'nin gereksiz toplu bitişine genişletme |
| F03-P01 manifest → F10-BASE başlangıcı | Karakter alanlarının tek anlamı | Koru. Başlamak için full F03 isteme |
| F10-BASE çıkışı + F03-AC-003/005 | Karakter/kaynak doğruluğu ve tekrar/kalıcılık güvencesi | Koru; yalnız “sekiz BASE testi geçti” yeterli sayma |
| Full F03 ve F10-BASE exit → F04 başlangıcı | Anlatının yanlış veya geçici state'i gerçek diye sunmaması | İlk geçişte koru. Yaratıcı planlama/read-only çalışma beklemek zorunda değil; uygulama kapısı ayrı |
| F04 exit → F05; F05 exit → F06 | Hatalı niyet/anlatı üzerine hareket ve sosyal durum yığmamak | Geniş fazlarda koru; dar LR00 pilotu OH1-SCOPE-01 istisnasıyla açıkça ayrılır |
| F06 → F07-OWN; OWN + yetkili içerik → EXPAND | Boş katalogda dürüstlük, sonra gerçek görev/ödül yetkisi | Koru. LR00 yerel mesele pilotu görev/ödül kataloğu değildir |
| Full F03 + F10-BASE/F04 exit → F08 | Savaş state'i ve anlatısının güvenilir temeli | Koru. F07 yeni önkoşul yapılmaz |
| F11-BASE için F05 + full F03 | Oda/rota/kimlik ve kalıcılık | Koru. LR00 sahne ayrıntısı tam dungeon aktivasyonu değildir |
| F12 paket bazlı girişler | Sunumun gösterdiği verinin gerçekten var olması | Koru: shell için full F03, sheet BASE, hava F05, combat F08. Bütün F12'nin tamamını her küçük UI işine kapı yapma |
| GOLD-SYSTEM → GOLD-EXPERIENCE + anlamlı yetkili içerik | Düzgün görünen ama kaydetmeyen oyun veya yalnız boş ret ile sahte kabulü önlemek | Koru. Dar anlamlı içerik artık pilotla sağlanabilir; ilerideki bütün LR'leri gerektirme |
| F13 admission ve şehir başına aktivasyon | Kaynaklı setting genişlemesi ve ayrı risk | Koru. Genel yaratıcı DM onayı şehir açma izni değildir |
| F15'in özgül girişleri | Sesin aynı güvenilir eylem yoluna bağlanması | Koru; F14 veya full F12 gibi yeni toplu kapılar ekleme |

Bu tabloda belirtilmeyen eski F AC'leri sessizce kaldırılmaz. İlk manifest her ilgili eski AC'yi **korundu / dar eşdeğer kanıtla karşılanacak / açık değişiklik gerekli / bu paketin dışında** diye işaretler. Çıkış manifesti çözülmemiş bir yükümlülüğü başka LR adına saklayamaz. Tam F fazı PASS yalnız kendi bütün koşullarıyla verilir. [S1, S2]

Daha sonra gereksiz kapı görülürse güvence ihtiyacını ve yerine konan eşdeğer kanıtı gösteren dar değişiklik yapılabilir. Sadeleştirme tercih edilir; her risk için yeni faz, yeni onay ve yeni gate üretmek hedef değildir. Eski bir sıra yalnız tarihsel olduğu için korunmaz, fakat kaldırılması da gerekçesiz olmaz.

### 11.3 LR00 Reforged — gerçekten oynanabilir yaratıcı temel

**Oyuncu sonucu:** Kendi cümlesiyle oynayabilir; sistem doğru kişi/nesneye yönelir; yeni bir şey gerçekten yaratılır ve hatırlanır; seçimleri sonuç doğurur; ekran bunu anlaşılır gösterir.

**İçeride:** Eski LR00'nun ilgili F01/F02/F03, erken F10-BASE ve F04 yükümlülükleri; canlı sorunların teşhisi; dar yaratıcı pilot; kalıcılık; temel viewport/doğru sonuç sunumu. **Dışarıda:** Tam FR haritası, tam görev/eşya/ticaret kataloğu, yeni şehir, tam savaş sistemi, bütün D&D 2024, multiplayer ve üretim yayını.

Aşağıdaki paketlerin AC'leri §13'teki OH1 adaylarıdır. Her paketin “bitti” kaydı yalnız kendi sınırını kapatır.

#### LR00-P0 — Kaynak ve canlı kanıtı sabitle

- **Amaç:** Hangi kaynak ve kampanya durumunda hangi hata yaşandı sorusunu yanıtlamak.
- **Sahip:** Entegrasyon sahibi + salt okunur teşhis sorumlusu. Mevcut API/log/owner envanteri kullanılır; yeni telemetry modülü peşinen atanmaz.
- **Girdi:** §15 snapshot'ı, mevcut Cursor teşhis sonucu, orijinal 14 görünür girdi ve erişilebilir runtime kayıtları.
- **Çıktı:** Kaynak/ortam/diff manifesti; her belirti için kanıt zinciri veya açık eksik; eski AC eşlemesi ve ilk değişiklik sınırı.
- **Bitti:** En azından değişiklik yapılacak davranış için başlangıç durumu, yanlış sınır ve gerçek yetki belirli; diğer açıklar dürüstçe ayrılmış. Canlı log yoksa kaynak hipotezi tek başına kök neden yapılmaz.
- **Dur:** Canlı save değişimi, eksik erişim, kaynak uyuşmazlığı veya başka yazar varsa; kanıtı koru. Erişilemeyen teşhis bütün bağımsız tasarım işini durdurmaz.

#### LR00-P1 — Niyet, referans ve hedefi tutarlı çöz

- **Amaç:** Kapı/teklif, pencere/han, soru/eylem, zamir/konu ayrımlarını genel sözleşmeyle düzeltmek.
- **Sahip:** Mevcut `game.py` yorumlama/dispatch sahibi; ilgili exploration/living-world ve dialogue owner'ları. Kesin değişecek dosyalar P0'da doğrulanır.
- **Giriş:** P0'ın bu akışa ait manifesti; ilgili F03/F04 teknik girişleri. Read-only ve test tasarımı önce yapılabilir.
- **Kapsam:** Tek giriş ve çoklu eylem politikası, hedef kimliği, son önerme/konu, açık belirsizlik, olumsuzlama/koşul.
- **AC:** OH1-01/02/03; orijinal örnekler yanında görülmemiş dil ve farklı state birleşimleri.
- **Bitti:** Yanlış niyetle state değişimi yok; makul belirsizlikte kısa netleştirme; desteklenen yaratıcı ifade tek cümleye özel kod istemiyor.
- **Dur:** Sorun yeni mekanik gerektiriyorsa kapsamı açık ayır; bir route düzeltmek için bütün motoru yeniden yazma.

#### LR00-P2 — Somut sonuç ve güvenilir anlatı

- **Amaç:** Gerçek hedefe ait keşfi ve sonucu anlaşılır sunmak; generic success ile yetinmemek.
- **Sahip:** Mevcut mekanik sonuç sahipleri, narration claim kontrolü ve F04 anlatı hattı.
- **Giriş:** P1'in ilgili niyet/hedef sınırı, mevcut karakter/kalıcılık kapıları.
- **Kapsam:** Makbuzdaki keşif/etki alanları; doğrulanmış anlatı; destekli başarısızlık/kısmi sonuç; fallback ve iki çağrı izi.
- **AC:** OH1-04/08; hem bilgi bulunan hem bulunmayan, hem başarı hem başarısızlık durumu.
- **Bitti:** Oyuncu ne olduğunu anlar; metin sonuçla çelişmez; anlatı hatası zar/kaynağı yinelemez.
- **Dur:** Keşfi destekleyen kayıt yoksa bulgu icat etme; gerekiyorsa P3 kabul yoluna bağla. Bu paket P3'ün tamamını beklemeden mevcut yetkili bilgiyle test edilebilir.

#### LR00-P3 — Yaratıcı ve kalıcı küçük kampanya pilotu

- **Amaç:** Yeni kampanya-yerel kişi/amaç/ayrıntı/meselenin gerçekten yaratılıp kullanılabildiğini kanıtlamak.
- **Sahip:** Mevcut `living_world.py`, öneri doğrulama sınırı, `local_dialogue.py`, bilgi projeksiyonu ve narrative memory sahipleri; schema ihtiyacı kanıtlanırsa mevcut persistence sahibi.
- **Giriş:** OH1-SCOPE-01 onaylı kapsamı; ilgili P1/P2 arayüzleri ve persistence korumaları. F06/F07'nin tamamı giriş koşulu değildir.
- **Kapsam:** §3'teki dar yaratım zarfı; kampanyalar arası çeşitlilik; kampanya içi kimlik; bir kişinin bildiğinin diğerine aktarım sınırı; alternatif çözüm ve reddedilebilir mesele.
- **AC:** OH1-05/06/07/09; pozitif yaratım ve sonraki etkileşim zorunlu. Yalnız bütün yeni önerileri reddetmek PASS değildir.
- **Bitti:** Canlı modelle yeni kabul edilmiş içerik tekrar ziyaret/restart sonrası kullanılır; iki yaklaşım gerçek fark doğurur; gizli gerçek oyuncu tercihinden kaçmak için değiştirilmez.
- **Dur:** Quest ödülü, yeni şehir, mekanik ilişki veya geniş simülasyon gerekirse ayrı kapsam aç; pilotu bu fazlara döngüsel bağlama. İki çağrıda kalite çıkmıyorsa bütün denemelerle ölçüm raporu ver; gizli retry yapma.

#### LR00-P4 — Kalıcılık ve kurtarmayı uçtan uca doğrula

- **Amaç:** Yeni ve mevcut etkilerin bir kez, doğru kampanyaya kaydolması.
- **Sahip:** Mevcut API/SQLite, engine save ve ilgili world/event sahipleri.
- **Giriş:** P1–P3'ün test edilecek veri sözleşmeleri. Bu güvence paketi baştan paralel test tasarımı yapar; en sonda eklenen yama değildir.
- **Kapsam:** Aynı istek, farklı payload, eşzamanlı revizyon, commit öncesi/sonrası crash, restart, eski save ve kampanya izolasyonu.
- **AC:** OH1-09/10; ilgili eski F03/BASE replay-resume-rollback alanları.
- **Bitti:** Etkiler tek, görünüm doğru, kabul edilmiş içerik kalıcı; eski kayıtlarda değişim açık ve testli. Migration yoksa bunun neden gerekmediği kaydedilir.
- **Dur:** Veri kaybı/çift tüketim görülürse canlı batch durur; kopya kanıt korunur. Kullanıcının olayını yeniden oynatıp düzeltme yapılmaz.

#### LR00-P5 — Oynanabilir ekran ve zar sunumu

- **Amaç:** Ana döngüyü erişilebilir viewport içinde anlaşılır kılmak.
- **Sahip:** Mevcut Experience UI/API projeksiyon sahipleri. Kesin bileşen adları güncel incelemeden sonra atanır.
- **Giriş:** Sonuç/alan sözleşmesi; shell/sheet kapsamının ilgili F12 kapıları. Statik tasarım çalışması önceden yapılabilir.
- **Kapsam:** Tek giriş, açılır detaylar, gerçek sonuç kartı, bekleme/hata, draft korunması, erişilebilir reflow; bağımsız küçük 3D zar alt teslimi.
- **AC:** OH1-11/12; oyun mantığı ile görsel doğruluk ayrı.
- **Bitti:** Normal/dar/zoom/klavye akışında hamle gönderilir ve sonuç okunur; otomatik kart eylemi yok. 3D alt teslim durumu ayrı görünür.
- **Dur:** UI değişikliği API doğruluğunu varsaymaya başlıyorsa dur; yeni state üretme. Performans sorunu varsa metin/2D yolunu koru ve 3D açık işi bildir.

#### LR00-P6 — Gerçek oyun kabulü ve çıkış kararı

- **Amaç:** Paketlerin bir arada oyuncunun istediği oyunu verip vermediğini değerlendirmek.
- **Sahip:** Entegrasyon sahibi kanıtı toplar; bağımsız inceleyen teknik zinciri kontrol eder; proje sahibi deneyimi kabul eder.
- **Giriş:** İlgili eski yükümlülüklerin manifesti, P1–P5'in gerekli çekirdek teslimleri, yetkili anlamlı pilot içeriği.
- **AC:** OH1-01–11'in çekirdek sonucu, OH1-12'nin gerçek durumu; GOLD-SYSTEM ve GOLD-EXPERIENCE ayrı.
- **Bitti:** Kanıtlı kapsam, kalan kusurlar ve insan değerlendirmesiyle açık karar. 3D görsel cilası gibi bağımsız açıklar LR00 çekirdek kararıyla karıştırılmaz.
- **Dur:** State bozulması, oyuncu iradesinin tersine işlem, bilgi sızıntısı veya yönlendirmesiz oynanamama varsa FAIL/BLOCKED; paket testlerini LR00 PASS'e yükseltme.

#### LR00-P7 — Bir tur geri alma için bağımsız güvenli dilim

- **Amaç:** §8.4'teki açık oyuncu undo eylemini bütün bağlı etkileriyle tutarlı kılmak.
- **Sahip:** Mevcut engine save/API SQLite, olay/RNG, narrative memory/player knowledge ve Experience sahipleri; tek entegrasyon sahibi. Yeni paralel persistence yoktur.
- **Giriş:** İlgili P4 işlem/kalıcılık sözleşmesi ve son teknik undo politikasının onayı. P0–P3 veya ilk UI tesliminin başlaması P7'yi beklemez.
- **Kapsam:** Tur sınırı, snapshot/branch veya eşdeğer mevcut kayıt yolu, sürümlü migration gerekiyorsa test kopyası, atomik restore, RNG/aynı hamle politikası, aktif context/provenance izolasyonu ve açık UI izi.
- **AC:** OH1-13; undo sonrası HP/konum/zaman/eşya/bilgi/olay/RNG karşılaştırması; aynı/different action, çift undo, in-flight, gecikmiş model/medya, restart, eski save ve migration/restore negatifleri.
- **Bitti:** Son tur tutarlı geri alınır, terkedilmiş dal kanıt olarak kalır ama aktif oyuna sızmaz; aynı işlem ikinci geri alma veya zar üretmez. Özellik durumu kendi satırında görünür.
- **Dur:** Güvenilir pre-turn kayıt yoksa desteklenmiyor; state tahmin edilmez. Veri kaybı veya dal sızıntısı varsa rollout durur. Kullanıcı kampanyasına migration ayrıca yetkilendirilir.
- **Faz konumu:** Bağımsız LR00 Reforged takip dilimi; ilk çekirdek LR00 paketlerinin önkoşulu değildir. P7 açıkken çekirdek kabul ayrı verilebilir, fakat bir tur geri alma isteği tamamlandı denmez.

### 11.4 LR01 — The Open Road

**Oyuncu sonucu:** Bildiği çıkıştan gider, durur, araştırır, geri döner; konum, zaman ve dünyadaki gelişme gerçekten değişir.

**Teknik temel:** F05 ve ilgili F12; yalnız ayrıca seçilirse küçük F11-BASE. **Giriş:** LR00 çekirdek ürün kabulü ve F05 için F04 çıkışı. Araştırma/planlama daha önce yapılabilir. **İçeride:** Yer/rota kimliği, kaynaklı süre, seyahat kesintisi, dönüş, görünür hava/zaman; pilot yaratımının izinli yerel alanlarda genişletilmesi. **Dışarıda:** Yeni resmî şehir aktivasyonu, uydurma mesafe, sınırsız harita, otomatik encounter/quest kataloğu.

**Paketler:** Rota/topoloji ve kalıcı yer; süre/kesinti/dönüş; bilinen dünyanın sunumu. **Sahip:** Mevcut exploration, living-world, campaign-time, lore authority ve Experience projeksiyonları; değişecek modül girişte doğrulanır. **Aday kabul:** Her test geçişinde konum/zaman doğru; yarıda kesilen yolculuk aynı anda varış sayılmaz; tekrar istek ikinci ilerleme yaratmaz; bilinmeyen hava dürüst görünür; restart aynı konum ve yol durumu verir. Serbest “geri dön” bir uydurma yön değildir.

**Oyuncu yolculuğu:** Tanıdığı yerden çıkar, yol üzerinde kendi seçimiyle durur, bir ayrıntıyı araştırır ve farklı karar verir. Dönünce aynı yer ve insanlar bulunur; yetkili olay değişimi varsa gerekçesi vardır. **Bitti:** Seçilen sınırlı rota kümesinde bu zincir ve insan okunurluğu kanıtlı. **Dur:** Süre/kaynak/lore yoksa kesinlik üretme; yeni şehir F13 sürecine ayrılır. Büyük harita özgürlük kanıtı sayılmaz.

### 11.5 LR02 — Living Souls

**Oyuncu sonucu:** İnsanlar kendi amaçları ve yaşadıkları üzerinden tepki verir; önceki sözler, reddetmeler ve karşı teklifler önem taşır.

**Teknik temel:** F06, mevcut günlük, F07-OWN; yetkili içerikle F07-EXPAND. **Giriş:** F05/F03 korumaları; geniş ürün için LR01'in ilgili hareket/süreklilik kabulü. LR00'ın dar NPC pilotu burada derinleşir, sıfırdan ayrı motor yapılmaz. **İçeride:** Kişiye özel uzun süreli bilgi, olaydan türeyen ilişki, gelişen amaçlar, kaynaklı söylenti/iddia, açık mesele ve görev yaşam döngüsü için yetkili içerik. **Dışarıda:** Otomatik evrensel söylenti ağı, yeni sayısal trust/faction, companion sistemi ve yetkisiz fail-forward mekaniği.

**Paketler:** NPC amaç/bilgi sürekliliği; olay/ilişki/günlük; OWN dürüstlüğü ve ayrı EXPAND içerik teslimi. **Sahip:** Mevcut local dialogue, living world, narrative memory, journal ve ilgili quest/ilişki owner'ları. **Aday kabul:** A'nın özel bilgisi B'ye geçmez; bilgi kaynağı tutulur; ilişki değişimi olaya bağlıdır; açık mesele tamamlanma koşullarıyla kapanır; ödül varsa yetkili owner tarafından bir kez uygulanır; restart ve kampanya izolasyonu korunur.

**Oyuncu yolculuğu:** Teklifi reddeder veya kılıç karşılığı pazarlık eder; karşı taraf kendi motivasyonu ve gerçek sahiplik/kural sınırında yanıt verir. Daha sonra dönüşte önceki konuşma anlam taşır. **Bitti:** En az bir yetkili sonuçlu sosyal/görev zinciri farklı girişimlerle oynanabilir; boş katalog düzgün reddediliyor diye EXPAND kapanmaz. **Dur:** Ödül/transaction yetkisi yoksa gerçek sonuç kapısı BLOCKED; para veya eşya anlatıyla yaratılmaz.

### 11.6 LR03 — Steel & Sorcery

**Oyuncu sonucu:** Yaratıcı taktik düşünebilir; kime ne yaptığını, ne harcadığını, riskini ve savaşın nasıl değiştiğini görür.

**Teknik temel:** F08; tanımlı F10-ADV; gerekirse seçili F09 loot veya F11-EXPAND. **Giriş:** F08 için full F03, F10-BASE ve F04 çıkışı; F07 zorunlu değildir. F10-ADV için BASE ve F08, ilgili kaynak/save kapsamı gerekir. **İçeride:** Meşru katılımcı, sıra/aksiyon ekonomisi, destekli saldırı/büyü/yaratıcı beceri yolu, hasar/koşul/yenilgi, açık savaş ve kaynak sunumu. **Dışarıda:** Bütün sınıflar, bütün D&D 2024, yeni grid/LOS motoru ve sınırsız özel büyü.

**Paketler:** İlk kaynaklı eksik combat dilimi; seçili ileri karakter/büyü; savaş sunumu/3D sonuç bütünlüğü. **Sahip:** Mevcut combat lifecycle, core resolution, action economy, spell ve karakter owner'ları. **Aday kabul:** Hedef, zar, HP, slot ve koşul birebir aynı; yasadışı eylem kaynak tüketmez; replay XP/loot çoğaltmaz; yenilgi ve restart tutarlı; yaratıcı yöntem destekli kurala bağlanır.

**Oyuncu yolculuğu:** Yetkili çatışmada yöntemi değiştirir, sonucu görüp sonraki kararını verir, ara verip aynı sıradan devam eder. **Bitti:** Seçilmiş kurallı combat kapsamı, negatifler ve insan okunurluğu kanıtlı. **Dur:** Kaynaksız kural veya yeni katalog gereksinimi kapsam değişikliğine ayrılır; görkemli zar eksik resolver'ı örtmez.

### 11.7 LR04 — A World Alive

**Oyuncu sonucu:** Keşif, konuşma, savaş, karakter ve atmosfer aynı dünyanın tutarlı parçaları gibi hissettirir.

**Teknik temel:** F12 entegrasyonu; mevcut yetkili zaman/hava/sahne görsel ve ses projeksiyonları. **Giriş:** Her sunum paketinin kendi veri kapısı; bütün LR'lerin toplu bitişiyle küçük görsel işleri kilitleme. **İçeride:** Nihai bilgi hiyerarşisi, atmosfer, portre/sahne, görsel geçişler, 3D zar kalite/performance, ses kapalı ve reduced-motion yolları. **Dışarıda:** Zaman/yolculuğu ilk kez bu fazda kurmak, her tur medya, sonsuz NPC simülasyonu, native mobil uygulama vaadi.

**Paketler:** Birleşik Experience; seçilmiş görsel kimlik/logo entegrasyonu; hareket/ses/3D erişilebilirliği ve performans. **Sahip:** Mevcut frontend/projeksiyon ve varlık sahipleri. **Aday kabul:** Geniş/dar/zoom görünümler aynı kritik gerçeği gösterir; metin okunur; animasyon atlanır; sırsız metadata; 3D yokken mekanik sonuç kaybolmaz. Sanat/asset hakları incelenir.

**Oyuncu yolculuğu:** Sıcak bir handan dışarı çıkar, konuşmadan çatışmaya geçer; nerede olduğunu ve sonraki girişimini kaybetmez. **Bitti:** Seçilmiş ekranlar gerçek veriyle görsel ve insan erişim incelemesinden geçer. **Dur:** Görsel tutarlılık için state uydurma veya sır açma gerekiyorsa veri sözleşmesine dön; dekor oyunu bloke etmesin.

### 11.8 LR05 — Beyond the Horizon

**Oyuncu sonucu:** İsterse konuşarak oynar; ayrı geliştirme sonrasında yetkili kişilerle aynı kampanyayı güvenle paylaşabilir.

**Önerilen sıra:** İsteğe bağlı ses, sonra ayrı multiplayer tasarımı. **Teknik temel:** Ses için F15. Giriş; owner onaylı Phase 8 Expansion kapanışı, F01/F03/F04 PASS, F12-P01/P04 manifestleri ve ayrı izin. Bütün F12 veya F14 yeni önkoşul yapılmaz. **İçeride:** Sesin metne çevrilmesi, isim düzeltme, niyet onayı, aynı resolver; multiplayer için ayrı üyelik, turn ownership, eşzamanlılık ve reconnect sözleşmesi. **Dışarıda:** Arka plan mikrofonu, otomatik hamle, erken topluluk dünyaları, sürekli video ve Phase 9'un otomatik açılması.

**Sahip:** Mevcut eylem/API/kalıcılık sahipleri; ses ve multiplayer adapter sahipleri gerçek tasarımda atanır, burada varmış gibi gösterilmez. **Aday kabul:** Yanlış duyulan isim eylemden önce düzeltilir; yalnız onaylı metin işlenir; tekrar onay ikinci hamle değildir; metin yolu açık kalır. Multiplayer kabulü ayrı plan ister; başka kampanyaya sızıntı ve yetkisiz üyelik negatifleri zorunludur.

**Oyuncu yolculuğu:** Konuşur, metni görür/düzeltir, gönderir; sonuç yazılı girişle aynı güvenceye sahiptir. **Bitti:** Önce sesin sınırlı kapsamı doğrulanır; multiplayer bitti denmez. **Dur:** Mikrofon/veri saklama/ağ/çağrı maliyeti yetkisi eksikse bağımlı adım durur; çekirdeğin sorunları yeni kanala taşınmaz.

## 12. Araştırmadan alınan ve alınmayan kararlar

Yirmi araştırma başlığı yirmi bağımsız doğrudan rakip demek değildir. Friends & Fables/Fables.gg aynıdır; LoreKeeper başlığında ayrı ürünler, Grim başlığında iki oyun vardır. İki özgün 36/41 sayfalık PDF farklıdır; sayıları ve kabul önerileri tek tarihsel sözleşme gibi birleştirilmez. Güncel araştırma resmî belge/ekranları inceler; canlı hesapta karşılaştırmalı oyun testi yapılmış değildir. [S5, S6]

- **Al:** Fables'tan kişiye bağlı hafıza ve görünür sonuç; Auferet'ten dünya/kural ayrımı ve denetlenebilir kayıt; Old Greg's Tavern'den sorun/söylenti temelli açık yaklaşım ve sonlu hikâye yayları; AI Dungeon/NovelAI çizgisinden seçici bağlamı inceleyebilme; AI Realm'den kişiye bağlı görünüm.
- **Uyarla:** AI Game Master/Questner'deki doğaçlama özgürlüğü mekanik doğrulukla; Questsmith'teki esnek kilometre taşlarını gerçekleşmiş olayla; Fallen London'daki koşullu sonuçları önceden yazılmış tek çözüm zinciri olmadan.
- **Alma:** Anlatıdan doğrudan state çıkarıp mekanik gerçek sayma; kusursuz hafıza pazarlaması; evrensel RPG platformunu erken kurma; her tur çoklu ajan/medya; oyuncunun kararını onun adına anlatma.
- **Araştırma olarak tut:** Daha fazla model çağrısı, araçlı yaratıcı hazırlık, kapsamlı retcon ve arka plan NPC simülasyonu. Başka ürünün vaat etmesi yerel 8B modelde kalite/latency kanıtı değildir.

Rakipler ürün kararını gerekçelendirir; UNWRITTEN'in kabul koşullarını geçmez. Özellikle Fables'ın 2026'da planlama adımını performans gerekçesiyle kaldırması, sürekli planlayıcıyı varsayılan çözüm saymamak için uyarıdır. Hafıza benchmark'ında doğru olguları baştan sağlamak, oyundan olguyu doğru edinmeyi ölçmez. [S6]

### 12.1 Son kullanıcı kararları: kabul edilen ürün yönleri

16 Ekim 19:40'taki kullanıcı yanıtıyla aşağıdaki beş öneri ürün yönü olarak kabul edildi. Teknik tasarım, uygulama ve son sözleşme onayı bundan ayrıdır; bunlar kendiliğinden yeni zorunlu LR00 giriş kapıları oluşturmaz:

- **Kısa, isteğe bağlı session zero:** Ton, zorluk, keşif/savaş/sosyal ağırlık ve içerik tercihleri. Atlanabilir. Zorluk seçimi D&D sonuçlarını gizlice değiştirmez; mekanik etkisi varsa açık sözleşme gerekir.
- **Oyuncunun seçtiği geçmiş bağları:** Kullanıcının onayladığı kişiler/yerler/bağlardan kişisel hikâye kancaları. Seçilmemiş geçmiş veya zorunlu duygu icat edilmez.
- **Olay/zaman tetiklemeli NPC amaçları:** Sürekli her NPC için model çalıştırmak yerine ilgili olay veya yetkili zaman ilerlemesiyle amaçları değerlendirme. Mevcut §5 yaklaşımının kapsamı LR02'de derinleşir; otomasyon ayrıntısı henüz uygulama onayı değildir.
- **Yanlış anlaşılmayı düzeltme ve bir tur geri alma:** Kullanıcı dördüncü öneriye geri alma isteğini ve ardından küçük bir ↶ düğmesi tercihini ekledi. Düzeltme otomatik state değişikliği değildir; §8.4 ve LR00-P7 açık oyuncu eylemi, dal ve zar politikasını önerir.
- **Seçici yaratıcı alan kilitleri:** Yüz/görünüş/kişilik gibi kullanıcının sevdiği özellikler korunarak yalnız seçilen alanlar yeniden üretilir. §10.6 bu yönün teknik aday akışını tanımlar; çalışır özellik iddiası değildir.

Session zero ve geçmiş bağları karakter/kampanya başlangıç diliminde; NPC tetikleri LR02'de; seçici kilitler ilgili karakter/medya diliminde ayrıntılandırılır. Dar undo P7'de bağımsız yürür. Kullanıcıdan bu beş yönü yeniden seçmesi istenmez; bütçe, sağlayıcı, mekanik etkiler ve uygulama sınırları gerektiğinde somutlaştırılır.

### 12.2 Kabul edilen dört kullanım kolaylığı

16 Ekim 19:44'te kullanıcı aşağıdaki dört yönün de eklenmesini istedi. Bunlar mevcut bilgi, günlük ve UI sahiplerini kullanır; aynı yeteneği ikinci bir motor veya yeni faz olarak tekrar kurmaz. Teknik uygulama son sözleşme/paket yetkisini bekler; dördü birden ilk LR00 çıkışının yeni önkoşulu değildir.

- **“Nerede kalmıştık?” dönüş özeti:** Mevcut kayıt/knowledge/narrative-memory yolundan son konum, son kabul edilmiş gelişme ve ilgili açık meseleyi kısa sunar. Model özetliyorsa yalnız kaynaklı, aktif dala ait ve oyuncunun bildiği olgular kullanılır; kaynak referansları tutulur. Yeni geçmiş, amaç veya keşif icat edilmez; geri alınmış dal etkin özete sızmaz. Yerleşim: P4/P5'in resume yüzeyine dar ek; geniş günlük devamı LR02. Mevcut kanıtlı veriden deterministik özet ilk uygulanabilir varsayılandır.
- **Anlatıdaki kişi/yer adına tıklama:** Oyuncunun zaten bildiği bilgi kartını açar. Adlar kalıcı kimliklere bağlanır; aynı adlı kişiler karışmaz. Tıklama konuşma, seyahat veya başka oyun eylemi başlatmaz; gizli metadata göstermez. Yerleşim: mevcut P5 bilgi panelinin küçük sunum eki, görsel bütünlük LR04. Ayrı bilgi sistemi kurulmaz.
- **Küçük oyun dışı DM yardımı:** §10.2'deki ikincil yardımcı yüzeyi güçlendirir; zorunlu Say/Do/Ask modu olmaz. Zaman, kaynak ve oyun state'i değişmez; sır açılmaz. Model gerekirse oyuncunun açıkça başlattığı ayrı read-only istek kimliği, çağrı/kota kaydı ve bütçesi olur; önerilen ilk sınır bir model çağrısı ve otomatik retry olmamasıdır. Bu hat, oyun turunun reddedilen anlatısını gizlice üçüncü çağrıyla onarmak için kullanılamaz. Yerleşim: P5'in mevcut yardımcı yüzeyi; ilgili güvenlik/çağrı sınırlarıyla küçük bağımsız teslim.
- **Verilen sözler ve açık meseleler günlüğü:** Kabul edilmiş konuşma/olaylardan oyuncuya açık taahhütleri ve çözülmemiş konuları gösterir; DM yalnız ilgili bağlamda hatırlatır, her tur bildirim yağdırmaz. Söylenti veya teklif otomatik görev kabulü, ödül ya da oyuncu taahhüdü değildir. Yerleşim: P3'ün dar açık mesele verisini kullanarak LR02'nin mevcut journal/quest-ownership dilimi; yeni paralel journal yoktur.

Bu yönler için yeniden ürün tercihi sorulmaz. Her ekin bitti sayılması, kendi kaynak/kimlik/bilgi sınırı ve gerçek UI davranışının doğrulanmasını gerektirir. İlk çekirdek teslimde açık kalanlar dürüstçe ayrı gösterilir; bütün kolaylıklar uygulanmış denmez.

## 13. Kabul ve kanıt: OH1 aday matrisi

### 13.1 Tek PASS yok

**Paket PASS**, **teknik çıkış PASS**, **F faz PASS**, **LR ürün kabulü**, **GOLD-SYSTEM**, **GOLD-EXPERIENCE** ve **release izni** ayrı kararlar olarak kalır. Çalıştırılmayan NOT TESTED; dış koşulla yapılamayan BLOCKED; gözlenen başarısızlık FAIL; eski sürümdeki kanıt HISTORICAL'dır. Exit code 0, insanın anlatıyı kabul ettiği anlamına gelmez.

Yeni kabul kimlikleri bu sözleşmeye aittir; eski F04-AC-006/007 veya GOLD borçlarını yeniden adlandırarak kapatmaz. Eski AC ile aynı güvenceyi kanıtlayan tek test uygun kapsamla iki satıra referans olabilir; gereksiz aynı testi sırf iki ad var diye çalıştırmak gerekmez. Kaynak/fixture/model/çevre değişmişse etkilenen kanıt güncellenir; ilgisiz değişiklik bütün tarihsel kanıtı yok etmez ama “current” kapsamı açık yazılır.

| Aday kimlik | Kabul edilen davranış | Gerekli kanıt ve başarısızlık örneği |
|---|---|---|
| OH1-01 Niyet/ hedef | Açık eylem doğru hedefe gider; koşul, alıntı ve olumsuzlama korunur | Orijinal örnek + görülmemiş ifade/state; kapı çalarken teklif kabulü bloklayıcı |
| OH1-02 Referans | “Neden/diğeri/orası” doğru kişi ve önermeye bağlanır; gerçek belirsizlik netleştirilir | Konu değişimi, iki benzer kişi, araya giren olay ve restart; yanlış kişiye hafıza yazımı bloklayıcı |
| OH1-03 Birleşik giriş | Sıra/koşul korunur; bağımsız önemli eylemler sessiz yürütülmez | Aynı alt adımlar farklı sıra ve olumsuzlukla; ikinci cümleyi kaybetme veya gizli çoklu tur başarısız |
| OH1-04 Somut sonuç | İnceleme sonucu hedefe bağlı ve kullanılabilir; yokluk iddiası ölçülü | Başarı/başarısızlık, bulgu var/yok, görüş sınırı; generic success tek başına yeterli değil |
| OH1-05 Pozitif yaratım | Gerçek model yeni izinli yerel içerik üretir, kabul edilir ve sonraki etkileşimde kullanılır | Oluşum→kayıt→referans→etkileşim zinciri; bütün yaratımı reddeden sistem geçmez |
| OH1-06 Çeşitlilik/kimlik | Yeni kampanyalarda yalnız ad değil amaç/ilişki/gerilim çeşitlenir; aynı kampanya sabittir | Ayrı temiz kampanyaların birden çok canlı çalışması; aynı kampanyada dönüş/restart; yaratımı sürekli değiştirmek başarısız |
| OH1-07 Bilgi/agency | NPC kendi bilgisiyle yanıt verir; oyuncu reddedebilir/alternatif seçebilir | A/B bilgi asimetrisi, bilgi aktarma, ret ve farklı yaklaşım; gizli spoiler veya zorunlu kabul bloklayıcı |
| OH1-08 Anlatı/bütçe | Metin makbuzla uyumlu; toplam çağrı sayımı açık; red sonrası yeni çağrı yok | Gerçek model izi, timeout/red/fallback; gizli retry veya uydurma sonuç bloklayıcı |
| OH1-09 Kalıcılık | Yeni ve eski kimlik/olgu/keşif aynı kalır; kampanyalar ayrıdır | Save/reload ve gerçek süreç restart, eski save; yeni örneklenmiş kişi veya sızıntı bloklayıcı |
| OH1-10 Tek etki/kurtarma | Tek istek tek mekanik etki; revizyon ve crash güvenli | Çift istek, farklı payload, commit sınırı, geç yanıt; çift harcama/zar bloklayıcı |
| OH1-11 Oynanabilir UI | Tek giriş ve kritik durum erişilir; uzun metin kaybolmaz; kart yalnız taslak doldurur | Gerçek tarayıcı geniş/dar/zoom/klavye/hata akışı; kırpılan Gönder veya otomatik kart eylemi başarısız |
| OH1-12 3D sunum | Kaydedilmiş zarın isteğe bağlı 3D gösterimi; metin/fallback her zaman çalışır | Skip/reduced-motion/WebGL hata/replay/eski toplam-only save; istemcide yeni oyun zarı bloklayıcı |
| OH1-13 Bir tur geri alma | Son tamamlanmış turun bağlı etkileri atomik geri alınır; eski dal aktif contextten ayrılır | Snapshot/restore/migration/RNG/provenance/UI, çift istek ve geç yanıt; eksik restore veya dal sızıntısı bloklayıcı |

OH1-13 yalnız bağımsız P7 undo diliminin kabulüdür; ilk çekirdek LR00 paketlerini bloke etmez. OH1-12 bağımsız sunum alt teslimidir; §10.3'teki faz ayrımı geçerlidir. OH1-05/06/07'nin dar LR00 kapsamı daha geniş LR02 dünyasını kabul etmiş sayılmaz. Kabul matrisi kapsamı sınırsız büyütmez; test sayısı veya yeni özellik üretmek için açık çek değildir.

### 13.2 Üç kanıt katmanı

1. **Deterministik:** Doğrudan öneri/makbuz/fixture ile owner ve state kuralları. Zorlanmış zarlar burada yararlıdır; doğal oynanış diye gösterilmez.
2. **Canlı model:** Gerçek kurulu Ollama modeli, gerçek context ve validation hattı. Input/output, öneri, kabul/red, süre, token ve çağrı sayısı tutulur; gizli düşünce kaydı gerekmez.
3. **İnsan oyunu:** Kullanıcıya “şu komutu yazarsan geçiyor” koçluğu yapılmadan serbest küçük oturum. Oyuncu kendi yaklaşımını, reddi, geri dönüşü ve ayrıntı merakını seçer. Yapay corpus veya araştırmacı puanı bunun yerine geçmez.

GOLD-SYSTEM browser→API→Python→SQLite sürekliliği, alan eşitliği, kayıt/yeniden açma ve makbuz izini gerektirir. GOLD-EXPERIENCE anlamlı seçim, anlaşılır risk, gerçek sonuç, karakter inandırıcılığı ve devam etme isteği üzerine insan kararıdır. Pasif bakış, lore sorusu veya boş katalog reddi tek başına bu kapıyı geçmez. Yeni yaratıcı pilot yetkili anlamlı içerik sağlar; başarılı oyun sonucu garanti etmez.

### 13.3 Örnekler, varyasyon ve bütçe

Özgün hatalar regresyon setine alınır. Uygulayıcının görmediği dil ve bazı farklı başlangıç state'leri ayrı tutulur: kilitli/açık, görünür/gizli, kişi burada/yok, keşfedildi/yeni, aynı ad/başka kimlik. Bir yeni ifade onarımda kullanıldıktan sonra regresyon setine taşınır; görülmemiş set yenilenir. Testin beklenen anlam zarfı sonuç görüldükten sonra değiştirilmez.

Pozitif yaratım birkaç farklı canlı kampanyada değerlendirilir; tek hoş yanıt çeşitlilik kanıtı değildir. Tam adların farklı çıkması da yeterli değildir. Öte yandan küçük örnekten güvenilirlik yüzdesi çıkarılmaz. Her başarısız deneme ve tekrar rapora girer; en güzel örneği seçip önceki başarısızlıkları gizlemek yoktur. Kontrollü seed/snapshot karşılaştırması mekanik farkı anlamak için kullanılır; doğal yaratıcı başarı kanıtı diye etiketlenmez.

Araştırmadaki 24 probe, iki altı-turluk bölüm veya 15–20 turluk oturum gibi sayılar olası planlama örnekleriydi; bu metin onları zorunlu yeni gate yapmaz. İlk smoke süresi ve kapsama göre sınırlı test manifesti hazırlanır. Başarı/failure, yeni/eskimiş bağlam, ret/alternatif, restart ve bilgi asimetrisi kapsanır. Uzun kampanya iddiası yapılacaksa ayrıca uzun ve değişken bağlam kanıtı gerekir; LR00 kısa kesit bunu sağlamış sayılmaz.

Batch sınırı süre/maliyet/kapsam bakımından önceden açıktır. State bozulması veya yetkisiz oyuncu eylemi varsa canlı çalışma durur, iz korunur; kalanlar NOT TESTED olur. Aynı kusuru bilerek tekrar tekrar oynatıp bütçe harcamak yerine ilk kanıtlı sınır onarılır. Teste devam izni ayrı sınırsız canlı oyun izni değildir.

### 13.4 Tek teslim kaydı

Her teslim: sözleşme sürümü; paket/AC kapsamı; commit ve ilgili dosya hash/diff; model/runtime kimliği; fixture/save sürümü; tam komut ve seçiciler; katman bazlı sonuçlar; açık kusurlar; fallback ve çağrı verisi; insan inceleme kararı. Kaynakta davranış görülmesi, testte çalışması, canlı modelde gerçekleşmesi ve kullanıcı tarafından kabulü ayrı sütunlardır.

Başarısızlığın ilk kanıtlı sınırı belirtilir: niyet, context, hedef/yetenek, kural/yetki, bilgi, yaratım, anlatı, kalıcılık, UI/deneyim veya altyapı. Birden fazla etki olabilir; kanıt yoksa kök neden “bilinmiyor” kalır. Kritik ihlal yok ama dil hâlâ tekrarlıysa güvenli sistem ile iyi oyun arasındaki fark açıkça raporlanır; otomatik sayı toplamıyla kapatılmaz.

## 14. Ajanlar, Git ve entegrasyon düzeni

### 14.1 Bir entegrasyon sahibi

Her aktif paketin bir entegrasyon sahibi ve sınırlı dosya sahipliği vardır. Araştırma, test, UI ve model değerlendirmesi bağımsızsa paralel yürür. Aynı fiziksel repoda Cursor ve Antigravity ayrı bilgisayar gibi davranmaz; aynı çalışma ağacına yazabilirler. `game.py`, ortak schema ve save dosyalarında tek yazarlı devir sırası uygulanır.

Görev kaydı kısa olmalıdır: amaç; başlangıç kaynağı; izinli dosya/iş; bağımlılık; yapılmayacaklar; test; teslim; durma koşulu. “Oyunu düzelt” veya “tüm testleri yeşile çevir” sınırsız görev değildir. Bir ajan diğerinin yaptığı uzun dış işlemi tekrar etmeden mevcut sonucu kontrol eder.

### 14.2 Branch ve checkpoint disiplini

`dev/ai-dnd` entegrasyon hattıdır; `main` stabil promotion için ayrı açık yetki gerektirir. Aday kalıcı düzen: paket için task branch; PR/diff incelemesi; yetkili entegrasyon sahibinin kontrollü birleştirmesi; kaynak ve test manifesti. Dev üzerinde farklı ajanların bağımsız checkpoint/commit düzenlemesi yapılmaz. Mevcut Replit otomatik checkpoint davranışı göz ardı edilmez; tasarlanan düzenin gerçekten uygulanabildiği ayrıca doğrulanır.

**Kalıcı Replit görev branch/workflow kurulumu henüz tamamlanmış değildir.** Önceki girişim iptal edildi; bu sözleşme onu çalışıyor gibi kabul etmez. Kurulum yapılacaksa mevcut branch/checkpoint davranışı gözlenir, backup ve geri dönüş planı kurulur, bounded deneme yapılır. Kullanıcı işi iptal ettiyse eski talimatla devam edilmez; yeni kapsam izni gerekir.

Replit checkpoint'i aynı kaynak içeriğine yeni commit ekleyebilir. Bu nedenle her ortamı sonsuza dek aynı HEAD'e zorlamak yanlış eşitlik ölçütüdür. Kaynak kimliği; ilgili commit ancestry, ağaç/dosya manifesti, dirty diff, env/config ve çalıştırılan artifact ile değerlendirilir. Farklı SHA'nın önemsiz olduğu varsayılmaz; gerçek kod/config farkı varsa önce incelenir. Aynı SHA da aynı runtime/model/veritabanını kanıtlamaz.

### 14.3 Güvenli Git ve guard

Başlamadan status, branch, remote ve yerel değişiklikler görülür. Kullanıcı çalışması silinmez; eski dirty worktree, untracked dosyalar ve backup ref'leri korunur. Reset/clean/force push veya büyük sync önerisi “hızlı çözüm” diye kendiliğinden uygulanmaz. İzinli geri dönüşün kapsamı ve kaybedebileceği şeyler açık olur.

Guard/hook hatası önce sınıflandırılır: gerçek kapsam ihlali mi, ortam problemi mi, eski yanlış kural mı? Global bypass, bütün guard'ları kapatma veya blanket allow varsayılan çözüm değildir. Gerekli dar istisna varsa tam komut/dosya/süre/risk/yerine kanıt ve onay belirtilir. Başarısız kontrolü atlamak onu PASS yapmaz. Kurallar/AGENTS güncellemesi de kapsamlı çalışma kararıdır; checkpoint döngüsünden kaçmak için sessizce değiştirilmez.

Commit/push/merge/deploy izinleri görevin açık sınırına göre ele alınır. Önceden verilmiş geçerli yetki tekrar sorulmaz; fakat read-only araştırma kod, kod görevi production migration veya deployment izni sayılamaz. Kullanıcının canlı kampanyasında teşhis sırasında state onarma, zar rerun veya event silme yoktur.

## 15. Gerçek mevcut durum: 16 Ekim devir snapshot'ı

Bu bölüm tarihli durumdur; ilk uygulama görevinde yeniden doğrulanır. Yeni belge hiçbir ortamda komut çalıştırmış veya testi yeniden koşmuş değildir.

| Konu | Bilinen durum | Söylenmeyecek yanlış sonuç |
|---|---|---|
| GitHub dev | İnceleme baseline'ı `476ba9bd148da18e24cb5dab020c116ba4907445` | Bugün her çalışan process kesin bu kaynakta |
| PR #5 | Door break/unlock kapsamı merge edildi; merge `231b6cd0fa1530a44017cc5d2897cdcf587956ba` | Knock, pencere, bütün LR00 düzeldi |
| PR #6 | Clerk return URL düzeltmesi merge edildi; baseline bu merge | Bütün auth/browser deneyimi kabul edildi |
| Cursor/Antigravity | Aynı fiziksel repo; bu baseline'a eşitlik daha önce doğrulandı | İki bağımsız güvenli yazma alanı |
| Replit sync | İşlem anında aynı baseline'a kaynak eşitleme yapıldı; eski çalışma korundu | Otomatik checkpoint sonrası sonsuza dek aynı SHA veya kurulmuş kalıcı workflow |
| Replit backup | 30 yerel commit korunarak `backup/dev-ai-dnd-pre-sync-0cf2df84-20261016T1811Z` → `c1c83f6518e0d0d05b733c6f51dbb55f6e7cb38c`; ayrıca dört dosya hash'li korundu, eski b7 dirty worktree saklandı | Backup ref'i bütün dört dosyayı da mutlaka içeriyor veya geri yükleme bu belgede yeniden test edildi |
| Kalıcı görev düzeni | Kurulum girişimi iptal; tamamlandığı doğrulanmadı | Replit task branch/guard düzeni hazır |
| Test raporları | Cursor UI auth için merge sonrası 12 geçiş, typecheck 0 raporu; door için merge sonrası 88 geçiş raporu | Bu belge test koştu veya bütün paketler current PASS |
| LR00 / F04 / GOLD | LR00 tam kabul yok; F04 anlatı ve GOLD-EXPERIENCE açık; sınırlı fallback insan kabulleri geri çekildi | Merge veya deterministik test otomatik deneyim kabulü |
| Eski 74/74, 41/41, 563/563 | Tarihsel/kanıt kapsamı sınırlı; kaynak kayıtları kendi statüsünde | Yeni kabul sayacı |

Kaynak PR'ler ve kabul kayıtları [S1, S2, S4]. Replit/masaüstü sync ayrıntıları bu konuşmanın operasyon devir raporudur; kaynak araştırmasının bağımsız yeni runtime ölçümü değildir. Dört dosyanın tam manifesti veya restore komutu burada yeniden oluşturulmaz; gerektiğinde özgün koruma kaydı alınır.

### 15.1 Açık canlı teşhis

Son aktarılan transkriptte toplam **14 görünür kullanıcı girdisi** vardır: 2 eski + 12 yeni. Devam koşusu için verilen üst sınır **5 yeni istek** idi; paylaşılan 12 yeni görünür girdi bu sınırın aşılmış göründüğünü gösterir. Bu sayı, beş backend bütçe hatası yaşandığı veya belirli sayıda model çağrısı yapıldığı anlamına gelmez. Gerçek backend hata/çağrı kayıtları doğrulanmamıştır. Önceki raporda ayrıca geçen araçsız 400 girdisi bu 14 girdilik görünür dökümde yer almaz; görünür sayı backend toplamı diye sunulmaz. Cursor'a salt okunur teşhis prompt'u iletilmiştir; bu devirde sonucu henüz dönmüş sayılmaz.

| Gözlenen belirti | Kaynakta ilgili bulgu/hipotez | Eksik kanıt |
|---|---|---|
| Kapıyı çalma → teklif alıcısı | Birden fazla route yüzeyi; PR5 yalnız break/unlock | Ham/normalize niyet, seçilen işlem/route, gerçek hedef |
| Pencereyi inceleme → han arama | Cümle genelinde tavern+search eşleşmesi olası scope çakışması | Tam girdi ve runtime trace; yeniden üretim |
| Gezinme/bakınmada tekrar | Sahne materialization kalıcı ve tek seferlik; renderer/fallback de olası | Kabul edilmiş sahne, son olay, model context ve final kaynak |
| Kilitli hana giriş → genel belirsizlik | Kapı owner'ı var; eski save kapı kaydı boş olabilir | Venue origin/parent/door, revizyon ve route |
| Investigation 18 / DC 15 → genel başarı | Kaynakta generic Investigation fallback var | O tur gerçekten fallback mi; keşif paketinde ne vardı |
| “Neden?” → konu kaybı | Aktif NPC ve hafıza yolu var | Son önerme/konu gerçekten modele taşındı mı |
| Güvenlik gerekçesi | Doğrulanabilir profil/olay veya NPC inancı olabilir | Tam iddianın provenance'ı ve NPC bilgi kaynağı |

Bu tablo kök neden ilanı değildir. Kaynakta olası kod bulmak, canlı turn'ün o yoldan geçtiğini kanıtlamaz. Orijinal girdiler, state, dice/DC ve sonuçlar korunur. Teşhis sonuç alınca snapshot'a tarihli ekleme yapılır; geçmiş sayılar/olaylar düzeltilmiş oyuna benzeyecek biçimde değiştirilmez.

## 16. Koru / değiştir / emekliye ayır: supersession kaydı

Bu tablonun yürürlüğü §0.1'deki son metin onayına bağlıdır. Kapsam açıkça yazılmamış eski yükümlülük kaldırılmış değildir. Eski belge bir sonraki sahibin onaylı sözleşmesine karşı sonsuza dek değişmez değildir; fakat yalnız araştırma ve taslak onun yerine geçmez.

| Kaynak ve eski hüküm | Karar | Yeni normatif kapsam ve sınır |
|---|---|---|
| Bible anayasa/F04: Python state, Qwen anlatı | **Koru + genişlet** | §2: Python mekanik/kabul/kalıcılık sahibi; AI ayrıca niyet ve yaratıcı yerel öneri sahibi. Doğrudan model state yazımı yok |
| 12 Ekim handoff §2: “Canon, mekanik veya lore icat edemez” | **Değiştir** | §2–3: resmî lore ve desteksiz geçmiş yaratamaz; izinli kampanya-yerel yeni gerçek önerebilir, kabul edilince kampanya olgusu olur |
| F04 AC-003/008: sahte lore/hafıza/görev ve reddedilen metin kayıt olamaz | **Koru; terimi netleştir** | Yetkili ileriye dönük yeni kişi/olgu “sahte geçmiş” değildir. Gerçekleşmemiş oyuncu eylemi ve reddedilmiş anlatı hâlâ yazılamaz |
| F04'e yeni katalog eklenmemesi; F06/F07 geniş içerik sırası | **Dar değişiklik** | OH1-SCOPE-01: LR00-P3 sınırlı yaratıcı pilotu açılır. Geniş görev/ödül, faction/companion ve tam sosyal simülasyon açılmaz |
| 0–2 çağrı; red sonrası ek çağrı yok | **İlk sürümde koru** | §7: bütün girişimin toplam bütçesi, başlangıç işlemi de tanımlı. Kalite verisiyle ileride açık sürüm değişikliği mümkün |
| Sabit scene arketipleri/küçük ad havuzu | **Uygulama tercihini değiştir adayı** | §3: yeni kampanyada gerçek yaratıcı çeşitlilik; kabul edilmiş eski kimliği yeniden örnekleme yok |
| F05 ambience lore değildir; bilinmeyen rota/süreye kesinlik yok | **Koru + ayır** | Atmosfer ile etkileşilebilir yerel gerçek ayrılır. Yeni gerçek kabul yolu ister; resmî şehir/rota icadı açılmaz |
| F06 yalnız olay kaynaklı ilişki | **Koru** | NPC amacı/kişiliği yaratılabilir; oyuncuyla yaşanmamış ilişki sonucu uydurulmaz. Yeni sayısal ilişki sistemi ayrıca kapsam ister |
| Mevcut owner'lar; ikinci narrator/persistence yok; game.py tek yazarlı devir | **Koru** | §9/14 aşamalı geçiş. Gerçek boşluk varsa gerekçeli mimari değişikliği ayrıca yapılabilir |
| v0.2 LR ürün sırası | **Geliştir ve bu sürüme al** | §11 paket/AC/stop koşulları yeni aday sözleşmedir; v0.2 zaten uygulanmış veya dondurulmuş denmez |
| Eski “Replit kullanılmaz”, eski HEAD ve ortam tabloları | **Güncel operasyon kuralı olarak emekliye ayır** | §14/15 güncel iş bölümü ve zaman damgalı snapshot; tarihsel metin silinmez |
| Kartın tıklanarak doğrudan action göndermesi yönündeki eski v3 anlatımı | **Sonraki seçimi koru** | §10: 14 Ekim kararı uyarınca taslak doldurur, açık Gönder gerekir; bu davranışın uygulanmışlığı ayrıca test edilir |
| Say/Do/Ask DM zorunlu kategori seçimi | **Varsa kaldır** | §4/10: tek serbest giriş; isteğe bağlı OOC/target yardımı; parser yükü oyuncuya bırakılmaz |
| Görsel kaliteyi LR04'e erteleme yorumu | **Netleştir** | Temel viewport/sonuç doğruluğu LR00; 3D küçük alt teslim ve ileri kalite LR04. Zaman/hareket LR01'de, LR04'e bırakılmaz |
| Test sonucu = ürün/insan PASS yorumu | **Reddet; eski doğru ayrımı koru** | §13: ayrı kanıt katmanları ve iki GOLD. Ret/fallback güvenliği yaratıcı deneyim yerine geçmez |
| F01'e özel owner-review istisnası | **Dar kapsamını koru** | F04/GOLD insan incelemesi kaldırılmaz |
| Kapasite 2 / turda en fazla 1 slot kullanımı için 11 Ekim açıklaması | **Koru** | Eski tek-slot cümlesinden kapasite düşürme işi çıkarılmaz; ilgili mechanic mevcut kaynak/owner kapsamıyla uygulanır |
| Geçmişin değiştirilmemesi; daha önce genel retcon/undo kapsamı açılmaması | **Dar ve açık değişiklik** | §8.4 ve P7: kullanıcı başlatmalı tek-tur undo, eski kayıtları silmeden aktif dalı tur öncesine taşır. Sessiz DM retcon'u, transport retry'da reroll ve tarihsel kanıt silme hâlâ yasaktır; aynı hamlede kayıtlı zar önerilen varsayılandır |
| F13 şehir, F15 ses ve release izinleri | **Koru** | Yaratıcı DM vizyonu bunların ayrı veri/güvenlik/içerik yetkisini topluca açmaz |

**Çatışma çözümü:** En son açık kullanıcı kararı kendi kapsamı içinde önceliklidir; ardından onaylı bu sürümün açık değiştirme maddeleri, korunmuş teknik sözleşmeler ve mevcut owner kuralları gelir. Kaynak kodu mevcut davranışın kanıtıdır; hatalı davranışı ürün gereksinimi yapmaz. Test kaydı gerçekleşmiş çalışmanın kanıtıdır; kapsam yetkisi değildir. Araştırma ve rakip belgeleri gerekçe sunar, normatif hüküm üretmez.

Master Handoff v2/v3'ün tam özgün dosyaları bu araştırma turunda doğrudan geri alınamadı. v0.2, 12 Ekim handoff, kaynak ekleri ve iki özgün PDF geri alındı. Bu nedenle “hiç LR planı yok” da “bütün eski maddeler tek tek yeniden okundu” da denmez. Yeni bir özgün çelişki ortaya çıkarsa etkilenen madde açıkça uzlaştırılır; bu eksik erişim bütün tasarımı belirsiz bırakmak için kullanılmaz. [S2, S5]

## 17. Onay sonrası ilk üç sınırlı iş

Şu an aktif uygulama paketi **yoktur**; aktif iş sözleşmenin REVIEW ve tutarlılık incelemesidir. Aşağıdakiler yeni sözleşme ve ilgili uygulama başlangıcı onayından sonra yürütülebilir. Kullanıcı “v1.0'ı ve ilk üç işi onaylıyorum” gibi açık birleşik yetki verirse her küçük adımda tekrar hedef sorulmaz. Git/dağıtım/migration kapsamı ayrıca açık olmalıdır.

### İş 1 — LR00-P0: canlı hata ve kaynak manifesti

**Girdi:** Mevcut teşhis yanıtı veya gerçekten erişilebilir read-only log; güncel ortam status/branch/diff; orijinal turn kanıtı. **İş:** İlk yanlış sınırı belirle, model çağrılarını ayır, eski/yeni save farkını kaydet, current/historical kanıt tablosunu çıkar. **Çıktı:** Tek küçük teşhis+başlangıç manifesti, ilk düzeltme hedefi ve açık eksikler. **Yasak:** State fix, zar tekrar atma, save silme, kod/Git/deploy değişimi. **Bitti:** İlk bounded düzeltme kanıtla seçilebilir. **Dur:** Erişim yoksa tam eksik kaydı ver; source hipotezini runtime nedeni yapma.

### İş 2 — LR00-P1/P2: tek akışın davranış ve test sözleşmesi

**Girdi:** İş 1'in en erken kanıtlı sınırı. **Varsayılan odak:** Kapı/pencere nesnesine serbest niyet → doğru hedef → yetkili inceleme/etkileşim → somut sonuç. NPC “neden” aynı bağlam çerçevesinde incelenir fakat gerekirse sonraki ayrı dilim olur. **İş:** Mevcut owner arayüzünü, izinli dosyaları, olumlu/olumsuz/görülmemiş testleri, makbuz ve bütçe izini tanımla; izole test fixture'ı hazırla. **Çıktı:** Kısa uygulanabilir paket, gerçek seçiciler ve rollback sınırı; yeni fonksiyon adları tahmin edilmez. **Yasak:** Üretim kampanyasını fixture'a dönüştürmek, zorlanmış success'i doğal kanıt saymak, kapsamı bütün motor yapısına genişletmek. **Bitti:** Değişiklik ve test doğrudan çalıştırılabilir; eski AC borçları görünür. **Dur:** Önkoşul eksikse tamamlanacak dar korumayı belirt; bütün LR01/02'yi önkoşul yapma.

### İş 3 — İlk dikey dilimi uygula ve kanıtla

**Girdi:** Onaylı İş 2 kapsamı ve task branch/tek-yazar düzeni. **İş:** Kanıtlı sınırda en küçük genel düzeltmeyi mevcut owner'larda yap; ilgili deterministik testleri çalıştır; yetkili canlı model denemesi ve gerçek UI zinciriyle doğrula. Tasarım için yeni yerel ayrıntı gerekiyorsa yalnız P3'ün açık zarfı ve bütçesi kullanılır. **Çıktı:** İncelenebilir diff, komut/çıktı, kaynak/model manifesti, başarısız örnekler ve sınırlı sonuç. **Yasak:** Otomatik LR00/GOLD PASS, blanket guard bypass, izinsiz merge/deploy/migration, bütün diğer sorunları aynı PR'a doldurmak. **Bitti:** Seçilen dilim kanıtlı veya belirli blocker ile dürüstçe durdu; sonraki paket P3/P4/P5'tan kanıta göre seçilir. **Dur:** Authority/state ihlali veya kapsam dışı ihtiyaç; tekrar örnekleyerek güzel sonuç avlama yok.

Bu üç işten sonra otomatik olarak tüm yol haritası açılmaz. Entegrasyon sahibi hangi LR00 diliminin gerçekten hazır olduğunu ve kalan borcu gösterir. Sıradaki paket, mevcut yetki sınırı içinde ilerler; yeni kullanıcı kararı gerekiyorsa tek net seçenek ve önerilen varsayılanla sorulur. Kullanıcıdan önceden belirlediği vizyonu tekrar tanımlaması istenmez.

## 18. Kaynaklar ve son tutarlılık kontrolü

### 18.1 Birincil kaynak omurgası

**S1 — Mevcut teknik sözleşme ve onay:** [Future Project Bible v2.3.2](https://github.com/kadirkayarr-beep/AI-DND/blob/476ba9bd148da18e24cb5dab020c116ba4907445/ai-dnd/docs/AI-DND_Future_Project_Bible_v2_3_2_PROPOSED.md), [9 Ekim owner approval](https://github.com/kadirkayarr-beep/AI-DND/blob/476ba9bd148da18e24cb5dab020c116ba4907445/ai-dnd/docs/AI-DND_Future_Project_Bible_v2_3_2_OWNER_APPROVAL_2026-10-09.md). Özellikle anayasa §§1–2, bağımlılık tablosu L156–184, GOLD L253–281, statüler L285–307, F04 L609–657. PROPOSED dosya adı ayrı onay kaydını geçersiz kılmaz.

**S2 — Operasyon ve kapsam:** [AGENTS.md](https://github.com/kadirkayarr-beep/AI-DND/blob/476ba9bd148da18e24cb5dab020c116ba4907445/AGENTS.md), [Cursor/Replit handoff](https://github.com/kadirkayarr-beep/AI-DND/blob/476ba9bd148da18e24cb5dab020c116ba4907445/docs/CURSOR_REPLIT_HANDOFF.md), [owner rules](https://github.com/kadirkayarr-beep/AI-DND/blob/476ba9bd148da18e24cb5dab020c116ba4907445/.cursor/rules/ai-dnd-owners.mdc), [PR5](https://github.com/kadirkayarr-beep/AI-DND/pull/5), [PR6](https://github.com/kadirkayarr-beep/AI-DND/pull/6). Güncel kaynak/roadmap denetimi 16 Ekim tarihli araştırma tesliminde tam referanslarıyla yer alır; eski handoff HEAD'leri güncel snapshot yerine kullanılmaz.

**S3 — Mevcut yetenek sınırları:** [Öneri doğrulama](https://github.com/kadirkayarr-beep/AI-DND/blob/476ba9bd148da18e24cb5dab020c116ba4907445/ai-dnd/game.py#L4750-L4815), [yerel diyalog provenance](https://github.com/kadirkayarr-beep/AI-DND/blob/476ba9bd148da18e24cb5dab020c116ba4907445/ai-dnd/local_dialogue.py#L1-L78), [scene materialization](https://github.com/kadirkayarr-beep/AI-DND/blob/476ba9bd148da18e24cb5dab020c116ba4907445/ai-dnd/living_world.py#L1036-L1108), [NPC ad seçimi](https://github.com/kadirkayarr-beep/AI-DND/blob/476ba9bd148da18e24cb5dab020c116ba4907445/ai-dnd/living_world.py#L976-L995), [narrative memory](https://github.com/kadirkayarr-beep/AI-DND/blob/476ba9bd148da18e24cb5dab020c116ba4907445/ai-dnd/api/narrative_memory.py), [player knowledge](https://github.com/kadirkayarr-beep/AI-DND/blob/476ba9bd148da18e24cb5dab020c116ba4907445/ai-dnd/api/lore_authority/player_knowledge.py). Bunlar kaynak kanıtıdır; ilgili canlı akışın başarılı olduğu kanıtı değildir.

**S4 — Açık kabul:** [LR00 checkpoint](https://github.com/kadirkayarr-beep/AI-DND/blob/476ba9bd148da18e24cb5dab020c116ba4907445/ai-dnd/docs/LR00_CHECKPOINT_CANDIDATE_2026-10-15.md), [LR00 experience review](https://github.com/kadirkayarr-beep/AI-DND/blob/476ba9bd148da18e24cb5dab020c116ba4907445/ai-dnd/docs/LR00_EXPERIENCE_REVIEW_2026-10-15.md), [regression evidence](https://github.com/kadirkayarr-beep/AI-DND/blob/476ba9bd148da18e24cb5dab020c116ba4907445/ai-dnd/docs/regression-evidence.md).

**S5 — Geri alınmış tarihsel ürün kaynakları:** Living Realms Plan Taslağı v0.2 (14 Ekim); 12 Ekim Yeni Sohbet Devir Promptu; 36 sayfalık Rakip Evreni ve Ürün Stratejisi ile 41 sayfalık Yaşayan Bir Faerûn araştırmaları; 16 Ekim özgün araştırma uzlaştırması. Kullanıcı dosyaları doğrudan okundu; genel erişime açık paylaşım URL'si doğrulanmadığı için uydurma belge linki verilmez. [İlk LR00 yön onayı](https://chatgpt.com/c/6acbcc40-4cd8-83ed-96e1-7d83937ce5ab?messageId=5adf424f-f3dc-4cd0-82b5-80f998789f3c) yeni ayrıntılı v1.0 sözleşme onayı yerine geçirilmez.

**S6 — 16 Ekim Reforged araştırması ve başlıca birincil örnekler:** [Fables NPC memory](https://fables.gg/patch-notes/patch-notes-2541-npc-memory-planning), [Fables planlama değişikliği](https://fables.gg/patch-notes/patch-notes-2603-craft-update), [Auferet memory benchmark](https://auferet.com/memory-benchmark), [Old Greg's Tavern söylenti/quest](https://oldgregstavern.beehiiv.com/p/rumors-completely-reworked-quests), [AI Dungeon context](https://help.aidungeon.com/how-do-i-manage-context), [Questner FAQ](https://questner.ai/faq). Tam yirmi başlık araştırma raporunda korunur; bu sözleşme satın alma veya doğrulanmış rakip performansı iddiası taşımaz.

**S7 — Değerlendirme araştırma dayanağı:** [TextWorld](https://arxiv.org/abs/1806.11532), [FANToM](https://aclanthology.org/2023.emnlp-main.890/), [Agency Reconsidered](https://dl.digra.org/index.php/dl/article/view/369). Dil/state çeşitlendirme, bilgi asimetrisi ve oyuncu niyetinin karşılanmasını düşünmeye yarar; UNWRITTEN testi değildir.

**S8 — Model protokolü:** [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs), [tool calling](https://docs.ollama.com/capabilities/tool-calling), [chat API](https://docs.ollama.com/api/chat), [Qwen3-8B model card](https://huggingface.co/Qwen/Qwen3-8B). Şema/araç olanağı, yerel kalite veya iki çağrının yeterliliğini kanıtlamaz.

**S9 — Kayıt sınırları:** [SQLite transactions](https://www.sqlite.org/lang_transaction.html), [foreign keys](https://www.sqlite.org/foreignkeys.html), [WAL](https://sqlite.org/wal.html), [online backup](https://www.sqlite.org/backup.html). Gerçek uygulama ayarları ayrıca doğrulanır.

**S10 — UI'nin görülen referansları:** [Fables Combat V4](https://fables.gg/patch-notes/combat-v4), [Craft demo](https://www.craftrpgs.com/), [AI Realm V2 rehberi](https://airealm.com/home/v2Guide), [Runebook](https://runebook.gg/), [AI Dungeon oynama rehberi](https://help.aidungeon.com/faq/how-to-play). 16 Ekim UI araştırması hangisinin tarihli resim, demo veya belge olduğunu ayırır. UNWRITTEN UI brief'i ve statik wireframe bu sözleşmenin önerisini görselleştirir; çalışan ekran veya son asset değildir.

**S11 — Medya adayları:** [Diffusers IP-Adapter](https://huggingface.co/docs/diffusers/main/en/using-diffusers/ip_adapter), [bellek optimizasyonu](https://huggingface.co/docs/diffusers/main/en/optimization/memory), [BFL referanslı düzenleme](https://docs.bfl.ai/flux_2/flux2_image_editing), [FastAPI ağır arka plan işi uyarısı](https://fastapi.tiangolo.com/tutorial/background-tasks/#caveat), [Web Audio uygulama ilkeleri](https://developer.mozilla.org/en-US/docs/Web/API/Web_Audio_API/Best_practices). 16 Ekim medya araştırması yalnız yetenek/tercih incelemesidir; kurulum, sağlayıcı seçimi veya hız ölçümü değildir.

### 18.2 Bu sürümün son kontrol listesi

- [x] Yaratıcı AI DM yetkisi, resmî lore/mekanik/oyuncu iradesinden ayrıldı.
- [x] Yeni yaratımın kabul ve kalıcılık yolu, duyusal süsten ayrıldı.
- [x] İki çağrı önerisinin sınırı, timeout/retry hesabı ve gelecekte değişme yolu açık.
- [x] LR00 yaratıcı pilotu LR01/02 veya tam F06/F07'ye döngüsel bağlanmadı.
- [x] Eski teknik kapıların güvence gerekçesi ve dar değişiklik açık.
- [x] Pozitif yaratım, farklı kampanyalar, alternatif oyuncu yaklaşımı ve insan oyunu kabulde var.
- [x] Eski test, yeni kaynak, canlı kanıt ve insan kabulü birbirine çevrilmedi.
- [x] Tek giriş, viewport, uzun metin erişimi, 3D zar ve mevcut logo yönü birlikte ele alındı.
- [x] Yeni kabul edilen ürün yönleri ve tek-tur undo isteği, teknik adayları ve bağımsız kapsamıyla ayrıldı.
- [x] Replit kalıcı düzeni yapılmış gösterilmedi; güvenli Git ve tek-yazar sınırı açık.
- [x] İlk üç iş sınırlı; mevcut teslimde hiçbir proje değişikliği yapılmadı.
- [ ] Son metin sahibi onayı ve onaylı artifact hash'i.
- [ ] İlgili uygulama paketinin açık başlangıç yetkisi.

**Son karar cümlesi:** UNWRITTEN'in ayırt edici yanı, AI'ın özgürce hikâye fikri üretebilmesi ile oyunun o fikri güvenilir bir dünyaya dönüştürmesinin birlikte çalışmasıdır. Güvenilirlik yaratıcılığın yerine geçmez; yaratıcılık da oyuncunun kararını, kuralları ve geçmişi geçersiz kılamaz.
