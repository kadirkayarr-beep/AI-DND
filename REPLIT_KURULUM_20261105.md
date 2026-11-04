# Replit'i projeye bağlama (2026-11-05)

Amaç (Kadir): (1) oyunu internetten oynamak, (2) benim haftalık kullanımım yokken Replit Agent ile kodlamaya devam etmek.
Not: Replit hesabına girişi, GitHub bağlantısını ve gizli anahtarları **sen** girersin; ben veya hiçbir ajan anahtar girmez.

## Önce bilmen gereken dört engel (depoda doğruladım)
1. **Anahtarlar bugün yalnız Windows dosyalarından okunuyor.** `ai-dnd/api/model_chain.py` anahtarı `%USERPROFILE%\.aidnd-gemini-key` ve `.aidnd-anthropic-key` dosyalarından okur (`_read_key`). Replit Linux'tur ve `USERPROFILE` yoktur → anahtar boş gelir → zincir hiç kurulmaz → oyun yerel Ollama bekler, orada Ollama/Gemma yok. **Küçük bir kod değişikliği şart:** anahtar ortam değişkeninden de okunmalı (ör. `AI_DND_GEMINI_KEY`, `AI_DND_ANTHROPIC_KEY`). Aşağıdaki Replit Agent görev metni bunu istiyor.
2. **Kayıtlar silinebilir.** `.replit` şu an `autoscale` dağıtımı kullanıyor; bu dağıtımın dosya sistemi kalıcı değildir. Kayıt (sqlite) kaybolur. Oynamak için **Reserved VM** (ya da kalıcı disk) gerekir, yoksa "kaydedilen oyun kaybolmaz" kuralımız bozulur. Kayıt yolu `AI_DND_CAMPAIGN_DB` ortam değişkeniyle verilir.
3. **Herkes oynayabilir/kullanabilir riski.** Yerel kimlik modu (`AI_DND_AUTH_MODE=local`) giriş sormaz. Adresi internete açarsan adresi bulan biri **senin Gemini/Haiku anahtarınla** oynar (Haiku ücretli). Çözüm: Replit'in özel (giriş isteyen) dağıtımı ya da Clerk kimlik doğrulaması (`AI_DND_AUTH_MODE=clerk`, `SECURITY_POSTURE.md`'ye bak). **Kimlik doğrulaması olmadan herkese açık dağıtım yapma.**
4. **Arayüz sunulmuyor.** `.replit` yalnız FastAPI'yi (port 8000) çalıştırıyor. Oyun arayüzü `artifacts/ai-dnd-experience` (Vite/React); derlenip sunulması ya da ayrı çalıştırılması gerekir.
Ek: yerel Gemma yok → zincir yalnız Gemini → Haiku. Gemini ücretsiz katmanda hız sınırına takılabilir (ölçümde bir kez oldu); o zaman Haiku devreye girer ve para harcar (3 USD/gün uyarı eşiği vardır).

## Adımlar (sen yaparsın)
1. replit.com'a gir → **Create App → Import from GitHub** → `kadirkayarr-beep/AI-DND` (özel depo; Replit GitHub bağlantısına izin ver).
2. Dal: **`task/c-series-merge`** (kararlı hat, `ae815c4f`). Dilim 0/1 henüz birleşmedi; devam işi için aşağıya bak.
3. Replit'te yeni bir dal aç: **`replit/online-play-20261105`**. `main` ve `dev/ai-dnd` dallarına ASLA yazdırma.
4. **Secrets** (sol menü, kilit simgesi): `AI_DND_MODEL_CHAIN=gemini,haiku`, `AI_DND_GEMINI_KEY=<anahtar>`, `AI_DND_ANTHROPIC_KEY=<anahtar>` (anahtarlar `C:\Users\Kadir\.aidnd-*-key` dosyalarında; ben göstermem, sen kopyala), `AI_DND_AUTH_MODE=local` (yalnız özel dağıtımda; yoksa clerk), `AI_DND_CAMPAIGN_DB=<kalıcı diskte yol>`.
5. Aşağıdaki **Replit Agent görev metnini** Agent'a yapıştır.
6. Dağıtım türü: **Reserved VM**, **özel** (giriş gerekli). Telefondan adresi aç.

