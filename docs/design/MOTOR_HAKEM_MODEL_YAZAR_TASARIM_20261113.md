# Motor hakem, model yazar: tasarım (2026-11-13)

Durum: Kadir onayladı (2026-11-13, 03:12; savaş anlatımı üç cümle olarak düzeltildi). §4b aynı mesajdaki yön kararıyla eklendi ve ayrıca onay bekliyor.
Üst ilke (Kadir, 2026-11-13): kural, zar, para, zaman, kayıt ve denetim motorda kalır; iş, söylenti, NPC cevabı ve sahne metni modelden gelir, motor doğrular ve kaydeder. Hazır metin yalnız yedek ve örnektir.
İlgili belgeler: `KESME_SONRASI_TASARIM_20261112.md` §10.3b-c, `ANA_ENVANTER_20261113.md` 5.x, `OYNAYIS_NOTLARI_20261113.md` (H-S, W, X, L-sonuç).

## 1. Kanıt

Kaynak: Kadir'in 13 Kasım oynayışı, 67 tur, anlatıcı yalnız yerel Gemma; Kadir'in gönderdiği tam metin.
Sayım (Claude Code, çıkarım): motorun hazır cümlesi 41 tur (%61), model 22 (%33), ikisi 4 (%6). En iyimser okumada motor yaklaşık %42.

Metinde altı kusur sınıfı var. Her birinin örneği:

| Sınıf | Ne | Örnek (tur) |
|---|---|---|
| K1 Düz sonuç | Motor çözdü, hazır cümleyle yazdı | "Yakınında bir barmen var." (19); "İlan panosu: Üstüne üst üste çivilenmiş…" aynı cümle iki kez (3, 4); "Ümvila, bir darbe alır: 8 hasar. Rakibinin karşı saldırısı seni ıskalar." (66) |
| K2 Bağsız anlatım | Model bir sonucu anlattı, motor yapmadı | Kısa dinlenme: satıcı "iyi dinlenmeler" dedi, dinlenme çalışmadı (33); İlahi Darbe uzun paragraf, hasar yok (61); zarsız itme (58) |
| K3 Yanlış yola giden hamle | Yazılan hamle başka eyleme ya da hiçbir eyleme eşlendi | "Kervancı itiyorum" → NPC "anlamadım" (44), aynı hamle iki tur sonra savaş açtı (46); "kendimi tanıtıyorum ve iş soruyorum" → yalnız tanışma, soru yutuldu (23); "Bir muhafız bulana kadar geziyorum" → kervancı yolculuktan söz etti (38); "hana giriyorum" (17) |
| K4 Yapıştırma | Motor etiketi, model metni ve motor satırı uç uca eklendi | "Bir kervancı Eline bir kalem…" (39); muhafız "her şey yolunda" der, hemen ardından motor satırı "Bir kervancı öldürüldü, duydun mu?" (52, 53) |
| K5 Sessiz ret | Hamle reddedildi, neden söylenmedi | "Çevrede şimdilik belirgin bir değişiklik olmuyor" (40, 42); "Öyle olsun bakalım" iki kez (55, 56); "İşlem gerçekleşmedi" (12) |
| K6 Şablon içerik | İşler ve ilanlar 60 hazır şablondan | "nemli paketleri ayıracak yardımcı" (5, 24, 30) |

Çalışan şeyler (korunacak): ilan panosundan iki iş bulundu, biri yapıldı ve ücreti ödendi; kervancı öldürülünce tanıklar kaçtı ve bir muhafız cinayeti söylenti olarak aktardı. Yani "iz bul, peşine düş, seçimin sonucunu gör" döngüsü motor düzeyinde var; sorun nasıl söylendiği ve hamlenin nasıl anlaşıldığıdır.

## 2. Kodda bugün olan (2026-11-13, `main`; yalnız okuma)

