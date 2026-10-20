# AI-DND için yedi GitHub deposunun teknik incelemesi

İnceleme tarihi: 20 Ekim 2026. Odak: Python backend + React UI + yerel Qwen3:8b kullanan AI-DND'de NPC'lerin doğal konuşmasını sağlarken kanon ve oyun durumunu korumak.

## Okuma yöntemi ve sınırlar

Bu bir salt okunur kaynak kod incelemesidir. Depoların erişimi ve incelenen commit kimlikleri doğrulandı; ana çalışma akışları, model çağrıları, promptlar, bellek/durum yazımları, doğrulayıcılar ve test dosyaları okundu. Hiçbir repository kodu kurulmadı veya çalıştırılmadı; benchmark, canlı oyun veya penetrasyon testi yapılmadı. “Kodda var” çalışan ürün garantisi değildir; “incelenen akışta bulunmadı” deponun hiçbir yerinde bulunmadığı anlamına gelmez. README vaatleri uygulamadan ayrıldı. Devam eden AI-DND taşımasına dokunulmadı.

## Karar özeti

Bu yedi projeden birini bütünüyle temel almak yerine, dar ve sınanabilir fikirleri almak daha güvenli. Ortak ders şu: **NPC'nin cümlelerini dünya durumunun kendisi sayma. Konuşma özgürlüğünü genişlet; kalıcı mutation yetkisini daralt.**

1. **llm_RPG:** Küçük ve anlaşılır diyalog/action protokolü, envanter doğrulaması ve kilitli sırları bağlama vermeme yaklaşımı için güçlü aday. Fakat keyword ile topic açma ve gevşek boolean dönüşümü aynen alınmamalı.
2. **NarrativeEngine-P:** NPC/faction bilgi kapsamı, sahnedeki kişileri filtreleme, üretim ve commit ayrımı için kapsamlı referans. Gizli olguların UNKNOWN FACTS olarak modele yine verilmesi ve geçmiş prose'tan otomatik inventory patch çıkarılması ciddi sınırlamalar.
3. **Axidify/ai-dnd-rpg:** Kanonik state özeti, mekanik sonucu motorun belirlemesi ve item grant doğrulaması için güçlü aday. Keyword tabanlı action/check ayrıştırmasını, sosyal retry bloklarını ve bilinmeyen kişilere otomatik “never heard” yaklaşımını aynen taşımamak gerekir.
4. **WorldLines:** NPC sesi/world-agent yetkisi ayrımı, soul başına veri düzeni ve trace/replay arayüz fikri yararlı. Motor kapalı; açık bir doğrulanmış event-sourcing motoru diye alınmamalı.
5. **Diğer üç depo:** Ayrıntılı bölümlerde gösterildiği gibi, uygulama bütünlüğü ve bağımlılık farkları nedeniyle özellik listeleri tek başına tercih gerekçesi değil. Özellikle skeleton ve chat-wrapper ile gerçek oyun-state motoru ayrılmalı.

llm_RPG küçük bir protokolü anlamak için; NarrativeEngine daha kapsamlı bağlam/commit tasarımını incelemek için; Axidify mekanik otorite sınırını görmek için öncelikli.

Bu sıralama “en iyi genel proje” veya popülerlik sıralaması değil; mevcut NPC aşırı engelleme sorununa uygulanabilirlik önceliğidir.

## Mevcut yapıya küçük adımlarla uyarlama

### 1. Konuşma ile mutation'ı ayrı sözleşmelere böl

NPC çağrısının girdisi sadece karakter kimliği, sahne, konuşma geçmişinin ilgili bölümü ve o NPC'nin bildiği olgulardan oluşsun. Çıktı `utterance`, `visible_action` ve isteğe bağlı `proposed_actions` gibi ayrı alanlara bölünebilir. Buradaki isimler öneridir, mevcut projede varmış gibi ileri sürülmüyor.

“Hancı sana anahtarı uzatır” ifadesi envanteri değiştirmesin. Anahtar verme için ayrı `transfer_item` önerisi ve sunucuda item ownership, mesafe, miktar, koşul kontrolleri gereksin. Başarısız işlem tüm konuşmayı “doğrulayamıyorum” cevabına çevirmesin; yalnızca eylem reddedilsin veya doğal bir düzeltme üretilsin.

### 2. Kapıyı kelimelere değil yetkiye koy

Oyuncu bir sırdaki sözcüğü söyledi diye NPC diyalog çağrısı engellenmesin. İstek önce sohbet, bilgi sorgusu, kontrol gerektiren eylem veya state değişikliği olarak ayrıştırılsın. Sohbet için lore anahtar sözcüğünün varlığı otomatik ret nedeni olmasın.

NPC bilmediği şeyi kesin gerçek diye uydurmasın; ama kişilik, duygu, gündelik sohbet, görüş, açıkça söylenti veya belirsizlik şeklinde cevap verebilsin. “Bilmiyorum” gerektiğinde kullanılabilir, fakat bütün belirsizlikleri tek sabit fallback'e indirgemek karakteri yok eder. Sır metnini “bunu bilmiyorsun” başlığıyla vermek yerine prompttan tamamen çıkar.

### 3. Kanon yazımını tek sunucu hizmetinde topla

LLM çıktısı önce typed/schema doğrulamasından geçsin; enum, boolean, sayı sınırları, entity ID ve ilişki koşulları kontrol edilsin. Ardından yetkili mutation commit edilsin. Serbest metinden keyword eşleşmesiyle bilgi kilidi açma, LLM'nin yazdığı zarı gerçek roll sayma ve konuşma geçmişinden otomatik item grant yapma yolları kapatılsın.

Bir turn için `turn_id`, beklenen state sürümü ve idempotency anahtarı kullanmak tekrar denemelerde iki kez item/XP vermeyi önleyebilir. Önce küçük bir audit kaydı yeterli; tam event-sourcing veya yeni veritabanı zorunlu değil.

### 4. Aşırı engellemeyi ölçülebilir hale getir

NPC hattında model çağrıldı mı, hangi kapı reddetti, reddetme nedeni, hangi fact ID'leri bağlama girdi, hangi mutation önerisi kabul edildi kaydedilsin. Gizli lore metnini loglamak yerine kimlik ve neden kodları yeterli olabilir. Böylece sorun modelin Türkçesi mi, lexical gate mi, parse hatası mı, fallback mi ayrılır.

Başlangıç regresyon seti: gündelik selam; karaktere kişisel soru; bilinen olgu; bilinmeyen olgu; oyuncunun sahte kanon iddiası; kilitli sır için açık talep; sırla ortak sözcük içeren masum cümle; NPC'nin sahip olmadığı item; başarılı/başarısız persuasion; iki NPC arasında sır sızıntısı; iki oyun oturumu arasında hafıza sızıntısı; aynı turn'ün yeniden denenmesi; bozuk JSON; string `"false"`; konuşmada verilen ama commit edilmeyen item.

Başarı ölçütü yalnızca “ret oranı düştü” olmasın: masum konuşmanın doğal devamı, gizli bilgi sızıntısı, yetkisiz mutation, yanlış item transferi ve gecikme birlikte izlensin. Qwen3:8b için sonuçlar varsayılmasın; mevcut modeli sabit tutup tek değişkenli karşılaştırma yap.

### 5. Uyarlama sırası

- İlk adım: hiçbir davranışı değiştirmeden gate/fallback izleme ve regresyon senaryoları.
- İkinci adım: bir NPC üzerinde read-only konuşma yolu ve sırları bağlamdan çıkarma.
- Üçüncü adım: sadece bir action türü için typed öneri + deterministik commit.
- Sonraki adım: bellek kapsamını session/NPC kimliğiyle daraltma; ihtiyaç kanıtlanırsa audit/rollback.

Mevcut taşıma tamamlanmadan paralel mimari dönüşüm önermiyorum. Çoklu agent sistemi, yeni framework veya model değişikliği bu sorunu çözmenin önkoşulu değil.

---

# Depo bazında bulgular

## 1. gddickinson/llm_RPG

