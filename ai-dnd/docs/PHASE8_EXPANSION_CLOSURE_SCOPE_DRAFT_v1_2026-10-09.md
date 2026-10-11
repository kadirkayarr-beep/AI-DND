# AI-DND — Phase 8 Expansion Closure Scope Draft v1

**Belge kodu:** `AI-DND-P8-CLOSURE-SCOPE-DRAFT-v1`  
**Tarih:** 2026-10-09, Europe/Istanbul  
**Durum:** **DRAFT. KAPANIŞ DEĞİLDİR. PASS DEĞİLDİR. OWNER ONAYI DEĞİLDİR.**

Bu taslak, owner incelemesi için önerilen Phase 8 Expansion kapanış kapsamını dondurur. Hiçbir maddeyi PASS yapmaz. Tarihsel FAIL kayıtlarını kapsam dışına almaz. Oyun kodu, lore, pin, save, aktivasyon bayrağı, `.gitattributes` ve Git geçmişi bu belgeyle değişmez.

## 1. Bağlanan kaynaklar

İncelenen ağaç: `C:\Users\Kadir\Desktop\AI-DND-phase8-expansion`  
Dal: `phase8/emergent-storytelling-expansion`  
HEAD: `0c7b24cd7ec9e32f0a54412769f85851b30d11a2`  
Önceki checkpoint: `4fadca4c42f0fa4ccea7ca9d918406a3182b0e56`  
Oyun kaynağı checkpoint’i: `f503d99`  
`f503d99..HEAD` yalnız doküman ve arşiv `.gitattributes` satırıdır. Bu taslak o aralıkta test koşmadı.

| Belge | Rol |
|---|---|
| `ai-dnd/docs/AI-DND_Future_Project_Bible_v2_3_2_PROPOSED.md` | Onaylı yol haritası. SHA-256 `7685bc4318bea56a5b23713af712d22b3a4749d2e5c2d97b551b1e545ef3fcb3`. Baytları bu taslakla değişmez. |
| `ai-dnd/docs/AI-DND_Future_Project_Bible_v2_3_2_OWNER_APPROVAL_2026-10-09.md` | Yol haritası freeze kaydı. Faz, kapanış veya şehir açmaz. |
| `ai-dnd/docs/PHASE8_LOCAL_CHECKPOINT_CLOSEOUT_2026-10-09.md` | Yerel mühendislik checkpoint’i CLOSED. Live-release NO-GO. Bu taslağın yerine geçmez. |
| `ai-dnd/docs/STAGE10A_FINAL_CLOSURE_CURSOR_HANDOFF_v2_2026-10-09.md` | Stage 10A reconstructed yerel kabul CLOSED. Özgün tam sözleşme bulunamadı. |
| `ai-dnd/docs/STAGE10B_REPAIR_FINAL_ACCEPTANCE_CURSOR_HANDOFF_v2_2026-10-09.md` | Final kabul FAIL. Kapanış yazılmadı. |
| `ai-dnd/docs/STAGE10B_LORE_INTEGRITY_REPAIR_FINAL_ACCEPTANCE_CURSOR_HANDOFF_v1_2026-10-09.md` | Yerel lore-integrity kabulü. Depo geneli veya production değildir. |
| `ai-dnd/docs/STAGE10B_MASTER_IMPLEMENTATION_PLAN_v2.md` | S10B-INV-001 hükmü. |
| `ai-dnd/docs/evidence/phase8-expansion/gate-ledger.json` | Tarihsel `release: NO-GO`. Metni bu taslak değiştirmez. |

## 2. Dört ayrı onay kapısı

Bu kapılar birbirinin PASS’i değildir.

| Kapı | Bu taslağın hükmü |
|---|---|
| Phase 8 Expansion kapanışı | Kapsam önerisi. Kapanış kaydı yoktur. PASS yazılmaz. |
| F01 bütünlük | Beş lore pininin taze ölçümü, yayın manifestosunun bağımsız incelemesi ve üç Neverwinter dosyasının öznitelik karar kaydı bu taslakta yoktur. F01 faz PASS değildir. |
| F13 admission ve aktivasyon | Araştırma hazırlığı erken planlanır. Admission ve aktivasyon başlamaz. Waterdeep ve Baldur’s Gate kapalı kalır. |
| Production release | Gate ledger NO-GO durur. Bu taslak yayını açmaz. |

## 3. Önerilen kapanış kapsamı

Kapsam, kapanış iddiasından önce yazılır. Aşağıdaki maddeler önerilen kapsamın içindedir. Hiçbiri bu belgeyle PASS olmaz. Zorunlu bir FAIL, “ertelendi” veya “yeniden adlandırıldı” diye kapsamdan çıkmaz.

### 3.1 Kapsamda duran tarihsel hükümler