- Motor sonucu `action_result` sözlüğüdür. İçinde `direct_response` varsa tur çoğu yerde o metinle biter (`game.py`, `finish_turn(action_result, action_result["direct_response"], is_final=True)`; dosyada 132 `direct_response` geçişi).
- Model anlatımı için altyapı zaten var: `_narration_fact_packet` ve `narration_claims.packet_from_result` (anlatıcının söyleyebileceği gerçekler), `_narrator_fact_view`, `finalize_narration`, `_narration_safety_decision` (1.051 satır), `_narrated_money_can_lie`, `_fallback_narration`.
- "Etrafa bakma" turunda örnek bir yol var: `direct_response` metni modele gerçek olarak verilir ve model onu anlatır (istemde "direct_response içindeki kişileri ve ayrıntıları…" satırı).
- `narration_source` kodda hesaplanıyor ama tur kaydına yazılmıyor.
- Düğmeler yapılı eylem gönderir ve motor çözer; aynı şey yazıyla söylenince sınıf özelliğine eşlenmez (Claude Code, M4).
- Motorun bonus eylem listesi yalnız tür yeteneklerini sayar (M2). Yaklaşık 111 iç hata kodu var, arayüzde 19'u geçiyor (M3, tahmin).

Sonuç: yeni bir anlatım sistemi yazılmaz. İş, hazır cümleyle biten çıkışları var olan "gerçek paketi → model → denetim → yedek" yoluna bağlamaktır.

## 3. Tur sözleşmesi

Her tur dört adımdan geçer; bugün bazı turlar bir ya da iki adımı atlıyor.

1. **Çöz:** yazılan hamle bir ya da birkaç motor eylemine eşlenir. Eşlenemiyorsa motor bunu bilir ve söyler.
2. **Uygula:** motor eylemi kurallarla çalıştırır; zar, para, zaman, kayıt burada değişir. Model bu adımda hiçbir şeyi değiştiremez.
3. **Anlat:** motor sonucu gerçek paketi olarak modele verilir; model yalnız o sonucu anlatır.
4. **Denetle:** motor anlatımı gerçek paketiyle karşılaştırır. Tutmuyorsa onarır; onaramıyorsa hazır cümleyi kullanır.

Değişmez kurallar:
- S1. Motor sonucu olmayan eylem anlatılmaz. Model "dinlendin", "vurdun", "aldın" diyemez; yalnız motor diyebilir.
- S2. Para, eşya, can, XP, zar sonucu ve süre anlatımda yalnız motorun verdiği sayıyla geçer. Para satırı her zaman motorun kendi cümlesidir; model onu yeniden yazmaz.
- S3. Ret her zaman nedenlidir: motor nedeni sade Türkçe verir, iç kod oyuncuya gitmez.
- S4. Model çalışmıyorsa ya da denetim iki kez düşerse tur hazır cümleyle biter. Oyun modelsiz de oynanır kalır.
- S5. Tek ses: bir turun metni tek anlatımdır. Motorun eklemek istediği gerçek (söylenti, iş haberi, tanığın kaçışı) modele gerçek olarak verilir; sonradan uca eklenmez. İstisna: S2'deki para satırı ve zar satırı.

## 4. Dilimler

Her dilim kendi başına çalışan ve ölçülebilen bir değişikliktir. Sıra bağımlılığa göredir.

