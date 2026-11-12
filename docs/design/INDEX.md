# Tasarım ve plan belgeleri dizini

Kural: önce bu dizine bak. Güncel belgeler depo kökünde durur (çalışan ajanlar yolları okur); biten dilimlerin belgeleri `arsiv/` altındadır. Bu dosya yerel/izlenmeyen belgeleri gösterir; yeni belge eklenince buraya bir satır yazılır.

## Güncel (kökte)
| Belge | Durum |
|---|---|
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

## Arşiv (`arsiv/`)
ADIM0-4, DILIM0-3 plan/tasarım/devir, Jarvis devirleri, yol haritaları, ölçüm ve inceleme raporları, canlı oyun notları. Hepsi bitmiş ya da değiştirilmiş işlerin kaydıdır.

`arsiv/eski-donem/`: Cursor ve Replit dönemi belgeleri (`replit.md`, `DEVELOPER_RECOMMENDATIONS.md`, Cursor kural dosyası); 12 Kasım 2026'da kökten taşındı.

## Dosya olmayan klasörler
`*_GERCEK_KOSU*`, `DILIM*_OLCUM*`, `DILIM3B_VARIS_KOSU*`: gerçek model koşu çıktıları. `UI_PROTOTIP_*`: atılabilir prototipler. `UI_S2_EKRANLAR_20261111`: S2 ekran görüntüleri.
