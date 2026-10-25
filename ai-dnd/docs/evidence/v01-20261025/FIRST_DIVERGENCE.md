# Faz 0: ilk sapma kaydı

Tarih: 25 Ekim 2026 · Kaynak: `2d02a5e` (izole worktree `cursor/v01-scene-truth-20261025`).

## Hüküm

**Canlı olay için: `UNRESOLVED`.** Seçilen dal yok. Kanıtın doğrudan karşılığı aşağıda.

Canlı oynanıştaki çelişki ("anlatı tavernanın içini anlatıyor, gözlem sokak/kapı gösteriyor, oturma ve barmen hedefleme çalışmıyor") için şu kanıtlar yok:

| Gereken kanıt | Durum |
|---|---|
| Özgün H01–H05 girdi/mod/target/action id kaydı | Okunmadı. Kişisel kayıt ve kampanya dosyalarına bilerek dokunulmadı. |
| Çalışan sürecin kaynak ağacı | Kanıtlanamadı (`SOURCE_IDENTITY.json`: çalışma dizini `null`). Süreç 24 Ekim 13:44'te başlamış; son `game.py` commit'i 23:27. |
| Ham ve gösterilen model yanıtı, bağlam paketi | Yok. Canlı modele tur gönderilmedi. |

Planın tanı matrisine göre bu durum, "Kimlik/trace yok, ilk sapma bilinmiyor" dalıdır: Faz 1 sentetik tanı ilerleyebilir, canlı hata için "düzeltildi" iddiası durur.

## Sentetik tanıdan gelen, canlı olaydan bağımsız bulgular

Hepsi geçici sentetik veritabanında, gerçek modele gitmeden, gerçek ASGI ve oyun motoruyla çalıştırıldı.

| # | Bulgu | Kanıt | Sınıf |
|---|---|---|---|
| F1 | Temiz sentetik dünyada gerçek yaklaşma → giriş → oturma → gözlem zinciri tutarlı (aynı konum kimliği, aynı özellik kimliği, gözlem han adını içeriyor). | `test_scene_truth_contract.test_real_entry_seat_and_look_agree` PASS | Canlı çelişki bu zincirin temel halinden gelmiyor. Ancak canlıdaki nedenin ne olduğu bu testten çıkarılamaz. |
| F2 | Alıntı içindeki "otur" oyuncuyu gerçekten oturtuyor: `Garsona 'masaya otur' diyorum`. | `test_scene_compound_contract.test_quoted_sit_command_is_speech_not_action` RED | Gerçek kusur (söz–komut ayrımı). |
| F3 | Oturma yolu gizli bir özelliği seçiyor ve adını anlatıma sızdırıyor. Kanonik görünürlük sahibi `living_world.visible_features` bu yolda kullanılmıyor. | `test_scene_truth_contract.test_hidden_seat_target_is_not_selected_or_disclosed` RED | Gerçek kusur (gizli hedef eşlemesi). |
| F4 | Birleşik komutta (`gidip içeri girip masaya oturuyorum`) oturma adımı için işleyici yok; giriş yapılıyor, oturma denenmiyor ve oyuncuya "tam çıkaramadım" deniyor. Kilitli girişte zincir doğru duruyor. | `test_compound_open_door_completes_entry_and_seat` RED; `test_compound_stops_at_locked_entry` PASS | Eksik özellik, yalan değil: kuyruk olmuş gibi anlatılmıyor. |
| F5 | "Çevreyi gözlemliyorum" turu çözülmüş anlatım için modeli çağırıyor (giriş ve oturma çağırmıyor). Sentetik testte model reddedilip belirlenimci yedek anlatım kullanıldı. | Faz 1 çalıştırma kaydı: `model_calls=1`, `Resolved narration unavailable; deterministic fallback retained` | Canlı olayın "ham/gösterilen" dalıyla ilgili bir **adaydır**. Neden olduğu kanıtlanmadı. |
| F6 | `ai-dnd/run_tests.py` Windows'ta `Gate process-tree cleanup requires a POSIX runtime` ile hemen düşüyor; `.\dev.ps1` bu yüzden günlük kapıyı koşturamıyor. `test_runner_inventory` Windows'ta aynı 55 failure / 11 error ile başarısız (değişmemiş ana klasörde de aynı). | `baseline-daily.log`, `baseline-gates.jsonl` | Araç/ortam bulgusu; ürün kusuru değil. |

## Bu fazda yapılmayanlar

- Çalışan 8008 sürecine tur gönderilmedi, süreç durdurulmadı veya yeniden başlatılmadı.
- Kişisel kayıt, kampanya veritabanı ve secret kopyalanmadı veya okunmadı.
- Canlı Qwen çağrısı yapılmadı.
- Üretim kodu Faz 0 sırasında değiştirilmedi; baseline `2d02a5e` üzerinde kaydedildi.

## Faz 1-2 sonrası

F2, F3 ve F4 düzeltildi ve testle sabitlendi. Canlı olay UNRESOLVED kalıyor. Hüküm ve sınırlar: [V01_KABUL_NOTU.md](V01_KABUL_NOTU.md).
