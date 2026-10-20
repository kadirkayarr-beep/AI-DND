# Yedi depo araştırması — ajanlar için okuma ve planlama dizini

Tarih: 20 Ekim 2026. Durum: **Araştırma kaydı ve aşamalı planlama için onaylı; uygulama emri değildir.**

## Önce bunu okuyun

Kullanıcı değerlendirmelerin ve aşamalı önerilerin kaydedilmesini, diğer proje ajanlarının da görebilmesi için proje içine eklenmesini istedi. Bu kayıt bütün özellikleri geliştirme, kod taşıma, kurulum, model değiştirme, merge veya deployment izni vermez. Mevcut owner-approved Project Bible ve operasyonel handoff otoritelerini değiştirmez.

- [Tam teknik inceleme](AI_DND_Yedi_Repo_Detayli_Inceleme_2026-10-20.md): yedi deponun gerçek kaynak akışları, güçlü/zayıf yanları, kanıt bağlantıları ve lisans sınırları.
- [Tam fırsat haritası](AI_DND_Repo_Firsat_Haritasi_2026-10-20.md): yalnız bugfix değil; seçici ürün geliştirme, harita/authoring, NPC rutinleri, sosyal ağ, agency ve diğer aşamalı fırsatlar.
- [Geliştirme belgeleri dizini](../../README.md).
- [Mevcut operasyonel handoff](../../../../docs/CURSOR_REPLIT_HANDOFF.md).

İki rapor tam metin olarak korunmuştur. Kaynak kodlar kurulmadı veya çalıştırılmadı. Kaynakta bulunan testler çalıştırılmış test sonucu sayılmaz; bu belge AI-DND gameplay, Qwen kalitesi veya release doğrulaması değildir.

## AI-DND tabanı ve tarihsel kaynak ayrımı

Bu dokümantasyonun doğrulanmış tabanı: `fix/npc-default-dialogue-path-20261020`, commit [2a5f21b86066de2c5efb59af0604cbf65bfc27d2](https://github.com/kadirkayarr-beep/AI-DND/commit/2a5f21b86066de2c5efb59af0604cbf65bfc27d2), [draft PR #23](https://github.com/kadirkayarr-beep/AI-DND/pull/23). Kayıt ayrı `docs/repo-research-handoff-20261020` dalındadır; aday dalı değiştirmez ve dev/main içine entegre edildiği anlamına gelmez.

Fırsat haritasındaki AI-DND kaynak bağlantıları tarihsel [476ba9bd148da18e24cb5dab020c116ba4907445](https://github.com/kadirkayarr-beep/AI-DND/commit/476ba9bd148da18e24cb5dab020c116ba4907445) snapshot'ına aittir. Bu bağlantılar mevcut adayın yeniden incelendiği iddiası değildir. Uygulama seçmeden önce güncel HEAD, ilgili modül, aktif sözleşme ve dosya sahipliği yeniden kontrol edilmelidir.

## Kaynak snapshot'ları

- [gddickinson/llm_RPG](https://github.com/gddickinson/llm_RPG/commit/ad760b3c52db072188e1a79cd1cb2983eb8321e6) — `ad760b3c52db072188e1a79cd1cb2983eb8321e6`.
- [msadeqsirjani/dnd_ai_dm](https://github.com/msadeqsirjani/dnd_ai_dm/commit/db09ab403d234da37446ea4b73e4c3d349c40ece) — `db09ab403d234da37446ea4b73e4c3d349c40ece`.
- [guzmanvitar/dungeonmind-llm-rpg-adventure](https://github.com/guzmanvitar/dungeonmind-llm-rpg-adventure/commit/f1eb7dd1dfdcb0e01791870167eb98dd77fa3bd9) — `f1eb7dd1dfdcb0e01791870167eb98dd77fa3bd9`.
- [Sagesheep/NarrativeEngine-P](https://github.com/Sagesheep/NarrativeEngine-P/commit/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b) — `a5020b93fccd56ea91a5b1b2dd30053b35c5a66b`.
- [Axidify/ai-dnd-rpg](https://github.com/Axidify/ai-dnd-rpg/commit/395f86a441984c9a2c91272ef2a502f2553d93e3) — `395f86a441984c9a2c91272ef2a502f2553d93e3`.
- [fedefreak92/dungeon-master-ai-project](https://github.com/fedefreak92/dungeon-master-ai-project/commit/38b655aa432d73eec78eebcb0dbf0442f7491ab5) — `38b655aa432d73eec78eebcb0dbf0442f7491ab5`.
- [LudicDynamics/WorldLines](https://github.com/LudicDynamics/WorldLines/commit/4ee61a368c381f2f8db43b4454f088a7388693bf) — `4ee61a368c381f2f8db43b4454f088a7388693bf`.

Rapordaki satır bağlantıları bu sabit commit'lere dayanır. Bunlar 20 Ekim araştırma snapshot'larıdır; daha sonraki upstream değişiklikleri kapsanmaz.

## Lisans ve aktarım sınırı

- llm_RPG, dnd_ai_dm ve NarrativeEngine-P: incelenen LICENSE dosyaları MIT. Bildirimler ve üçüncü taraf içerik/asset/model hakları ayrıca korunmalıdır.
- DungeonMind: README MIT, LICENSE GPLv3 çelişkisi vardır; permissive kod aktarımı varsayılmamalıdır.
- Axidify/ai-dnd-rpg: açık permissive yeniden kullanım izni doğrulanmamıştır; lisans netleşmeden kod kopyalanmamalıdır.
- fedefreak92/dungeon-master-ai-project: kişisel/ticari olmayan kullanım sınırı vardır.
- WorldLines: açık UI/kabuk/örnekler AGPL-3.0-or-later; neonrp çekirdeği kapalıdır. Açık bir motor veya doğrulanmış deterministik replay çözümü gibi değerlendirilmemelidir.

Bu özet hukuki kesinlik değildir. Bağımsız kavramsal uygulama ile kaynak kod/prompt/asset kopyalama ayrı kararlardır; raporlardaki sabit lisans bağlantılarını inceleyin.

## Sonraki ajan için seçim kapısı

1. Raporu ve fırsat haritasını okuyup tek, dar kapsamlı dilim önerin; mevcut özellikleri yok sayarak yeniden yazım önermeyin.
2. Python mekanik/state otoritesini, Qwen anlatım rolünü ve campaign/NPC bilgi kapsamını koruyun. Konuşma metnini kalıcı mutation saymayın.
3. Yakın dönem önerileri: gözlemlenebilirlik, model/protokol regresyonları, güvenli save/recovery ve dar konuşma/action ayrımı. Harita, rutin, sosyal ağ ve agency fikirleri sonraki seçimlerdir; otomatik backlog yürütümü değildir.
4. Her dilim için fayda, mevcut modül, kabul kanıtı, lisans, maliyet, veri/geri dönüş riski ve dosya sahibi belirtilsin. Uygulama kapsamı ayrıca kararlaştırılsın.
5. Birleştirme/yayın ve canlı veriye müdahale bu kayıt tarafından yetkilendirilmez. Tarihsel NO-GO/PASS kayıtları yeniden yazılmaz.

## Tam metin bütünlüğü

- Teknik inceleme: 81.932 UTF-8 bayt; SHA-256 `882596b461b59301bd63728f678ab54cb4b24b5d56e0f9606f1d8858ba78f449`.
- Fırsat haritası: 45.570 UTF-8 bayt; SHA-256 `88f99754b7bb9ba21bbdf22f8d12008f776fc36c3e5d99d6016580928e45a8db`.
