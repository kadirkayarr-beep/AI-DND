## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- When graphify-out/graph.json exists, run `graphify query "<question>"` before your first grep, search or source-file read for a codebase question, and put this rule in every subagent prompt that explores code. Read raw files only for lines the graph or an earlier read already located. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- Run `graphify update .` (AST-only, no API cost) once at the end of a task and before handing a diff to review, not after every edit; keep `graphify-out` ready in every long-lived worktree. The graph is a navigation aid, not a substitute for reading: most bugs live in JSON content (templates, catalogs, menu tables) and dynamic paths, which the AST graph cannot see.
- graphify-out/ is local-only and gitignored on this shared branch (it is rewritten whole on every build); do not commit it.

# CLAUDE.md — AI-DND

Kadir programcı değil: kısa, açık, dürüst ve sade Türkçe yaz; doğrulamadığın şeye "doğrulamadım" de; harcama ve silme için onay iste.

## Kodlama ilkeleri

- **Varsayımı görünür kıl:** sessizce seçme. Durmayı gerektirmeyen belirsizlikte karar ver ve `Ruling` yaz (aşağıda "Belirsizlik ve karar"); daha basit bir yol varsa söyle.
- **En az kod:** istenmeyen özellik, tek kullanımlık soyutlama, istenmemiş ayar, imkânsız durum için hata işleme yok.
- **Cerrahi değişiklik:** yalnız görevin gerektirdiği satırlara dokun; komşu kodu, yorumu, biçimi düzeltme; var olan stile uy. Yalnız kendi değişikliğinin boşa çıkardığı import/değişken/işlevi kaldır; eski ölü kodu bildir, silme.
- **Doğrulanabilir hedef:** her işi teste çevir (önce kırmızı test, sonra düzeltme); çok adımlı işte her adımın yanına doğrulamasını yaz.
- **Motor dosyası (karar 8):** game.py'ye yeni işlev eklenmez; yeni kod ilgili `game_parts` modülüne ya da kendi modülüne girer. `game_parts` içinde motor adları `game.X` diye çağrılır. Boyut bütçesi yalnız Kadir'in onayıyla yükseltilir.

## Agent skills

### Issue tracker

İşler yerel markdown olarak `.scratch/` altında tutulur (GitHub Issues kullanılmaz). Bkz. `docs/agents/issue-tracker.md`.

### Triage labels

Varsayılan beş etiket: needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix. Bkz. `docs/agents/triage-labels.md`.

### Domain docs

Tek bağlam (single-context): kökte `GLOSSARY.md` ve `docs/adr/`. Bkz. `docs/agents/domain.md`.

Tasarım ve plan belgeleri: `docs/design/INDEX.md`; sıra ve durum: `docs/design/YOL_HARITASI.md`.

## Çalışma ve test disiplini

**Ana ilke:** işi hızlandır ama kalite ve güvenlikten ödün verme: hız için kaliteyi ya da güvenliği zayıflatan kural uygulanmaz ve Kadir'e bildirilir; çelişkide kalite ve güvenlik kazanır. Ledger = çalışan planın `.superpowers/sdd/<plan>/progress.md` dosyası.