1. Stage 10A reconstructed yerel kabul PASS / OWNER-APPROVED / CLOSED’dur. Özgün tam kabul listesi bulunamadı. Production NO-GO’dur. Bu hüküm yeniden açılmaz ve taze PASS sayılmaz.
2. Stage 10B repair-v2 final kabulü **FAIL**’dir. Kapanış yazılmamıştır. Bu FAIL önerilen kapsamın içindedir.
3. Repair-v2 zorunlu lore koşusu: 165 test, 4 failure, 14 error, exit 1. Kanıt adı `boundary-persistence-weather-final`. Bu sonuç **S10B-AC-027 FAIL** olarak kapsamda kalır.
4. Repair-v2 `regressions-final`: 633 test, 3 failure, 2 error, exit 1. CP1254 tanı çıktısı ayrı olaydır. Bu kırmızı koşu silinmez.
5. Repair-v2 `regressions-final-02`: 634 yürütme / 632 farklı test, exit 0. Bu, 165 testlik FAIL’in yerine otomatik geçmez. Komut eşdeğerliği owner kabulü olmadan kurulmaz.
6. Repair-v2 anındaki Castle Ward hash uyuşmazlığı kaydı durur. Beklenen pin `be4b2f8a399103537f93fc33cfebe47524bd811a6fb232b577b480a087895d8a`, o andaki hash `d8accdf67802838b6e019cd8b05a75c781fc5a4837c14bbeb0d15c29c2d420da`. Sonraki lore-integrity onarımı ve closeout hizalama iddiası ayrı tarihsel kayıttır. Bu taslak pin baytını yeniden ölçmedi. Eski FAIL satırı silinmez. Güncel bayt bu belgeyle PASS yazılmaz.
7. Repair-v2 import engeli: `test_lore_1501_integration` o kayıtta `OwnerContinuityRecord` bulamamıştır. Sahte sınıf veya skip eklenmemiştir. Bu engel kaydı kapsamda kalır. Sonraki yeşil lore koşusu bu satırı yok etmez.
8. Lore-integrity handoff yerel PASS yazar: 296 test exit 0 ve 634 test exit 0. AC-001–AC-026 ve AC-028 önceki kanıta bağlanır. AC-027 için o handoff PASS der. Bu taslak o PASS’i taze kabul saymaz. 165 testlik FAIL, owner eşdeğerlik kabulü olmadan kapanmış sayılmaz.
9. Closeout yerel checkpoint’i CLOSED der ve live-release NO-GO’yu korur. 634, 296, 67 frontend testi, Vite ve 20 adımlı `qwen3:8b` senaryosu o belgenin tarihsel sonucudur. Bu taslak onları yeniden koşmadı.
10. Closeout, taze etkileşimli tarayıcı turunu bu checkpoint’te koşmadığını yazar. Stage 10B tarayıcı kanıtı tarihseldir. Taze tarayıcı **NOT TESTED**’dir.
11. S10B-INV-001 aralıklı HTTP 500 **UNCONFIRMED**’dır. Kapsamdadır. UNCONFIRMED kalması o maddenin PASS’i değildir. Kapsam dışına almak da onun geçtiği anlamına gelmez.
12. Gate ledger `release: NO-GO`. Waterdeep ve Baldur’s Gate `UNREVIEWED_DISABLED`. Bu cümleler kapsamda durur ve PASS’e çevrilmez.
13. Erken canlı senaryodaki HTTP 503, Ollama ortamı olmadığı için korunur. Sonraki loopback koşusu ayrı kayıttır. 503, INV-001 değildir.

### 3.2 Kapanışın şu an yazılamama nedeni

Önerilen kapsam onaylansa bile kapanış kaydı yazılamaz. Açık zorunlu maddeler:

- S10B-AC-027 repair-v2 FAIL’i, owner eşdeğerlik kabulü veya aynı yükümlülüğün taze ve geçerli kanıtı olmadan durur.
- S10B-INV-001 UNCONFIRMED’dır.
- Bağımsız lore yayın incelemesi yoktur. Release NO-GO’dur.
- Taze tarayıcı kanıtı yoktur.
- F01 yayın manifestosu ve üç Neverwinter öznitelik karar kaydı yoktur. Bunlar F01 kapısıdır. Yoklukları Phase 8 kapanışını production veya F15 iznine çevirmez.
- Phase 8 Expansion kapanışının hangi 10A ve 10B maddelerini zorunlu sayacağı owner kararıdır. Bu taslak listeyi yukarıdaki zorunlu FAIL ve UNCONFIRMED maddeleri düşürerek daraltmaz.

## 4. S10B-INV-001 araştırma planı

Bu bölüm soruşturma planıdır. Koşu bu taslakla başlamaz. Kusur fixed değildir. Şu an yeniden üretildiği de iddia edilmez.

### 4.1 Bilinen sınır

Plan v2, maddeyi `api/main.py` tur sınırıyla ilişkilendirir ve kök neden uydurulmasını yasaklar. Çıkmaması düzeltildiği anlamına gelmez. Beklenmeyen 500, ilgili kabul maddesini FAIL veya BLOCKED yapar. Traceback saklanır.

Repair-v2 üç ayrı 500 sınıfını karıştırmaz:

- Tarihsel aralıklı HTTP 500: UNCONFIRMED. Özgün istek, kampanya kimliği ve traceback bu taslağın okuduğu el devirlerinde tek bir vaka dosyasına bağlanmamıştır.
- CP1254 tanı çıktısından üretilen 500: `regressions-final.log` içinde kayıtlıdır. Dar kodlama testi `regressions-final-02` ile yeşildir. Bunun INV-001 ile aynı kök olduğu iddia edilmez.
- Kasıtlı save-failure ve proxy drop: ayrı test kayıtlarıdır. Soruşturma bunları INV-001 saymaz.

### 4.2 En küçük disposable prova

Onay çıkmadan koşulmaz. Üretim save, pin, lore ve tarihsel kanıt klasörleri yazılmaz.

1. Kaynak snapshot: HEAD `0c7b24c` ve oyun ağacı `f503d99` ile aynı olduğu için komut kaydı her iki kimliği yazar.
2. Veritabanı: boş, geçici bir SQLite dosyası. Mevcut kampanya dosyası açılmaz.
3. Ortam: yerel API, `qwen3:8b` kapalı ve açık iki kol. Kapalı kol, model yokken 503 ile 500’ü ayırır. Açık kol canlı çağrı yapar. İkisi ayrı günlük tutar.
4. Senaryo: tek kampanya, Neverwinter başlangıcı, bir serbest metin turu, bir doğrudan Python turu, bir çift gönderim, bir süreç yeniden başlatma ve ikinci kampanya. Yeni görev, şehir veya lore yazılmaz.
5. Gözlem: HTTP durumu, traceback, tur kimliği, çözüm öncesi veya sonrası sınır, çağrı sayısı. Beklenmeyen 500 olursa tam traceback yeni bir kanıt klasörüne kopyalanır. Tarihsel log üzerine yazılmaz.
6. Tekrar: aynı senaryo art arda üç disposable veritabanında. Bir kez çıkması CONFIRMED değildir. Üçünde de çıkmaması FIXED değildir. Sonuç UNCONFIRMED kalır veya, tekrarlanabilir traceback varsa, ayrı bir bug kaydı açılır.
7. Karşılaştırma: yeni traceback, `regressions-final.log` içindeki CP1254 500’ü ile satır satır karşılaştırılır. Aynı değilse INV-001’e bağlanmaz.

Kök neden ancak tekrarlanabilir traceback ve sahip modül yazılırsa önerilir. Öneri onarım izni değildir.

## 5. Erken F13-RESEARCH

F13-RESEARCH, Phase 8 kapanış çalışmasıyla aynı takvimde okunabilir. Admission ve aktivasyon değildir.

Başlamadan önce, salt okuma:

- Kurulu katalog yalnız `fr:pack:the_north:neverwinter:v1` ve `VERIFIED_PARTIAL`.
- `pack_index.json` içinde `fr:pack:waterdeep:v1` ve `fr:pack:baldurs_gate:v1` durumu `INCOMPLETE`.
- Çıkarım dosyaları diskte durur. Çıkarım, admission değildir.
- Test beklentisi `DISABLED = {waterdeep.v1, baldurs_gate.v1}`.
- `production_authorized` false.
- 1501 DR ve Neverwinter pinleri F01 koruması altındadır. Araştırma pin baytını değiştirmez.

Araştırma paketi, onaydan sonra yalnız şunları okur: extraction JSON, review eksikliği, public claim olup olmadığı, kısıt sınıfı, mevcut save konumlarının Neverwinter’da kalması. Yeni claim, pin, şehir bayrağı veya kampanya olayı yazmaz. Boş claim kümesi admission PASS değildir. İmza yokken runtime açılmaz.

F01 faz PASS, F13-ACTIVATION ve production release bu araştırmanın çıktısı değildir.

## 6. Owner kararları

Bu taslak bunları kapatmaz.

1. Önerilen kapsamın, bölüm 3’teki FAIL ve UNCONFIRMED maddeler dahil, Phase 8 Expansion kapanış listesi olarak kabul edilip edilmeyeceği.
2. Repair-v2’deki 165 testlik S10B-AC-027 FAIL’i ile sonraki 296/634 yeşil koşusunun aynı yükümlülük sayılıp sayılmayacağı. Kabul yoksa FAIL durur.
3. S10B-INV-001 disposable provasının çalıştırılmasına izin verilip verilmeyeceği. İzin, fixed hükmü değildir.
4. Bağımsız lore yayın incelemesi ve live-release NO-GO’nun ayrıca kapanıp kapanmayacağı. Bu taslak hayır der.
5. F01-AC-004 yayın manifestosu ve F01-AC-005 üç Neverwinter öznitelik karar kaydının ayrı F01 işi olarak açılıp açılmayacağı.
6. Waterdeep ve Baldur’s Gate için F13-RESEARCH okumasının, admission ve aktivasyon olmadan, Phase 8 kapsam çalışmasına paralel başlayıp başlamayacağı.

## 7. Bu belgenin açmadığı işler

Oyun kodu, test assertion’ı, lore baytı, save, şehir aktivasyonu, Phase 9, production, commit ve push bu taslağın izni değildir. Onaylı Bible ve owner onay kaydı yerinde kalır. Tarihsel el devirleri yerinde kalır.

**SON DURUM:** `DRAFT — OWNER REVIEW PENDING`. Kapanış yoktur. PASS yoktur.