## Replit Agent görev metni (yapıştır)
```
Bu depo AI-DND: Türkçe, tek oyunculu D&D 2024 oyunu (FastAPI motoru `ai-dnd/`, React arayüzü `artifacts/ai-dnd-experience/`). Önce `replit.md`, `CLAUDE.md` ve `START_HERE.md` dosyalarını oku.
KURALLAR: Yalnız `replit/online-play-20261105` dalında çalış. `main` ve `dev/ai-dnd` dallarına yazma, force push yapma. Commit mesajına atıf satırı ekleme. Anahtarları (Gemini/Anthropic) hiçbir dosyaya, günlüğe veya commit'e yazma; yalnız Replit Secrets'tan oku. Para, kayıt ve Geri Al davranışına dokunma (sıfır tolerans).
GÖREV (oyunu internette oynanır yapmak):
1) `ai-dnd/api/model_chain.py` içinde `_read_key`: anahtar önce ortam değişkeninden (`AI_DND_GEMINI_KEY`, `AI_DND_ANTHROPIC_KEY`) okunsun, yoksa mevcut dosyadan; davranış başka hiçbir yerde değişmesin. Bunun için önce başarısız test yaz (`ai-dnd/api/tests/test_model_chain.py` desenine uy), sonra geçir. Harcama/kullanım dosyaları (`_spend_path`, `_usage_path`) Linux'ta `Path.home()` altına düşüyor; kalıcı bir dizine (`AI_DND_DATA_DIR` gibi bir ortam değişkeniyle) yönlendirilebilsin.
2) Kayıt sqlite dosyası `AI_DND_CAMPAIGN_DB` ile kalıcı diske konsun; dağıtım türü Reserved VM olsun, `.replit` `[deployment]` ayarını buna göre güncelle (autoscale kayıtları siler).
3) Arayüzü derle (`pnpm --filter @workspace/ai-dnd-experience run build`) ve FastAPI'nin ya da küçük bir statik sunucunun onu aynı adresten sunmasını sağla; API adresi göreli olsun.
4) Herkese açık dağıtım yapma: giriş isteyen (özel) dağıtım kullan. Kimlik doğrulama gereksinimi için `SECURITY_POSTURE.md` ve `ai-dnd/api/auth.py` oku; Clerk gerekiyorsa Kadir'e sor, kendin hesap açma.
5) Bitince: kısa Türkçe rapor yaz (ne değişti, ne denendi, ne denenmedi), dalı GitHub'a it.
```

## Replit'te kodlamaya devam etmek (benim kullanımım yokken)
- İş **Dilim 0 ve Dilim 1**; durum, kalan görevler ve komutlar `HANDOFF.md` içindeki "DURUM: HER ŞEY DURDURULDU" bölümünde. HANDOFF.md ve tüm tasarım/plan belgeleri GitHub'da **`docs/devir-belgeleri-20261105`** dalında. Replit'e o dalı da getir (Git panelinden `Fetch`), dosyaları `Desktop\AI-DND-b01-isolated` karşılığı olarak bir `devir/` klasörüne kopyala (depoya commit etme).
- Dilim 1 dalı: `task/dilim1-money-memory-20261104` (`353ce7d6`, Görev 10 WIP). Dilim 0 dalı: `task/dilim0-ui-20261104` (`4455b5b9`, Görev 5 WIP). Replit Agent bu dallarda **tek yazar** olarak devam eder; ben (Claude) aynı anda aynı dalda yazmam.
- Uzun testler yine `TESTLER_BEKLIYOR_20261104.md` listesine yazılır; test altyapısı (`slot.sh`, WSL, korumalı başlatıcı) **yalnız senin Windows bilgisayarında** çalışır, Replit'te çalışmaz. Replit'te yalnız hızlı `python -m unittest api.tests.<modül>` ile odaklı test koşulabilir; sonuçları "Windows'ta doğrulanmadı" diye işaretle.
- Para/kayıt/Geri Al görevlerinde (Dilim 1 Görev 10, 20, 21) Replit'in ürettiği kodu bilgisayarında tam test paketiyle doğrulamadan birleştirme.