### Dilim 0: Ölçüm (S)
`narration_source` tur kaydına yazılır. Değerler kodda bugün var olanlardır (`main`'de görülenler: `deterministic_fallback`, `qwen`, `python_memory_response`, `deterministic_system`; tam liste uygulamada koddan çıkarılır). Yeni değer adı uydurulmaz (2026-11-13 düzeltmesi: bu satırın ilk hâli uydurma Türkçe adlar içeriyordu). §6'daki "modelden gelir" ölçütü hangi değerlerin model sayılacağı yazılarak hesaplanır. Davranış değişmez. Alanı olmayan eski kayıtlar aynen yüklenir; Geri Al sonrası alan tutarlı kalır. Kayıt koduna dokunur: bağımsız inceleme.

### Dilim 0b: Kaynağı son metnin çıktığı yerde etiketle (S-M) (2026-11-13, 04:10 eki)
Dilim 0 uygulandı (commit 7bd49a27, push bekliyor) ve iki eksik gösterdi (Claude Code, envanter 5.17):
- Motorun telemetri döndürmediği çıkışlar kaynaksız kaydediliyor: `_dispatch_player_turn` içinde 43 `return`, dışında 4 çıkış. Bunların çoğu hazır cümleyle biten turlardır; yani ölçmek istediğimiz şeyin kendisi.
- Telemetri kurulduktan sonra çalışan adımlar metni değiştirebiliyor (`_person_answers_stock`, `_the_rest_of_the_line`, kapı metinleri); kayıtlı değer son metni değil, motorun o an bildirdiğini gösteriyor.
Kök neden tektir: kaynak, metnin son hâlinin belli olduğu yerde değil, daha önce belirleniyor. Düzeltme: etiket turun bittiği tek noktada, son metinle birlikte verilir.
Beşinci değer: son metin model anlatımı ile motor satırının birleşimiyse (Dilim 1'den sonra S2 gereği para ve zar satırı her zaman böyle olacak) dürüst etiket "karışık"tır. Öneri: beşinci bir değer eklenir; §6'daki ölçütte model ve karışık birlikte "modelden" sayılır, yalnız motorun hazır cümlesi ve yedek "motordan" sayılır. Kadir'in kararı gerekir.
Para, kayıt ya da Geri Al'a dokunmaz; kayıt kodundaki izinli değer listesi ve onu motorla eşleyen test birlikte güncellenir.

### Dilim 1: Düz sonucu model anlatır (K1, K4) (M-L)
Kapsam, yalnız parasız sonuçlar: varış ve gezinme, "burada kimler var", nesne ve pano inceleme, arama (bir şey bulunmadığında), konuşmayı bitirme, savaş turu sonucu.
Kapsam dışı: ücret, satın alma, yağma, teklif (S2 gereği motor cümlesiyle kalır; Dilim 4'ten önce dokunulmaz).

- Bu çıkışlarda `direct_response` metni artık oyuncuya giden cümle değil, modele verilen gerçektir (§2'deki "etrafa bakma" yolu genelleştirilir).
- K4 için: konuşan kişinin etiketi ile model metni arasındaki birleştirme tek yerde yapılır ("Bir kervancı Eline…" hatası); söylenti ve iş haberi satırları gerçek paketine girer.
- Savaşta anlatım kısa tutulur: en çok üç cümle (Kadir, 2026-11-13); zar ve hasar satırı S2 gereği motor cümlesi olarak ayrıca görünür. Uzunluk sınırı ayardan değişmez; ilk sürümde sabittir.
- Aynı sahne cümlesi art arda iki turda aynen yinelenmez (mevcut `_drop_repeated_sentences` kullanılır).
- Denetim en az şunları yakalar: gerçek paketinde olmayan para, eşya, hasar, can, yeni adlı kişi ya da yer; paketteki ad ve sayının değişmesi; reddedilmiş bir eylemin başarılı anlatılması. Yakalanan önce onarılır (22 Kasım 2026, Kadir'in "reddetme, onar" kuralı; ana plan B2): desteksiz para/eşya/hasar/can cümlesi çıkar ya da motor değeriyle düzeltilir, yeni ad kayda alınmaz ama metin kalır; metnin tümü yalnız reddedilmiş eylemi başarılı anlatıyorsa geri çevrilir. S4'teki "iki kez düşerse" onarımdan sonraki düşüştür.

Bedel: bu turlar bugün model çağırmıyor. Yerel Gemma'da tur başına birkaç saniye eklenir (ölçülmedi); bulutta çağrı sayısı artar ve oyuncu başına sınıra sayılır.

### Dilim 2: Bağsız anlatımı ve yanlış yolu kapat (K2, K3, K5)
- **2a Nedenli ret (S-M):** "Çevrede belirgin bir değişiklik olmuyor", "Öyle olsun bakalım" ve "İşlem gerçekleşmedi" yerine motorun bildiği neden. İç hata kodları için tek Türkçe tablo; karşılığı olmayan kod için tek genel cümle ve kod yalnız kayda.
- **2b Yazı ile düğme aynı yol (M):** yazıyla söylenen sınıf ve tür yeteneği (İlahi Darbe, Şifa Eli, Divine Sense ve diğerleri) düğmenin gönderdiği yapılı eyleme eşlenir. Eşleme tek ad tablosundan (`tr-names.ts` ile aynı kaynak; motor tarafında karşılığı) yapılır. Motorun bonus eylem listesi sınıf yeteneklerini de sayar (M2).
- **2c Konuşma hamleyi yutmaz (M):** konuşma açıkken yazılan eylem (dinlenme, itme, saldırı, ayrılma) NPC'ye söz olarak gitmez; önce eylem olarak çözülmeye çalışılır. Savaş başlatan her hamle aynı onay sorusundan geçer ("… ile kavga mı başlatıyorsun?"); bugün kervancıda soruluyor, muhafızda sorulmuyor.
- **2d Bileşik hamle (M-L):** tek mesajda iki niyet varsa (tanış ve sor) ikisi de sırayla işlenir; ikincisi işlenemiyorsa oyuncuya söylenir, sessizce atılmaz.

### Dilim 3: Model iş önerir, motor doğrular (K6; Kadir'in Q kararı) (L)
- Model bir NPC konuşmasında ya da panoda iş önerebilir. Öneri kapalı bir biçimdedir: işveren (kayıtlı kişi ya da yer), iş türü (motorun bildiği türlerden), süre, kısa tanım.
- Ücreti model yazmaz. Motor ücreti iş türü, süre ve seviyeye göre kendi tablosundan belirler.
- Motor doğrular: işveren kayıtta var ya da kurallı biçimde yaratılabilir; tür ve süre geçerli; aynı işin kopyası yok. Geçerse iş, şablondan gelen işle aynı kayda yazılır ve aynı ücret yolundan ödenir. Geçmezse şablon işi sunulur ve oyuncu farkı görmez.
- Bir NPC'nin sözü tek başına iş yaratmaz; iş ancak motor kaydettiğinde gerçektir.
- Para ve kayıt yüzeyi: önce kırmızı test, bağımsız inceleme, en güçlü model. İş ücreti hatası (notlar H) bu dilimden önce düzeltilmiş olmalıdır.

### Dilim 4: Üslup (S-M)
Yerel model için daha zengin örnek (`LOCAL_DM_EXAMPLE` seçimi), NPC'ye rol ve ruh hâliyle ses; aynı beş sabit sahnede eski ve yeni istem ile bulut modeli karşılaştırılır, Kadir puanlar. Sıcaklık ancak denetim (Dilim 1) yerindeyken değiştirilir.

## 4b. Modelin önünü güvenli biçimde açmak (Kadir, 2026-11-13: "modelin önünü güvenli şekilde olabildiğince açmak istiyorum")

İlke: model dünyaya yeni şey **önerebilir**; öneri motor doğrulayıp kaydettiğinde gerçek olur. Model hiçbir şeyi doğrudan kayda yazmaz. Açıklık, "öneri şeridi" sayısı ve her şeridin sınırıyla ölçülür.

Kodda bugün olan şeritler (yalnız işlev adları okundu; ne kadar açık oldukları ölçülmedi): kişi (`validate_npc_proposal`, `create_npc_from_ai`, `_validated_local_person_proposal`), sahne ayrıntısı (`create_local_feature`, `_scene_detail_proposals_allowed`), dükkân (`validate_shop_proposal`), yer (`validate_location_proposal`), eşya isteği (`_grounded_item_request_proposal`). Yani kapılar var; soru hangi turda açık oldukları ve önerilerin ne kadarının kabul edildiğidir.

Şeritler, en güvenliden en riskliye:

| # | Şerit | Model ne önerir | Motor neyi doğrular | Durum |
|---|---|---|---|---|
| Ş1 | Süs | Koku, ses, hava, kalabalık, jest | Kayıt yok; adlı kişi, alınabilir eşya, para içeremez | Dilim 1 ile gelir |
| Ş2 | Sahne ayrıntısı | Sahnede bir nesne ya da köşe | Yerin türüne uygun; değer ve mekanik iddiası yok; oyuncu dokununca kalıcılaşır | Kodda var |
| Ş3 | Kişi | Ad, görünüş, ruh hâli, rol (kapalı rol listesi) | Yer ve rol uyumu, ad çakışması, sahne başına üst sınır | Kodda var |
| Ş4 | Söylenti ve iz | Bir NPC'nin iddiası | "Söylenti" olarak kaydedilir, gerçek olarak değil; görev ya da ödül doğurmaz; kayıtlı bir gerçeğe bağlanırsa ize dönüşür | Yeni |
| Ş5 | Tutum | NPC'nin oyuncuya tavrındaki değişim | Sınırlı adım (bir turda en çok bir kademe), nedeni o turdaki olay | Yeni |
| Ş6 | Yer | Var olan semtin içinde dükkân, han, sokak | Üst yer kayıtlı; türü listeden; kopya yok | Kodda var |
| Ş7 | Küçük olay | Ortam olayı (kavga sesi, arabanın devrilmesi) | Olay türü listeden; para, hasar ve ödül içermez | Kısmen (ortam olayları hazır listeden) |
| Ş8 | İş | Dilim 3 | Ücreti motor belirler | Yeni, Kapı 1'den sonra |

Hiçbir şeritte modelin dokunamayacakları: para ve fiyat, değerli eşya, can, XP, zar, süre ve zaman, ödül, ölüm, kural sonucu.

Bir şeridi açmanın koşulu (hepsi için aynı):
1. Kırmızı test: sahte model sınırı aşan öneri verir (para ekler, kayıtsız yere bağlar, üst sınırı aşar); beklenen ret ya da onarım.
2. Sabit tohumlu bir yolculuk senaryosu: öneri kabul edilir, kaydedilir, kaydet-yükle ve Geri Al sonrası tutarlıdır.
3. Sahne ve tur başına üst sınır (öneri bütçesi) tanımlıdır.
4. Reddedilen öneri oyuncuya hata olarak görünmez; anlatım öneriden arındırılır (mevcut `_filter_unaccepted_proposal_mentions`).
5. Kadir oynar ve şeridi kabul eder. Şerit bir ayar anahtarıyla kapatılabilir.

İlk adım ölçümdür (kod değişmez): 13 Kasım oynayışının 67 turunda model hangi şeritte kaç öneri yaptı, kaçı kabul edildi, kaçı neden reddedildi; her şerit hangi tür turda açık. Kayıt bunu tutmuyorsa Dilim 0'a şerit ve sonuç alanı eklenir. Açma sırası bu ölçümden çıkar; ölçümsüz öneri: Ş1 (Dilim 1 ile), sonra Ş2 ve Ş3'ün açık olduğu tur türlerini genişletmek, sonra Ş4 ve Ş5, sonra Ş6 ve Ş7, en son Ş8.

Risk: açıklık arttıkça dünya tutarsızlaşabilir (aynı sokakta üç han). Karşılığı öneri bütçesi ve kopya denetimidir; ölçü, bir oturumda reddedilen önerilerin oranıdır.

## 5. Sıra ve kapılar

Kapı 1'den önce (tavan: beş parça): Dilim 0, Dilim 1, 2a, 2b, 2c.
Kapı 1'den sonra, oynayışın gösterdiğine göre: 2d, Dilim 3, Dilim 4.
Öneri şeritleri (§4b): ölçüm hemen (kod değişmez); Ş1 Dilim 1'in içindedir; Ş2 ve Ş3'ün genişletilmesi Kapı 1'den önce ancak beş parçalık tavanda yer açılırsa, yoksa hemen sonrasında; Ş4-Ş8 Kapı 1'den sonra.
Motor hattındaki diğer işler (ücret hatası H, han girişi I, XP kuralı) bu belgenin parçası değildir; aynı hatta sırayla yürür. `game.py` tek yazıcı kuralı geçerlidir: bu dilimler arayüz işiyle aynı anda yürüyebilir, birbirleriyle aynı anda yürümez. Dokunulan bölge önce ayrı modüle taşınır (dokunduğun yeri önce ayır).

## 6. Başarı ölçütü

- Kadir'in bir sonraki 30 dakikalık oynayışında, sistem ve para satırları hariç turların en az %80'inde anlatım modelden gelir (`narration_source`).
- Aynı oynayışta K2 sayısı sıfırdır: motor sonucu olmayan hiçbir eylem başarılı anlatılmamıştır.
- Sessiz ret sayısı sıfırdır.
- Yerel modelde ortanca tur süresi Dilim 1'den önceki ölçümün en çok iki katıdır (eşik öneridir; önce bugünkü süre ölçülür).
- Hüküm Kadir'indir: "mekanik değil". Rakamlar hükmün yerini tutmaz.

## 7. Test

- Kadir'in 13 Kasım oynayışı sabit tohumlu üç yolculuk senaryosuna çevrilir: liman işi ve ücret; han bulma ve girme; kervancı, itme, savaş ve tanıklar. Her senaryo bugün kırmızı olan en az bir beklenti taşır.
- Denetim testleri sahte modelle yazılır: model gerçek paketine para ekler, hasarı değiştirir, olmayan bir kişiyi adlandırır, reddedilen eylemi başarılı anlatır. Her birinde beklenen: anlatım reddedilir ya da onarılır, kayıt değişmez.
- S4 testi: model hata verir; tur hazır cümleyle biter, kayıt tutarlıdır.
- Geri Al: model anlatımlı bir tur geri alınır; para, çanta ve kayıt önceki hâline döner.
- Sabit komşu yolculuk seti her görevde koşar. Hazır cümleyi sabitleyen eski testler eşit sıkılıkla yeniden yazılır ve onay listesine "[GEVŞETME OLABİLİR]" işaretiyle girer; sayıları planda önceden sayılır.

## 8. Riskler

| Risk | Karşılığı |
|---|---|
| Yerel Gemma denetimi sık düşürür, turlar yine hazır cümleyle biter | `narration_source` oranı izlenir; `yedek` oranı %30'u aşarsa Dilim 4 öne çekilir |
| Tur süresi uzar, oyun ağırlaşır | Savaşta üç cümle sınırı; ölçüm Dilim 1'in bitiş koşuludur |
| Hazır cümleyi sabitleyen çok sayıda test kırılır | Planın ilk görevi bu testleri saymaktır; sayı büyükse Dilim 1 yüzey yüzey bölünür |
| Denetim 1.051 satırlık işleve yeni dallar ekler | Yeni denetim kuralları ayrı modülde yazılır; `_narration_safety_decision` büyütülmez |
| Model iş önerisiyle para yüzeyi açılır | Ücreti yalnız motor belirler; Dilim 3 Kapı 1'den sonra |

## 9. Kapsam dışı

Yeni model ya da sağlayıcı; Nemotron'un geri getirilmesi; kural içeriği değişikliği; modelin kişi, yer ya da eşyayı doğrudan kayda yazması; savaş ekranı tasarımı (ayrı iş); metindeki tek tek içerik hataları (açılış cümlesine ham köken metninin girmesi, peynir evinin sokak pazarı gibi anlatılması, "Prone" gibi İngilizce sözcükler) motor hattında ayrı kalemlerdir.

## 10. Doğrulanmayanlar

- %61 oranı çıkarımdır; Dilim 0 kesinleştirir.
- §2'deki kod okuması işlev adları düzeyindedir; `finish_turn` çıkışlarının kaçının Dilim 1 kapsamına girdiği sayılmadı.
- Tur süreleri ve bulut çağrı artışı ölçülmedi.
- Oynayış yalnız yerel Gemma ile yapıldı; bulut zinciriyle K2 ve K4'ün ne kadar azaldığı bilinmiyor.
- Hazır cümleyi sabitleyen test sayısı bilinmiyor.
- Bu tasarım için test koşulmadı, oyun çalıştırılmadı.
