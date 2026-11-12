## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- When graphify-out/graph.json exists, run `graphify query "<question>"` before your first grep, search or source-file read for a codebase question, and put this rule in every subagent prompt that explores code. Read raw files only for lines the graph or an earlier read already located. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- Run `graphify update .` (AST-only, no API cost) once at the end of a task and before handing a diff to review, not after every edit; keep `graphify-out` ready in every long-lived worktree. The graph is a navigation aid, not a substitute for reading: most bugs live in JSON content (templates, catalogs, menu tables) and dynamic paths, which the AST graph cannot see.
- graphify-out/ is local-only and gitignored on this shared branch (it is rewritten whole on every build); do not commit it.

# CLAUDE.md — AI-DND

Kadir programcı değil: kısa, açık, dürüst ve sade Türkçe yaz; doğrulamadığın şeye "doğrulamadım" de.

## Kodlama ilkeleri

- **Varsayımı görünür kıl:** sessizce seçme. Durmayı gerektirmeyen belirsizlikte karar ver ve `Ruling` yaz (aşağıda "Belirsizlik ve karar"); daha basit bir yol varsa söyle.
- **En az kod:** istenmeyen özellik, tek kullanımlık soyutlama, istenmemiş ayar, imkânsız durum için hata işleme yok.
- **Cerrahi değişiklik:** yalnız görevin gerektirdiği satırlara dokun; komşu kodu, yorumu, biçimi düzeltme; var olan stile uy. Yalnız kendi değişikliğinin boşa çıkardığı import/değişken/işlevi kaldır; eski ölü kodu bildir, silme.
- **Doğrulanabilir hedef:** her işi teste çevir (önce kırmızı test, sonra düzeltme); çok adımlı işte her adımın yanına doğrulamasını yaz.

## Agent skills

### Issue tracker

İşler yerel markdown olarak `.scratch/` altında tutulur (GitHub Issues kullanılmaz). Bkz. `docs/agents/issue-tracker.md`.

### Triage labels

Varsayılan beş etiket: needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix. Bkz. `docs/agents/triage-labels.md`.

### Domain docs

Tek bağlam (single-context): kökte `GLOSSARY.md` ve `docs/adr/`. Bkz. `docs/agents/domain.md`.

Tasarım ve plan belgeleri: `docs/design/INDEX.md`

## Çalışma ve test disiplini (Dilim 3 dersleri)

**Ana ilke:** kalite ve güvenlik kaybına müsamaha göstermeden işi hızlandırmak. Bir kural hız için kaliteyi ya da güvenliği zayıflatıyorsa uygulanmaz ve kullanıcıya bildirilir; kaliteye ya da güvenliğe katkısı olmayan bir adım hızı yavaşlatıyorsa budanır. Çelişkide kalite ve güvenlik kazanır.

