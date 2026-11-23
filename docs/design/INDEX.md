# Tasarım ve plan belgeleri dizini

**Önce:** [docs/design/YOL_HARITASI.md](YOL_HARITASI.md) — sıra ve durum için tek kaynak. Motor yapısında bölme tasarımı §11/§12 ve ADR 0001 kazanır.

Devir notu: [docs/design/HANDOFF.md](HANDOFF.md).

Kural: önce bu dizine bak. Güncel belgeler depo kökünde durur (çalışan ajanlar yolları okur); biten dilimlerin belgeleri `arsiv/` altındadır. Bu dosya yerel/izlenmeyen belgeleri gösterir; yeni belge eklenince buraya bir satır yazılır.

## Güncel (kökte)
| Belge | Durum |
|---|---|
| docs/design/ZAR_KURALLARI_DND2024_20261114.md (depoda) | zar kuralları rehberi, D&D 2024 / SRD 5.2.1; bağlayıcı (Kadir, 2026-11-14): oyundaki her zar, test, kurtarma ve saldırı buna uyar |
| docs/superpowers/specs/2026-11-17-game-py-bolme-design.md ve docs/superpowers/plans/2026-11-17-game-py-bolme-plan-1.md (depoda) | game.py bölme tasarımı (onaylı, Kadir 2026-11-17, 11 karar öneri yönünde) ve Plan 1 (T0-T2, onaylı); T3-T7 ayrı planlar; kapandı (oynayış bekliyor) |
| docs/superpowers/plans/2026-11-18-game-py-bolme-plan-2.md (depoda) | game.py bölme Plan 2: eksik ağlar (bayrak düzeltmesi, N4, N7, N3 kör noktaları) ve T3 yaprakları (`tables`, `schemas`, `text_rules_a/b`) TM2'ye kadar; Kadir onayı 2026-11-18 |
| docs/superpowers/plans/2026-11-19-game-py-bolme-plan-3.md, ek dosyası ve `-measure/` klasörü (depoda) | game.py bölme Plan 3: T4 düşük etkili alanlar (241 ad, yaklaşık 7 363 satır; `character_rules` ve yeni parçalar) TM3'e kadar; Stage A ağ borçları ve prova; Kadir onayı; Görev 0 2026-11-20 (taban 5ea18cc7) |
| docs/superpowers/plans/2026-11-20-game-py-bolme-plan-4.md, ek dosyası ve `-measure/` klasörü (depoda) | game.py bölme Plan 4: T5 (`combat_flow`, `coin`, `savefile` ve hassas kalanlar, 139 ad, yaklaşık 7 070 satır) TM4'e kadar; Stage A hız (`_GameModule` kancası), ağ borçları ve prova; Kadir'in otonom izni 2026-11-20; Görev 0 2026-11-20 (taban bdeddf2a) |
| docs/superpowers/plans/2026-11-21-game-py-bolme-plan-5.md, ek dosyası ve `-measure/` klasörü (depoda) | game.py bölme Plan 5: T6 tur çekirdeği iki parçaya (`turn_front.py` 51 ad yaklaşık 2 180 satır; `turn.py` 16 ad yaklaşık 3 975 satır, gelişte dondurulur; 6 parti) TM5'e kadar, ardından D-429 para düzeltmesi (Aşama C); ölçüm p4m 0b1dca5a üzerinde, Görev 0 TM4 sonrası yeniden ölçer; bitti, main'de (#139, #140, #141) |
| docs/superpowers/plans/2026-11-21-game-py-bolme-plan-6.md ve `-measure/` klasörü (depoda) | game.py bölme Plan 6: T7 kapanış (taşımadan kalan boş satırlar silinerek `game.py` ≤ 1 500, son boyut bütçeleri, ölü kod kanıt tablosu (silme yok, Kadir'in "evet"ine bağlı), CLAUDE.md kuralı, GLOSSARY ve ADR, kapanış kapısı, Kadir'in oynayışı); ölçüm p5m 01cc6f84 üzerinde (Plan 5 Aşama B'nin son kod commit'i): `_narrate_resolved_turn` (351 satır) `game.py`'de kalır, boş satır kuralıyla `game.py` yaklaşık 1 400 satır; Görev 0 Plan 5 sonrası yeniden ölçer; kalıcı kayıt: docs/adr/0001-game-parts-merkez-kurali.md (karar ve sonraki dilimler için kurallar), GLOSSARY.md (terimler), docs/engine-split/olu-kod-kaniti.md (ölü kod kanıt tablosu, Görev 5); main'de (#145); oynayış bekliyor |
| docs/superpowers/specs/2026-11-22-yol-haritasi-design.md ve docs/superpowers/plans/2026-11-22-belge-pr.md (depoda) | yol haritası tasarımı (Kadir kararları S1-S9, 2026-11-22) ve belge PR'ının planı |
| docs/design/NPC_BILGI_ANLATICI_TASARIM_20261116.md (depoda) | D-249 + D-250 dilimi: NPC bilgisi genişler, duyulmuş yer ve söylenti kayda girer (Ş4), anlatıcı sınırları gevşer; onaylı (Kadir, 2026-11-16); bitti (#118, #121) |
| YOL_HARITASI_20261112.md | eskidi (2026-11-22): yerini docs/design/YOL_HARITASI.md aldı; geçerli kararları orada; dosya depo dışında, yerinde kalır |
| KARAR_LISTESI_20261112.md | eskidi (2026-11-22): yerini docs/design/YOL_HARITASI.md aldı; geçerli kararları orada; dosya depo dışında, yerinde kalır |
| docs/design/HANDOFF.md (depoda) | kısa devir notu; geçerli olan bu (2026-11-22). Eski kök kopyası (HANDOFF.md, depo dışında) dondu (2026-11-22) |
| NIGHT_BRIEF.md | gece çalışma özeti |
| DILIM4_TASARIM_TASLAK_20261110.md | Dilim 4 genel tasarım, onaylı (4A, 4B bitti ve main'de) |
| DILIM4C_TASARIM_TASLAK_20261111.md | 4C büyü tasarımı, yedi öneri onaylı, bitti, main'de (PR #30) |
| HANDOFF_4B_TASLAK_20261111.md | 4B devir taslağı |
| UI_TASARIM_PLANI_20261111.md | UI kavram planı (Unwritten, kitap sayfası); eskidi (2026-11-22): yerini YENIDEN_TASARIM_PLANI_20261113.md ve ARAYUZ_KALITE_KURALLARI_20261113.md aldı |
| UI_TASARIM_BELGESI_20261111.md | UI tasarım belgesi, onaylı; eskidi (2026-11-22): yerini YENIDEN_TASARIM_PLANI_20261113.md ve ARAYUZ_KALITE_KURALLARI_20261113.md aldı |
| UI_MOTOR_SOZLESMESI_20261111.md | motorun UI'ye verdiği/vermediği olgular |
| UI_TEMEL_PLAN_20261111.md | UI temeli planı, bitti ve main'de (PR #26, #27) |
| UI_DILIM1_PLAN_20261111.md | UI dilim 2 planı (S1, S2 bitti; S3'ün yerini A1 ve A2.7 aldı) |
| UI_BILINEN_KIRIKLAR_20261111.md | iki eski testin kökeni |
| docs/design/YENIDEN_TASARIM_PLANI_20261113.md (depoda) | yeniden tasarım üst planı (arayüz hattı, motor hattı, Kapı 1 sonrası Hat C), onaylı (Kadir, 2026-11-13); sırada YOL_HARITASI.md esastır; ayrıntıda bu belge |
| ANA_ENVANTER_20261113.md | onaylanan ya da istenen her işin tek listesi; üst planın girdisi |
| KESME_SONRASI_TASARIM_20261112.md | aşamalar, kapılar ve oyuncu yolculuğu tablosu, onaylı (Kadir, 2026-11-12); bölüm 10 13 Kasım güncellemesi |
| docs/design/MOTOR_HAKEM_MODEL_YAZAR_TASARIM_20261113.md (depoda) | "motor hakem, model yazar" tasarımı (dilimler, öneri şeritleri), onaylı (Kadir, 2026-11-13) |
| PROTOTIP_ENVANTERI_20261113.md | onaylı prototipin 33 öğesi ve gerçek arayüzdeki durumu |
| ARAYUZ_KALITE_KURALLARI_20261113.md | arayüz kalite kuralları ve hazır istemler; bölüm 1 `CLAUDE.md` "Arayüz işi" bölümüdür |

## Arşiv (`arsiv/`)
ADIM0-4, DILIM0-3 plan/tasarım/devir, Jarvis devirleri, yol haritaları, ölçüm ve inceleme raporları, canlı oyun notları. Hepsi bitmiş ya da değiştirilmiş işlerin kaydıdır.

`arsiv/eski-donem/`: Cursor ve Replit dönemi belgeleri (`replit.md`, `DEVELOPER_RECOMMENDATIONS.md`, Cursor kural dosyası); 12 Kasım 2026'da kökten taşındı.

## Dosya olmayan klasörler
`*_GERCEK_KOSU*`, `DILIM*_OLCUM*`, `DILIM3B_VARIS_KOSU*`: gerçek model koşu çıktıları. `UI_PROTOTIP_*`: atılabilir prototipler. `UI_S2_EKRANLAR_20261111`: S2 ekran görüntüleri.
