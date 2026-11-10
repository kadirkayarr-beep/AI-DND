## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- When graphify-out/graph.json exists, run `graphify query "<question>"` before your first grep, search or source-file read for a codebase question, and put this rule in every subagent prompt that explores code. Read raw files only for lines the graph or an earlier read already located. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- Run `graphify update .` (AST-only, no API cost) once at the end of a task and before handing a diff to review, not after every edit; keep `graphify-out` ready in every long-lived worktree. The graph is a navigation aid, not a substitute for reading: most bugs live in JSON content (templates, catalogs, menu tables) and dynamic paths, which the AST graph cannot see.
- graphify-out/ is local-only and gitignored on this shared branch (it is rewritten whole on every build); do not commit it.

# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

## Agent skills

### Issue tracker

İşler yerel markdown olarak `.scratch/` altında tutulur (GitHub Issues kullanılmaz). Bkz. `docs/agents/issue-tracker.md`.

### Triage labels

Varsayılan beş etiket: needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix. Bkz. `docs/agents/triage-labels.md`.

### Domain docs

Tek bağlam (single-context): kökte `GLOSSARY.md` ve `docs/adr/`. Bkz. `docs/agents/domain.md`.

## Çalışma ve test disiplini (Dilim 3 dersleri)

**Ana ilke:** kalite ve güvenlik kaybına müsamaha göstermeden işi hızlandırmak. Bir kural hız için kaliteyi ya da güvenliği zayıflatıyorsa uygulanmaz ve kullanıcıya bildirilir; kaliteye ya da güvenliğe katkısı olmayan bir adım hızı yavaşlatıyorsa budanır. Çelişkide kalite ve güvenlik kazanır.

