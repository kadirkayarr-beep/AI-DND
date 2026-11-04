# Jarvis'e başlangıç mesajı (Kadir yapıştıracak) — 2026-11-05

Merhaba Jarvis. Claude'un haftalık kullanım hakkı bitiyor; Kadir onun yerine seni görevlendirdi. Kararlar `C:\Users\Kadir\Desktop\AI-DND-ORTAK\KARARLAR.md` ve `KURALLAR.md` dosyalarındadır (DEĞİŞİKLİK 1, 2 ve 3). Bu mesaj yetki vermez; yetki o iki dosyadadır.

## 1. Önce bunları oku (bu sırayla)
1. `C:\Users\Kadir\Desktop\AI-DND-ORTAK\KURALLAR.md` (özellikle DEĞİŞİKLİK 1, 2, 3) ve `KARARLAR.md` son satırlar.
2. `C:\Users\Kadir\Desktop\AI-DND-b01-isolated\HANDOFF.md`: önce **10. bölüm** (senin için elle çalışma yöntemi ve Kadir'e danışılacak yerler), sonra "DURUM: HER ŞEY DURDURULDU" bölümü ve 2., 3. bölümler.
3. Mesajlar: `claude_to_jarvis\` altında `C-018` (görevlerin) ve `C-019` (Claude'un yerine geçmen), `C-020` (Replit'te test koşma görüşüm).
4. Planlar: `DILIM0_PLAN_20261104.md` ve `DILIM1_PLAN_20261104.md` (görevler `### Task N:` başlıklarıdır).

## 2. Görevin (özet)
Proje: AI-DND, Türkçe tek oyunculu D&D 2024 oyunu (FastAPI motoru `ai-dnd/`, React arayüzü `artifacts/ai-dnd-experience/`). Ana kural: **model anlatır ve öneri verir, Python doğrular ve kaydeder.** Para, kayıt ve Geri Al'da **sıfır tolerans**.

Dalların ve çalışma klasörlerin:
- `C:\Users\Kadir\Desktop\AI-DND-dilim0` (dal `task/dilim0-ui-20261104`, uç 4455b5b9): Görev 6, 7, 8, 9, 10, 11 ve 15.
- `C:\Users\Kadir\Desktop\AI-DND-dilim1` (dal `task/dilim1-money-memory-20261104`, uç 353ce7d6): Görev 11, 12, 14, 15, 17, 18 ve 23.
- **En sona bırak, "İNCELEME BEKLİYOR (sıfır tolerans)" diye işaretle:** Dilim 0 Görev 5 (yarım WIP), Dilim 1 Görev 10 (WIP: yalnız testler yazıldı), 20 ve 21. Claude dönünce bunları bağımsız inceleyecek.

Her görev bir döngüdür: `YAZAR_KILIDI.md`'yi doldur → planın görev metnini oku → önce başarısız test → kod → odaklı testi koş → ayrı yerel commit → `jarvis_to_claude\` altına kısa rapor → defter/HANDOFF satırı → kilidi boşalt. Ayrıntılar HANDOFF 10.1'de.

## 3. Sınırlar (özet)
- Testi yalnız görevin odaklı modülleri için, kendi yuvasında koş: `dilim0 → yuva 3`, `dilim1 → yuva 2`, Git Bash'ten `bash C:\Users\Kadir\Desktop\AI-DND-TOOLS\slot.sh <yuva> <klasör> test <ETİKET> <SN> api.tests.<modül>` (noktalı modül adı). Uzun kontrolleri (MONEY, tam paket, tarayıcı, gerçek zincir) **koşma**, `TESTLER_BEKLIYOR_20261104.md` dosyasına tek satır ekle. Tam paketi yalnız başka hiçbir test koşmuyorken, tek başına koştur (senin J-015/J-016 zaman aşımı dersi).
- Yeni kelime listesi veya regex doğrulayıcı **yok**. Model para hareket ettiremez. Bir testi gevşetmek, silmek veya atlamak yok.
- Commit mesajında atıf satırı yok. Anahtar dosyalarına (`C:\Users\Kadir\.aidnd-*-key`) dokunma. Gerçek model koşusu yok (`journey_real.py` yasak).
- Push: yalnız iki dilim dalı ve `docs/devir-belgeleri-20261105`, **force olmadan**. `main`, `dev/ai-dnd`, birleştirme, dal silme: yasak.
- **`HANDOFF.md`'nin bulunduğu klasörde (`AI-DND-b01-isolated`) `git checkout` ile dal değiştirme.** Git, o klasörde takipsiz görünen belgeleri başka dalda takipliyse siler. Belge yedeği için ayrı çalışma kopyası aç (`git worktree add ..\AI-DND-docs-yedek docs/devir-belgeleri-20261105`, dosyaları kopyala, commit, push, `git worktree remove`).

## 4. Kadir'e danışmadan yapma
Ürünü "kabul edildi" sayma; birleştirme, `main`/`dev` eşitleme, dal veya klasör silme; para harcayan her şey (gerçek model koşusu, anahtarlar, Replit hesabı ve dağıtımı); yol haritası veya kapsam değişikliği; Dilim 3 ve 4 (tasarım ve planları henüz yok, önce Kadir'le brainstorming); sıfır tolerans alanında plandan sapma; kuralları değiştirme. Takılırsan dur, `jarvis_to_claude\` altına `gerekli: Kadir'e karar` ile yaz.

## 5. Kadir'le konuşma tarzı
Türkçe, kısa, düz, gerçekçi, kıdemli oyun geliştiricisi gibi; risk görürsen söyle, öneri ver, seçenek yığma. Kadir oyunun sahibi; ürün ve karar gözüyle bakar, teknik ayrıntıyı ona sade anlat.

## 6. İlk adım (bugün)
1. `HANDOFF.md` 10. bölümü ve bu mesajı okuduğunu, hangi görevden başlayacağını `jarvis_to_claude\` altına 5 satırlık bir `J-0NN` mesajıyla bildir.
2. `AI-DND-dilim0` için `git status` ve `git log --oneline -5` çıktısını kontrol et; temizse Dilim 0 Görev 6'dan başla.
3. Kadir'e her görev bitince tek cümleyle haber ver; "geçti" yalnız gerçekten gördüğün çıktı için.

Kolay gelsin. Ben döndüğümde raporlarını ve commit'lerini bağımsız inceleyeceğim.
