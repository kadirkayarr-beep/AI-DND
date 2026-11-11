# Borç defteri (park defteri)

## Amaç
Plan ledger'larında ve incelemelerde "park" diye yazılan küçük bulgular tek yerde, sahibi ve tetikleyicisiyle durur. Sahipsiz park kalmaz; unutulan park gizli borçtur.

## Kural
- Her park, dilim sonunda (devir görevinde) ledger'dan ya da inceleme dosyasından buraya kopyalanır; sahip ve tetikleyici ile birlikte.
- Sahipsiz park olmaz: sahip Kadir, bir dilim ya da bir dosyaya ilk dokunuş olabilir.
- Bir satır yalnız onu düzelten commit ile ya da Kadir'in "wontfix" kararıyla silinir/kapatılır (durum sütununa commit sha ya da "wontfix" yazılır).
- Kapıyı (ara kapı, dilim sonu) etkileyen kırık park değildir; durdurur.
- Sınıflar: money / save / undo / display / ux / test / process.

## Defter
Kaynak kısaltmaları: L4A = `.superpowers/sdd/DILIM4A_PLAN_20261111/progress.md`; L4B = `.superpowers/sdd/DILIM4B_PLAN_20261111/progress.md`; BR4B = `.../branch-review.md`; T8R = `.../task-8-review.md`; CL4B = `.../cleanup-report.md`; HO = `HANDOFF.md` (4A ve 4B bölümleri).

