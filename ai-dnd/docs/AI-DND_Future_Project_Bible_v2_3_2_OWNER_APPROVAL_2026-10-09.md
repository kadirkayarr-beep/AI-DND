# AI-DND — Future Project Bible v2.3.2 Owner Approval / Freeze Record

**Tarih:** 2026-10-09 (Türkiye, Europe/Istanbul)  
**Karar:** OWNER-APPROVED — roadmap/governance freeze only  
**Karar türü:** Ayrı onay kaydı; kaynak Project Bible dosyası değiştirilmez.

## Onaylanan kaynak

- **Dosya:** `ai-dnd/docs/AI-DND_Future_Project_Bible_v2_3_2_PROPOSED.md`
- **SHA-256 (tam dosya, bayt bazında):** `7685bc4318bea56a5b23713af712d22b3a4749d2e5c2d97b551b1e545ef3fcb3`
- **Ölçüm:** 2026-10-09 tarihinde mevcut yerel çalışma dosyasında `certutil -hashfile ... SHA256` ile doğrulandı.
- **Belgedeki kimlik:** `AI-DND-FPB-2.3.2-PROPOSED`. Başlıktaki PROPOSED tarihsel kaynak metnidir; owner onayı yalnız bu ayrı kayıtla verilir.

## Owner onayı

Önceki görüşmede assistant, bu SHA-256 ile Project Bible v2.3.2'nin AI-DND'nin onaylı gelecek geliştirme yol haritası olarak dondurulması için açık onay istedi.

**Owner'ın mevcut konuşmadaki açık yanıtı:** “onay veriyorum devam”

Bu yanıt, yukarıda tam yol ve SHA-256 ile tanımlanan **Future Project Bible v2.3.2 yol haritasını**, gelecekteki uygulama planlarının hazırlanmasında referans alınacak **dondurulmuş, owner-approved roadmap** olarak kabul eder.

Master Handoff v3'ün mevcut mimari sahiplik hükümleri korunur. Mevcut D&D 2024 ve Forgotten Realms kaynak otoriteleri ile kampanya canon'u yerinde durur. Bu kayıt daha önce doğrulanmış oyun kabul testlerinin yerine geçmez.

## Bu onay NELERİ açmaz

- F01–F15 dahil hiçbir uygulama fazını veya kapsamı otomatik başlatmaz; her uygulama fazı ayrı sürümlü master plan ve açık owner onayı gerektirir.
- Phase 8 Expansion'ın kapanışı, Stage 10B'nin tüm repo/production kabulü veya S10B-INV-001'in çözülmesi anlamına gelmez.
- Git `add`, stage, commit, push, merge, reset, clean, restore, stash, branch değiştirme veya yıkıcı işlem izni değildir.
- Production/deployment, Phase 9, yeni şehir admission/aktivasyonu, yeni lore pinleri, save migration veya oyun kodunda yetki değişikliği değildir.
- Henüz OPEN DECISION / BLOCKED / PENDING olan maddeleri PASS'a dönüştürmez.

## Dondurulan belgenin uygulanması

1. Gelecekteki tüm faz/FX planları bu tam SHA-256 ile referans verir ve Master Handoff v3 ile uyumlu olmalıdır.
2. Sonradan gelen yeni fikir, otomatik kapsam genişlemesi değil; Future Project Bible'daki FX/change-control süreciyle ayrı kapsam/onay konusudur.
3. Belgenin baytları değiştirilirse bu kayıt yeni SHA-256'ya taşınmaz. Yeni sürümün yeniden incelenmesi ve ayrı owner onayı gerekir.
4. Önceki v2, v2.1, v2.2, v2.3 ve v2.3.1 dosyaları tarihsel belgeler olarak değiştirilmeden korunur.
5. Phase 8 kapanışı için Stage 10A/10B tarihsel kabul, gerçek kaynak snapshot'ı, Git taşınabilirliği, eksik kanıtlar ve ayrı owner kapanış kararı incelenir. Bu freeze kaydı o incelemenin PASS'i değildir.

## Kaydın kendi sınırı

Bu onay belgesinin oluşturulması yalnızca dokümantasyon işlemidir. Bu aşamada oyun kaynağı, test, lore verisi, pin, `.gitattributes`, Git index veya Git geçmişi değiştirilmez. `git add/commit/push` işlemleri ayrıca onaylanacaktır.
