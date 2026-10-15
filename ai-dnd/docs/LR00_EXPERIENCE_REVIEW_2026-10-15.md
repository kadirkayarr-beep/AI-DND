# LR00 deneyim paketi — insan okuması

Bu belge bir PASS kararı değildir. F04-AC-006, F04-AC-007, GOLD-SYSTEM ve GOLD-EXPERIENCE açık kalır. Eski 74/74 ve 41/41 sonuçları bu sürüme taşınmaz. F03 arayüz SKIP'i bu pakette kapanmaz.

Başlangıç `5a3972c109cf75d8c7eff0965731dcccf1575c1c`, dal `dev/ai-dnd`. Bible değişmedi. Yeni API alanı yok. Eski kampanyadaki hana kapı geri yazılmaz; kapı yalnız bu değişiklikten sonra kurulan handa oluşur.

## Kontrollü kapı turları

Konum fikstürü `forest`. Zar zorlanmıştır. Bu turlar doğal oyun değildir.

Arama cümlesi: "Yakınlarda Garrick Hanı adlı küçük bir han buluyorsun. Sokağa açılan kapısı kapalı ve kilitli."

Kapı kaydı: `venue-door:location_001`, ad "Garrick Hanı Kapısı", konum `forest`, `open` false, `locked` true, `broken` false. Oyuncu sokaktadır.

Başarısız açma. Ham model yok; çağrı `AssertionError` ile kesildi. Görünen metin: "Garrick Hanı Kapısı kilitli kalır." Gerekçe `MODEL_UNAVAILABLE`. Çağrı sayısı 2 (niyet 1, anlatı 1). Ret sonrası ek çağrı yok. Kapı kilitli kaldı. Konum `forest`.

Başarılı açma. Ham model: "Kapı kilitli kalır." Görünen metin: "Garrick Hanı Kapısı açılır." Gerekçe `DOOR_STATE_CONTRADICTION`. Çağrı sayısı 2. Ret sonrası ek çağrı yok. Reddedilen cümle `recent_dm_narrations` içinde yok. Kapı `open` true, `locked` false. Konum hâlâ `forest`.

İçeri girme: "Kapıdan içeri giriyorsun. Yakınında bir barmen var." Konum `location_001`. Barmen Thalen, bellek boş.

Kapı kilitliyken içeri girme: "Garrick Hanı Kapısı kilitli. İçeri geçemezsin." Konum `forest`, kapı kapalı.

Herkese açık serileştirme aynı kapıyı mevcut alanlarla verir: `id`, `name`, `location`, `description`, `open`, `locked`, `broken`.

İkinci oturum bu kapı kimliğini taşımaz. Kayıt yüklenince açık kapı ve han konumu geri gelir.

## Çalışan hedefli testler

- `api.tests.test_narration_claims`: geçti. İki açık-kapı cümlesi kabul, kilitli cümle ret, algı zinciri ret, rüzgâr ve selam kabul, yanlış hasar sayısı ret.
- `test_narrative_safety_calibration`: geçti.
- `test_playable_living_world.PlayableLivingWorldTests.test_new_tavern_door_opens_or_stays_locked_and_reloads` ve han giriş testleri: geçti.
- `api.tests.test_f03_fault_chains`: geçti. Bu, atlanan React F03 SKIP'inin yerine geçmez.
- `api.tests.test_spell_slot_projection` içindeki tek projeksiyon testi geçti. Bu diff büyü ve zırh fonksiyonuna girmez.
- `api.tests.test_f04_n08_npc_memory`: geçti.
- Kampanya testleri: han kurup kapıyı açmadan içeri alan beş akış, kapı test içinde açıldıktan sonra geçti. `test_discovered_tavern_visit_city_return_and_revisit_survive_resume` şehir ziyaret sayısında `2 != 1` verdi. Aynı hata `5a3972c` üzerinde de vardır; bu kapı işinin yeni kırığı değildir.
- Dört arayüz dosyası açık komutla çalıştı: `not-found`, `skill-history-contract`, `character-armor-source`, `conditional-renderers`. 17 geçti, 0 kaldı. `package.json` test listesi değişmedi.

## Çalıştırılmayanlar

Canlı Qwen yolu çalışmadı. Bu ortamda Ollama yok. Altı turluk doğal kampanya, ham model metni ve sahibin ekrandan okuması yoktur.

İzole tarayıcıda han cümlesi, kapı ve konum birlikte açılmadı. Kapı hali yukarıdaki serileştirmede görüldü. Bu, tarayıcı kabulü değildir.

Kritik ve Dodge canlı han yolunun yerine konmadı. Savaş anlatısındaki sonuç ailesi otomatik testte durur.

## Açık insan satırları

Ajans, anlaşılır risk, yetkili zar, görünen sonuç, kayıt sürekliliği, barmen ve muhafız ayrımı ile sahibin okuduğu Türkçe bu belgede teknik olarak kuruludur. Onay, sahibin bu metni oyunda okumasına bağlıdır. Bu dosya o onayı yazmaz.