| id | Kısa başlık | Sınıf | Nerede bulundu | Sahip | Tetikleyici | Durum |
|---|---|---|---|---|---|---|
| D-001 | B1: kaydı yazılamayan ödül her turda reddedilir (10 000 makbuz, XP tavanı, v6 reddi, kayıp işaret); T1 F2, T3 F2, T4 F1, T5 F2 ve Görev 8 vuruş anı yarım bayıltma aynı sınıf | save | BR4B B1, L4B T1/T3/T4/T5/T8, HO | Kadir | 4C sonu (Kadir kararı 2026-11-11: 4C sonuna park) | açık (Kadir kararı) |
| D-002 | `settle_session` her biten dinamik görevde tam anlık görüntü alır, ölçülmedi | process | BR4B B2, HO | Dilim 4 sonu | Yavaşlık görülürse ölç | açık |
| D-003 | Seviye duyurusu bir tur geç (tur dışı ödül); geri alınca satır iki kez | display | BR4B B3, HO | Dilim 4 sonu | Kozmetik | açık |
| D-004 | `world_threads.validate` `100 000` literal, `xp.MAX_GRANT` ile eşit olmalı (B1 kilit riski) | save | BR4B B5, HO | Dosyaya ilk dokunuş | `world_threads.py` ya da `xp.MAX_GRANT` değişince | açık |
| D-005 | G1: teslimi kabul edilen yaratık aktif düşman sayılır, yeniden saldırabilir; "teslim oldu" durumu yok | ux | L4B T2 G1, HO | Dilim 4C (Kadir kararı 2026-11-11: 4C içinde) | 4C satırı | tamamlandı (4731cdc2, 8bca6f77; inceleme bekliyor) |
| D-006 | G2: savaşta taşınan yaratık kabulleri `invalid_combat_target` ile düşürür (önceden var) | ux | L4B T2 G2, HO | Dilim 4 sonu | Dilim sonu listesi | açık |
| D-007 | G3: `player_stable` / `participants_left` sonlarında ölü yaratık ödenmez (eksik ödeme, ürün çağrısı yok) | money | L4B T2 G3 ve park, HO | Dilim 4 sonu | Bu sonları üreten ürün yolu eklenince | açık |
| D-008 | G4: elle düzenlenmiş kayıtta `monster_combat` sözlük değil, `surrendered_in` hata verir | save | L4B T2 G4, HO | Düşük | Elle düzenlenmiş kayıt şikâyeti | açık |
| D-009 | F1: stat bloğu CR'ı XP tablosu dışındaysa ödül rol tablosuna düşer (henüz canavar yok) | money | L4B T1 F1, HO | Canavar eklenince | CR'ı tablo dışı ilk canavar | açık |
| D-010 | F2 (INFO): `models._identity` boşluk ve 120 karakter kabul eder, makbuz regex'i reddeder (ürün kimlikleri hash'li) | save | L4B T4 F2, HO | Düşük | Kimlik üreten yeni yol | açık |
| D-011 | T3 F5: `_trim_history(world=None)` varsayılanı; `_thread_gate` sessiz yutma (önceden var) | process | L4B T3, HO | Dilim 4 sonu | Dilim sonu listesi | açık |
| D-012 | T5 F3: Python XP satırı modelin kendi mesajına girer; model yankısı `CANONICAL_XP_CONTRADICTION` tetikleyebilir (durum güvenli) | display | L4B T5, HO | Dilim 4 sonu | Gerçek zincirde görülürse | açık |
| D-013 | T5 F2: v1-3 durum, v6 kabulünün reddettiği hâlde savaşı kilitler (yalnız elle düzenlenmiş makbuz) | save | L4B T5 | Kadir (D-001 ile) | 4C sonu | açık (D-001 sınıfı) |
| D-014 | İngilizce iş teklifinde "?" ile biten satır teklif sayılmaz (`close_words` yalnız Türkçe) | ux | L4B T6, HO | Kadir, İngilizce dil desteği gelince | İngilizce dil desteği (Kadir kararı 2026-11-11: dokunulmaz) | açık (Kadir kararı) |
| D-015 | Savaş ortasında bayıltma ödülünden sonra oyuncu aynı turda ölürse eski seviye atlama duyurusu kalır | display | L4B T8, T8R F1, HO | 4C başı | `_restore_combat_death_checkpoint` `_xp_level_up`'ı temizler; kırmızı test DownedPays | tamamlandı (d6227f10, CL4B) |
| D-016 | Savaş dışı bayıltılan düşman, oyuncu kaçsa da XP öder; öldürülen düşman ödemez (tasarım notu) | ux | T8R F3, HO | Dilim 4 sonu (önerilen) | Kaçış kuralı tartışılınca | açık |
| D-017 | F4 (INFO): bilinmeyen sınıf, seviyeyi değiştirmeyen ödülde hata vermez (tüm ödüllerle aynı) | save | T8R F4 | Düşük | Sınıf doğrulaması gelince | açık |
| D-018 | XP=0 / CR0 notu (J-099 / J-100) | test | HO | Düşük | CR0 yaratık eklenince | açık |
| D-019 | Ölü yaratık + `opponents_relocated` sonu ölüyü ödemez (T1 F3) | money | L4B T1 F3 | Görev 2 | Görev 2 ödeme okuması | tamamlandı (65ca146c; kalan hâli D-007) |
| D-020 | Sokakta duyulan iş haberi iz bırakır testi: runner kurulumu "open"/"heard" iş kuramıyor; yolculuk 41'in 5 adımı known_broken | test | L4A Görev 1, HO | Dilim 4 sonu / Kadir | Runner'a `job.status: open` ya da ürün kararı | açık |
| D-021 | Gerçek modelde "I shove the guard" her zaman kavga sorusunu tetiklemiyor (`strike_to` verilmiyor; motor güvenli); Türkçe eşi aynı; rc14 1/3 | ux | L4A Görev 6, HO | Kadir / Dilim 4 sonu | Ön yüz modeli değişince ya da `strike_to` zorlaması kararı | açık |
| D-022 | İngilizce "shove five feet" varsayılan olarak prone, itme değil; İngilizce sözcük ayrımı küçük | ux | L4A Görev 2 | Dilim 4 sonu | İngilizce dil desteği | açık |
| D-023 | Healer's Kit (kod yok) | ux | L4A Görev 4, HO | Kadir kararı 2026-11-11: NPC müttefik ölüm kurtarmaları ile birlikte | NPC müttefik ölüm kurtarmaları | açık (Kadir kararı) |
| D-024 | K07 Unconscious yaprağı PHB s.376 doğrulanmadı (Massive Damage vakaları 27'ye düzeltildi) | process | L4A Görev 4, HO, CL4B | Dilim 4 sonu | PDF açılabilir olunca | açık (Massive Damage kısmı tamamlandı: ed23a27b) |
| D-025 | him/her/them cinsiyet kontrolü yok; "guard" sözcüğü aramasız kabul | ux | L4A düzeltme turu 3, HO | Dilim 4 sonu | İngilizce dil desteği | açık |
| D-026 | Türkçe "ok" ile başlayan satır artık İngilizce evet sayılmıyor | ux | L4A düzeltme turu 2-3, HO | Dilim 4 sonu | İngilizce dil desteği | açık (izin listesi güvenli yönde) |
| D-027 | Fighter oluşturma `main_hand` longsword bırakır; Longsword'lu senaryo çantası setup testini bozar | test | L4A Görev 5, HO | Dilim 4 sonu | Longsword'lu yeni senaryo | açık |
| D-028 | Yaşlı kayıtta `no_action` reddi `turn_resources`'a yazar (draw yoluyla aynı) | save | L4A Görev 5 (Low1), HO | Dilim 4 sonu | Kayıt biçimi değişikliği | açık |
| D-029 | Dodge "aynı konum" denetimi yaklaşık (ikisi de sahneye yerel) | ux | L4A Görev 3, HO | Dilim 4 sonu | Konum modeli gelince | açık |
| D-030 | Yeniden yazılan Dodge testinin adı bayat ("...only the dexterity save advantage") | test | L4A Görev 3, HO | Dilim 4 sonu | `test_combat_move_accuracy.py`'a ilk dokunuş | açık |
| D-031 | rc14'te muhafız HP'si doğrulanmıyor (anahtar yok) | test | L4A Görev 6 | Dilim 4 sonu | rc14 değişince | açık |
| D-032 | Dodge saldırı dezavantajı (Dilim 3 parkı) | ux | HO (Dilim 3) | Dilim 4A | 4A Görev 3 | tamamlandı (6e5157ab) |
| D-033 | Sokaktan iş haberi senaryosu (Dilim 3 parkı) | test | HO (Dilim 3) | Dilim 4A Görev 1 | 4A Görev 1 | tamamlandı (19ed20cf; kalan hâli D-020) |
| D-034 | Katip yeniden adlandırması | ux | Kadir kararı 2026-11-11 | Yalnız Kadir | Kadir isterse | açık (yalnız Kadir) |
| D-035 | Savaş panelinde katılımcı durumu "surrendered" çevrilmeden görünür (`combatStatusLabel` ve oyun tarayıcısı etiketi) | display | 4C.0 (UI'ye dokunulmadı) | UI görevi (Dilim 4 / UI yeniden tasarımı) | İlk UI dokunuşu | açık |
| D-036 | Teslim olmuş yaratığa büyü (`spell_scope` yolu) ve sınırlı karşılaşma komutu sorulmadan uygulanır; yalnız silah saldırısı sorulur | ux | 4C.0 | Dilim 4C büyü görevleri | 4C büyü hedeflemesi | açık |
