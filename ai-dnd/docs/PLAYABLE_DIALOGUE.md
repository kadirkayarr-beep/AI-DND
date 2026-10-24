# Oynanabilir serbest diyalog: tek güncel uygulama rehberi

Durum: **izole aday, sentetik doğrulama**. Gerçek Qwen ve oyuncu kabulü tamamlanmadan canlı sürüm veya bütün oyunun düzeldiği söylenmez. Taban: `e51790e678409c1d75956e802140a38d20a7067a` (`dev/ai-dnd`). Bu dosya eski koordinasyon/handoff talimatlarının yeni `free_v1` diyalog yolu için yerine geçer; kimlik doğrulama, kayıt ve mekanik sahiplik sözleşmelerini kaldırmaz.

## Ne değişti?

- NPC konuşması yeni kampanyada tek `dialogue_runtime` yolundan geçer. Kişilik, güncel ruh hali, son dört eşleşmiş konuşma ve gerçek ilişki ayrı bağlamdır. Meslek paragrafı her cevaba zorla eklenmez. Eski üslup/lore/tekrar onarımları bu serbest konuşma cevabını yeniden yazmaz.
- “Kapı niye kilitliydi?” bir konuşma sorusudur. Fiziksel kapı/araç işlemleri `grounded_action` sahibinde kalır; “Han kapısını açıyorum” ve “Kapıyı maymuncukla açıyorum” aynı gerçek kapıya bağlanabilir. Kilit, alet ve zar gereksinimleri kaldırılmaz.
- Yer teklifi aynı turda gerçek konuma kaydedilir; tam ad korunur. Modelin yazdığı JSON doğrudan dünya yazma yetkisi değildir. Desteklenmeyen veya çelişen teklif gösterilmeden işlem geri alınır.
- DELIVERY ve URBAN_INVESTIGATION işleri mevcut `adventure` kayıtlarından üretilir. Kabul oyuncuya aittir. Bu iki hareketli iş şablonunda hedef aynı yerleşimdeki farklı bir gerçek konum olmalıdır; aynı konumda takılacak teklif hazırlanmaz. Teslimatta gerçek paket alınır/teslim edilir; görev adımı hazır olmadan paket oyuncudan alınmaz; soruşturmada gerçek kontrol yapılır. Ödül mevcut kayıt üzerinden bir kez verilir. Günlükteki başlık, hedef ve ödül motor tarafından üretilir; modelin başlık/açıklaması mekanik görev tanımlamaz.
- Gerçek yardım/teslimat ilişkiyi etkiler. Sadece “dün sana yardım ettim” demek geçmiş yaratmaz. Doğrudan tehdit sınırlı etki yapabilir; sıradan anlaşmazlık otomatik düşmanlık değildir. Gerekçeli kaçınma ancak kayıtlı yaşanmış olayla ve dar konuda, bir kullanımlık olabilir; hayali yer/görev için bahane değildir.
- NPC görünür bir savaş yaralanmasına karşı kısa inisiyatif alabilir. Gizli HP/sır verilmez. Aynı olay tekrar tekrar araya girmez. İnisiyatif, mevcut turdaki en fazla iki model çağrısı bütçesinin içinde kalır; arka planda model taraması veya gizli yeniden deneme yoktur.
- NPC rutinleri mevcut dünya saatinde çözülür. Varsayılan çalışma08.00–22.00, dinlenme22.00–08.00; özel kayıtlı program bunun yerine geçebilir. Ayrı dinlenme yeri yoksa yeni ev uydurulmaz. Şehir aktörü aynı şehirde dinlenme faaliyetine geçebilir. Han/işyeri çalışanı mevcut üst konuma ayrılabilir; yerine kendiliğinden kopya kişi yaratılmaz.
- Açık görevin tarafları, devam eden konuşma ve savaş rutin hareketinden korunur. Senaryolu yer değiştirme/düşmanlık olayı eski rutinden önceliklidir ve rutini açıkça yeniden kurulana kadar askıya alır.
- Yeni serbest konuşma 60 oyun saniyesi, paket aktarımı 6 oyun saniyesi sürer. Diğer mevcut eylem süreleri korunur. Yazma, düşünme, model gecikmesi, uygulamanın kapalı kalması veya yeniden yükleme zaman atlatmaz.

## Tek başlatma yolu ve temiz kampanya

Yerel ana kaynak: `C:\Users\Kadir\Desktop\AI - DND`. Tek başlatıcı mevcut `start_local.ps1` dosyasıdır. Eski Documents/Codex kopyalarındaki `run-current-api.py` başlatıcısını kullanmayın. Kod aktarımı/push/merge bu paketin hazırlanmasıyla gerçekleşmiş sayılmaz.

