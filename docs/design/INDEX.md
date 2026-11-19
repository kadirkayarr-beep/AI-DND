# Tasarım ve plan belgeleri dizini

Kural: önce bu dizine bak. Güncel belgeler depo kökünde durur (çalışan ajanlar yolları okur); biten dilimlerin belgeleri `arsiv/` altındadır. Bu dosya yerel/izlenmeyen belgeleri gösterir; yeni belge eklenince buraya bir satır yazılır.

## Güncel (kökte)
| Belge | Durum |
|---|---|
| docs/design/ZAR_KURALLARI_DND2024_20261114.md (depoda) | zar kuralları rehberi, D&D 2024 / SRD 5.2.1; bağlayıcı (Kadir, 2026-11-14): oyundaki her zar, test, kurtarma ve saldırı buna uyar |
| docs/superpowers/specs/2026-11-17-game-py-bolme-design.md ve docs/superpowers/plans/2026-11-17-game-py-bolme-plan-1.md (depoda) | game.py bölme tasarımı (onaylı, Kadir 2026-11-17, 11 karar öneri yönünde) ve Plan 1 (T0-T2, onaylı); T3-T7 ayrı planlar |
| docs/superpowers/plans/2026-11-18-game-py-bolme-plan-2.md (depoda) | game.py bölme Plan 2: eksik ağlar (bayrak düzeltmesi, N4, N7, N3 kör noktaları) ve T3 yaprakları (`tables`, `schemas`, `text_rules_a/b`) TM2'ye kadar; Kadir onayı 2026-11-18 |
| docs/superpowers/plans/2026-11-19-game-py-bolme-plan-3.md, ek dosyası ve `-measure/` klasörü (depoda) | game.py bölme Plan 3: T4 düşük etkili alanlar (241 ad, yaklaşık 7 363 satır; `character_rules` ve yeni parçalar) TM3'e kadar; Stage A ağ borçları ve prova; Kadir onayı; Görev 0 2026-11-20 (taban 5ea18cc7) |
| docs/design/NPC_BILGI_ANLATICI_TASARIM_20261116.md (depoda) | D-249 + D-250 dilimi: NPC bilgisi genişler, duyulmuş yer ve söylenti kayda girer (Ş4), anlatıcı sınırları gevşer; onaylı (Kadir, 2026-11-16) |
| YOL_HARITASI_20261112.md | güncel yol haritası, onaylı (Kadir, 2026-11-12); şu an Faz 0 |
| KARAR_LISTESI_20261112.md | Kadir'i bekleyen onay ve kararlar |
| HANDOFF.md | canlı devir notu (4B ve 4A bölümleri; eskisi HANDOFF_ARSIV_20261112.md) |
| NIGHT_BRIEF.md | gece çalışma özeti |
| DILIM4_TASARIM_TASLAK_20261110.md | Dilim 4 genel tasarım, onaylı (4A, 4B bitti ve main'de) |
| DILIM4C_TASARIM_TASLAK_20261111.md | 4C büyü tasarımı, yedi öneri onaylı, uygulamada |
| HANDOFF_4B_TASLAK_20261111.md | 4B devir taslağı |
| UI_TASARIM_PLANI_20261111.md | UI kavram planı (Unwritten, kitap sayfası) |
| UI_TASARIM_BELGESI_20261111.md | UI tasarım belgesi, onaylı |
| UI_MOTOR_SOZLESMESI_20261111.md | motorun UI'ye verdiği/vermediği olgular |
| UI_TEMEL_PLAN_20261111.md | UI temeli planı, bitti ve main'de (PR #26, #27) |
| UI_DILIM1_PLAN_20261111.md | UI dilim 2 planı (S1, S2 bitti; S3 sırada) |
| UI_BILINEN_KIRIKLAR_20261111.md | iki eski testin kökeni |
| YENIDEN_TASARIM_PLANI_20261113.md | yeniden tasarım üst planı (arayüz hattı, motor hattı, Kapı 1 sonrası Hat C), onaylı (Kadir, 2026-11-13); iş sırasında çelişki olursa bu belge geçerli |
| ANA_ENVANTER_20261113.md | onaylanan ya da istenen her işin tek listesi; üst planın girdisi |
| KESME_SONRASI_TASARIM_20261112.md | aşamalar, kapılar ve oyuncu yolculuğu tablosu, onaylı (Kadir, 2026-11-12); bölüm 10 13 Kasım güncellemesi |
| MOTOR_HAKEM_MODEL_YAZAR_TASARIM_20261113.md | "motor hakem, model yazar" tasarımı (dilimler, öneri şeritleri), onaylı (Kadir, 2026-11-13) |
| PROTOTIP_ENVANTERI_20261113.md | onaylı prototipin 33 öğesi ve gerçek arayüzdeki durumu |
| ARAYUZ_KALITE_KURALLARI_20261113.md | arayüz kalite kuralları ve hazır istemler; bölüm 1 `CLAUDE.md` "Arayüz işi" bölümüdür |

## Arşiv (`arsiv/`)
ADIM0-4, DILIM0-3 plan/tasarım/devir, Jarvis devirleri, yol haritaları, ölçüm ve inceleme raporları, canlı oyun notları. Hepsi bitmiş ya da değiştirilmiş işlerin kaydıdır.

`arsiv/eski-donem/`: Cursor ve Replit dönemi belgeleri (`replit.md`, `DEVELOPER_RECOMMENDATIONS.md`, Cursor kural dosyası); 12 Kasım 2026'da kökten taşındı.

## Dosya olmayan klasörler
`*_GERCEK_KOSU*`, `DILIM*_OLCUM*`, `DILIM3B_VARIS_KOSU*`: gerçek model koşu çıktıları. `UI_PROTOTIP_*`: atılabilir prototipler. `UI_S2_EKRANLAR_20261111`: S2 ekran görüntüleri.
