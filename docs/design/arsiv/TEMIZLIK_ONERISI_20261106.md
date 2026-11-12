# Masaüstü temizlik önerisi (2026-11-06) — HİÇBİR ŞEY SİLİNMEDİ

Salt-okuma envanterinden çıktı. Silme için Kadir'in ayrı "yap"ı gerekir. Silmeden önce her klasör için yedek/uzakta var mı kontrol edilir.

## A. DOKUNMA (aktif iş)
- `AI - DND` (ana depo, dev/ai-dnd)
- `AI-DND-b01-isolated` (Claude: belgeler, HANDOFF)
- `AI-DND-dilim0`, `AI-DND-dilim1` (Jarvis/Codex yazıyor), `AI-DND-jarvis-test` (test)
- `AI-DND-docs-yedek` (belge dalı yedeği), `AI-DND-c-merge` (birleştirme tabanı)
- `AI-DND-ORTAK` (posta kutusu, kurallar), `AI-DND-TOOLS` (slot.sh, journey_real.py)
- Bu aktif işlerin bitmesi beklenmeden hiçbiri taşınmaz/silinmez.

## B. GÜVENLE SİLİNEBİLİR İŞ KOPYALARI (commit'leri başka dalda var, kirli dosya yok)
Her biri: kirli=0 ve commit `task/c-series-merge` (GitHub'da) içinde ya da uzak dalda.
- `AI-DND-c-monk`, `AI-DND-c-paladin`, `AI-DND-c-rogue`
- `AI-DND-step0`, `AI-DND-step0-side`, `AI-DND-step2`
- `AI-DND-v01-scene-truth`
- `AI-DND-character-identity-persistence-proof`
- `AI-DND-local-person-replay-review` (dalı GitHub'da)
- `AI-DND-ui-labels` (dalı GitHub'da, `task/handoff-notes-20261103`)
Yöntem: `git worktree remove <klasör>` (klasörü elle silme). Dal silinmez, yalnız klasör gider.

## C. DİKKAT: YEDEĞİ YOK / KİRLİ (silmeden önce Kadir karar versin)
- `AI-DND-p2-live`: 22 kaydedilmemiş değişiklik, uzakta yok
- `AI-DND-lr00-fix`: 1 değişiklik, uzakta yok
- `AI-DND-lr00-regression-map`: 2 değişiklik, uzakta yok
- `AI-DND-npc-dialogue-stage-a`: 2 değişiklik, uzakta yok
Öneri: önce içeriklerine bakılır; değerliyse yedek dalı itilir, değilse atılır.

## D. MASAÜSTÜNDEKİ ESKİ KOPYA/YEDEK KLASÖRLER (git dışı, içeriğine bakılmalı)
Hepsi 9–10 Ekim ile 30 Ekim arası, bugünkü işle ilgisiz görünüyor:
- Yedek/eşitleme: `AI-DND-DEVIR-YEDEK-20261030`, `...-R2`, `AI_DND_FULL_LOCAL_SYNC_20261024`, `AI_DND_UI_DESKTOP_SYNC_20261025`, `AI-DND-Replit-Sync-2026-10-10`, `AI-DND-c-seri-yedek-20261030.bundle`
- Araştırma/eski JARVIS: `AI-DND-JARVIS-290-20261101`, `-310-KALIP-`, `-60TUR-`, `-ARASTIRMA`, `-DORT-IS-`, `-TEKLIF-AD-`, `-YASAYAN-DUNYA-`, `AI-DND-MODEL-DENEMESI-20261031`, `AI-DND Araştırma Merkezi`, `AI_DND_ARASTIRMA_MERKEZI_20261025`
- C06 kaynak ve düzeltme: `AI-DND-C06-*` (4 klasör)
- Diğer denemeler: `AI-DND-Serbest-Deneme`, `AI-DND-13-KOR-PUANLAMA`, `funneltestaidnd`, `AI_DND_Oyun_Tasarimi_2`, `ONEPLANTORULETHEMALL`
- `AI-DND-SİLİNECEKLER` (4 eski kopya + GERİ_ALMA.txt): zaten silinecek diye ayrılmış
- `AI-DND ARŞİV` (525 öğe) ve `Arsivler`, `Diger`, `Belgeler`, `Gelen Kutusu`, `Yeni klasör`: içi ayrı incelenir

Öneri: silme yerine önce hepsi tek bir `ARSIV_2026-10` klasörüne taşınır (geri alınabilir), 2 hafta sonra silinir.

## E. KİŞİSEL / OYUN DIŞI (dokunma, sahibi karar verir)
`Oyunlar`, `Programlar`, `Kurulum_Dosyalari`, `Görseller`, `CURSOR FH`, `Faerun_Unbound_*`, `Faerun_*.json`, kısayollar, `phb.pdf`, `Kayıt ...mp4`, `Start-AI-DND-9B.ps1` ve benzerleri.

## Önerilen sıra
1. Bölüm B: 10 iş kopyasını `git worktree remove` ile kaldır (güvenli).
2. Bölüm C: dört kirli klasörü Kadir'le tek tek gözden geçir.
3. Bölüm D: ARSIV_2026-10 klasörüne taşı; içine bakıp ayıkla.
4. Aktif işler bitince (Dilim 0/1 birleşince) A grubunu sadeleştir.

## DURUM (2026-11-06)
B grubu 10 iş kopyası kaldırıldı. C grubu (4) ve D grubu (27) `Desktop\ARSIV_2026-10\` içine taşındı, silinmedi. Kadir: "Bekletelim". En erken silme: 2026-11-20, yalnız Kadir'in ayrı "yap"ı ile. Önce C_yedeksiz_kirli içeriği gözden geçirilecek.
