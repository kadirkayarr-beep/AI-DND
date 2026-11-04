# Motor defteri ve compact bellek: tasarım taslağı (2026-10-31)

Durum: taslak. Kod yazılmadı. Okunan dal `task/c-series-merge` (`f41698c`). Kabul belgesi değildir.

## Bugün olan

- `api/narrative_memory.py` belirlenimci çalışır. Model özeti yoktur. `story_summary` yalnız motordan gelen kayıtları tutar.
- Anlatıcıya giden bağlam paketi en çok 4800 bayttır. Paket taşınca `story_summary` üçüncü sırada atılır.
- DM'nin yazdıkları kampanya belleğine girmez (`[presentation omitted from continuity]`).
- Tek istisna son 8 anlatımdır: her biri 240 karakterde kesilir, "olgusal dayanak değil" etiketiyle gider.
- Sonuç: DM'nin sahnede uydurup oyuncuya gösterdiği ayrıntı (yara izi, kapı rengi, NPC'nin tavrı) birkaç tur sonra unutulur. Kadir'in en çok şikâyet ettiği tutarsızlığın ana adayı budur; ölçülmedi.
- Sağlam parçalar zaten var: `campaign_journal`, `npc_statements` (söz ve yer defteri), `relationships`, `dialogue_commitments`, `world_state["events"]`, `incident_projection`.
- `memory_archive.py` yazılmış ve testli, ama oyun akışına bağlı değil.

## Önerilen yapı

### Katman 1: motor defteri (yeni depo yok)

Yeni modül `campaign_ledger.py`, yukarıdaki kaynaklardan her tur **salt okunur izdüşüm** üretir. Ayrı bir kopya tutulmaz, böylece defter durumla çelişemez.

İçerik: ölen ve yaşayan önemli NPC'ler, verilen ve kapanan sözler, görevler, ilişkiler, ziyaret edilen yerler, önemli eşya ve olaylar.

Yalnız oyuncunun bildiği kayıtlar girer. Gizli alan bu modüle hiç ulaşmaz. Pakette bütçesi korunur: anlatı bloklarından önce gelir, en son kırpılır.

### Katman 2: compact özet

`narrative_memory` şema 2'ye geçer, yeni alan `compact_summaries` eklenir. Eski kayıt boş listeyle göç eder.

- Her 6 turda bir veya mekân değişince, bitmiş anlatımlardan kısa özet çıkarılır.
- Özetin girdisi yalnız oyuncunun gördüğü metindir, yani sır girmez.
- Etiket `authority: "summary"`. Durum yazmaz, olay sayılmaz.
- Çelişkide defter kazanır: prompt önce defteri verir, kural açıkça yazılır. Metni reddeden yeni bir denetim eklenmez (az engelleme kararı).
- Özet başarısız olursa tur etkilenmez, sonraki aralıkta tekrar denenir.
- Sahnede kurulan ayrıntılar özette taşınır. `RECENT NARRATION` etiketi düzeltilir: anlatılmış sahne ayrıntısı tutarlı kullanılır, ama mekanik kanıt değildir.

`memory_archive` eski NPC kayıtlarını taşımak için bu aşamada bağlanır.

### Sır kuralı

`build_world_context` alan alan denetlenir, oyuncunun bilmediği her şey anlatıcı girdisinden çıkarılır. Test: gizli işaretli değer üretilen promptta geçmemeli.

## Doğrulama

- Jarvis'in üç oturumluk bellek testi ve özgürlük testi, gerçek motordan.
- Birim testleri: göç, bütçe, sır, başarısız özet, tekrar yükleme.

## Karar: oyun testi dili

Kadir 2026-10-31'de A seçeneğini seçti: Türkçe, önce ölçüm. Gerekçe aşağıda.

Kararlarda "oyun testi İngilizce" yazıyor, ama motor bugün Türkçedir: DM promptu "Türkçe yaz" der, niyet çözümleyici ve denetimler Türkçe kalıplara dayanır. Yalnız `game.py` içinde 1337 satır Türkçe karakter içeriyor.

Kör testler İngilizce ve ayrı bir promptla yapıldı. Gemma'nın gerçek motorda Türkçe kalitesi ölçülmedi.

| Seçenek | Artı | Eksi |
|---|---|---|
| A. Oyun testi Türkçe (öneri) | Hemen oynanır, geçiş riski yok | Kör test sonucu Türkçeye taşınmaz, önce kısa ölçüm gerekir |
| B. Önce İngilizceye geçiş | Kararla ve testlerle aynı dil | Uzun ve bozucu iş, oyun testini geciktirir |

Öneri A: önce Gemma ile gerçek motorda 20 Türkçe tur ölçülür. Kalite düşükse B konuşulur.