- **[Güvenlik] İzolasyon:** her iş kendi worktree'sinde, worktree başına tek yazıcı. Bağımsız işler ayrı worktree ve ayrı test yuvasıyla aynı anda yürüyebilir.
- **[Kalite] Sabit kasaba:** yeni kampanya başlatan her test kampanya tohumunu sabitler (`api/tests/town_seed.py` → `fixed_town`; yolculuk senaryolarında `campaign_seed`); rastgele kimlik rastgele kırık getirir.
- **[Kalite] Sabit komşu seti (atlanamaz; hızlı katman da içerir):** her görevin hedefli testlerine `api.tests.test_journey_runner`, `test_journey_report`, `test_journey_schema`, `test_journeys` girer. Yeni numaralı senaryonun türü rapor tablosuna eklenir.
- **[Hız] Tam paket:** yalnız dilim sonunda ve planın ara kapılarında.
- **[Güvenlik] İnceleme seviyesi:** para, kayıt ve Geri Al'a dokunan işte önce kırmızı test, sonra düzeltme; inceleme bağımsız ve Opus ile. Küçük kırmızı-yeşil ya da yalnız test düzeltmesine ucuz yeniden inceleme yeter; para/kayıt/Geri Al'a dokunmayan tek satırlık ya da yalnız metin düzeltmede, kırmızı-yeşil testi varsa atlanabilir (ledger'a Ruling; dilim sonu bütün dal incelemesi kapsar).
- **[Kalite] Bilinen kırıklar:** başka yerde görülen kırığın kökeni commit'e kadar izlenir; "zaten kırıktı" kabul edilmez, gerçekten eskiyse deftere yazılır. Aynı kodda yinelenen koşuda sonuç değişiyorsa flake'tir: bisect yok, tohum sabitlenir. Köken bulunamazsa deftere "kökeni bilinmiyor" yazılır, kapıya etkisi değerlendirilir.
- **[Hız] Belirsizlik ve karar:** çalışan plan insan beklemez. Dur ve sor yalnız dört durumda (başka durma koşulu yok): geri alınamaz/yıkıcı işlem; güvenlik açısından hassas işlem (anahtar, harcama dahil); worktree dışı yan etki (yeşil CI olmadan push veya merge, ölü kod silme işinin push/PR/merge'ü, herkese açık yayın); her yolu tahmine bırakan bozuk plan. Diğer her belirsizlikte karar ver, ledger'a `Ruling: <karar> — <neden> — <yanlışsa maliyeti>` yaz.
- **[Hız] Park etme:** küçük bulgu deftere "park" olarak yazılır, işi durdurmaz; kapıyı etkileyen kırık durdurur. Sahipsiz park bırakılmaz.
- **[Kalite] Yeniden kullanım:** yeni kod yazmadan önce repoda ve standart kütüphanede hazır olanı ara (`docs/agents/implementer-preamble.md` madde h); para/kayıt/Geri Al kodunda doğrulama, hata işleme, makbuz, denetim ve testler ASLA azalmaz.
- **[Kalite] Test yeniden yazımı:** eski davranışı sabitleyen test ancak eşit sıkılıkla yeniden yazılır ve onay listesine girer; sınırı değiştiren her değişiklik "gevşetme olabilir" diye işaretlenir ve işi durdurmaz. İşaretsiz gevşetme, atlama ya da silme işi durdurur.
- **[Hız] Hız kuralları:** tam metin `docs/agents/hiz-kurallari.md` (uygulamadan önce okunur): çakışan inceleme, her implementer istemine `docs/agents/implementer-preamble.md`, brifte satır numarası değil işlev/dosya adı, hızlı katman, paketleme, süreli bekleme döngüleri. Tur bölmede kalite önde gelir; hız kuralları belge ve arayüz yazısı işlerinde tam uygulanır (Kadir, 2026-11-22).

**[Güvenlik] Dokunulmaz:** para/kayıt/Geri Al için Opus ile bağımsız inceleme, sıfır tolerans yolculukları, dilim sonu tam paket ve Opus ile bütün dal incelemesi, main'e yalnız yeşil CI ile merge.

## Sahibin kuralları (tek kaynak)

Kadir'in kalıcı kurallarıdır; bellek dosyaları değil bu bölüm esastır. Çelişkide güvenlik ve kalite kazanır.

- **[Güvenlik] Push/merge/yayın (Kadir, 2026-11-22; Kadir geri alana kadar):** yeşil CI'dan sonra push, PR ve main'e merge için kalıcı onay var. Ölü kod silme işinin push/PR/merge'ü, her silme ve herkese açık yayın ayrıca sorulur. Force push yok, dal silinmez (geri alınamaz).
- **[Güvenlik] CI kontrolü:** her push/merge sonrası `gh run list --repo kadirkayarr-beep/AI-DND` ile 'AI-DND bounded verification' bakılır (CI yalnız main push ve pull_request'te çalışır); kırmızı hemen bildirilir, sonra düzeltilir; yeşil olmadan "bitti" denmez (yerel yeşil CI'ın yerini tutmaz). Merge'den hemen önce main'in son koşusuna bakılır; kırmızıysa ya da sürüyorsa merge edilmez, Kadir'e yazılır. Dar istisna (Kadir, 2026-11-14): main kırmızıyken merge yalnız üç koşul birlikte sağlanırsa olur: (a) PR'ın son koşusu yeşil ve kaydında "Merge <PR ucu> into <main'in şu anki ucu>" yazıyor; (b) main'in her kırmızı denemesinin düşen satırı okunmuş ve borç defterinde kayıtlı rastgele kırık; (c) o merge için Kadir'in taze onayı.
- **[Güvenlik] Commit kaybı:** birleştirmeden/push'tan önce dal ve commitlerin başka yerde olup olmadığına bak (hedef uç atası mı); eski Ekim dallarına dokunulmaz.
- **[Güvenlik] Anahtarlar:** anahtar/API dosyaları okunmaz, yazdırılmaz, commit edilmez; anahtarları yalnız sahibi girer (sızıntı geri alınamaz).
- **[Güvenlik] Dış kod ve veri:** doğrulanmamış skill, hook, npx kurulmaz; önce repo okunur, yalnız markdown içerenler kurulur; ekran görüntüsü ya da veri dış servise sorulmadan gönderilmez.
- **[Güvenlik] Silme koruması:** silmeden önce hedefe bak (kirli dosya, uzak dalda olmayan commit); her silme Kadir'e sorulur; dallar silinmez.
- **[Hız] Model ve tahmin (Kadir, 2026-11-22):** haftalık limit dar: işlere ucuz model; para/kayıt/Geri Al ve bütün-dal incelemesi Opus; fable yalnız Kadir o iş için söylerse. Tur bölme Kadir'in seçimiyle Fable ile yürür; Fable'ın haftalık limiti biterse kalan parça Opus ile sürer (ledger'a Ruling). Her dilimden önce Kadir'e tahmini gün, model başına token, tam paket ve oynayış sayısı yazılır (geçmiş ledger'lardan); tahmin bilgidir, iş beklemez; yalnız tur bölmenin planı ve tahmini Kadir'in onayını bekler. Tahmini aşan dilim durmaz; aşım nedeniyle `docs/design/YOL_HARITASI.md`'ye yazılır. Dilim sonunda gerçek gün ve token aynı PR'da yol haritasına yazılır; ölçülmeyen sayıya "ölçülmedi" denir.
- **[Kalite] Oynayış kapısı (Kadir, 2026-11-12; 2026-11-22):** oyun koduna (motor, API, arayüz, içerik JSON'ları) dokunan dilim, Kadir en az 10 dakika oynamadan "bitti" sayılmaz ve main'e girmez; yeşil test oynayışın yerini tutmaz. Oynayış beklerken sonraki dilim kendi worktree'sinde, öncekinin üstünde başlayabilir; oynayış bekleyen en çok üç dilim olur, dördüncüsü başlamaz ve Kadir'e haber verilir. Bekleyen dilimler en üstteki sürümde tek oynayışla, birleşik kontrol listesiyle oynanır; sorun çıkan dilim ve üstündekiler bekler, gerisi main'e girer. Yalnız test, belge ya da CI dosyasına dokunan iş oynayış beklemez ve üç dilim sınırına sayılmaz. Oynanmadıysa ledger'a "oynayış bekliyor" yazılır.
- **[Kalite] Sabah özeti (Kadir, 2026-11-12):** Kadir yokken yapılan her çalışmanın sonunda en çok beş satırlık sade Türkçe özet: ne değişti, neden, hangi dosyalarda, ne doğrulandı, Kadir'den ne bekleniyor.
- **[Hız] Kısa yazım ve az okuma (Kadir, 2026-11-14):** önce sonuç, sonra kanıt, sonra Kadir'den beklenen; araç çağrıları arasında anlatım yok. Sayılar, komutlar, yollar ve hata metinleri birebir; "değil", "yalnız", "hiç" atılmaz. Güvenlik uyarısı, geri alınamaz işlem ve Kadir'in anlamadığı konu tam cümleyle. Test/CI çıktısında önce düşen satır aranır; aynı dosya aynı oturumda iki kez baştan okunmaz. Rapor en çok 25 satır; fazlası dosyaya.
- **[Kalite] Hata önceliği (Kadir, 2026-11-14):** her hata borç defterine KRİTİK/YÜKSEK/ORTA/DÜŞÜK ile yazılır; hiçbiri göz ardı edilmez; çözüm bu sırayla.
- **[Kalite] Zar kuralları (Kadir, 2026-11-14):** her zar, beceri testi, kurtarma ve saldırı `docs/design/ZAR_KURALLARI_DND2024_20261114.md` (D&D 2024 / SRD 5.2.1) rehberine uyar: önce karar ağacı (bölüm 2) okunur; zar yalnız sonuç belirsizse atılır; zar çözülmeden durum (para, eşya, can, sahiplik) değişmez; test kataloğu (D01–V02) zar işlerinin test listesidir.
- **[Hız] Eski kayıtlar (Kadir, 2026-11-16):** eski kayıtların önemi yok; uyumluluk işi yapılmaz, eski kayıt sorusu sorulmaz.

## Otonom çalışma ve izinler

- İzinler `.claude/settings.json` dosyasındadır: dosya düzenleme onaysızdır; silme komutları her seferinde sorulur; force push, main/dev'e doğrudan push ve dal silme kapalıdır.
- Bir komut reddedilirse aynı işi başka yazımla (ör. `git -C`, `bash -c`) deneme; ne yapmak istediğini Kadir'e yaz.
- "Bitti" demeden önce koşunun çıktısını göster; koşmadığın testi geçti sayma.
- **[Hız] Eski kanıt:** `attached_assets/`, `docs/design/arsiv/`, `docs/acceptance/`, `.local/evidence/` toplu okunmaz; yalnız adı verilen tek kayıt açılır.

## Arayüz işi (Kadir, 2026-11-13)

Bu bölüm `artifacts/ai-dnd-experience` altındaki her görsel değişiklik için geçerlidir. "En az kod" kuralı burada gereksiz soyutlama yazmamak demektir; eksik durum, ham tarayıcı bileşeni ya da yarım görsel bırakmak demek değildir.

- **[Kalite] Hedef resimdir:** her ekran işi bir hedefle başlar: onaylı prototip (`UI_PROTOTIP_V4_20261111`), `PROTOTIP_ENVANTERI_20261113.md` satırı ya da Kadir'in ekran görüntüsü. Hedef yoksa önce Kadir'e taslak gösterilir, kod yazılmaz.
- **[Kalite] Gör, sonra "bitti" de:** iş, çalışan oyunun 1440 ve 390 piksel genişlikte ekran görüntüsü alınıp hedefin yanına konmadan bitmez. Görüntüler rapora dosya adıyla yazılır. Ekran görüntüsü alınamıyorsa durulur ve Kadir'e söylenir; görmeden "bitti" denmez.
- **[Kalite] Bitti tanımı:** (1) hedefle yan yana karşılaştırma ve kalan farkların listesi; (2) boş, yükleniyor, hata ve uzun içerik durumları; (3) üç tema: Gündüz, Gece ve Karanlık; (4) 390 pikselde yatay kaydırma yok; (5) klavyeyle gezinme ve odak görünür; (6) renk, yazı tipi ve boşluk yalnız `src/index.css` değişkenlerinden gelir, elle renk kodu yazılmaz; (7) ham tarayıcı `select`, `checkbox`, `alert` kullanılmaz, depodaki hazır bileşenler (`src/components/ui`) kullanılır; (8) bütün arayüz testleri yeşil.
- **[Kalite] Kısayolu söyle:** bir şey basit yoldan yapıldıysa ya da bırakıldıysa raporun ilk satırına "Kısayol: <ne, neden>" yazılır. Söylenmemiş kısayol, işaretsiz gevşetme sayılır ve işi durdurur.
- **[Kalite] Tek ekran, tek oturum:** bir oturum bir ekranı (ya da bir paneli) bitirir. Sıradaki ekran yeni oturumda başlar.
- **[Kalite] Ayrı göz:** ekran görüntüleri, kodu yazmamış ayrı bir oturumda `ui-design-review:review` ile incelenir. Bulgular önem sırasıyla Kadir'e gider; hangilerinin düzeltileceğine Kadir karar verir.
- **[Kalite] Model:** tasarım dilini kuran iş (ilk ekran, ortak görsel kurallar, yeni gösterge) en güçlü modelle yapılır. O kurallara uyan tekrar işleri ucuz modelle yapılabilir. Bu, "Model ve tahmin" kuralının arayüz istisnasıdır.
- **[Kalite] Kabul:** bir ekranı yalnız Kadir kabul eder. Test yeşili ve inceleme raporu kabul değildir.

## İçerik kapsamı ve açık kapı

- Oyun yetişkinlere yönelik karanlık fantezidir. Savaş, kan, korku, suç (hırsızlık, cinayet), acımasız ya da kötü NPC'ler ve sert dil kurgu olarak kapsam içindedir; bunlar için sorma, uyarı ekleme, metni kendiliğinden yumuşatma.
- **Açık kapı:** bir metni ya da kodu yazmayacaksan işi durdurma. Tek cümleyle neyi yazmadığını söyle, o yere `KADIR_DOLDURACAK: <burada ne bekleniyor>` yer tutucusu koy, ledger'a park olarak yaz ve işin kalanını bitir. Yer tutucuyu haber vermeden yumuşatılmış metinle doldurma.