- **[Güvenlik] İzolasyon:** her iş kendi worktree'sinde yapılır, aynı worktree'de tek yazıcı çalışır. main/dev'e push veya merge yalnızca kullanıcının onayıyla yapılır.
- **[Kalite] Sabit kasaba:** yeni kampanya başlatan her test kampanya tohumunu sabitler (`api/tests/town_seed.py` → `fixed_town`; yolculuk senaryolarında `campaign_seed`). Kasaba kampanya kimliğinden üretilir; rastgele kimlik rastgele kırıklara yol açar.
- **[Kalite] Sabit komşu seti (atlanamaz; hızlı katman da bunu içerir):** her görevin hedefli testlerine ayrıca şunlar girer: `api.tests.test_journey_runner`, `test_journey_report`, `test_journey_schema`, `test_journeys`. Yeni numaralı senaryo eklenirse rapor tablosuna türü de eklenir.
- **[Hız] Tam paket:** yalnız dilim sonunda ve planda ara kapı olarak işaretlenen kilometre taşlarında; her görevde değil.
- **[Güvenlik] İnceleme seviyesi:** para, kayıt ve Geri Al'a dokunan iş için bağımsız inceleme ve en güçlü model; yalnız test düzeltmesi ya da küçük kırmızı-yeşil düzeltme için ucuz kapsamlı yeniden inceleme. Önce kırmızı test, sonra düzeltme. Para/kayıt/Geri Al'a dokunmayan, tek satırlık ya da yalnız metin/ek düzeltmede ve kırmızı-yeşil testi olduğunda yeniden inceleme atlanabilir; bu ledger'a "Ruling" olarak yazılır ve dilim sonu bütün dal incelemesi kapsar.
- **[Kalite] Bilinen kırıklar:** bir görevin hedefli koşusu başka yerde kırık gösterirse kökeni commit'e kadar izlenir (hangi Dilim commit'i getirdi); "zaten kırıktı" kabul edilmez. Gerçekten eskiyse deftere yazılır. Kırık rastgele (flake) ise bisect yapılmaz, tohum sabitlenir; aynı kodda yinelenen koşuda sonuç değişiyorsa flake sayılır. Köken bulunamazsa deftere "kökeni bilinmiyor" yazılır ve kapıya etkisi değerlendirilir.
- **[Hız] Belirsizlik ve karar:** çalışan bir plan insan beklemez. Dur ve sor yalnız dört durumda: geri alınamaz/yıkıcı işlem; güvenlik açısından hassas işlem (anahtar, harcama dahil); worktree dışı yan etki (main/dev'e push veya merge, yayın); her yolu tahmine bırakan bozuk plan. Diğer her belirsizlikte karar ver ve ledger'a `Ruling: <karar> — <neden> — <yanlışsa maliyeti>` yaz; yanlış karar geri alınabilir, bekleyen oturum geri alınamaz.
- **[Hız] Park etme:** küçük bulgular deftere "park" olarak yazılır, çekirdek işi durdurmaz; kapıyı (ara kapı, dilim sonu) etkileyen kırık durdurur. Parklar dilim sonu karar/devir listesinde toplanır; sahipsiz park bırakılmaz.
- **[Kalite] Yeniden kullanım:** yeni kod yazmadan önce repoda ve standart kütüphanede hazır olanı ara (`docs/agents/implementer-preamble.md` madde h); bu kural para/kayıt/Geri Al kodunda doğrulamayı, hata işlemeyi, makbuzu, kayıt ve Geri Al denetimini ve testleri ASLA azaltmaz.
- **[Kalite] Test yeniden yazımı:** eski davranışı sabitleyen testler ancak eşit sıkılıkla yeniden yazılır ve onay listesine girer (sınırı yeniden tanımlayan her değişiklik açıkça "gevşetme olabilir" diye işaretlenir); işaretli değişiklik işi durdurmaz ama onay listesine girer; işaretsiz gevşetme, atlama ya da silme işi durdurur.

### Hız kuralları (güvenlik ve kaliteden ödün vermeden)

*Ledger = çalışmakta olan planın `.superpowers/sdd/<plan>/progress.md` dosyası. 1. ve 2. maddeler pilottur: dilim sonunda ledger'daki ölçümle tutulur, budanır ya da değiştirilir.* Tam metin: `docs/agents/hiz-kurallari.md`; bir maddeyi uygulamadan önce oradaki tam hâlini oku.

1. **[Hız] Çakışan inceleme (pilot):** görev N incelenirken N+1'in implementer'ı başlayabilir; yalnız N+1, N'nin çıktısını tüketmiyorsa ve dosya listeleri çakışmıyorsa. İnceleme `git archive <sha>` kopyasında ayrı slotta koşar; iki implementer asla aynı anda yazmaz.
2. **[Kalite] İmplementer kontrol listesi (pilot):** her implementer istemine `docs/agents/implementer-preamble.md` konur; her madde cevaplanır.
3. **[Hız] Brifler:** satır numarası değil işlev/dosya adı verilir.
4. **[Hız] Hızlı katman:** görev içinde hızlı set (yeni testler + komşu geçit seti), uzun set görev sonunda bir kez; süre ölçülür, tahmin edilmez.
5. **[Hız] Paketleme:** küçük, aynı şekilli, bağımsız işler tek brif ve tek diff; kendi karar, test ya da inceleme yüzeyi olan iş paketlenmez.
6. **[Hız] Bekleme döngüleri:** her bekleme döngüsünün üst süresi olur; oturum ve dilim sonunda açık `bash`/`sleep` süreçleri kontrol edilir.

**[Güvenlik] Dokunulmaz:** para/kayıt/Geri Al için bağımsız inceleme, sıfır tolerans yolculukları, dilim sonu tam paket ve bütün dal incelemesi (en güçlü model), main/dev'e yalnız kullanıcı onayıyla merge.

## Sahibin kuralları (tek kaynak)

Bunlar Kadir'in kalıcı kurallarıdır; bellek dosyaları değil bu bölüm esastır. Yukarıdaki "Çalışma ve test disiplini" ile çelişirse güvenlik ve kalite kazanır.

- **[Güvenlik] Push/merge/yayın:** yalnız Kadir'in o işlem için taze onayıyla; force push yok (geri alınamaz, başkasının işini siler).
- **[Güvenlik] CI kontrolü:** her push/merge sonrası `gh run list --repo kadirkayarr-beep/AI-DND` ile 'AI-DND bounded verification' bakılır (CI yalnız main push ve pull_request'te çalışır); kırmızıyı hemen bildir, sonra düzelt, yeşil olmadan "bitti" deme (yerel yeşil CI'ın yerini tutmaz).
- **[Güvenlik] Commit kaybı:** birleştirmeden/push'tan önce dal ve commitlerin başka yerde olup olmadığına bak (hedef uç atası mı); eski Ekim dallarına dokunulmaz (iş kaybı geri alınamaz).
- **[Güvenlik] Anahtarlar:** anahtar/API dosyaları okunmaz, yazdırılmaz, commit edilmez; anahtarları yalnız sahibi girer (sızıntı geri alınamaz).
- **[Güvenlik] Dış kod ve veri:** doğrulanmamış skill, hook, npx kurulmaz; önce repo okunur, yalnız markdown içerenler kurulur; ekran görüntüsü ya da veri dış servise sorulmadan gönderilmez (gizlilik, gizli hook riski).
- **[Güvenlik] Silme koruması:** silmeden önce hedefe bak (kirli dosya, uzak dalda olmayan commit); dallar silinmez (kayıp geri alınamaz).
- **[Hız] Paralel çalışma:** güvenlik ve kaliteden ödün vermeden mümkünse bağımsız işler aynı anda yürütülür: ayrı worktree, tek yazıcı, ayrı test yuvası (bkz. Hız kuralı 1).
- **[Hız] Tek durma koşulları:** liste "Belirsizlik ve karar" maddesindeki dört durumdur (geri alınamaz/yıkıcı, güvenlik açısından hassas, worktree dışı yan etki, bozuk plan); burada tekrarlanmaz, başka durma koşulu eklenmez.
- **[Hız] Token tasarrufu ve model seçimi:** haftalık limit dar; ucuz model işlere, fable yalnız para/kayıt/Geri Al ve bütün-dal incelemesine; yeni numaralı iş için önce bütçe tahmini.
- **[Kalite] Sahibin dili:** kısa, açık, dürüst ve sade Türkçe; Kadir programcı değil, doğrulamadığını söyle (yanlış güven zarar verir); harcama/push/merge/silme için onay iste.
- **[Kalite] Oynayış kapısı (Kadir, 2026-11-12):** Kadir en az 10 dakika oynamadan hiçbir dilim "bitti" sayılmaz; testlerin yeşil olması oynayışın yerini tutmaz. Oynayış yapılmadıysa ledger'a "oynayış bekliyor" yazılır ve sonraki dilim başlamaz.
- **[Kalite] Sabah özeti (Kadir, 2026-11-12):** Kadir yokken yapılan her çalışmanın sonunda en çok beş satırlık sade Türkçe özet yazılır: ne değişti, neden, hangi dosyalarda, ne doğrulandı, Kadir'den ne bekleniyor.

## Otonom çalışma ve izinler

- İzinler `.claude/settings.json` dosyasındadır: dosya düzenleme onaysızdır; push, merge, PR ve silme her seferinde Kadir'e sorulur; main/dev'e doğrudan push, force push ve dal silme kapalıdır.
- Bir komut reddedilirse aynı işi başka yazımla (ör. `git -C`, `bash -c`) deneme; ne yapmak istediğini Kadir'e yaz.
- "Bitti" demeden önce koşunun çıktısını göster; koşmadığın testi geçti sayma.
- **[Hız] Eski kanıt:** `attached_assets/`, `docs/design/arsiv/`, `docs/acceptance/`, `.local/evidence/` toplu okunmaz; yalnız adı verilen tek kayıt açılır.

## Arayüz işi (Kadir, 2026-11-13)

Bu bölüm `artifacts/ai-dnd-experience` altındaki her görsel değişiklik için geçerlidir. "En az kod" kuralı burada gereksiz soyutlama yazmamak demektir; eksik durum, ham tarayıcı bileşeni ya da yarım görsel bırakmak demek değildir.

- **[Kalite] Hedef resimdir:** her ekran işi bir hedefle başlar: onaylı prototip (`UI_PROTOTIP_V4_20261111`), `PROTOTIP_ENVANTERI_20261113.md` satırı ya da Kadir'in ekran görüntüsü. Hedef yoksa önce Kadir'e taslak gösterilir, kod yazılmaz.
- **[Kalite] Gör, sonra "bitti" de:** iş, çalışan oyunun 1440 ve 390 piksel genişlikte ekran görüntüsü alınıp hedefin yanına konmadan bitmez. Görüntüler rapora dosya adıyla yazılır. Ekran görüntüsü alınamıyorsa durulur ve Kadir'e söylenir; görmeden "bitti" denmez.
- **[Kalite] Bitti tanımı:** (1) hedefle yan yana karşılaştırma ve kalan farkların listesi; (2) boş, yükleniyor, hata ve uzun içerik durumları; (3) gece ve gündüz teması; (4) 390 pikselde yatay kaydırma yok; (5) klavyeyle gezinme ve odak görünür; (6) renk, yazı tipi ve boşluk yalnız `src/index.css` değişkenlerinden gelir, elle renk kodu yazılmaz; (7) ham tarayıcı `select`, `checkbox`, `alert` kullanılmaz, depodaki hazır bileşenler (`src/components/ui`) kullanılır; (8) bütün arayüz testleri yeşil.
- **[Kalite] Kısayolu söyle:** bir şey basit yoldan yapıldıysa ya da bırakıldıysa raporun ilk satırına "Kısayol: <ne, neden>" yazılır. Söylenmemiş kısayol, işaretsiz gevşetme sayılır ve işi durdurur.
- **[Kalite] Tek ekran, tek oturum:** bir oturum bir ekranı (ya da bir paneli) bitirir. Sıradaki ekran yeni oturumda başlar.
- **[Kalite] Ayrı göz:** ekran görüntüleri, kodu yazmamış ayrı bir oturumda `ui-design-review:review` ile incelenir. Bulgular önem sırasıyla Kadir'e gider; hangilerinin düzeltileceğine Kadir karar verir.
- **[Kalite] Model:** tasarım dilini kuran iş (ilk ekran, ortak görsel kurallar, yeni gösterge) en güçlü modelle yapılır. O kurallara uyan tekrar işleri ucuz modelle yapılabilir. Bu, "Token tasarrufu ve model seçimi" kuralının arayüz istisnasıdır.
- **[Kalite] Kabul:** bir ekranı yalnız Kadir kabul eder. Test yeşili ve inceleme raporu kabul değildir.

## İçerik kapsamı ve açık kapı

- Oyun yetişkinlere yönelik karanlık fantezidir. Savaş, kan, korku, suç (hırsızlık, cinayet), acımasız ya da kötü NPC'ler ve sert dil kurgu olarak kapsam içindedir; bunlar için sorma, uyarı ekleme, metni kendiliğinden yumuşatma.
- **Açık kapı:** bir metni ya da kodu yazmayacaksan işi durdurma. Tek cümleyle neyi yazmadığını söyle, o yere `KADIR_DOLDURACAK: <burada ne bekleniyor>` yer tutucusu koy, ledger'a park olarak yaz ve işin kalanını bitir. Yer tutucuyu haber vermeden yumuşatılmış metinle doldurma.