- **[Güvenlik] İzolasyon:** her iş kendi worktree'sinde yapılır, aynı worktree'de tek yazıcı çalışır. main/dev'e push veya merge yalnızca kullanıcının onayıyla yapılır.
- **[Kalite] Sabit kasaba:** (`town_seed.py` ve `campaign_seed` yalnız Dilim 3 dalında var; dal birleşince bu not silinir) yeni kampanya başlatan her test kampanya tohumunu sabitler (`api/tests/town_seed.py` → `fixed_town`; yolculuk senaryolarında `campaign_seed`). Kasaba kampanya kimliğinden üretilir; rastgele kimlik rastgele kırıklara yol açar.
- **[Kalite] Sabit komşu seti (atlanamaz; hızlı katman da bunu içerir):** her görevin hedefli testlerine ayrıca şunlar girer: `api.tests.test_journey_runner`, `test_journey_report`, `test_journey_schema`, `test_journeys`. Yeni numaralı senaryo eklenirse rapor tablosuna türü de eklenir.
- **[Hız] Tam paket:** yalnız dilim sonunda ve planda ara kapı olarak işaretlenen kilometre taşlarında; her görevde değil.
- **[Güvenlik] İnceleme seviyesi:** para, kayıt ve Geri Al'a dokunan iş için bağımsız inceleme ve en güçlü model; yalnız test düzeltmesi ya da küçük kırmızı-yeşil düzeltme için ucuz kapsamlı yeniden inceleme. Önce kırmızı test, sonra düzeltme. Para/kayıt/Geri Al'a dokunmayan, tek satırlık ya da yalnız metin/ek düzeltmede ve kırmızı-yeşil testi olduğunda yeniden inceleme atlanabilir; bu ledger'a "Ruling" olarak yazılır ve dilim sonu bütün dal incelemesi kapsar.
- **[Kalite] Bilinen kırıklar:** bir görevin hedefli koşusu başka yerde kırık gösterirse kökeni commit'e kadar izlenir (hangi Dilim commit'i getirdi); "zaten kırıktı" kabul edilmez. Gerçekten eskiyse deftere yazılır. Kırık rastgele (flake) ise bisect yapılmaz, tohum sabitlenir; aynı kodda yinelenen koşuda sonuç değişiyorsa flake sayılır. Köken bulunamazsa deftere "kökeni bilinmiyor" yazılır ve kapıya etkisi değerlendirilir.
- **[Hız] Belirsizlik ve karar:** çalışan bir plan insan beklemez. Dur ve sor yalnız dört durumda: geri alınamaz/yıkıcı işlem; güvenlik açısından hassas işlem (anahtar, harcama dahil); worktree dışı yan etki (main/dev'e push veya merge, yayın); her yolu tahmine bırakan bozuk plan. Diğer her belirsizlikte karar ver ve ledger'a `Ruling: <karar> — <neden> — <yanlışsa maliyeti>` yaz; yanlış karar geri alınabilir, bekleyen oturum geri alınamaz.
- **[Hız] Park etme:** küçük bulgular deftere "park" olarak yazılır, çekirdek işi durdurmaz; kapıyı (ara kapı, dilim sonu) etkileyen kırık durdurur. Parklar dilim sonu karar/devir listesinde toplanır; sahipsiz park bırakılmaz.
- **[Kalite] Test yeniden yazımı:** eski davranışı sabitleyen testler ancak eşit sıkılıkla yeniden yazılır ve onay listesine girer (sınırı yeniden tanımlayan her değişiklik açıkça "gevşetme olabilir" diye işaretlenir); işaretli değişiklik işi durdurmaz ama onay listesine girer; işaretsiz gevşetme, atlama ya da silme işi durdurur.

### Hız kuralları (güvenlik ve kaliteden ödün vermeden)

*Ledger = çalışmakta olan planın `.superpowers/sdd/<plan>/progress.md` dosyası. 1. ve 2. maddeler pilottur: dilim sonunda (devir görevinde) ledger'daki ölçümle tutulur, budanır ya da değiştirilir.*

1. **[Hız] Çakışan inceleme:** görev N'nin bağımsız incelemesi sürerken görev N+1'in implementer'ı başlayabilir. İnceleme, incelenen commit'in `git archive <sha>` kopyasını ayrı slotta (slot 3) koşar; slot.sh varsayılanı çalışma ağacını yığar, NOSTAGE=1 ise yalnız o anki HEAD'i arşivler, ikisi de çakışan incelemede başka commit'i ya da yarım işi test eder, bu yüzden kullanılmaz. Implementer kendi slotunda (slot 2) çalışır. Düzeltme turu, N+1'in implementer'ı rapor verip durduktan sonra (N+1'in incelemesinden önce) N'nin implementer'ına yaptırılır ve N+1'in üstüne biner; iki implementer asla aynı anda yazmaz. Yalnız N+1, N'nin çıktısını (arayüz, veri, test yardımcısı) tüketmiyorsa ve brifteki dosya listeleri çakışmıyorsa uygulanır; aksi hâlde sırayla yapılır. **Pilot:** kazanç ölçülmedi; ledger'a görev başına süre ve düzeltme turu sayısı yazılır.
2. **[Kalite] İmplementer kontrol listesi:** her implementer istemine `docs/agents/implementer-preamble.md` konur (kontrol listesi a–g ve graphify/brif kuralları orada; inceleme bulgularından süzülmüştür); her madde cevaplanır, uygulanmıyorsa "uygulanmaz" ve nedeni yazılır. **Ölçüm:** ledger'a görev başına düzeltme turu sayısı yazılır; liste turları azaltmıyorsa budanır.
3. **[Hız] Brifler:** graphify kuralları yukarıdaki graphify bölümündedir ve implementer önsözüne girer; görev brifleri satır numarası değil işlev/dosya adı verir (satır numaraları bayatlar).
4. **[Hız] Hızlı katman:** görev içi döngüde önce hızlı set (yeni testler + komşu geçit seti, hedef birkaç dakika), uzun set görev sonunda bir kez. Yavaş modüller ölçülür (kampanyayı her testte yeniden yaratan sınıflarda yalnız değişmeyen kurulum `setUpClass`'ta paylaşılır, her test derin kopya alır; paylaşılan değişebilir dünya yasak) ve ölçüm ledger'a yazılır; sayı tahmin edilmez.
5. **[Hız] Paketleme:** küçük, aynı şekilli ve bağımsız görevler (cila, ufak metin/etiket düzeltmeleri, 3b maddeleri) tek implementer'a tek brifle verilir ve tek diff olarak incelenir. Kendi karar, test ya da inceleme yüzeyi gerektiren iş paketlenmez.
6. **[Hız] Bekleme döngüleri:** bir testi ya da çıktı dosyasını bekleyen döngünün her zaman üst süresi olur (testin planlanan süresi + pay); süre dolunca döngü kendiliğinden biter ve log'a bakılır. Test bitince ya da iş iptal edilince bekleyen döngü kapatılır. Bir ajan beklediği testin sonucunu zaten gördüyse artık beklemez; açık kalan döngü ajanın raporunu saatlerce geciktirir (Dilim 3'te 9-11 saat). Oturum sonunda ve her dilim sonunda açık `bash`/`sleep` süreçleri kontrol edilir.

**[Güvenlik] Dokunulmaz:** para/kayıt/Geri Al için bağımsız inceleme, sıfır tolerans yolculukları, dilim sonu tam paket ve bütün dal incelemesi (en güçlü model), main/dev'e yalnız kullanıcı onayıyla merge.