İncelenen main HEAD: **ad760b3c52db072188e1a79cd1cb2983eb8321e6**, commit tarihi **5 Ağustos 2026 10:57:44 -05:00**. [Commit](https://github.com/gddickinson/llm_RPG/commit/ad760b3c52db072188e1a79cd1cb2983eb8321e6).

### Kısa karar

İki depo içinde AI-DND'nin mevcut sorununa açık ara daha yararlı örnek bu. Python oyun motoruna yerel LLM, NPC başına hafıza, doğrulanan diyalog eylemleri ve sır izinleri gerçekten bağlanmış. Ancak **tam bir güvenlik/kanon doğruluğu çözümü değil**. Özellikle anlatıdan topic state üretmesi ve sosyal check sonucunu modele bırakması aynen taşınmamalı. Pygame/terminal oyununu React projenize taşımak yerine birkaç sınırlandırılmış fikri almak mantıklı.

### Gerçek diyalog akışı

`DialogSystem.player_to_npc` NPC ve yakınlık kontrolünden sonra özel komutları ayırıyor. Normal konuşma structured protocol'e gidiyor; protokol uygulanamazsa eski process/inline diyalog yoluna dönüyor. Cevap günlük ve NPC hafızasına yazılıyor. Yani sadece README'de bir JSON örneği değil, ana konuşma yoluna bağlı uygulanmış sistem. [Akış](https://github.com/gddickinson/llm_RPG/blob/ad760b3c52db072188e1a79cd1cb2983eb8321e6/engine/dialog_system.py#L19-L147).

Kontrat `dialogue`, `mood`, `action`, `action_args` alanlarını ayırıyor. İzinli eylemler ilişki değişimi, envanterden eşya verme, sır açıklama, reddetme ve bitirme ile sınırlı. Bilinmeyen eylem siliniyor; ilişki değişimi ±3'e kırpılıyor; eşya ancak NPC'nin gerçek inventory'sinde bulunursa taşınıyor. Bu, konuşmanın akıcı olmasına izin verirken mekanik yetkiyi backend'de tutmanın iyi, küçük örneği. [Parser ve executor](https://github.com/gddickinson/llm_RPG/blob/ad760b3c52db072188e1a79cd1cb2983eb8321e6/engine/dialog_protocol.py#L108-L190).

Fakat iki ayrım önemli:

1. Eşyanın mevcut olması kontrol ediliyor; NPC'nin bu eşyayı gerçekten bağışlamaya yetkili olması, eşyanın quest için ayrılmış olması, ekonomik limit veya tek-seferlik ödül yetkisi ayrıca kontrol edilmiyor. Model ikna edilirse var olan değerli eşyayı verebilir. Dolayısıyla "envanter uydurmuyor" ile "yetkisiz ödül vermiyor" aynı şey değil.
2. Doğrulanamayan eylem sessizce yok sayılıyor ama aynı model cevabındaki “kılıcı sana verdim” cümlesi düzeltilmiyor. State doğru kalabilir, ekrandaki hikâye yanlış kalabilir. AI-DND'de eylem sonucundan sonra son cümleyi üretmek veya başarısız eylem iddiasını dar kapsamlı düzeltmek daha güvenli.

### Sır kilidi: kelime yasaklamak yerine bilgiyi erişilebilir kılmak

`secrets.py` sırları NPC ID'sine bağlar; affinity, teslim edilmiş quest, oyuncunun taşıdığı item ve skill level koşullarını kodda kontrol eder. Kilitli sırın metni prompt'a eklenmez. Açılabilen sır için de `reveal` tekrar gerçek koşulları denetler ve bilinen sır ID'sini state'e kaydeder. [Koşullar ve açıklama](https://github.com/gddickinson/llm_RPG/blob/ad760b3c52db072188e1a79cd1cb2983eb8321e6/engine/secrets.py#L32-L105).

Bu, sizin "bilmiyorum/doğrulayamıyorum" problemine en doğrudan fikir: tüm cümlenin kelime hazinesini kapatmak yerine, NPC'nin erişebileceği gizli gerçekleri sınırlamak. Selamlaşma, şaka, öfke, tereddüt veya oyuncunun sözünü tartışma sır açıklamak değildir. Bir özel adın konuşmada geçmesi otomatik olarak o adla ilgili yeni kanon yaratmak sayılmamalı.

Sınır: depodaki “injection-proof” ifadesi yalnızca kilitli sır metninin bu prompt yoluna verilmemesi bakımından güçlüdür; modelin tahmin etmesini, oyuncudan gelen metni tekrarlamasını, başka hafıza/bağlam kanallarını veya açık sırdan yeni yanlış sonuç üretmesini genel olarak ispatlamaz. Sır kilidi genel bilgi doğruluğu garantisi değildir.

### Hafıza ve izolasyon

NPC'nin kendi memories listesinden top-k kayıt seçiliyor, kendi son konuşmaları ve kendi opinions alanı prompt'a ekleniyor. Son on konuşma tutuluyor; prompt son dört alışverişi ve dört seçilmiş hafızayı alıyor. Embedding servisi gerektirmeyen basit bir başlangıç. İlginç ayrıntı: açıklama “recency × importance × relevance” dese de gerçek skor **0.4×recency + 0.3×importance + 1.2×relevance**, yani ağırlıklı toplam. [Hafıza uygulaması](https://github.com/gddickinson/llm_RPG/blob/ad760b3c52db072188e1a79cd1cb2983eb8321e6/engine/npc_memory.py#L26-L90), [prompt bağlama](https://github.com/gddickinson/llm_RPG/blob/ad760b3c52db072188e1a79cd1cb2983eb8321e6/engine/dialog_protocol.py#L46-L105).

Birebir alınmaması gerekenler:
- Tokenizer `[a-z']+` ve İngilizce stopword listesi kullanıyor. Türkçe karakterler ve ekler için zayıf; “şövalye”, “görev”, “İstanbul” gibi sözcüklerde bozulma beklenir.
- Ham oyuncu iddiası ile motorun doğruladığı olay aynı serbest metin hafıza kanalına girebiliyor. “Kral bana kaleyi verdi” sözünü hatırlamak, gerçekten mülk devri olduğunu bilmek değildir.
- Günlük reflection LLM'den çıkarım alıp opinions alanına kaydediyor; doğruluk/provenance kontrolü yok. Görüşü dünya gerçeğinden ayrı tutmak gerekir. [Reflection](https://github.com/gddickinson/llm_RPG/blob/ad760b3c52db072188e1a79cd1cb2983eb8321e6/engine/npc_memory.py#L96-L147).
- İzolasyon NPC nesnesi düzeyinde. Buradan çok kullanıcılı backend için campaign/session/tenant izolasyonu sağlandığı sonucu çıkmaz.

Save/load gerçekten mevcut: tam state JSON snapshot, geçici dosya ve `os.replace` ile yazım; NPC memories ve metadata geri yükleniyor. Bu, kalıcılık için iyi örnek, ama event sourcing değildir. [Snapshot yazımı](https://github.com/gddickinson/llm_RPG/blob/ad760b3c52db072188e1a79cd1cb2983eb8321e6/engine/save_load.py#L61-L96), [NPC serileştirme](https://github.com/gddickinson/llm_RPG/blob/ad760b3c52db072188e1a79cd1cb2983eb8321e6/engine/save_load.py#L232-L248), [geri yükleme](https://github.com/gddickinson/llm_RPG/blob/ad760b3c52db072188e1a79cd1cb2983eb8321e6/engine/save_load.py#L417-L430).

### Kritik kanon sınırı: prose bazı state'leri yine etkiliyor

Topic journal event log'a observer olarak bağlı. NPC'nin cevabı event log'a eklenince `scan`, substring keyword eşleşmesinden `topics_known` listesine yeni konu yazar. Oyuncunun kendi konuşma log'u hariç tutulmuş, fakat NPC'nin oyuncu sözünü tekrarlaması veya bir konuyu halüsinasyonla anması hariç tutulmamış. Statik akıştan çıkan sonuç: **ham NPC prose → topic unlock** yolu var. Bu yüzden “LLM ses, motor gerçeklik” ilkesi burada tam kapalı bir sınır değil. [Observer bağlantısı](https://github.com/gddickinson/llm_RPG/blob/ad760b3c52db072188e1a79cd1cb2983eb8321e6/engine/engine_setup.py#L67-L72), [konuşmanın loglanması](https://github.com/gddickinson/llm_RPG/blob/ad760b3c52db072188e1a79cd1cb2983eb8321e6/engine/dialog_system.py#L116-L123), [keyword'den state üretimi](https://github.com/gddickinson/llm_RPG/blob/ad760b3c52db072188e1a79cd1cb2983eb8321e6/engine/topics.py#L40-L70).

AI-DND için bunun tersini öneririm: konuşmada geçen isim journal'a “duyuldu, doğrulanmadı” olarak düşebilir; gerçek bilgi açılması yalnızca doğrulanmış `KnowledgeRevealed` olayıyla yapılmalı. Bu aynı zamanda mevcut lexical gate'in ters yöndeki aşırı bloklamasını da önler.

Global MemoryManager'ın kayıtları tipli olay değil metin + duvar saati; `game_time` None. Ayrıca history trim kodu `add_event` yerine `add_observer` içinde duruyor. Normal olay ekleyişinde büyüme sınırı uygulanmıyor. Bu bir canonical event-store örneği olarak alınmamalı. [MemoryManager](https://github.com/gddickinson/llm_RPG/blob/ad760b3c52db072188e1a79cd1cb2983eb8321e6/engine/memory_manager.py#L25-L55).

### Check, affinity ve validation sorunları

Sosyal eylemler başarısızlık bedeli ve oyun-günü lockout ile uygulanmış. Offline modda zar + stat + ilişki DC karşılaştırması var; LLM modda başarı kararını model veriyor. Daha ciddi olarak parser `bool(data.get("success"))` kullanıyor: JSON boolean false doğru işlerken, JSON string **"false" truthy** olur ve başarı kabul edilir. Bu strict schema yerine truthiness kullanmanın somut hatasıdır. [LLM kararı](https://github.com/gddickinson/llm_RPG/blob/ad760b3c52db072188e1a79cd1cb2983eb8321e6/engine/persuasion.py#L105-L142), [zar yolu](https://github.com/gddickinson/llm_RPG/blob/ad760b3c52db072188e1a79cd1cb2983eb8321e6/engine/persuasion.py#L144-L157).

Normal her konuşma, belirli düşman sınıfları dışında, ayrıca +2 ilişki veriyor. Bu sayede uygun olmayan veya anlamsız konuşma tekrarlarıyla bile sır eşiğine ilerlemek mümkün; özel sosyal eylem lockout'u normal sohbet spam'ini kapatmıyor. [Sohbet bonusu](https://github.com/gddickinson/llm_RPG/blob/ad760b3c52db072188e1a79cd1cb2983eb8321e6/engine/dialog_system.py#L128-L132).

AI-DND'de check sonucu ve ödül motor tarafında kalmalı. Model yalnızca sosyal niyet/ilgili gerekçe önerebilir. Boolean alanları strict doğrulayın; yanlış tipte sonucu başarısız/yok sayılmış teklif olarak ele alın. Aynı event/action ID ikinci kez uygulanmamalı.

### DM yetkileri ve olay mimarisi

Ayrı DM API'nin izinli fonksiyonları, mutation bütçesi, item değeri/monster level/terrain boyutu gibi cap'leri ve kabul/red notebook'u var. Otonom DM günlük küçük komut paketi öneriyor ve aynı API'den geçiriliyor. Bu gerçekten uygulanmış yetki ayrımıdır. Ancak NPC konuşmasının aynı yaratıcı yetkilere sahip olması gerekmiyor. [DM charter uygulaması](https://github.com/gddickinson/llm_RPG/blob/ad760b3c52db072188e1a79cd1cb2983eb8321e6/engine/dm_api.py#L1-L115), [otonom komut dispatch](https://github.com/gddickinson/llm_RPG/blob/ad760b3c52db072188e1a79cd1cb2983eb8321e6/engine/dm_autonomous.py#L51-L95).

Notebook/snapshot olması deterministik replay, atomik transaction veya tam event sourcing olduğu anlamına gelmez. AI-DND'yi yeniden yazmak yerine mevcut state commit noktasına küçük, tipli accepted/rejected action kayıtları eklemek yeterli bir ilk adım.

### Ollama, Qwen3:8b ve maliyet

Ollama provider gerçek HTTP `/api/generate` çağrısı yapıyor; model adı parametreli, default llama3. CLI provider/model seçimi var. Dolayısıyla Qwen3:8b için adaptasyon yüzeyi küçük, fakat **bu commit üzerinde Qwen3:8b ile çalıştığını test etmedim**. [Ollama adapter](https://github.com/gddickinson/llm_RPG/blob/ad760b3c52db072188e1a79cd1cb2983eb8321e6/llm/providers/ollama.py#L20-L48), [CLI](https://github.com/gddickinson/llm_RPG/blob/ad760b3c52db072188e1a79cd1cb2983eb8321e6/main.py#L50-L54), [varsayılanlar](https://github.com/gddickinson/llm_RPG/blob/ad760b3c52db072188e1a79cd1cb2983eb8321e6/config.py#L6-L8).

Adapter doğrudan üst düzey `max_tokens` ve `temperature` gönderiyor; `format` schema/JSON veya `think` ayarı yok. Güncel Ollama API dokümanı yapılandırılmış çıktı için `format`, generation ayarları için `options`, thinking için `think` sunuyor. Bu adapter aynen taşınmamalı; kurulu Ollama/model sürümünüzle resmi alanlar ve JSON doğrulaması ayrı test edilmeli. Burada bir timeout'un Qwen kalitesizliği değil ayar/yükleme süresi olabileceğini de ayırın. [Resmi Ollama API](https://docs.ollama.com/api/generate).

Heuristic mod API ücreti gerektirmiyor; yerel Ollama'nın dış API token ücreti olmasa da donanım/elektrik/gecikme maliyeti var. OpenAI ve Anthropic isteğe bağlı. NPC ambient çağrılarına cooldown, selamlamaya cache konmuş; reflection ise taze hafızası olan her aktif NPC için ayrı çağrı yapabiliyor. Büyük NPC sayısında gecikme/token maliyeti birikir. [Çağrı disiplini](https://github.com/gddickinson/llm_RPG/blob/ad760b3c52db072188e1a79cd1cb2983eb8321e6/engine/llm_budget.py#L1-L67).

Bağımlılıklar requests, pygame, pygame_gui, numpy ve başka yardımcı paketler; React backend için bunları topluca ithal etmek gereksiz. [Requirements](https://github.com/gddickinson/llm_RPG/blob/ad760b3c52db072188e1a79cd1cb2983eb8321e6/requirements.txt#L1-L11).

### Testler ve olgunluk

Bu snapshot'ta 400 adet `test*.py` dosyası var. Özellikle unknown action, olmayan eşya, affinity clamp, kilitli sırın prompt'tan çıkarılması, save/load ve mocked LLM routing testleri gerçekten yazılmış. Test sayısı veya dosya varlığı başarı kanıtı değildir; çalıştırmadım. İncelenen snapshot'ta `.github` workflow dosyası görmedim. [Protokol testleri](https://github.com/gddickinson/llm_RPG/blob/ad760b3c52db072188e1a79cd1cb2983eb8321e6/tests/test_dialog_protocol.py#L11-L150), [sır testleri](https://github.com/gddickinson/llm_RPG/blob/ad760b3c52db072188e1a79cd1cb2983eb8321e6/tests/test_secrets.py#L47-L142).

Lisans dosyası MIT. Bu tespit üçüncü taraf varlıkların, modelin veya D&D içeriklerinin tüm kullanım koşullarını otomatik çözmez. [Lisans](https://github.com/gddickinson/llm_RPG/blob/ad760b3c52db072188e1a79cd1cb2983eb8321e6/LICENSE#L1-L21).

## 2. msadeqsirjani/dnd_ai_dm

İncelenen master HEAD: **db09ab403d234da37446ea4b73e4c3d349c40ece**, commit tarihi **24 Kasım 2024 18:02:55 +01:00**. [Commit](https://github.com/msadeqsirjani/dnd_ai_dm/commit/db09ab403d234da37446ea4b73e4c3d349c40ece).

### Kısa karar

Bu depo işlevsel AI DM mimarisi için değil, çok erken Python modül iskeleti olarak değerlendirilmeli. README'nin NPC yönetimi, doğal komutlar ve combat iddiaları ana oyun döngüsünde karşılığını bulmuyor. Sizin mevcut Python+React/Qwen sisteminizin yerine geçecek veya diyalog sorununu çözecek bir temel değil.

### Ana döngünün gerçekten yaptığı

`start_new_game` GPT'den bir quest metni alıyor, konumu atıyor. `process_command(command)` **command argümanını kullanmıyor**; yalnızca aynı konum için medium zorlukta yeni quest istiyor. Oyuncu “han sahibine merhaba”, “saldır”, “envanter” veya başka bir şey yazsa da model bu girdiyi görmüyor. [GameManager'ın tamamı](https://github.com/msadeqsirjani/dnd_ai_dm/blob/db09ab403d234da37446ea4b73e4c3d349c40ece/core/game_manager.py#L1-L24).

`StoryGenerator` her çağrıda sabit system mesajı ve konum/zorluk prompt'u gönderiyor. `story_context=[]` oluşturulmuş ancak ne dolduruluyor ne API'ye gönderiliyor. NPC bilgisi, önceki konuşma, quest geçmişi, envanter veya doğrulanmış dünya state'i model bağlamında yok. [StoryGenerator](https://github.com/msadeqsirjani/dnd_ai_dm/blob/db09ab403d234da37446ea4b73e4c3d349c40ece/core/story_generator.py#L5-L21).

Bu nedenle burada gördüğünüz akıcı quest metni hafızalı/kurallı DM değildir; ayrı ayrı yapılan hikâye üretim çağrılarıdır.

### NPC kapıları ve açık hatalar

NPC dataclass'ında knowledge listesi ve disposition var. `will_share_info(topic)` tam topic üyeliği ve disposition >50 koşulu döndürüyor. Fakat bu method ana diyalog akışına bağlı değil; gerçek bir LLM knowledge firewall oluşturmuyor. [NPC](https://github.com/msadeqsirjani/dnd_ai_dm/blob/db09ab403d234da37446ea4b73e4c3d349c40ece/models/npc.py#L16-L36).

NPC üretimi human/elf/dwarf arasından seçim yapıyor ama isim şablonunda yalnızca human var. Elf/dwarf seçilirse dictionary erişimi KeyError üretir. Üretilen NPC de `self.npcs` sözlüğüne eklenmeden dönüyor; dolayısıyla `get_npc` kendiliğinden üretilen NPC'yi bulmaz. [NPCManager](https://github.com/msadeqsirjani/dnd_ai_dm/blob/db09ab403d234da37446ea4b73e4c3d349c40ece/core/npc_manager.py#L7-L48).

Sizin projenize çıkarılacak küçük fikir yalnızca “NPC'nin bildiği ve paylaşmaya razı olduğu bilgi ayrı kavramlardır.” Bu kadar basit tek affinity eşiğini doğal sohbetin tamamına uygulamak mevcut aşırı bloklama sorununu daha da büyütebilir.

### Combat, inventory ve world-state

CombatSystem initiative ve basit saldırı hesabı içeriyor; fakat ana GameManager bu sınıfı kullanmıyor. Daha önemlisi NPC savunucu isabet aldığında `defender.modify_hp` çağrılıyor ama NPC sınıfında HP veya modify_hp yok. Düşmana vurma yolu bağlansa çalışmayacak. Ayrıca `1d8 + strength modifier` negatif olabilir; Character.modify_hp negatif hasarın ters işaretiyle iyileşme doğurabilir. Bunlar statik olarak açık boşluklar. [Saldırı](https://github.com/msadeqsirjani/dnd_ai_dm/blob/db09ab403d234da37446ea4b73e4c3d349c40ece/core/combat_system.py#L34-L47), [Character](https://github.com/msadeqsirjani/dnd_ai_dm/blob/db09ab403d234da37446ea4b73e4c3d349c40ece/models/character.py#L1-L18).

Inventory yalnızca string listesine append; sahiplik, adet, transfer veya LLM eylem doğrulaması yok. `WorldState` lokasyon/quest/global-state alanlarını tanımlıyor fakat ana akış quest metnini active_quests'e bağlamıyor. Başlangıç konumu modelde `starting_village`, GameManager'da `starting village`; locations sözlüğü boş kaldığından doğrudan travel kontrolü current-location lookup'ta hata verebilir. [WorldState](https://github.com/msadeqsirjani/dnd_ai_dm/blob/db09ab403d234da37446ea4b73e4c3d349c40ece/models/world_state.py#L13-L34), [başlangıç akışı](https://github.com/msadeqsirjani/dnd_ai_dm/blob/db09ab403d234da37446ea4b73e4c3d349c40ece/core/game_manager.py#L7-L24).

Repo ağacında save/load, event sourcing, transaction/idempotency, canonical state reducer veya oturum izolasyonu uygulaması bulunmadı. Prose gerçek state'e çevrilmiyor; bu güvenli state yönetimi olduğu için değil, oyun uygulaması o noktaya ulaşmadığı için.

### Yerel model, maliyet ve bakım

OpenAI client ve model `gpt-4` sabit; Ollama provider veya parametreli base_url/model seçimi uygulanmamış. `.env` API anahtarı olmadan main başlamıyor. Her quit dışı komut dış API isteği doğuruyor. Güncel fiyat iddiası yapmıyorum; koddan çıkan sonuç token bazlı dış servis bağımlılığı olduğu. Yerel Qwen eklemek mümkün ama sadece URL/model değiştirmek NPC hafızası veya oyun mekanikleri sağlamaz. [API çağrısı](https://github.com/msadeqsirjani/dnd_ai_dm/blob/db09ab403d234da37446ea4b73e4c3d349c40ece/core/story_generator.py#L5-L21), [başlangıç ve loop](https://github.com/msadeqsirjani/dnd_ai_dm/blob/db09ab403d234da37446ea4b73e4c3d349c40ece/main.py#L5-L36).

Requirements eski sabit SDK sürümleri içeriyor; örneğin OpenAI 1.54.5. Bu sürümlerde güvenlik açığı bulunduğu iddiasında bulunmuyorum, audit yapılmadı. README Python 3.8+ derken combat type annotation `Character | NPC` kullanıyor; bu biçim Python 3.10+ beklentisiyle uyumlu, belirtilen tabanla tutarsız. Depoda test dosyası veya CI workflow bulamadım; README'nin “test ekleyin” demesi mevcut test kapsamı demek değil. [README](https://github.com/msadeqsirjani/dnd_ai_dm/blob/db09ab403d234da37446ea4b73e4c3d349c40ece/README.md), [combat annotation](https://github.com/msadeqsirjani/dnd_ai_dm/blob/db09ab403d234da37446ea4b73e4c3d349c40ece/core/combat_system.py#L34-L35), [requirements](https://github.com/msadeqsirjani/dnd_ai_dm/blob/db09ab403d234da37446ea4b73e4c3d349c40ece/requirements.txt).

Lisans dosyası MIT. [Lisans](https://github.com/msadeqsirjani/dnd_ai_dm/blob/db09ab403d234da37446ea4b73e4c3d349c40ece/LICENSE#L1-L21).


---

## 3. DungeonMind

### İncelenen sürüm ve gerçek mimari

Depo: guzmanvitar/dungeonmind-llm-rpg-adventure. İncelenen varsayılan dal HEAD: **f1eb7dd1dfdcb0e01791870167eb98dd77fa3bd9**, commit zamanı **25 Şubat 2025, 14:33:46 UTC**. [Commit](https://github.com/guzmanvitar/dungeonmind-llm-rpg-adventure/commit/f1eb7dd1dfdcb0e01791870167eb98dd77fa3bd9).

FastAPI + SQLAlchemy/SQLite arka uç, Flask/HTML/JS ön yüz, FAISS + NetworkX kampanya hazırlama hattı. React değil. Python benzerliği taşımayı kolaylaştırabilir fakat buradaki uygulama bütün olarak AI-DND’nin yerine konmamalı. [Bağımlılıklar](https://github.com/guzmanvitar/dungeonmind-llm-rpg-adventure/blob/f1eb7dd1dfdcb0e01791870167eb98dd77fa3bd9/pyproject.toml#L1-L40).

`/chat` önce veritabanındaki ilk karakteri kontrol ediyor, sonra global active_campaign.txt dosyasını kontrol ediyor, ardından geçmişi modele verip serbest metin döndürüyor. Kampanya/NPC bazlı yetkilendirilmiş aksiyon çözücü yok; endpoint’in normal tur kısmında inventory/HP reducer veya dice adjudicator çağrısı bulunmuyor. Bu sınırlama doğrudan kontrol akışından geliyor. [Tur hattı](https://github.com/guzmanvitar/dungeonmind-llm-rpg-adventure/blob/f1eb7dd1dfdcb0e01791870167eb98dd77fa3bd9/src/backend/orchestrator/main.py#L53-L83).

### NPC diyalogları ve kanon

NPC’lerin farklı kişilikte konuşması, oyuncuya bilgiyi bedelsiz vermemesi, fizik/magic kısıtlarına uyması, envanterde olmayan silahı kullanmaması sistem prompt’una yazılmış. Bunlar deterministik kontroller değil. Kullanıcının katı lexical gate sorununa hazır alternatif bir bilgi-yetki katmanı sunmuyor; daha çok genel DM talimatları sunuyor. [DM prompt’u](https://github.com/guzmanvitar/dungeonmind-llm-rpg-adventure/blob/f1eb7dd1dfdcb0e01791870167eb98dd77fa3bd9/src/backend/llm-services-config.yaml#L19-L76).

Kampanya üretilirken bütün hikâye `system` rolünde istemciye metadata olarak dönüyor; “gelecekteki olayları açıklama” deniyor. Sunucuda üretilen tam hikâyeyi karakterin bilebildiği parçalara bölen mekanizma değil, modele verilen bir sır saklama talimatı. [Kampanya metadata’sı](https://github.com/guzmanvitar/dungeonmind-llm-rpg-adventure/blob/f1eb7dd1dfdcb0e01791870167eb98dd77fa3bd9/src/backend/game_dynamics/campaign_creation.py#L281-L335).

**Alınabilecek küçük fikir:** NPC sesini ve kısa yanıt tarzını prompt’ta belirlemek. **Alınmaması gereken yaklaşım:** “HP ve inventory’yi titizlikle takip et” demeyi state güvenliği sanmak.

### Hafıza ve oturum izolasyonu

`active_campaign_chat_history.json` tek global dosya. Önce disk geçmişi okunup istemcinin son iki mesajı eklenerek kaydediliyor; fakat modele dönen bağlam disk geçmişi değil, `request.conversation_history` veya onun özeti. Dolayısıyla kalıcı kayıt ile sonraki çağrıda kullanılan otoriter bağlam aynı kaynak değil. İstemcinin gönderdiği rol/içerik listesi üzerinde sıkı rol/kimlik doğrulaması bu modelde yok. [Geçmiş yönetimi](https://github.com/guzmanvitar/dungeonmind-llm-rpg-adventure/blob/f1eb7dd1dfdcb0e01791870167eb98dd77fa3bd9/src/backend/game_dynamics/game_state_manager.py#L11-L90), [istek modeli](https://github.com/guzmanvitar/dungeonmind-llm-rpg-adventure/blob/f1eb7dd1dfdcb0e01791870167eb98dd77fa3bd9/src/backend/orchestrator/models.py#L6-L16).

Özetleme 16 non-system mesaj eşiğinde gerçekleşiyor; son dört mesaj korunuyor, önceki non-system mesajlar özetlenip yeni bir system mesajına dönüşüyor. Bütün eski system mesajları korunuyor. Uzayan kampanyada eski özetlerin birikmesi ve modelin tahminlerinin yüksek öncelikli bağlama yükselmesi riski var. Ayrıca bu gerçek token bütçesi değil, mesaj sayısı eşiği. Aynı dosyaya düz `open(..., 'w')` ile yazılıyor, görünür atomic write/locking yok. [Özet ve yazma](https://github.com/guzmanvitar/dungeonmind-llm-rpg-adventure/blob/f1eb7dd1dfdcb0e01791870167eb98dd77fa3bd9/src/backend/game_dynamics/game_state_manager.py#L23-L60).

Global aktif kampanya ve `Character.first()` düzeni tek kullanıcı prototipine uygun olabilir; çoklu kampanya veya eşzamanlı kullanıcı izolasyonuna örnek alınmamalı. Kullanıcının uygulamasında en az campaign_id + session_id + npc_id + scope + state_version anahtarları ayrı tutulmalı.

### Gerçek kurallar, inventory ve doğrulama

Karakter oluşturma gerçekten uygulanmış: modelden JSON alınıyor; race/class/background izinli veritabanı değerlerine göre daraltılıyor; HP, başlangıç altını, sınıf/geçmiş ekipmanı backend’de hesaplanıp DB’ye yazılıyor. Bu, modelin önerisini izinli seçeneklerle sınırlama açısından yararlı bir küçük örnek. [Parsing ve doğrulama](https://github.com/guzmanvitar/dungeonmind-llm-rpg-adventure/blob/f1eb7dd1dfdcb0e01791870167eb98dd77fa3bd9/src/backend/game_dynamics/character_creation.py#L67-L135), [karakter hesapları](https://github.com/guzmanvitar/dungeonmind-llm-rpg-adventure/blob/f1eb7dd1dfdcb0e01791870167eb98dd77fa3bd9/src/backend/game_dynamics/character_creation.py#L136-L219).

Somut kod kusuru: `armor_items` yalnızca `category == 'Armor'` olanları seçiyor; aynı nesnede daha sonra `category == 'Light Armor'` veya `'Medium Armor'` aranıyor. Bu dallar o filtreden geçen nesne için erişilemez. AC kural kodunu aynen kopyalamamak gerekir. Aynı bölüm inventory nesnelerini set ile birleştiriyor; adet modeli yerine benzersiz ekipman listesi yaklaşımı var. [İlgili satırlar](https://github.com/guzmanvitar/dungeonmind-llm-rpg-adventure/blob/f1eb7dd1dfdcb0e01791870167eb98dd77fa3bd9/src/backend/game_dynamics/character_creation.py#L158-L197).

README başta “D&D Rule Enforcement” diyor; ama aşağıdaki roadmap’te explicit inventory/spell tracking, dice roll mechanics, NPC ve shared world state henüz yapılacak iş olarak işaretli. Gerçek kodla tutarlı okuma şudur: başlangıç karakteri vardır, bütün oyun boyunca güvenilir mekanik otorite henüz yoktur. [Roadmap](https://github.com/guzmanvitar/dungeonmind-llm-rpg-adventure/blob/f1eb7dd1dfdcb0e01791870167eb98dd77fa3bd9/README.md#L134-L170).

### RAG ve yerel model

FAISS/NetworkX kullanımı gerçek; kampanya yeri ve ilgili NPC/yaratık/eşya/kültür parçaları seçiliyor. Ancak bu, her NPC cümlesine erişim kontrolü yapan bir runtime lore doğrulayıcı değil. Modelin seçtiği yer adı exact-match ile adaylardan aranıp `[0]` alınıyor; eşleşmeyen model çıktısı için bu noktada sağlam geri dönüş yok. [Yer seçimi](https://github.com/guzmanvitar/dungeonmind-llm-rpg-adventure/blob/f1eb7dd1dfdcb0e01791870167eb98dd77fa3bd9/src/backend/game_dynamics/campaign_creation.py#L148-L199). FAISS yerel yüklemede dangerous deserialization açık; yalnızca güvenilen indeksler kullanılmalı. [İndeks yükleme](https://github.com/guzmanvitar/dungeonmind-llm-rpg-adventure/blob/f1eb7dd1dfdcb0e01791870167eb98dd77fa3bd9/src/backend/game_dynamics/campaign_creation.py#L43-L79).

Yerel backend sınıfı var, fakat adı Mixtral iken varsayılan model Mistral-7B. Hugging Face Transformers ile CPU float32 yükleme yapıyor; tokenizer input cihazını CUDA varsa CUDA seçiyor. GPU bulunan sistemde model-input device uyumu ayrıca doğrulanmalı. Ollama adapter’i veya Qwen3:8b’ye özgü destek incelenen servis factory’sinde yok. Üstelik normal /chat GPT-4’e, karakter oluşturma GPT-3.5’e sabit. “Local modeller desteklenir” ibaresi “Qwen3:8b ile tak-çalıştır” demek değil. [Servisler](https://github.com/guzmanvitar/dungeonmind-llm-rpg-adventure/blob/f1eb7dd1dfdcb0e01791870167eb98dd77fa3bd9/src/backend/orchestrator/services.py#L143-L233), [factory](https://github.com/guzmanvitar/dungeonmind-llm-rpg-adventure/blob/f1eb7dd1dfdcb0e01791870167eb98dd77fa3bd9/src/backend/orchestrator/services.py#L252-L313).

### Bağımlılıklar, testler ve lisans

OpenAI metin ve embedding API’si kullanılıyor; kampanya hazırlama birden fazla üretim çağrısı ve retrieval sorgusu yapıyor. Yerel model yoluna geçmek embedding bağımlılığını kendiliğinden ortadan kaldırmıyor. Torch/Transformers servis modülünde top-level import olmasına rağmen pyproject’te dev grubunda; production-only dependency kurulumunda import hatası riski var. [Bağımlılıklar](https://github.com/guzmanvitar/dungeonmind-llm-rpg-adventure/blob/f1eb7dd1dfdcb0e01791870167eb98dd77fa3bd9/pyproject.toml#L7-L40).

İncelenen testler karakter parsing üzerine; GPT-3.5 çağırıyor, bazı beklentileri GPT-4’e “YES/NO” olarak değerlendirtiyor. Bunlar offline deterministik state regresyon testleri değil; API maliyeti/erişimi ve model değişkenliği taşıyor. [Test](https://github.com/guzmanvitar/dungeonmind-llm-rpg-adventure/blob/f1eb7dd1dfdcb0e01791870167eb98dd77fa3bd9/tests/backend/game_dynamics/test_character_creation.py#L26-L65).

**Lisans çelişkisi:** README MIT yazıyor; gerçek LICENSE GNU GPL version 3 metni. MIT varsayımıyla kod kopyalamayın; lisans belirsizliğini repo sahibinden netleştirmek gerekir. Bu bir hukuki yorum değil, iki dosyanın çeliştiği kaynak bulgusudur. [README](https://github.com/guzmanvitar/dungeonmind-llm-rpg-adventure/blob/f1eb7dd1dfdcb0e01791870167eb98dd77fa3bd9/README.md#L182-L183), [LICENSE](https://github.com/guzmanvitar/dungeonmind-llm-rpg-adventure/blob/f1eb7dd1dfdcb0e01791870167eb98dd77fa3bd9/LICENSE#L1-L5).

**Karar:** Kampanya hazırlama ve izinli karakter seçenekleri açısından okunur. Kullanıcının NPC gate sorununu çözmek veya güvenilir canon motoru kurmak için ana referans olarak önermiyorum.

## 4. NarrativeEngine-P

### İncelenen sürüm ve mimari

Depo: Sagesheep/NarrativeEngine-P. İncelenen HEAD: **a5020b93fccd56ea91a5b1b2dd30053b35c5a66b**; author zamanı **16 Ekim 2026, 04:50:18 UTC**, committer zamanı **04:53:05 UTC**. [Commit](https://github.com/Sagesheep/NarrativeEngine-P/commit/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b).

React 19/TypeScript/Zustand/Vite, Express, better-sqlite3 + sqlite-vec, yerel ONNX embedding ve ortak `packages/engine` modülleri. Python değil; React tarafı yakın olsa da bütün backend’i taşımak kullanıcının mevcut mimarisini gereksiz büyütür. package 2.0.1 iken README başlığı 2.0.0: değerlendirmeyi sürüm etiketi yerine commit’e sabitledim. [package.json](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/package.json#L1-L38).

### NPC bilgisini kelime yasakları yerine kapsamla sınırlama

En değerli parça `knownBy` semantiği: undefined public; boş liste secret; `npc:<id>`, `faction:<name>` ve player token’ları var. On-stage NPC bilip bilmiyor sorgusu saf fonksiyon. Player’ın bilmesi NPC’nin de bildiği anlamına gelmiyor. Bu, “kelime lore’da geçmiyorsa reddet” yaklaşımına göre çok daha doğru bir bilgi modellemesi. [knowledgeScope](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/src/services/campaign-state/knowledgeScope.ts#L3-L13), [görünürlük hesaplama](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/src/services/campaign-state/knowledgeScope.ts#L119-L169).

Prompt assembly’de public facts cacheable canon bölümüne, scoped facts sahneye özgü volatile bölüme ayrılıyor. Yalnızca sahnedeki bir NPC’nin bildiği olgular scoped block’a giriyor. Cast değişince cache’in bilgi sızdıracak şekilde tekrar kullanılması riskini düşünmüş olması iyi. [world.ts](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/src/services/payload/world.ts#L503-L547), [public-only filtre](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/src/services/campaign-state/divergenceRegister.ts#L165-L188).

**Ama tam izolasyon değil:** `buildKnowledgeBoundary` NPC’nin bulunmadığı önemli sahneleri ve bilmediği facts metinlerini yine prompt’a “bunları bilmiyorsun” diye koyabiliyor. En fazla beş örnek seçiliyor. Bu, aynı modelin bütün sırları bilip rol gereği saklaması demek; görünürlük ACL’siyle gizli verinin modele hiç verilmemesi demek değil. Çok NPC’li tek GM çağrısında sahnedeki birinin bildiği sır diğerinin üretimine de görünür olabilir. [Bilgi sınırı metni](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/src/services/npc/npcBehaviorDirective.ts#L186-L247), [gerçek payload çağrısı](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/src/services/payload/world.ts#L440-L470).

AI-DND için uyarlama: konuşan NPC’ye sadece bilebileceği facts gönder; gizli fact’in metnini negatif örnek diye bile gönderme. Ayrı GM planlayıcı gerekiyorsa onun erişimini NPC konuşmacısından ayır. Yetkisiz soruda bütün cevabı kalıp reddetmek yerine yalnızca istenen gizli iddiayı söyleme; NPC’nin görünür amacı, tavrı ve gündelik konuşması devam etsin.

### Doğal kişilik, tepki ve gate ayrımı

NPC core/extended bağlam, amaçlar, voice, boundaries, affinity/personality ve reaction menu var. Tepki menüsü motorca puanlanıyor; hikâye modelinden bir tanesini canlandırması isteniyor. Bunu seçilmiş davranış niyeti + serbest ifade olarak almak yararlı. Fakat “do NOT invent a softer reaction” cümlesi de halen prompt düzeyinde; zorunlu output validator değil. Ayrıca üretim path’inde reaction context varsayılan peaceful kalıyor; encounter/combat state bağlantısının henüz yapılmadığı yorum ve çağrıda açık. [Reaction menu](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/src/services/npc/npcBehaviorDirective.ts#L101-L131), [çağrı](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/src/services/payload/world.ts#L458-L467).

Bir kenar durum da görünür: legacy affinity yoksa `affinityDescriptor(undefined)` karşılaştırmalarının hepsi false olup “Devoted” dönüşüne düşüyor; kaynak yorumu bunu eski davranış olarak koruduğunu söylüyor. Bu küçük ayrıntı bile büyük NPC sistemini doğrudan kopyalamak yerine sade bir profil sözleşmesinin niçin daha güvenli olduğunu gösteriyor. [Affinity fallback](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/src/services/npc/npcBehaviorDirective.ts#L9-L45).

### RAG bütçesi, hafıza ve Türkçe

Lexical IDF + embedding rank fusion + recommender adayları, relevance floor ve bağlantılı entity çekme uygulanmış. Default IDF-RRF path’i en üst ilgili parçayı bütçeyi aşsa bile alıyor; zayıf her keyword eşleşmesini doldurmak yerine top-N/iki kanal/recommender ölçütü kullanıyor. Bu bir retrieval filtresi, NPC konuşma yasağı değil. [Ranking ve budget](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/src/services/lore/loreRetriever.ts#L262-L336).

Lean %5, balanced %10, deep %15 context payı ve min/max tavanları var. Faydalı fikir “sahneye göre az bağlam”; sayıların Qwen3:8b’ye aynen uyması kanıtlanmış değil. En iyi chunk’ın tavanı aşabilmesi nedeniyle toplam prompt bütçesi ayrıca korunmalı. [Budget profilleri](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/src/services/lore/loreBudget.ts#L30-L51).

Türkçe için somut dikkat: `searchLoreByQuery` İngilizce stop-word listesi ve `[^a-z0-9]` temizlemesi kullanıyor; Türkçe harfleri düşürüyor. Knowledge subject slug normalizasyonu da ASCII odaklı. Bu algoritmayı Türkçe AI-DND’ye aynen taşımak false-negative ve çakışma üretebilir. Unicode-aware normalizasyon, gerçek entity ID ve Türkçe test seti gerekir. [Query parsing](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/src/services/lore/loreRetriever.ts#L395-L429), [subject token](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/src/services/campaign-state/knowledgeScope.ts#L39-L51).

Yerel embedding modeli mxbai-embed-large-v1, q8, 1024 boyut, CPU; cold-load ve indexing maliyeti gerçek. SQLite vector sorguları campaign_id ile sınırlı. Bu izolasyon faydalı, fakat kapsam boş liste olduğunda “scope yok, hepsi” anlamını kullanan helper NPC erişim kontrolü için kopyalanmamalı; campaign sınırı yine korunur, boş alt kapsam sınırı korunmaz. [Embedder](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/server/lib/embedder.js#L5-L8), [model yükleme](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/server/lib/embedder.js#L65-L76), [scope helper ve sorgular](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/server/lib/vectorStore.js#L334-L403).

### Üretim, commit ve kalıcılık

Önemli güçlü yön: GM cevabı üretildiği an ile sonucun kalıcı arşive işlendiği an ayrılmış. Pending turn diske yazılıyor, birden fazla eşzamanlı commit tek promise paylaşarak duplicate işleme engel oluyor; başarısız commit yeniden denenecek marker’ı koruyor. Restart sonrası recovery var. [Pending persist](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/src/services/turn/pendingCommit.ts#L110-L131), [single-flight](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/src/services/turn/pendingCommit.ts#L296-L319), [başarı/başarısızlık ayrımı](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/src/services/turn/pendingCommit.ts#L399-L480).

Post-turn archive response kaybolduğunda son sahneyi kontrol edip yeniden append etmemeye çalışıyor. Background callback’lerde campaign değiştiyse yazma durduruluyor. Disk dosyası temp + rename ile atomic yazılıyor. Bunlar AI-DND’ye düşük riskle aktarılabilecek somut korumalar. Ancak bu parçaların varlığı bütün envanter, lore, ilişki, timeline değişikliklerinin tek ACID transaction olduğu anlamına gelmez. [Archive recovery](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/src/services/turn/postTurnPipeline.ts#L175-L225), [campaign guard](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/src/services/turn/tracks/guarded.ts#L1-L27), [atomic write](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/server/lib/fileStore.js#L84-L119).

**Event-sourcing ayrımı:** Kaynakta sahne arşivi, event hooks, snapshots/recovery ve lifecycle facts var. İncelenen hatları “bütün world state sadece doğrulanmış immutable domain event’lerden yeniden kurulur” anlamında tam event-sourced motor diye nitelemiyorum. Scene prose da kalıcı kaynak; birçok güncelleme LLM extraction ve store mutation ile geliyor.

### Kanonik olgular, envanter ve gerçek zar

Divergence register’da typed state slot ve supersession var: sadece aynı stateKey’de aktif, unpinned fact replace edilebiliyor. Bu iyi bir daraltma. Ama geçersiz replacement yeni active additive fact olarak ekleniyor; dolayısıyla çelişkiyi tamamen reddetmek yerine biriktirebilir. AI-DND’de yetkisiz/çelişkili değişikliği “kanıtlanmış yeni fact” olarak değil rejected/proposed olarak tutmak daha doğru. [Lifecycle merge](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/src/services/campaign-state/divergenceRegister.ts#L90-L161).

**En önemli alınmaması gereken davranış:** inventory scanner son 15 mesajı ve mevcut inventory’yi modele gönderiyor, JSON array içindeki add/remove/update/consume/equip işlemlerini uyguluyor. Bookkeeping track sonucu otomatik store’a yazıyor. Modelin metinden çıkardığı operasyon ile oyunun izin verdiği state mutation arasında güçlü yetki/kanıt/DC/kaynak denetimi bu hatta görünmüyor. [Scanner](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/src/services/inventoryParser.ts#L29-L60), [operation uygulama](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/src/services/inventoryParser.ts#L63-L136), [otomatik track](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/src/services/turn/tracks/postCommit/inventoryScanTrack.ts#L7-L35).

Özel doğrulama açığı örneği: `consume` miktarı pozitif integer olarak runtime doğrulanmadan mevcut qty’den çıkarılıyor; negatif qty büyümeye yol açabilir. `update` qty için alt sınır var, fakat action/alan sözleşmesi TypeScript type düzeyinde; JSON parse’dan sonra şema validator’ı yok. Bunun exploit edildiğini test etmedim; statik aritmetik ve kontrol akışı bulgusu. Prompt’taki oyuncu iddiası ile gerçekleşmiş, yetkili olayın ayrımı özellikle önemli.

Zar tarafı yalnızca prompt değil: `Math.random` ile gerçek sayılar oluşturuluyor, advantage/disadvantage ve toplama uygulanıyor. Ancak bu “bütün D&D 5e kuralları eksiksiz motorca uygulanıyor” anlamına gelmez; sonuçların model tarafından anlatıya doğru yansıtılması ayrı test gerektirir. [Zar motoru](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/packages/engine/src/rolls/engineRolls.ts#L16-L77).

### Ollama / Qwen3:8b uyumu ve maliyet

Native Ollama formatı gerçek: localhost:11434 algılama, `/api/chat`, `/api/tags`, içerik ayrıştırma var; model adı ayardan geliyor. Bu DungeonMind’den çok daha yakın bir yerel kullanım yolu. Fakat incelenen kaynakta Qwen3:8b’ye özel başarılı test veya benchmark doğrulamadım. [Adapter](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/src/utils/llmApiHelper.ts#L55-L108).

İki önemli adapter sınırı: native Ollama için `tools` body’ye eklenmiyor; bu nedenle genel “GM tool calling” özelliği bu yol üzerinden aynı şekilde taşınmıyor. Thinking açıkken `think=true` ve num_predict veriliyor; off durumunda Ollama için açık `think=false` ataması bu builder’da yok. Dolayısıyla UI’da off seçmenin Qwen’in native düşünme davranışını kesin kapattığı varsayılmamalı. Sampling alanlarının çoğu top-level yazılıyor; yerel sürümde etkilerinin ayrı contract testi yapılması gerekir. [Request body](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/src/utils/llmApiHelper.ts#L340-L412).

Uygulama self-hosted olabilir; bulut provider seçilirse prompt o provider’a gider ve maliyet doğar. “No cloud” sloganı koşulsuz veri dışarı çıkmaz garantisi değildir. Local embedding ve local Qwen seçildiğinde API kullanım maliyeti yerine RAM/CPU/GPU, model indirme, token budget ve çok aşamalı arka plan üretim yükü vardır. Inventory scan gibi gerçek ek model çağrıları kaynakta açık; lite/pro/max ve feature toggles göz önüne alınmadan “bir tur bir çağrı” varsaymayın. Tam fiyat veya gecikme ölçülmedi.

### Test olgunluğu ve lisans

Recursive kaynak ağacında mobile hariç `.test`/`.spec` JS/TS/TSX adlandırmalı **453 dosya** bulundu. Bu test case sayısı veya başarı oranı değil. Vitest/Playwright/Supertest araçları paket içinde. İncelediğim durable-commit testleri crash recovery, başarısız archive’ın retry edilmesi, kayıp cevabın duplicate oluşturmasının engellenmesi ve legacy history’nin korunmasını kapsıyor. Single-flight testi eşzamanlı iki commit’i özel olarak ele alıyor. [Durable tests](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/src/services/turn/__tests__/durableCommit.test.ts#L105-L240), [concurrency tests](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/src/services/turn/__tests__/commitSingleFlight.test.ts#L69-L126).

İncelenen tree’de `.github/workflows` görünmedi; bu testlerin otomatik CI’da çalıştığını doğrulamadım. Testlerin çokluğu üretim güvenliğinin, Türkçe NPC kalitesinin veya model hallüsinasyon güvenliğinin kanıtı değildir. Depo LICENSE dosyası MIT ve README ile tutarlı. [LICENSE](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/LICENSE#L1-L21).

**Karar:** En güçlü teknik ilham kaynağı. Özellikle knowledge scope, prompt katmanlama, commit/recovery ve test senaryoları alınmalı. Dev NPC agency/arc/mod sistemlerini ve automatic prose bookkeeping’i topluca taşımak yerine küçük bir vertical slice seçilmeli.


---

## 5. Axidify/ai-dnd-rpg

İncelenen main HEAD: [395f86a441984c9a2c91272ef2a502f2553d93e3](https://github.com/Axidify/ai-dnd-rpg/commit/395f86a441984c9a2c91272ef2a502f2553d93e3), commit tarihi 15 Ekim 2026 05:52:46 UTC. Bu projeyi yalnız eski Gemini demosu olarak değerlendirmek yanlış: güncel kaynakta Python/Flask + React, vLLM/OpenAI-compatible istemci, world-state ve memory katmanları mevcut.

### Kısa karar

Bu iki repo içinde mevcut Python+React AI-DND'ye en doğrudan fikir sağlayanı Axidify. Fakat alınacak şey bütün oyun/prompt/keyword sistemi değil: **motorun kararı önce vermesi, anlatıcıya yalnız kanonik sonuçların sunulması ve değişikliklerin motor tarafından doğrulanması**. Doğal NPC sohbeti sorununu çözmüş, kopyalanmaya hazır referans olarak görmüyorum. Bazı katı gate'leri sizin “bilmiyorum/doğrulayamıyorum” problemine çok benzer sonuçlar doğurabilir.

### Gerçek uygulama: iki aşama ve durum otoritesi

`start_turn` önce oyuncu aksiyonunu kaydeder. Senaryo etkileşimi eşleşirse zar ve etkiler Python tarafında çözülür; anlatıcıya gerçekleşmiş sonuç verilir. Ardından hostile-action, premise-check, arbiter ve sahne kuralları gelir. Bu yalnız dokümantasyon söylemi değil, çalışan akışın kod organizasyonu. [turn_service.py 252–320](https://github.com/Axidify/ai-dnd-rpg/blob/395f86a441984c9a2c91272ef2a502f2553d93e3/src/turn_service.py#L252-L320)

`world_state` esir/özgür NPC durumu, konum, takipçiler ve tamamlanan etkileşim ID'lerini tutuyor. Etkileşim yaklaşımı gereken eşya/takipçi ile süzülüyor; başarı olunca izinli effect türleri uygulanıyor. Serbest metin bir kilidi açılmış yapmıyor. Örneğin esiri kurtarmanın başarısızlığı, anlatıcının başarısını uydurmasından önce belirleniyor. [world_state.py 140–235](https://github.com/Axidify/ai-dnd-rpg/blob/395f86a441984c9a2c91272ef2a502f2553d93e3/src/world_state.py#L140-L235)

Bu, tam event-sourcing değil. Mutable snapshot + kısa chronicle + istemciye dönen olaylar var. Chronicle 40 kayıtla sınırlı, prompt'a son 15 kayıt giriyor; replay için eksiksiz, değişmez olay deposu veya version/CAS işlem protokolü olarak okunmamalı. [world_memory.py 21–25 ve 109–120](https://github.com/Axidify/ai-dnd-rpg/blob/395f86a441984c9a2c91272ef2a502f2553d93e3/src/world_memory.py#L21-L120)

### Lexical gate gerçekte ne yapıyor?

Dört farklı mekanizmayı ayırmak önemli:

1. **Action sınıflandırma:** `dm_arbiter` kelime gruplarıyla pazarlık, tehdit, aldatma, fiziksel eylem için skill-check seçiyor. Basit bilgi isteme için açık no-roll kuralı var. Bu tek başına lore cevabını reddetme filtresi değil. [dm_arbiter.py 154–220](https://github.com/Axidify/ai-dnd-rpg/blob/395f86a441984c9a2c91272ef2a502f2553d93e3/src/dm_arbiter.py#L154-L220)
2. **Premise kontrolü:** `analyze_action`, mevcut olmayan eşya/NPC veya yanlış ceset varsayımını işaretliyor. `blocks_roll=True` olduğunda `start_turn`, `finished=False` ile anlatıcıya devam ediyor. Yani çoğunlukla “konuşmayı sustur” değil “bu varsayıma mekanik başarı verme” sınırı. Bu ayrım sizin projeye aktarılmaya değer. Bununla birlikte eşleme İngilizce kelime/alias/iyelik regex'lerine dayanıyor; bir nesneyi kullanmak, hakkında soru sormak, alıntı yapmak ve varsayım kurmak her yerde semantik olarak ayrıştırılmıyor. Türkçeye liste çevirerek taşımak yeterli değil. [world_model.py 201–281](https://github.com/Axidify/ai-dnd-rpg/blob/395f86a441984c9a2c91272ef2a502f2553d93e3/src/world_model.py#L201-L281), [turn_service.py 303–311](https://github.com/Axidify/ai-dnd-rpg/blob/395f86a441984c9a2c91272ef2a502f2553d93e3/src/turn_service.py#L303-L311)
3. **Gerçek sosyal engelleme:** Başarısız sosyal check sonrası engelleme ve toplam üç failure'da game-over var. Kod yorumu “iki failure” diyor fakat uygulama `npc_context` varsa ilk failure'da blocked set'e ekliyor. Daha önemlisi, NPC ID yerine konum ve aktif görev adlarından kurulan context string kullanılıyor. Aynı konumdaki farklı NPC'ler aynı bloke bağlamını paylaşabilir. Bu gate yalnız sosyal-check yolunda çağrılıyor, her selamlaşmayı kapattığı ileri sürülmemeli. [api_server.py 342–381](https://github.com/Axidify/ai-dnd-rpg/blob/395f86a441984c9a2c91272ef2a502f2553d93e3/src/api_server.py#L342-L381), [dm_scene.py 486–516](https://github.com/Axidify/ai-dnd-rpg/blob/395f86a441984c9a2c91272ef2a502f2553d93e3/src/dm_scene.py#L486-L516), [turn_service.py 314–318](https://github.com/Axidify/ai-dnd-rpg/blob/395f86a441984c9a2c91272ef2a502f2553d93e3/src/turn_service.py#L314-L318)
4. **Prompt düzeyinde aşırı kısıt:** Bilinmeyen kişi/yer sorularında NPC'nin bilmediğini söylemesi doğrudan isteniyor. Daha ileride isimsiz figüranlara izin verilmesi, baştaki geniş “yeni NPC üretme” yasağıyla gerilim yaratıyor. Bu prompt'u aynen almak doğal sohbet problemini çözmez. [dm_engine.py 41–67](https://github.com/Axidify/ai-dnd-rpg/blob/395f86a441984c9a2c91272ef2a502f2553d93e3/src/dm_engine.py#L41-L67), [dm_engine.py 238–263](https://github.com/Axidify/ai-dnd-rpg/blob/395f86a441984c9a2c91272ef2a502f2553d93e3/src/dm_engine.py#L238-L263)

`dm_scene` ayrıca belirli arama kelimelerini zorunlu Investigation/Perception DC12'ye dönüştürüyor; serbest sohbet içinde geçen “secret” gibi kelimeler eylem niyetiyle karışabilir. Sonuç anlatımının “yeterli” olup olmadığını da İngilizce kelime listeleriyle ölçüyor. Bunlar Türkçe Qwen çıktıları için hazır çözüm değil. [dm_scene.py 91–129 ve 173–204](https://github.com/Axidify/ai-dnd-rpg/blob/395f86a441984c9a2c91272ef2a502f2553d93e3/src/dm_scene.py#L91-L204), [dm_scene.py 398–444](https://github.com/Axidify/ai-dnd-rpg/blob/395f86a441984c9a2c91272ef2a502f2553d93e3/src/dm_scene.py#L398-L444)

### Hafıza ve bağlam izolasyonu

Olumlu: Her NPC için kısa, deduplikasyonlu, sınırlı memory listesi; attitude adımı tag başına ±15; yalnız sahnede/partide olan NPC'lere memory-write; otomatik görev/parti olaylarının motor tarafından kaydı; save/load'da NPC anıları, gifts, attitude, world ve chronicle'ın korunması var. [world_memory.py 52–103](https://github.com/Axidify/ai-dnd-rpg/blob/395f86a441984c9a2c91272ef2a502f2553d93e3/src/world_memory.py#L52-L103), [turn_service.py 681–690](https://github.com/Axidify/ai-dnd-rpg/blob/395f86a441984c9a2c91272ef2a502f2553d93e3/src/turn_service.py#L681-L690), [game_mechanics.py 225–294](https://github.com/Axidify/ai-dnd-rpg/blob/395f86a441984c9a2c91272ef2a502f2553d93e3/src/game_mechanics.py#L225-L294)

Sınırları:
- Memory fact doğrulaması hakikati doğrulamıyor; NPC var mı, sahnede mi, metin kısa mı gibi kontroller var. Modelin uydurduğu bir “anı” epistemik gerçeğe dönüşebilir.
- Attitude sınırı tag başına; aynı çıktıda çok sayıda tag toplam değişimi büyütebilir. Prompt'taki “1–2 tag” motor kotası değildir.
- Tek anlatıcı, sahnedeki NPC'lerin ayrıntılarını ve diğer NPC'lerin son anısını aynı briefing'de görüyor. Bu DM için makul olabilir, ama “NPC A, NPC B'nin özel bilgisini bilemez” garantisi değil. [world_memory.py 185–213](https://github.com/Axidify/ai-dnd-rpg/blob/395f86a441984c9a2c91272ef2a502f2553d93e3/src/world_memory.py#L185-L213)
- Stateful VllmChat mesaj listesi her tur büyüyor; burada token-budget/özetleme/truncation görülmüyor. Statik prompt builder'ın son 10 mesajı alması, stateful chat'in otomatik bounded olduğu anlamına gelmiyor. İlk talimatlar gerçek system-role yerine user-role içinde başlatılıyor. [llm_client.py 94–150](https://github.com/Axidify/ai-dnd-rpg/blob/395f86a441984c9a2c91272ef2a502f2553d93e3/src/llm_client.py#L94-L150), [api_server.py 677–727](https://github.com/Axidify/ai-dnd-rpg/blob/395f86a441984c9a2c91272ef2a502f2553d93e3/src/api_server.py#L677-L727)

### Envanter ve mutation doğrulaması: iyi yön ve açık kalan yerler

İyi yön: Yerdeki eşya veya sahnedeki NPC'nin gift listesiyle sınırlı item grant; kaynak tüketilerek tekrar kazanma engeli; GOLD/XP anlatıcı tag'lerinin reddi; savaşın mevcut fixed encounter'a bağlanması. [world_model.py 300–352](https://github.com/Axidify/ai-dnd-rpg/blob/395f86a441984c9a2c91272ef2a502f2553d93e3/src/world_model.py#L300-L352), [turn_service.py 574–627](https://github.com/Axidify/ai-dnd-rpg/blob/395f86a441984c9a2c91272ef2a502f2553d93e3/src/turn_service.py#L574-L627)

Ama “LLM hiçbir state kararı veremez” iddiası fazla güçlü:
- BUY için bir merchant'ın sahnede olması, katalog fiyat tabanı ve yeterli para denetleniyor; bu yol belirli merchant stok/işlem onayıyla tam eşleşmiyor.
- PAY tag'i yeterli gold varsa parayı doğrudan düşürüyor. Alıcı, onaylanmış intent, fiyat teklifi veya ödeme idempotency'si kontrol edilmiyor.
- REMEMBER/ATTITUDE hâlâ model kontrollü state mutation.
- `finish_turn` anlatımın kullanıcıya zaten gösterildiğini açıkça belirtiyor. Reddedilen grant bir sonraki tur için correction notuna dönüşüyor. Envanter doğru kalırken kullanıcıya yanlış “kılıcı aldın” cümlesi çoktan görünmüş olabilir. State güvenliği ile prose doğruluğunu ayırmak şart. [turn_service.py 507–529](https://github.com/Axidify/ai-dnd-rpg/blob/395f86a441984c9a2c91272ef2a502f2553d93e3/src/turn_service.py#L507-L529), [turn_service.py 629–652](https://github.com/Axidify/ai-dnd-rpg/blob/395f86a441984c9a2c91272ef2a502f2553d93e3/src/turn_service.py#L629-L652)

### Yerel model, maliyet ve olgunluk

Gemini ve OpenAI-compatible vLLM istemcisi uygulanmış. Ayarlanabilir base URL/model sayesinde mevcut yerel servise adaptasyon mümkün görünüyor; bu, native Ollama entegrasyonu veya Qwen3:8b ile doğrulanmış uyumluluk/kalite demek değil. Bu repo için “Ollama hazır çalışır” iddiasında bulunmuyorum. Qwen thinking çıktısı, JSON bozulması, context ve latency için sizin modelinizde sözleşme testleri gerekir. vLLM arbiter yolunda JSON mode bilerek kapatılmış, cevap JSON parse/salvage + alan kontrolünden geçiriliyor. [llm_client.py 68–88, 153–174, 212–233](https://github.com/Axidify/ai-dnd-rpg/blob/395f86a441984c9a2c91272ef2a502f2553d93e3/src/llm_client.py#L68-L233), [dm_arbiter.py 291–385](https://github.com/Axidify/ai-dnd-rpg/blob/395f86a441984c9a2c91272ef2a502f2553d93e3/src/dm_arbiter.py#L291-L385)

Ücret sabit değil: rule override olmayan turda arbiter ve narrator çağrıları, yeniden denemeler ve giderek büyüyen history maliyeti/yerel gecikmeyi artırabilir. Varsayılan output tavanları narration 8192, classifier 4096. Qwen3:8b için bu değerler ölçülmeden alınmamalı. Python bağımlılıkları Flask, Flask-CORS, dotenv, PyYAML, OpenAI SDK ve Google generative AI SDK; geniş minimum sürümler kullanılmış. [llm_client.py 41–57](https://github.com/Axidify/ai-dnd-rpg/blob/395f86a441984c9a2c91272ef2a502f2553d93e3/src/llm_client.py#L41-L57), [requirements.txt](https://github.com/Axidify/ai-dnd-rpg/blob/395f86a441984c9a2c91272ef2a502f2553d93e3/requirements.txt#L1-L6)

Test açısından anlamlı mekanik regression testleri var: absent NPC memory, uydurma eşya/altın, save/load, kurtarma başarısızlığı ve narrator'a motor sonucunun aktarılması. CI offline pytest, Ruff ve frontend build tanımlıyor. Bunları çalıştırmadım; CI tanımını görmek son commit'in yeşil olduğunu veya canlı modelin güvenilirliğini kanıtlamaz. [test_world_model.py 109–184](https://github.com/Axidify/ai-dnd-rpg/blob/395f86a441984c9a2c91272ef2a502f2553d93e3/tests/test_world_model.py#L109-L184), [test_world_state.py 53–91](https://github.com/Axidify/ai-dnd-rpg/blob/395f86a441984c9a2c91272ef2a502f2553d93e3/tests/test_world_state.py#L53-L91), [ci.yml](https://github.com/Axidify/ai-dnd-rpg/blob/395f86a441984c9a2c91272ef2a502f2553d93e3/.github/workflows/ci.yml#L1-L38)

Lisans: ağaçta ayrı LICENSE yok; README yalnız eğitim amacı belirtiyor. MIT/Apache gibi açık yeniden kullanım izni varmış gibi kopyalama önermem. Mimari fikri bağımsız uygulamak ile kodu taşımak ayrılmalı. README'nin eski GOLD tag açıklaması da güncel `finish_turn` davranışını doğru yansıtmıyor. [README 7–12 ve 144–146](https://github.com/Axidify/ai-dnd-rpg/blob/395f86a441984c9a2c91272ef2a502f2553d93e3/README.md#L7-L12), [License bölümü](https://github.com/Axidify/ai-dnd-rpg/blob/395f86a441984c9a2c91272ef2a502f2553d93e3/README.md#L144-L146)

## 6. fedefreak92/dungeon-master-ai-project

İncelenen main HEAD: [38b655aa432d73eec78eebcb0dbf0442f7491ab5](https://github.com/fedefreak92/dungeon-master-ai-project/commit/38b655aa432d73eec78eebcb0dbf0442f7491ab5), commit tarihi 7 Nisan 2025 20:34:59 UTC. Repo'nun daha yeni updated/pushed alanları bu main snapshot'ın tarihi olarak kullanılmadı.

### Kısa karar: AI diyaloğu çözümü değil, mekanik backend örneği

Python, yığıt tabanlı FSM, harita, karakter/NPC, eşya ve check sistemi mevcut. GPT DM, doğal dil komutları, React frontend ve çok oyunculu yapı roadmap. “Dungeon Master AI” adına bakıp mevcut NPC konuşmasını LLM üretimi sanmak yanlış. [README 65–83](https://github.com/fedefreak92/dungeon-master-ai-project/blob/38b655aa432d73eec78eebcb0dbf0442f7491ab5/README.md#L65-L83)

`DialogoState`, NPC'nin JSON konuşma düğümünü okuyor; metni gösteriyor, sayısal seçenek alıyor ve sonraki düğüme geçiyor. NPC yoksa ya da düğüm yoksa deterministik çıkış var. Dolayısıyla burada lexical lore filtresi veya bir modelin yaratıcı konuşma/güvenlik dengesi yok. [dialogo.py 30–98](https://github.com/fedefreak92/dungeon-master-ai-project/blob/38b655aa432d73eec78eebcb0dbf0442f7491ab5/states/dialogo.py#L30-L98), [npg.py 101–128](https://github.com/fedefreak92/dungeon-master-ai-project/blob/38b655aa432d73eec78eebcb0dbf0442f7491ab5/entities/npg.py#L101-L128)

### Motor, envanter ve check'ler

Diyalog effect'leri `riposo`, `cura_leggera`, altın/eşya aktarımı ve alışveriş gibi ayrık dallar halinde Python kodunda uygulanıyor. Alışverişte NPC'nin envanterinde eşyanın bulunması ve oyuncunun parası kontrol ediliyor. Bunu “anlatıcı ürettiği kelimeyle state değiştiremez” şeklinde sınırlı tool/action sınırı tasarımına ilham olarak kullanabilirsiniz. Ancak LLM adapter eklenmedikçe doğrudan sizin sohbet probleminize çözüm değil. [dialogo.py 100–152](https://github.com/fedefreak92/dungeon-master-ai-project/blob/38b655aa432d73eec78eebcb0dbf0442f7491ab5/states/dialogo.py#L100-L152)

Skill-check UI'sı oyuncuya ability ve modalite seçtiriyor; temel check için DC'yi kullanıcıdan alıp 5–20 arasına kısıtlıyor, d20 + modifier hesaplıyor. Bu bir semantik intent arbiter değil, menüyle kontrol edilen mekanik örneği. [prova_abilita.py 120–164](https://github.com/fedefreak92/dungeon-master-ai-project/blob/38b655aa432d73eec78eebcb0dbf0442f7491ab5/states/prova_abilita.py#L120-L164)

### Hafıza ve persistence

Game state stack, haritalar, oyuncu ve NPC'ler JSON snapshot'a yazılıyor; HTTP session ayrıca pickle ile saklanıyor. Kalıcı LLM episodic memory, NPC başına retrieved context, anlatıcı prompt'u veya Ollama/Qwen provider katmanı incelemede yok. [core/game.py 402–433](https://github.com/fedefreak92/dungeon-master-ai-project/blob/38b655aa432d73eec78eebcb0dbf0442f7491ab5/core/game.py#L402-L433), [server.py 33–50](https://github.com/fedefreak92/dungeon-master-ai-project/blob/38b655aa432d73eec78eebcb0dbf0442f7491ab5/server.py#L33-L50)

Somut round-trip kusuru: `DialogoState.to_dict` aktif düğüm `stato_corrente` alanını kaydediyor; `from_dict` yeni instance yaratıp yalnız `dati_contestuali` ve `ultimo_input` yüklüyor, aktif düğümü geri koymuyor. Constructor başlangıcı `inizio`; dolayısıyla bu JSON yükleme yolunda konuşma düğümü sıfırlanabilir. Bu statik kod bulgusudur, canlı yeniden üretim yapılmadı. `ha_fatto_scelta` seçim geçmişi sözlüğünü okuyor fakat normal seçim dalı bu sözlüğe kayıt eklemiyor. [dialogo.py 15–20, 89–94, 179–193, 203–253](https://github.com/fedefreak92/dungeon-master-ai-project/blob/38b655aa432d73eec78eebcb0dbf0442f7491ab5/states/dialogo.py#L179-L253)

Effect, düğüm gösterilmeden ve seçim doğrulanmadan önce uygulanıyor. Tek kullanımlık effect'ler için replay/idempotency koruması şart; burada genel transaction/event log garantisi görülmüyor. Örneğin yanlış seçenek girip aynı düğüme dönme, effect'in tekrar değerlendirilmesine yol açabilir. Her effect'in sömürülebilir olduğu iddiası değil; FSM'yi alırken eklenmesi gereken invariant. [dialogo.py 52–81](https://github.com/fedefreak92/dungeon-master-ai-project/blob/38b655aa432d73eec78eebcb0dbf0442f7491ab5/states/dialogo.py#L52-L81)

### Validation, güvenlik ve olgunluk

Save validator temel alanları kontrol ediyor, sürüm farkını yalnız uyarıyor; derin schema/referential integrity validation değil. HTTP kodundaki pickle yükleme, geniş CORS ve kullanıcı kontrollü dosya adlarının güvenli path confinement olmaksızın dizine eklenmesi, internete açılmadan ayrıca sertleştirilmeli. Bu inceleme exploit denemesi veya tam güvenlik audit'i değil. [Dosya yolu birleştirme](https://github.com/fedefreak92/dungeon-master-ai-project/blob/38b655aa432d73eec78eebcb0dbf0442f7491ab5/util/config.py#L30-L47) [config.py 155–190](https://github.com/fedefreak92/dungeon-master-ai-project/blob/38b655aa432d73eec78eebcb0dbf0442f7491ab5/util/config.py#L155-L190), [server.py 21–50](https://github.com/fedefreak92/dungeon-master-ai-project/blob/38b655aa432d73eec78eebcb0dbf0442f7491ab5/server.py#L21-L50)

README standard-library-only diyor fakat web server Flask ve Flask-CORS import ediyor. CLI çekirdeğinin bağımlılığı ile HTTP katmanını ayırmak gerekiyor. İncelenen recursive tree'de otomatik test paketi/CI workflow ve dependency manifest görülmedi; “fully testable” sözü “testlerle doğrulanmış” demek değil. [README 97–99](https://github.com/fedefreak92/dungeon-master-ai-project/blob/38b655aa432d73eec78eebcb0dbf0442f7491ab5/README.md#L97-L99), [server.py 1–9](https://github.com/fedefreak92/dungeon-master-ai-project/blob/38b655aa432d73eec78eebcb0dbf0442f7491ab5/server.py#L1-L9), [incelenen kaynak ağacı](https://github.com/fedefreak92/dungeon-master-ai-project/tree/38b655aa432d73eec78eebcb0dbf0442f7491ab5)

AI API maliyeti mevcut uygulamada yok; çünkü AI provider uygulanmamış. Bu, aynı anlatım kabiliyetini ücretsiz sağladığı anlamına gelmiyor. Yerel Qwen entegrasyonu sizin ekleyeceğiniz yeni geliştirme olur.

Lisans belirleyici: kişisel/ticari olmayan kullanım; ticari/profesyonel entegrasyon için yazılı lisans gerektiği açıkça yazıyor. Açık kaynak permissive dependency gibi önermem. Kod kopyalamak yerine FSM/action-boundary fikrini bağımsız tasarlamak daha uygun. [LICENSE 1–37](https://github.com/fedefreak92/dungeon-master-ai-project/blob/38b655aa432d73eec78eebcb0dbf0442f7491ab5/LICENSE#L1-L37)


---

## 7. LudicDynamics/WorldLines

**İncelenen sürüm:** `4ee61a368c381f2f8db43b4454f088a7388693bf`, commit zamanı 6 Ekim 2026 09:34:28 UTC; inceleme 20 Ekim 2026. Depo herkese açık ve erişilebilir. [Sabit commit](https://github.com/LudicDynamics/WorldLines/commit/4ee61a368c381f2f8db43b4454f088a7388693bf).

### En önemli sonuç

Bu bir açık kaynak oyun motorunun tamamı değil. Açık kısım React web arayüzü, Tauri masaüstü kabuğu, paketleme betikleri ve örnek dünyalar. `neonrp` motoru özel mülkiyetli ve bu depoda bulunmuyor. Bu nedenle README'nin “file-backed, event-sourced”, deterministik replay, otomatik bağlam indeksleme ve şema doğrulama iddialarını motor uygulaması incelenerek doğrulanmış sonuç gibi sunmak yanlış olur. Bunların istemci tarafındaki karşılıkları ve örnek sözleşmeleri görülebiliyor; uygulama garantileri görülemiyor. [Lisans kapsamı, satır 18–26](https://github.com/LudicDynamics/WorldLines/blob/4ee61a368c381f2f8db43b4454f088a7388693bf/LICENSE#L18-L26).

### Mimari ve gerçekte görülen bileşenler

- React 19 + TypeScript + Vite arayüz; `@xyflow/react` görselleştirme, React Router ve Playwright geliştirme bağımlılıkları var. [package.json](https://github.com/LudicDynamics/WorldLines/blob/4ee61a368c381f2f8db43b4454f088a7388693bf/ui/package.json#L1-L43).
- `StageBackend` aynı istemciyi yerel ve hosted motorlara bağlıyor. `EventSource` ile `/events` okunuyor; `/cmd`, `/traces`, `/trace`, `/rollback` gerçek istemci çağrıları. Bunlar uygulanmış UI/protokol adaptörleridir, sunucuda nasıl doğrulandıklarının kanıtı değildir. [backend.ts](https://github.com/LudicDynamics/WorldLines/blob/4ee61a368c381f2f8db43b4454f088a7388693bf/ui/src/play/stage/backend.ts#L18-L67), [stageClient.ts](https://github.com/LudicDynamics/WorldLines/blob/4ee61a368c381f2f8db43b4454f088a7388693bf/ui/src/play/stage/stageClient.ts#L20-L83).
- İki farklı NPC yaklaşımını karıştırmamak gerekiyor: `orch` dünyasında world-agent gerektiğinde character-agent çağırıyor; `multi-agent` dünyasında her karakter ayrı soul kimliği ve dosyalarıyla temsil ediliyor. Stoneford-Elena'nın `playthrough.json` dosyası insan oyuncuyu ve Elena/Rowan NPC'lerini ayrı tanımlıyor. [playthrough.json](https://github.com/LudicDynamics/WorldLines/blob/4ee61a368c381f2f8db43b4454f088a7388693bf/examples/multi-agent/stoneford-elena/playthrough.json#L1-L60).

### NPC konuşması: model öncesi ve sonrası kapılar

`orch` character-agent yapılandırmasında okuma `game/**`, yazma izinleri boş. Bu, diyalog üreticisine kalıcı dünya yazma yetkisi vermemek bakımından iyi bir tasarım örneği. Fakat okuma yetkisinin genişliği, bilinmeyen veya gizli dünya bilgisini kodla filtreleyen sağlam bir sınır olduğunu göstermez. Prompt NPC'ye `gate_conditions` koşullarına uyup açılmamış sırları söylememesini istiyor; yani açık kaynakta görülen bilgi kapısı burada büyük ölçüde prompt disiplini. [agent.json](https://github.com/LudicDynamics/WorldLines/blob/4ee61a368c381f2f8db43b4454f088a7388693bf/examples/orch/stoneford/agents/character-agent/agent.json#L1-L22), [system.md, kaynaklar ve roller](https://github.com/LudicDynamics/WorldLines/blob/4ee61a368c381f2f8db43b4454f088a7388693bf/examples/orch/stoneford/agents/character-agent/system.md#L8-L39).

Konuşma 1–3 kısa paragraf olabilir; saf replik, beden hareketi veya karakter içi sessizlik kabul ediliyor. Karakter oyuncu adına karar vermiyor; gerekiyorsa bir kontrol talebi üretiyor. `affection`, `mood`, `inner_monologue` gibi değişiklikler yalnızca öneri olarak orchestrator'a dönüyor, karakter kendi dosyasına yazmıyor. Bu, “NPC doğal konuşsun ama söyledikleri otomatik oyun gerçeğine dönüşmesin” ihtiyacına doğrudan temas eden bir görev ayrımıdır. Ne var ki örnek `state_delta` strict JSON değil ve kabul/red doğrulayıcısı açık değil. [İlişki önerileri](https://github.com/LudicDynamics/WorldLines/blob/4ee61a368c381f2f8db43b4454f088a7388693bf/examples/orch/stoneford/agents/character-agent/system.md#L49-L85).

Multi-agent promptunda world-agent'ın NPC'nin sesi yerine konuşmaması, sadece soul çıktısını birleştirmesi isteniyor. Aynı yerde modelin `souls/**` okumaması, NPC'lerin aktiflik durumunun konuma göre motorca belirlenmesi ve insan oyuncunun bağımsız tutulması açıklanıyor. Bu iyi bir rol sözleşmesi; motor kaynakları kapalı olduğu için zorunlu yürütme ve bağlam izolasyonu ayrıca doğrulanamadı. [Sınırlar ve aktif soul yönetimi](https://github.com/LudicDynamics/WorldLines/blob/4ee61a368c381f2f8db43b4454f088a7388693bf/examples/multi-agent/stoneford-elena/agents/world-agent/system.md#L7-L36).

### Bellek, kanon ve state

Soul başına `short-term-memo`, `long-term-memo`, `persona`, `background`, `trajectory` dizinleri var. Elena'nın başlangıç `learned_facts.json` listesi boş; `current_context.json` ise sahne, tur ve kısa notlar içeriyor. Bu, kalıcı veri modelinin varlığını gösterir; geçmişten doğru geri getirme, unutma, özetleme veya oyuncular arası sızıntısız çalışma kalitesini kanıtlamaz. [Öğrenilen olgular](https://github.com/LudicDynamics/WorldLines/blob/4ee61a368c381f2f8db43b4454f088a7388693bf/examples/multi-agent/stoneford-elena/souls/elena-si-elena0001/long-term-memo/learned_facts.json#L1-L4), [anlık bağlam](https://github.com/LudicDynamics/WorldLines/blob/4ee61a368c381f2f8db43b4454f088a7388693bf/examples/multi-agent/stoneford-elena/souls/elena-si-elena0001/short-term-memo/current_context.json#L1-L11).

World-agent promptu kimlik/canon ile değişebilir durum alanlarını ayırıyor: mood/location/alive/flags değişebilir, name/id/faction/canonical dialogue gelişi güzel yeniden yazılmamalı. Ancak yapılandırmada player JSON dosyalarına `direct_write_globs` izni de var. Dolayısıyla “bütün değişiklikler yalnızca Plan–Diff–Validate–Apply üzerinden geçer” sonucuna varılamaz; en azından açık sözleşmelerde birden fazla yazma yolu bulunuyor. Ayrıca prompttaki `.neonrp` okumama ifadesi ile JSON'da `.neonrp/**` okuma izni arasında uyuşmazlık var. Bu, örnek promptların tek başına yetki denetimi sayılamayacağını gösteriyor. [Prompt yazma ayrımı](https://github.com/LudicDynamics/WorldLines/blob/4ee61a368c381f2f8db43b4454f088a7388693bf/examples/multi-agent/stoneford-elena/agents/world-agent/system.md#L56-L78), [gerçek yapılandırma](https://github.com/LudicDynamics/WorldLines/blob/4ee61a368c381f2f8db43b4454f088a7388693bf/examples/multi-agent/stoneford-elena/agents/world-agent/agent.json#L18-L37).

### Event sourcing, envanter ve zar

UI event tiplerinde `turn_seq`, `land.commit_id`, soul etkinlik nedenleri ve bus mesajları bulunuyor; rollback istemcisi commit kimliği gönderiyor. Bu, izlenebilirlik ve geri sarma ürün yüzeyinin gerçek uygulama kanıtı. Örnek `.neonrp/events/main.jsonl` dosyası ise bir dosya düzenleme olayı içeriyor. Tek başına tam replay, deterministik RNG veya atomik commit kanıtı değil. [Event tipleri](https://github.com/LudicDynamics/WorldLines/blob/4ee61a368c381f2f8db43b4454f088a7388693bf/ui/src/play/stage/events.ts#L66-L136), [örnek event](https://github.com/LudicDynamics/WorldLines/blob/4ee61a368c381f2f8db43b4454f088a7388693bf/examples/orch/stoneford/.neonrp/events/main.jsonl#L1).

`rules-referee` okumayı istatistikler/kurallar ile sınırlayan, yazma yetkisi olmayan bir uzman olarak tanımlanmış. Prompt d20, DC, total, sonuç ve sonuç önerilerini JSON olarak istiyor. Ancak açık kodda bu zarın güvenilir RNG'den geldiğini, envanter işlemlerinin atomik olduğunu veya D&D 5e ile tam uyum bulunduğunu gösteren motor yok. Hatta formül `attribute - 5` ve VIT gibi özellikler içeriyor; bunu D&D 5e motoru diye sınıflandırmamak gerekir. [Rules yapılandırması](https://github.com/LudicDynamics/WorldLines/blob/4ee61a368c381f2f8db43b4454f088a7388693bf/examples/orch/stoneford/agents/rules-referee/agent.json#L1-L28), [kural sözleşmesi](https://github.com/LudicDynamics/WorldLines/blob/4ee61a368c381f2f8db43b4454f088a7388693bf/examples/orch/stoneford/agents/rules-referee/system.md#L20-L132).

### Yerel Qwen/Ollama ve maliyet

Sadece README iddiası yok: UI'da custom model formunun varsayılan adresi `http://localhost:11434/v1`; model adı serbest metin, örnek `qwen2.5:14b`. Bu gerçek bir yerel OpenAI-uyumlu endpoint yapılandırma yüzeyidir. Fakat motor adaptörü kapalı; Qwen3:8b ile tool çağrıları, structured output, thinking çıktısı ve performans bu incelemede çalıştırılarak doğrulanmadı. “Qwen3:8b ile sorunsuz çalışır” garantisi verilemez. [ModelAccessPanel.tsx](https://github.com/LudicDynamics/WorldLines/blob/4ee61a368c381f2f8db43b4454f088a7388693bf/ui/src/play/ModelAccessPanel.tsx#L31-L70), [model alanı](https://github.com/LudicDynamics/WorldLines/blob/4ee61a368c381f2f8db43b4454f088a7388693bf/ui/src/play/ModelAccessPanel.tsx#L171-L203).

Çoklu soul ve domain-agent yaklaşımı tur başına birden fazla çıkarım gerektirebilir. Yerelde API faturası yerine RAM/VRAM, gecikme ve enerji; uzak sağlayıcıda çağrı/token maliyeti oluşur. Burada fiyat araştırması veya benchmark yapılmadı. Qwen3:8b üzerinde tüm mimariyi taşımak yerine tek NPC çağrısı + deterministik commit servisi daha düşük karmaşıklıklı başlangıçtır.

### Test ve olgunluk

Playwright dosyaları mevcut. İncelenen `stage.spec.ts` açıkça sıfır LLM ile session bağlama ve arayüz iskeletini test ediyor. Test varlığı olumlu; NPC bilgi sızıntısı, diyalog kalitesi, lore güvenliği veya modelin sözleşmeye uyumunun test edildiğini göstermiyor. Testler çalıştırılmadı. [Stage smoke testi](https://github.com/LudicDynamics/WorldLines/blob/4ee61a368c381f2f8db43b4454f088a7388693bf/ui/e2e/stage.spec.ts#L1-L46).

### Lisans ve yeniden kullanım

Açık deponun lisansı AGPL-3.0-or-later; kapsam açıkça UI, masaüstü kabukları, betikler ve örnekler. Motor ayrı lisanslı/proprietary. Doğrudan kod/prompt örneği aktarımından önce AGPL'nin dağıtım ve ağ üzerinden kullanım koşulları proje bağlamında incelenmeli; bu hukuki kesinlik değildir. Mimari fikri kendi kodunla uygulamak, depoyu doğrudan vendor etmekten farklı bir karardır. [LICENSE](https://github.com/LudicDynamics/WorldLines/blob/4ee61a368c381f2f8db43b4454f088a7388693bf/LICENSE#L1-L26).

### AI-DND için alınacak ve alınmayacak şeyler

**Alınacak:** NPC konuşma üreticisi read-only; oyuncu iradesi, NPC sesi ve dünya hakemi ayrı; kısa karakter hafızası kimlik/sahne bazında; mutation önerisi konuşmadan ayrı; hata ve kontrol sonucunu metadille değil karakter içi doğal dille anlatma; hangi bağlam ve kapının çalıştığını trace ekranında görme.

**Alınmayacak:** Sırları prompta koyup sadece “söyleme” demek; modelin kendi kendine zar üretmesini otorite saymak; bütün konuşmaları çok-agent zincirine sokmak; kapalı motorun bütün güvencelerini açık kaynak koddan doğrulanmış kabul etmek.

**Uyarlama karmaşıklığı:** İlke ve veri sözleşmelerini bağımsız küçük modüller halinde uygulamak orta/düşük; motoru temel almak yüksek ve kapalı çekirdeğe bağımlı. Kullanıcının mevcut Python+React yapısını değiştirmek için yeterli gerekçe yok. Bu depo özellikle rol ayrımı ve gözlemlenebilirlik referansı olarak değerli, kopyalanabilir açık motor olarak değil.