Onaylı aktarım yapıldıktan sonra, mevcut kimlik doğrulama yapılandırmasını koruyan PowerShell oturumunda:

```powershell
Set-Location 'C:\Users\Kadir\Desktop\AI - DND'
$env:AI_DND_OLLAMA_MODEL='qwen3.5:9b-q4_K_M'
$env:AI_DND_DIALOGUE_MODE='free_v1'
.\start_local.ps1
(Invoke-RestMethod 'http://127.0.0.1:8008/api/game/health').model
```

Bu komutlar auth anahtarı üretmez, güvenlik politikasını gevşetmez veya eski sunucuyu otomatik öldürmez.8008 doluysa çalışan PID/kaynak doğrulanmadan ikinci sunucu başlatılmamalı. “Kimlik doğrulaması gerekli” hatasında auth kapatılmamalı; mevcut yerel ayarlarla oturum açılmalı. `REPLIT_AUTH_AND_API_CONTRACT_HANDOFF_2026-10-12.md` yalnız halen geçerli auth sözleşmesi için korunmuştur.

UI: `http://127.0.0.1:22785/ai-dnd-experience/`. Yeni ve ayrı test kampanyası oluşturun. `free_v1` işareti kampanya oluşturulurken kaydedilir; ortam değişkenini ayarlamak mevcut kampanyaları dönüştürmez. Eski kayıtlar silinmez. Sağlık yanıtı yalnız model seçimini gösterir; gerçek tur veya oturum kabulü değildir.

## Doğrulama ve kabul

- Günlük kapı: repo kökünde `python ai-dnd/run_tests.py`; Windows mevcut `dev.ps1` yolunu kullanabilir.
- Yeni HTTP/testler: `ai-dnd/api/tests/test_dialogue_*`, `test_npc_persona_context`, `test_npc_initiative`, `test_npc_daily_routine`, `test_free_dialogue_playthrough`, `test_natural_door_phrases`.
- Kildrak → tam adlı han → kilit/alet/zar → içeri giriş → Edric kapı-nedeni → gerçek iş → teslimat/ödül → kayıt zinciri sentetik sağlayıcıyla sınanır. Bu gerçek Qwen’in aynı kalitede yazdığı anlamına gelmez.
- Gerçek model kalite listesi: `api/tests/fixtures/dialogue_quality_cases.json`:3 kişilik × 8 durum × 3 tekrar = 72 yanıt. İlgi, kişilik, Türkçe, referans sürekliliği ve tekrar ayrı değerlendirilir. Tüm çıktılar korunur; iyi örnekler seçilip toplam başarı diye sunulmaz.
- Her sonuç kaynak kimliği, seçili test kimlikleri, ham log, başlangıç/bitiş ve hata/atlama sayılarıyla eşleştirilir. Eski başarısızlıklar gizlenmez. Test toplamları örtüşen seçimler arasında benzersizmiş gibi toplanmaz.

## Açık sınırlar

Serbest doğal dilde her türlü yanlış iddiayı matematiksel olarak önlediğimiz iddia edilmiyor. Zorunlu teklif dizileri, kanonik görev kartları ve dar ad/taahhüt kontrolleri sık görülen kopuklukları yakalar; keyfi bir model ifadesi veya dolaylı mecaz bu kontrolleri aşabilir. Bunlar yeni üslup sansürü değil, oynanabilir hedef kaydı kontrolleridir. Gerçek modelde kaçırılan ya da yanlış reddedilen örnekler ilgili aşamayı yeniden açar.

Şu an yalnız iki görev şablonu bu teklif yoluna açılmıştır. Diğer şablonların dosyada bulunması oynanabilirlik kanıtı değildir. Eski/varsayılan kampanya yolu bilinen eski başarısızlıkları koruyabilir. Bu aday bütün eski motoru yeniden yazmaz.

## Arşiv ve geri dönüş

Tarihsel koordinasyon ile 8 eski Stage10 handoff ve eski NPC devir belgesi, kaynak dışındaki doğrulanmış `AI_DND_TARIHSEL_HANDOFF_ARSIVI_20261024.zip` içine alınır. Tam adlar/hashler teslim manifestinde bulunur. Eski kanıt loglarındaki tarihsel dosya referansları değiştirilmez; bunlar aktif talimat değildir. UNWRITTEN belgeleri, bu çalışmanın dışındaki gereksinimler eşlenmeden silinmez.

Teslimde ileri yama, ters yama, dosya hashleri, test raporu ve bu arşiv ayrı bulunur. Yalnız eşleşen tabana uygulayın; çalışma dosyalarının üstüne körlemesine kopyalamayın. Ters yama yeni kaydedilmiş test kampanyasını silmez veya eski kayda dönüştürmez. Git push/merge, herkese açık dağıtım ve güvenlik değişikliği bu uygulama kapsamının dışındadır.
