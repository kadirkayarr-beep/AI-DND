# D&D 2024 / SRD 5.2.1: Zar Gerektiren Durumlar ve AI Çözümleme Rehberi

> Kaynak: Kadir'in Codex'e yaptırdığı araştırma (2026-11-14). Kadir'in kararı (2026-11-14): oyun bu belgeye bağlı kalır. Bu dosya Kadir'in yapıştırdığı metnin birebir kopyasıdır; yalnız bu not eklendi.

```yaml
document_id: dnd-2024-dice-guide-tr
version: 1.0
research_date: 2026-11-14
language: tr
ruleset: D&D 2024
primary_source: SRD 5.2.1
purpose: AI oyun yöneticisi için kaynaklı kural rehberi ve uygulama denetimi
scope: SRD çekirdek kuralları, seçilmiş özel kurallar, sürüm ayrımları
not_scope: tüm ek kitapların her büyüsü, her canavarı ve her olası eylemi
status: araştırma ve tasarım belgesi; çalıştırılmış yazılım testi değildir
```

## 0. Bu belge nasıl okunmalı?

- **KURAL:** Kaynakta belirtilen oyun kuralı veya onun Türkçe özeti.
- **GM KARARI:** Kuralların oyun yöneticisine bıraktığı değerlendirme.
- **MOTOR ÖNERİSİ:** AI-DND benzeri bir uygulama için önerilen mühendislik davranışı. Resmî D&D kuralı değildir.
- **ÖRNEK:** Kuralın uygulanmasını açıklayan varsayımsal olay. Örnekte seçilmiş DC, açıkça kaynaklı değilse evrensel DC değildir.
- **SÜRÜM UYARISI:** 2014 kuralları, 2024 kuralları, bilgisayar oyunu uyarlamaları ve ev kuralları birbirinin yerine kullanılmamalıdır.

Bu belge, resmî İngilizce metnin açıklamalı Türkçe özeti ve özgün uygulama önerileridir; resmî Türkçe çeviri değildir. Kaynak metindeki özel kural genel kuralı geçersiz kılabilir. Bir büyü, eşya, sınıf özelliği veya canavar saldırısı kullanılıyorsa **tam olarak o özelliğin aynı sürümdeki metni** okunmalıdır.

**Kapsam dürüstlüğü:** Eylemlerin sayısı sınırsızdır. “Zar isteyen bütün fiillerin eksiksiz listesi” mümkün değildir. Sağlam çözüm; genel karar yöntemi, açık tetikleyiciler ve kaynaklı özel-kural kataloğudur. Bu belge SRD 5.2.1 temelini kapsar, SRD dışında kalan tüm resmî kitapları kapsadığı iddiasında değildir.

### Temel kaynaklar

1. [Resmî SRD sayfası](https://www.dndbeyond.com/srd).
2. [SRD 5.2.1 PDF, ana kaynak](https://media.dndbeyond.com/compendium-images/srd/5.2/SRD_CC_v5.2.1.pdf).
3. [2024 Basic Rules: Playing the Game](https://www.dndbeyond.com/sources/dnd/br-2024/playing-the-game).
4. [2024 Basic Rules: Rules Glossary](https://www.dndbeyond.com/sources/dnd/br-2024/rules-glossary).
5. [Resmî SRD 5.2.1 dönüşüm rehberi](https://media.dndbeyond.com/compendium-images/srd/guide/converting-to-srd-5.2.1.pdf).

Aşağıdaki sayılar SRD PDF'nin basılı sayfa numaralarıdır. Başlıklar da verilmiştir; PDF görüntüleyici sayacı farklıysa başlığa göre bulunmalıdır.

## 1. En önemli ayrım: Eylem, D20 Test ve diğer zarlar

**Her eylem zar gerektirmez. Her zar da bir eylem harcatmaz. Her d20 atışı D20 Test değildir.**

D20 Test üç ana türün ortak adıdır:

| Tür | Sorusu | Temel formül | Karşılaştırma |
|---|---|---|---|
| Ability Check | Bir şeyi yapmayı başarabiliyor musun? | d20 + ilgili ability modifier + uygunsa proficiency + diğer değiştiriciler | DC |
| Saving Throw | Bir tehlikeye/etkiye direnebiliyor musun? | d20 + ilgili ability modifier + uygunsa save proficiency + diğer değiştiriciler | DC |
| Attack Roll | Saldırın hedefe isabet ediyor mu? | d20 + saldırı ability modifier + uygunsa proficiency + diğer değiştiriciler | AC |

Bunlardan ayrı olarak hasar, iyileştirme, Hit Dice, rastgele tablolar, Recharge, süre ve kaynak yenilenmesi zarları vardır. Örneğin bir asanın son şarjında kırılıp kırılmadığını belirleyen d20, sırf d20 kullanıldığı için ability check olmaz.

**Eşitlik başarıdır:** Bir test toplamı hedef DC veya AC'ye eşitse başarı/isabet gerçekleşir. Attack Roll'un doğal 1/20 istisnaları ayrıca uygulanır. [SRD, s.6–9: D20 Tests](https://media.dndbeyond.com/compendium-images/srd/5.2/SRD_CC_v5.2.1.pdf).

## 2. Zar ne zaman istenir?

### 2.1 Kaynak kural önce gelir

Bir kural açıkça zar söylüyorsa önce onun tetikleyicisi ve önkoşulları değerlendirilir. Örneğin bir büyünün belirtilen kurtarma atışı, oyuncu “direniyorum” yazmasa da etkilenme anında gündeme gelir. Buna karşılık bir NPC'nin yalnızca kılıç göstermesi kendiliğinden Attack Roll değildir.

### 2.2 Serbest eylemlerde karar ağacı

1. **Gerçek niyet var mı?** Oyuncu eylemi gerçekten yapıyor mu, yoksa düşünüyor, soruyor, reddediyor veya başkasını alıntılıyor mu?
2. **Eylem mümkün mü?** Hedef erişilebilir mi, gerekli araç/menzil/duyu/boş el var mı?
3. **Özel kural var mı?** Hide, Influence, Grapple, büyü, eşya veya tuzak metni varsa onu kullan.
4. **Sonuç zaten kesin mi?** Basit, engelsiz, belirsizliği olmayan işlem için sırf dramatik olsun diye check üretme.
5. **Anlamlı başarısızlık ihtimali ve sonucu var mı?** Saldırı dışı bir yetenek meydan okumasının sonucu belirsiz ve anlatı açısından anlamlıysa GM ability check ister.
6. **Testi kim atıyor?** Aktörün denemesi mi, hedefin kurtarması mı, saldırı isabeti mi?
7. **Başarı/başarısızlık neyi değiştiriyor?** Sonuç gelmeden başarılı sonucu kesinleştirme.

**KURAL/GM KARARI:** Oyuncu “20 attım, kapıyı açtım” diyerek kendi kendine imkânsızı mümkün kılamaz. GM testi gerektiren durumu ve ilgili özelliği belirler. Bir sayı her engeli aşmaz. [SRD s.6, Ability Checks](https://media.dndbeyond.com/compendium-images/srd/5.2/SRD_CC_v5.2.1.pdf).

### 2.3 Örnek ayrımlar

| Durum | Doğru başlangıç kararı |
|---|---|
| Kilitsiz, sıkışmamış kapıyı açmak | Genellikle zar yok; etkileşim ekonomisini uygula |
| Sıkışmış kapıyı zorlamak | GM STR check belirleyebilir; Athletics her STR kullanımına otomatik eklenmez |
| İmkânsız ağırlıktaki dağı kaldırmak | Normal STR check ile mümkün hâle gelmez |
| Düşmana kılıçla vurmak | Attack Roll; hasar ancak isabet/özel etki sonrası |
| Fireball alanında kalmak | Büyünün DEX saving throw'u; “kaçıyorum” ifadesinden bağımsız tetiklenebilir |
| “Cüzdanını çalsam ne olur?” | Soru; otomatik hırsızlık gerçekleştirilmez |
| “Bahşiş vermiyorum” | Ret; ödeme veya zar üretme |
| “Kendimi iyi hissetmek için zar atıyorum” | Oyun mekaniğini değiştiren test sayılmaz |

Son üç satır **MOTOR ÖNERİSİ**dir: doğal dilde niyeti yanlış yorumlamayı önler.

## 3. D20 Test ortak matematiği

### 3.1 Değiştiriciler

Ability modifier, ability score'un kendisi değildir. Normal hesap `floor((score - 10) / 2)` şeklindedir. Proficiency Bonus yalnızca ilgili yeterlilik varsa eklenir. Aynı teste proficiency bonus birden çok kaynak nedeniyle iki kez eklenmez. Expertise, uygulanabildiği durumda proficiency katkısını iki katına çıkarır; ability modifier'ı ikiye katlamaz.

Proficiency genellikle deneme hakkının önkoşulu değildir. Ancak belirli bir kural, araç veya eylem özel bir yeterlilik şartı koyabilir. “Eğitimim yok, hiçbir şekilde deneyemem” de “Her durumda deneyebilirim” de evrensel doğru değildir. [SRD s.8–9, Proficiency](https://media.dndbeyond.com/compendium-images/srd/5.2/SRD_CC_v5.2.1.pdf).

### 3.2 Advantage / Disadvantage

- Advantage: iki d20 at, yüksek olanı kullan.
- Disadvantage: iki d20 at, düşük olanı kullan.
- Aynı yöndeki çok sayıda kaynak ek d20 üretmez.
- En az bir advantage ve en az bir disadvantage birlikte varsa birbirini götürür. Üç advantage ve bir disadvantage de normal tek d20'dir.
- Bir kural d20'yi yeniden attırıyor/değiştiriyorsa advantage/disadvantage çiftinin yalnızca bir zarına uygulanır; ilgili özelliğin metnini izle.
- **Heroic Inspiration:** Bir zarı attıktan hemen sonra yeniden atmak için harcanabilir; yeni sonuç kullanılmalıdır. Bu özellik yalnızca d20 veya attack roll ile sınırlı değildir, kendisi advantage demek değildir.

[SRD s.7–8, Advantage/Disadvantage; Rules Glossary, Heroic Inspiration](https://media.dndbeyond.com/compendium-images/srd/5.2/SRD_CC_v5.2.1.pdf).

### 3.3 Doğal 1 ve doğal 20

| Zar bağlamı | Doğal 1 | Doğal 20 |
|---|---|---|
| Ability Check | Genel otomatik başarısızlık yok | Genel otomatik başarı yok |
| Normal Saving Throw | Genel otomatik başarısızlık yok | Genel otomatik başarı yok |
| Attack Roll | Toplamdan bağımsız ıskalar | İsabet eder, Critical Hit |
| Death Saving Throw | İki başarısızlık | 1 HP kazanılır |
| Rastgele d20 tablosu | Tablo ne diyorsa | Tablo ne diyorsa |

**Örnek:** DC25 bir ability check'te doğal20+0 başarısızdır. DC10 check'te doğal1+10 başarılıdır. Bir karakter özelliğinin özel istisnası varsa ayrıca uygulanır. [SRD s.6–8, s.17–18](https://media.dndbeyond.com/compendium-images/srd/5.2/SRD_CC_v5.2.1.pdf).

### 3.4 Tipik DC tablosu

| Zorluk | DC |
|---|---:|
| Çok kolay | 5 |
| Kolay | 10 |
| Orta | 15 |
| Zor | 20 |
| Çok zor | 25 |
| Neredeyse imkânsız | 30 |

Bu, GM'nin serbest meydan okuma belirlemesi içindir. Her işlemi DC15 yapmak için gerekçe değildir. Belirli büyü/eşya/eylem DC'si varsa onu kullan. “Neredeyse imkânsız DC30” ifadesi gerçekten imkânsız her şeyin DC30 olması anlamına gelmez. [SRD s.6](https://media.dndbeyond.com/compendium-images/srd/5.2/SRD_CC_v5.2.1.pdf).

## 4. Ability Check kataloğu

Beceri isimleri ayrı zar türleri değildir. Örneğin “Perception zarı”, normalde Wisdom (Perception) ability check'in kısa adıdır.

| Beceri | Normal ability | Tipik uygulama |
|---|---|---|
| Acrobatics | DEX | Denge, çeviklik gösterileri, belirli inişler |
| Animal Handling | WIS | Hayvanı yatıştırma/yönlendirme |
| Arcana | INT | Büyü, büyülü işaret, düzlemler |
| Athletics | STR | Olağandışı fiziksel güç, zorlu yüzme/tırmanma gibi meydan okumalar |
| Deception | CHA | Yalan, aldatıcı davranış |
| History | INT | Tarih, gelenek, geçmiş bilgiler |
| Insight | WIS | Duygu ve niyeti yorumlama |
| Intimidation | CHA | Tehdit veya baskı yoluyla etkileme |
| Investigation | INT | İpuçlarından sonuç çıkarma, mekanizma/şifre çözme |
| Medicine | WIS | Hastalık, ölüm nedeni, belirli ilk yardım |
| Nature | INT | Doğa ve doğal çevre bilgisi |
| Perception | WIS | Duyusal ayrıntıları fark etme |
| Performance | CHA | Eğlence ve sanatsal performans |
| Persuasion | CHA | Dürüst, nazik ikna |
| Religion | INT | Tanrılar, dinî ritüeller ve ilgili bilgi |
| Sleight of Hand | DEX | Yankesicilik, küçük nesne gizleme |
| Stealth | DEX | Sessiz ve fark edilmeden hareket |
| Survival | WIS | İz sürme, yiyecek bulma, doğada yol bulma |

**GM KARARI:** Bağlam başka ability kullanımını haklı çıkarabilir. Fiziksel güç gösterisiyle gözdağı vermede STR (Intimidation) istenebilir. Bu, oyuncunun her zaman en yüksek ability'sini seçmesi demek değildir. [SRD s.8–9, Skills; Skills with Different Abilities](https://media.dndbeyond.com/compendium-images/srd/5.2/SRD_CC_v5.2.1.pdf).

### 4.1 Araçlar ve Help

Bir check'e hem uygun tool proficiency hem skill proficiency uygulanıyorsa proficiency iki kez eklenmez; uygun araç yeterliliğiyle birlikte ilgili beceri yeterliliği advantage sağlar.

Bir ability check'e **Help** sağlamak için yardımcı kendi skill/tool proficiencies'inden birini seçer, yardımı fiilen veya sözle sağlayabilecek kadar yakın olmalıdır. GM yardımın uygunluğunu belirler. Müttefikin o beceri/araçla bir sonraki ilgili check'i advantage alır; yardımcının sonraki tur başlangıcından önce kullanılmazsa yarar sona erer. Yardımcı normalde ayrı “yardım zarı” atmaz.

Saldırı için Help farklıdır: yardımcının 5 feet yakınındaki düşmanın dikkati dağıtılır; müttefikin o hedefe sonraki saldırısına advantage sağlanır, belirtilen süre içinde. Her “yardım ediyorum” ifadesi sınırsız advantage üretmez. [SRD s.9, s.182–183, Help](https://media.dndbeyond.com/compendium-images/srd/5.2/SRD_CC_v5.2.1.pdf).

### 4.2 Search, Study, algı ve yorum

**Search** Wisdom temellidir: gizli nesne/canlıyı fark etmek Perception; kişinin ruh hâli Insight; hastalık/ölüm nedeni Medicine; iz/yiyecek Survival.

**Study** Intelligence temellidir: büyüsel olgu Arcana; tarih History; mekanizma, tuzak, şifre Investigation; doğa Nature; dinî olgu Religion.

“Arıyorum” sözcüğü her zaman Investigation değildir. Önce bir çizgiyi görmek ile gördüğün çizginin tetik teli olduğunu çözmek ayrı sorunlar olabilir. Ancak her keşif için otomatik iki check isteme. Belirli tuzak metni doğrudan sonucu belirleyebilir: fark edilmiş bir teli kesmek veya etrafından geçmek ek check gerektirmeyebilir. [SRD Rules Glossary: Search, Study; s.199–200 tuzak örnekleri](https://media.dndbeyond.com/compendium-images/srd/5.2/SRD_CC_v5.2.1.pdf).

### 4.3 Passive Perception

`Passive Perception = 10 + Wisdom (Perception) check bonus`

İlgili advantage varsa +5; disadvantage varsa −5. Bu yeni d20 atışı değildir. GM bir karakterin bilinçli arama yapmadan bir şeyi fark edip etmediğini değerlendirirken kullanabilir.

- Aktif Perception sonucunun otomatik alt sınırı değildir.
- Her beceride aynı adlı pasif mekanik olduğunu varsayma.
- Duvarın arkasını görme veya bütün gizlenenleri otomatik bulma yetkisi değildir.
- Lightly Obscured ortamda görmeye bağlı Perception disadvantage alır.
- Göremeyen biri yalnızca görmeye bağlı check'lerde otomatik başarısız olur; işitme gibi diğer duyular ayrı değerlendirilir.

[SRD s.186, Passive Perception; Rules Glossary: Blinded; Vision and Light](https://media.dndbeyond.com/compendium-images/srd/5.2/SRD_CC_v5.2.1.pdf).

### 4.4 Hide: 2024 özel prosedürü

1. Heavily Obscured olmak veya Three-Quarters/Total Cover arkasında olmak gerekir.
2. Her düşmanın görüş hattı dışında olmak gerekir; GM gizlenmenin uygunluğunu belirler.
3. DC15 Dexterity (Stealth) check yapılır.
4. Başarıda gizlenmişken Invisible condition kazanılır.
5. Check'in **gerçek toplamı** saklanır: seni bulmaya çalışan Wisdom (Perception) check'in DC'sidir.
6. Fısıltıdan yüksek ses çıkarmak, düşman tarafından bulunmak, attack roll yapmak veya Verbal component içeren büyü yapmak gibi kuraldaki sona erdiriciler uygulanır.

**Örnek:** Stealth toplamı22 ise başlangıç DC15 aşılmıştır ve aktif tespit DC'si22'dir. “Hedef Perception attı, başlangıçta ona karşı yarıştın” diye 2014 karşılıklı check modelini otomatik kullanma. Açık alanda önkoşulsuz DC15 atıp gizlenme de yoktur. Invisible sonucu, görünmezlik büyüsüyle fiziksel olarak saydamlaşma anlatısı kurmayı gerektirmez; koşulun kaynağı gizlenmedir.

[SRD s.183, Hide](https://media.dndbeyond.com/compendium-images/srd/5.2/SRD_CC_v5.2.1.pdf).

### 4.5 Influence: ikna, yalan, tehdit

Önce hedefin isteğe **willing / unwilling / hesitant** oluşu belirlenir:

- Willing: zar gerekmeksizin kendi usulünce yardımcı olur.
- Unwilling: talebi reddeder; yüksek Persuasion sonucu otomatik zihin kontrolü değildir.
- Hesitant: uygun check ile etkileme denenebilir.

Hesitant hedef için varsayılan DC `max(15, hedefin Intelligence SCORE'u)` şeklindedir. Score kullanılır, modifier değil. Deception, Intimidation, Performance veya Persuasion tipik olarak CHA ile; Beast/Monstrosity'yi nazikçe yönlendirme Animal Handling ile WIS üzerinden çözülür. Hedefin söyleneni anlamasını gerektiren seçeneklerde iletişim şartları korunur.

Friendly attitude advantage, Hostile disadvantage sağlar. **Attitude ile willingness farklı şeylerdir:** dost bir kişi belirli talebe kesinlikle karşı olabilir. Başarısız aynı yöntemle yeniden etkileme girişimi için 24 saat veya GM'nin belirlediği süre kısıtı vardır. Bunu tüm check'lere yayma.

**Örnek:** INT score18 olan tereddütlü muhafız için DC18; INT modifier+4 kullanarak DC15'e indirme. Dost muhafızın ailesini öldürmesini istemek otomatik advantage'lı ikna fırsatı değildir.

[SRD s.184, Influence](https://media.dndbeyond.com/compendium-images/srd/5.2/SRD_CC_v5.2.1.pdf).

### 4.6 Hırsızlık, kilit ve zor kullanma

- Sahipsiz/engelsiz bir nesneyi almak nesne etkileşimi olabilir; her “almak” hırsızlık check'i değildir.
- Üzerinde taşınan küçük bir nesneyi fark ettirmeden almak DEX (Sleight of Hand) değerlendirmesidir.
- Önce fark edilmeden yaklaşmak gerekiyorsa Stealth ayrı engel olabilir; her hırsızlığa otomatik eklenmez.
- Bir kilidi açmak ilgili araç ve kilit/eşya kuralına tabidir. “Her kilit DC15” evrensel kural değildir.
- Her hırsızlığı hedefin karşılıklı Perception zarıyla çözmek 2024 SRD'nin evrensel prosedürü değildir; GM somut koşulları ve varsa özel kuralı seçer.
- **MOTOR ÖNERİSİ:** Hedef, nesne, mevcut sahibi ve yeni sahibi açık olmalıdır. Başarı çözülmeden envantere ekleme yapılmamalıdır. Başarısızlığın fark edilme mi, zaman kaybı mı, yalnızca alamama mı olduğuna bağlama göre karar verilir; her başarısızlık aynı sonuç değildir.

Belirli nesne örneği: Manacles için kurtulma DC20 DEX (Sleight of Hand), kırma DC25 STR (Athletics), uygun thieves' tools ile kilidi açma DC15 DEX (Sleight of Hand) check olarak yazılıdır. Bu DC'ler yalnızca o eşyanın metnine aittir. [SRD s.98, Manacles; s.8 Skills](https://media.dndbeyond.com/compendium-images/srd/5.2/SRD_CC_v5.2.1.pdf).

### 4.7 Grup check'leri ve yarışmalar

SRD 5.2.1 genel kurallarında, 2014'ün “grubun en az yarısı başarılıysa grup başarılı” prosedürünü veya genel “contest eşitliğinde durum korunur” bölümünü otomatik 2024 varsayılanı kabul etmeyin. Bunlar [2014 Using Ability Scores](https://www.dndbeyond.com/sources/dnd/basic-rules-2014/using-ability-scores) ve [SRD5.1](https://media.dndbeyond.com/compendium-images/srd/5.1/SRD_CC_v5.1.pdf) kapsamında açıkça etiketlenebilir.

Bu uyarı GM'nin karşılıklı test tasarlamasını yasakladığı anlamına gelmez. Kaynak statüsünü ayırır: açık 2024 özel kuralını eski genel yöntemle değiştirme.

## 5. Saldırı, hasar ve savunma

### 5.1 Attack Roll

Normal olarak melee weapon attack STR, ranged weapon attack DEX kullanır. Finesse gibi weapon property'leri ve sınıf özellikleri istisna getirebilir. Spell attack ilgili spellcasting ability kullanır. İlgili yeterlilik varsa proficiency eklenir.

`attack_total = d20 + ability_modifier + applicable_proficiency + other_modifiers`

`attack_total >= target_AC` isabettir; doğal1 ıskalar, doğal20 isabet eder ve crit olur. Menzil, cover, hedefin görülebilirliği, durum etkileri ve kullanılan saldırının hedef türü ayrıca değerlendirilir. “D20 yüksek geldi” total cover içindeki hedefe normal şekilde saldırma izni değildir.

Half Cover AC ve DEX saves için +2; Three-Quarters Cover +5 sağlar. Total Cover doğrudan saldırı/büyü hedeflemesini kısıtlar; alan etkisinin erişimi kendi kuralına göre çözülür. [SRD s.14–16, Making an Attack, Cover](https://media.dndbeyond.com/compendium-images/srd/5.2/SRD_CC_v5.2.1.pdf).

### 5.2 Hasar

Hasar zarı saldırı zarı değildir. Önce isabet veya ilgili özel tetikleyici belirlenir; sonra kaynakta yazılı hasar uygulanır. Her hasara ability modifier veya proficiency eklenmez. Silah hasarına uygun ability modifier uygulanabilir; büyü hasarında yalnızca metin/özellik izin verirse eklenir.

- Birden fazla ayrı attack roll genellikle ayrı isabet ve hasar çözümüdür.
- İki veya daha fazla hedefi **aynı anda saving throw yapmaya zorlayan** hasarlı etki için ilgili ortak hasar bir kez atılır; hedeflerin save/direnç sonuçları ayrı uygulanır.
- Bunu her çok hedefli saldırıda tek hasar atılır şeklinde genişletme.
- Damage resistance, vulnerability, immunity ve diğer değiştirmeler kaynak sırası/yuvarlama kurallarıyla uygulanır.

[SRD s.16–17, Damage and Healing](https://media.dndbeyond.com/compendium-images/srd/5.2/SRD_CC_v5.2.1.pdf).

### 5.3 Critical Hit

Attack Roll kritik olduğunda saldırının hasar zarları iki kez atılır; sabit modifier ikiye katlanmaz. Bir saldırıya bağlı ek hasar zarları kendi özel kuralı engellemiyorsa bu hesaba katılır. Bir hedefin save'de doğal1 atması genel olarak crit doğurmaz.

**Örnek:** `1d8+3` kritik sonucu `2d8+3`; `2 × (1d8+3)` değildir. Temel Unarmed Strike hasarı `1+STR modifier` olduğundan doğal20'nin ikiye katlayacağı hasar zarı yoktur. Hasarı zarla değiştiren özellik varsa o özelliği uygula. [SRD s.16, Critical Hits; s.190, Unarmed Strike](https://media.dndbeyond.com/compendium-images/srd/5.2/SRD_CC_v5.2.1.pdf).

### 5.4 Grapple ve Shove: saldırı zarı sanmayın

2024 temel Unarmed Strike seçenekleri:

| Seçenek | Zar atan | Çözüm |
|---|---|---|
| Damage | Saldıran | Attack roll; isabette temel `1+STR modifier` |
| Grapple | Hedef | Hedefin seçtiği STR veya DEX saving throw |
| Shove | Hedef | Hedefin seçtiği STR veya DEX saving throw |

Grapple/Shove DC'si `8 + saldıranın STR modifier + proficiency bonus`. Hedef en fazla bir boyut büyük olabilir. Grapple için boş el gerekir. Shove başarısız kurtarmada 5 feet itme veya Prone seçeneği verir. Özel canavar yeteneği veya karakter özelliği farklı yazıyorsa kendi metni kullanılır.

**Grapple'dan kurtulmak farklıdır:** Action harcayarak STR (Athletics) veya DEX (Acrobatics) **ability check**, grapple escape DC'ye karşı yapılır. Başlangıçtaki saving throw ile karıştırılmaz. [SRD s.182 Grappling, s.190 Unarmed Strike](https://media.dndbeyond.com/compendium-images/srd/5.2/SRD_CC_v5.2.1.pdf).

### 5.5 Initiative ve Surprise

Initiative Dexterity check'tir, attack/save değildir. Savaş başlangıcında katılımcıların sırasını belirler. GM aynı türden özdeş yaratık grubu için tek zar atar. Sıra normalde turdan tura korunur. Oyuncu karakterleri arasındaki eşitliği oyuncular, canavarlar arasını GM, karakter-canavar eşitliğini GM çözer.

2024 Surprise, initiative atışına disadvantage getirir. 2014'ün ilk tur eylemsizliği modelini otomatik uygulama. Initiative'e yalnızca bir karakter özelliği izin veriyorsa proficiency gibi ek bonuslar eklenir. [SRD s.13–14, Initiative](https://media.dndbeyond.com/compendium-images/srd/5.2/SRD_CC_v5.2.1.pdf).

### 5.6 Opportunity Attack

Görülebilen bir yaratık erişim alanından çıkarken, çıkmadan hemen önce **Reaction** harcayarak tek melee weapon attack veya Unarmed Strike yapılabilir. Reaction kullanılabilir olmalı ve tetik gerçekleşmelidir; düşmanın yakınında her hareket saldırı doğurmaz. İsabet için normal saldırı çözümü uygulanır; Unarmed Strike'ın seçilen alt seçeneği de kendi prosedürünü korur.

Disengage, normalde bu fırsat saldırısını tetiklemeyi önler. Teleport veya yaratığın kendi movement/action/Bonus Action/Reaction'ını kullanmadan hareket ettirilmesi de tetiklemez; örneğin patlamayla savrulmak veya düşerek erişim alanından geçmek. Özel özellikler istisna getirebilir. “İstemeden hareket” gibi gündelik bir ölçüt yerine kuraldaki hareket kaynağını denetleyin. [SRD s.15, Opportunity Attacks](https://media.dndbeyond.com/compendium-images/srd/5.2/SRD_CC_v5.2.1.pdf).

### 5.7 Knockout: 2024'te 0 HP değil 1 HP

Melee attack ile bir yaratığı 0 HP'ye düşürecekken saldıran, bunun yerine onu **1 HP'ye düşürüp Unconscious** yapmayı seçebilir. Bu seçenek için ayrı bir “bayıltma zarı” yoktur. Hedef Short Rest'e başlar; dinlenme sonunda koşul biter. HP kazanması veya birinin action harcayarak başarılı DC10 Wisdom (Medicine) ilk yardımı yapması koşulu erken bitirir.

Bunu 0 HP'deki kişiyi stabilize etmekle karıştırmayın: knockout hedefi 1 HP'dedir; normal ölüm kurtarma dizisine sokulmaz. Her ranged attack veya her hasar kaynağına bu seçeneği genişletmeyin. [SRD s.17, Knocking Out a Creature](https://media.dndbeyond.com/compendium-images/srd/5.2/SRD_CC_v5.2.1.pdf).

## 6. Saving Throw

Saving throw genellikle bir tehdide tepkidir; her zaman eylem veya reaction harcatmaz. Tehlikeyi oluşturan kural hangi ability, hangi DC, ne zaman ve başarı/başarısızlık sonucunu belirler.

| Ability | Tipik tehdit; otomatik sınıflandırma değildir |
|---|---|
| STR | Fiziksel olarak itilmeye/tutulmaya direnme |
| DEX | Belirli alan tehlikelerinden sakınma |
| CON | Zehir, fiziksel dayanıklılık, concentration |
| INT | Belirli zihinsel/büyüsel etkiler |
| WIS | Algı/irade üzerinde etkiler |
| CHA | Benliği veya varoluşu etkileyen belirli büyüler |

Bu örneklerden mekanik türetmeyin: bir büyü WIS diyorsa “zihinsel görünüyor, INT olsun” diye değiştirmeyin. Normal spell save DC `8+PB+spellcasting ability modifier` şeklindedir; özel kaynak DC'si farklı olabilir.

- Başarı her zaman sıfır hasar değildir.
- Başarı her zaman yarım hasar da değildir.
- Sonuç, ilgili büyü/özellikte yazdığı gibidir.
- 2024 genel kuralları saving throw'u zar atmadan gönüllü başarısız saymayı seçmeye izin verir.
- Paralyzed/Petrified/Unconscious gibi koşullar STR/DEX saves'i otomatik başarısız kılabilir; bunu bütün saves'e yayma.

[SRD s.7, Saving Throws; Rules Glossary: Saving Throw ve ilgili conditions](https://media.dndbeyond.com/compendium-images/srd/5.2/SRD_CC_v5.2.1.pdf).

### 6.0 Koşulların zarlara etkisi ve Exhaustion

Koşulun adından genel sonuç uydurmayın; tam etkisini uygulayın. Aşağıdaki tablo seçilmiş **zar etkilerinin** özetidir, koşulların hareket/duyu/eylem üzerindeki bütün etkilerinin yerine geçmez.

| Koşul | İlgili zar etkisi |
|---|---|
| Poisoned | Ability checks ve attack rolls disadvantage; genel bütün saves disadvantage değildir |
| Frightened | Korku kaynağı görüş hattındayken ability checks ve attack rolls disadvantage |
| Prone | Kendi attack rolls disadvantage; ona karşı attack roll saldıran 5 feet içindeyse advantage, değilse disadvantage |
| Restrained | Kendi saldırıları disadvantage; ona karşı saldırılar advantage; DEX saves disadvantage |
| Paralyzed | STR/DEX saves otomatik başarısız; ona karşı attacks advantage; 5 feet içindeki saldıranın isabet eden attack roll'u critical |
| Stunned | STR/DEX saves otomatik başarısız; ona karşı attacks advantage; Paralyzed'ın otomatik crit etkisini buraya kopyalama |
| Unconscious | STR/DEX saves otomatik başarısız; ona karşı attacks advantage; 5 feet içindeki saldıranın isabet eden attack roll'u critical |
| Blinded | Yalnızca görme gerektiren checks otomatik başarısız; kendi attacks disadvantage, ona karşı attacks advantage |

Paralyzed/Unconscious karşısındaki “automatic critical” ifadesi **otomatik isabet** demek değildir: önce saldırı isabet etmelidir. Birden çok koşuldan gelen advantage/disadvantage ortak iptal kuralına tabidir.

**Exhaustion (2024):** Birikimli seviye vardır. Her D20 Test sonucu exhaustion level'ın iki katı kadar azaltılır; Speed ise seviye başına 5 feet azalır. Seviye6 ölüm getirir. Long Rest bir seviyeyi kaldırır. Bu, eski sürümün farklı basamaklarda farklı etkiler veren tablosu değildir. Hasar ve rastgele tablo zarları D20 Test olmadığından bu ceza onlara kendiliğinden uygulanmaz; Death Saving Throw bir saving throw olduğu için ilgili D20 Test değiştiricileri değerlendirilir, doğal1/20 özel sonuçları korunur.

[SRD s.181 Exhaustion; s.182 Frightened; s.186–188 ilgili conditions; s.191 Unconscious; Rules Glossary](https://media.dndbeyond.com/compendium-images/srd/5.2/SRD_CC_v5.2.1.pdf).

### 6.1 Concentration

Hasar aldığında concentration korumak için CON saving throw gerekir:

`DC = min(30, max(10, floor(alınan_hasar / 2)))`

**KURAL:** Hasar almak concentration save tetikler. **GM KARARI / MOTOR ÖNERİSİ:** Ayrı zamanda çözülen hasar olaylarını ayrı tetikleyiciler olarak işlemek uygundur. Bununla birlikte SRD 5.2.1, eşzamanlı birden çok hasar kaynağının her durumda kaç ayrı hasar olayı sayılacağını burada ayrıntılı biçimde çözmez. Eşzamanlı mermi/hasar paketlerini koşulsuz olarak ayrı save sayan evrensel bir kural iddia etmeyin; özel etki metni ve açıkça kaydedilmiş GM yorumu gerekir. Incapacitated olmak veya ölmek gibi açık sona erdiricilerde normalde save ile concentration kurtarılmaz. Yeni concentration gerektiren etkiye başlamak da eskiyi bitirebilir.

**Örnekler:** 9 hasar → DC10; 25 hasar → DC12; 70 hasar → DC30. Birbirinden ayrı zamanlarda çözülen iki 8 hasarlı olay için iki DC10 save işlemek önerilen yorumdur. Eşzamanlı iki hasar paketinde gruplama kararı özel etki metnine ve GM yorumuna bırakılır; gerekçe kaydedilir. [SRD Rules Glossary: Concentration](https://media.dndbeyond.com/compendium-images/srd/5.2/SRD_CC_v5.2.1.pdf).

### 6.2 Death Saving Throw ve stabilizasyon

0 HP'de turuna başlıyor ve Stable değilsen death save gerekir. Bu normal ability score'a bağlı değildir.

- d20 ile uygulanabilir bonus/cezaların toplamı 10 veya üzeriyse başarı. Normal ability modifier eklenmez; ancak death saving throw'a uygulanabilen bir özellik bonusu veya Exhaustion gibi ceza ayrıca değerlendirilir. Doğal 1 ve 20 özel sonuçları korunur.
- Üç başarı: Stable. Üç başarısızlık: ölüm.
- Başarı/başarısızlıkların art arda gelmesi gerekmez.
- Doğal1: iki başarısızlık. Doğal20: 1 HP kazanma.
- HP kazanıldığında veya Stable olunduğunda sayaçlar sıfırlanır.
- 0 HP'de hasar: bir başarısızlık; Critical Hit ise iki.
- 0 HP'de alınan hasar maksimum HP'ye eşit/aşarsa ölüm.
- Stable yaratık 0 HP ve Unconscious kalır, death save atmaz; tekrar hasarda stabilitesini kaybeder.
- İyileştirilmeyen Stable yaratık 1d4 saat sonra1 HP kazanır.
- Help action ile DC10 Wisdom (Medicine) check, 0 HP yaratığı stabilize edebilir.

0 HP'ye ilk düşüşte anlık ölümün fazla hasar kuralı ayrıca değerlendirilir. Temporary HP, gerçek iyileştirme değildir ve 0 HP karakteri kendi başına uyandırmaz. [SRD s.17–18, Dropping to 0 Hit Points, Death Saving Throws, Stabilizing](https://media.dndbeyond.com/compendium-images/srd/5.2/SRD_CC_v5.2.1.pdf).

### 6.3 Counterspell ve Dispel Magic: benzer amaç, farklı zar

**Counterspell (2024):** Büyüyü yapan hedef yaratık **Constitution saving throw** yapar; karşı büyüyü yapan kişinin genel Arcana check'i değildir. Reaction tetikleyicisi, 60 feet içindeki görülebilen yaratığın Verbal/Somatic/Material component içeren büyü yapmasıdır. Hedef save'de başarısızsa büyü etkisiz dağılır; kullanılan action/Bonus Action/Reaction boşa gider. Spell slot ile yapılıyorsa hedefin o slotu harcanmaz. 2014 Counterspell prosedürünü buraya taşımayın.

**Dispel Magic (2024):** Hedef üzerindeki devam eden level3 veya düşük büyüler sonlanır. Level4 veya yüksek her devam eden büyü için, gerektiğinde, **kendi spellcasting ability'nle ability check** yapılır; DC `10 + bitirilmek istenen büyünün level'ı`. Bu varsayılan olarak Arcana proficiency içeren bir check değildir. Daha yüksek spell slot kullanıldığında, level'ı kullanılan slot level'ına eşit veya düşük büyü otomatik sonlanır. Her sihirli özellik bir ongoing spell değildir; spell olmayan her etkiyi otomatik silme yetkisi çıkarılmaz.

[SRD Spells: Counterspell ve Dispel Magic](https://media.dndbeyond.com/compendium-images/srd/5.2/SRD_CC_v5.2.1.pdf).

## 7. D20 Test olmayan zarlar

| Kullanım | Zar/formül örneği | Neden/şart |
|---|---|---|
| Hasar | Silah/büyü metnindeki d4/d6/d8/d10/d12 vb. | Başarılı saldırı veya özel etkinin büyüklüğü |
| İyileştirme | İlgili büyü/iksir metni | Geri kazanılan HP; her iyileştirme zar değildir |
| Short Rest Hit Dice | Harcanan Hit Die + CON modifier, **en az 1 HP** | Oyuncu harcamayı seçer; sonuca bakıp ek zar harcayabilir |
| Level-up HP | Yeni Hit Die + CON modifier, en az1 | Zar yerine sınıfın sabit seçeneği kullanılabilir |
| Ability score oluşturma | 4d6, düşük zarı çıkar, altı kez | Standard array/point buy alternatifleri vardır |
| Recharge X–Y | d6 | Yaratığın tur başlangıcında belirtilen aralıkta yetenek yenilenir |
| Süre | Örneğin1d4 saat | Etki metni söylüyorsa |
| Kaynak yenilenmesi | Örneğin1d6+1 şarj | Belirtilen zamanda, eşyanın azami şarjı ve diğer şartlarıyla |
| Rastgele etki | d100 | Tam tablonun aralıkları uygulanır |
| Özel d20 sonucu | Asanın son şarjında kırılma gibi | D20 Test değildir; bonus eklenmez, özel metin izlenir |

**Önemli:** Short Rest 1 saatlik uygun dinlenmedir; başlamak için en az 1 HP gerekir. Hit Dice ile minimum iyileşme SRD 5.2.1 metninde 1 HP olarak açıkça belirtilir. Long Rest varsayılanında HP ve harcanmış Hit Dice geri kazanımı ayrı bir iyileştirme zarı gerektirmez; 2014'teki yarı Hit Dice geri kazanımını 2024'e taşıma. [SRD s.21, s.23, s.187 Short Rest, Long Rest; s.257 Recharge](https://media.dndbeyond.com/compendium-images/srd/5.2/SRD_CC_v5.2.1.pdf).

### 7.1 Kaynaklı özel örnekler

- **Wand of Magic Missiles:** şafakta1d6+1 şarj; son şarj harcanırsa d20,1'de yok olur. İkinci atış saving throw değildir.
- **Wand of Magic Detection:** şarj geri kazanımı1d3.
- **Wand of Wonder:** d100 rastgele etki tablosu; çıkan sonuç ek zarlar gerektirebilir.
- **Amulet of the Planes:** ilgili Arcana check başarısızlığından sonra d100 varış yeri sonucu. Check ve tablo atışı ayrı kayıtlardır.
- **Blink (2024):** ilgili tur sonu tetikleyicisinde d6,4–6 sonucu Ethereal Plane; eski sürüm d20 prosedürünü kullanma.
- **Bazı golem Berserk özellikleri:** belirtilen Bloodied/tur başlangıcı şartında d6,6 sonucu. Bütün golem veya bütün Bloodied yaratıklara yayma.

[SRD s.113–114 Blink; s.209 Amulet of the Planes; s.251–252 asalar; ilgili golem stat block'ları](https://media.dndbeyond.com/compendium-images/srd/5.2/SRD_CC_v5.2.1.pdf).

### 7.2 d3 ve d100 gösterimi

Fiziksel d3 yoksa eşit olasılıklı bir dönüştürme kullanılabilir; örneğin d6 sonuçlarını1–2→1,3–4→2,5–6→3 eşleştirmek. d100 yazılımda1–100 tam sayı olabilir; fiziksel yüzde zarının00/0 gösterimi100 olarak yorumlanır. **MOTOR ÖNERİSİ:** İç veri biçiminde1–100 standardını kullan, arayüzde00 ile0'ı karıştırma. Tablo aralıklarını boşluksuz ve çakışmasız doğrula.

### 7.3 Hareket, düşme, çevre

Normal yürümek, sıradan tırmanma/yüzme ve kurallardaki normal sıçrama mesafesi her seferinde Athletics check gerektirmez. Zorlu koşullar veya özel kural check/save doğurabilir. Normal Long Jump mesafesi uygun koşuda STR score'a bağlıdır; bir d20 mesafe tablosu değildir.

Düşme hasarı normalde her10 feet için1d6, en çok20d6'dır; düşme için evrensel “DEX save başarılıysa yarısı” kuralı icat etme. İniş, özel özellik, su veya büyü gibi istisnalar ilgili metinle değerlendirilir. [SRD Rules Glossary: Falling, Jumping; hareket kuralları](https://media.dndbeyond.com/compendium-images/srd/5.2/SRD_CC_v5.2.1.pdf).

### 7.4 SRD dışı rastgele özellikler

Wild Magic gibi SRD dışında kalan alt sınıf tablolarını çekirdek kurala eklemeyin. Bunlar ayrı, sürümü belirlenmiş içerik modülleridir. Bir tanıtım yazısı tam özellik/tablo metninin yerine geçmez. Benzer şekilde rastgele karşılaşma, hava durumu, ganimet ve moral tabloları ancak kullanılan macera/modül/GM yöntemi öngörüyorsa çalıştırılmalıdır; hepsi her sahnede zorunlu değildir.

## 8. AI motoru için güvenilir işlem hattı

Bu bölüm bütünüyle **MOTOR ÖNERİSİ**dir. Kaynak kurallarını değiştirmez; doğru uygulanmalarına yardımcı olur.

### 8.1 İki farklı sınıflandırmayı ayrı tut

1. **Oyun zamanı/maliyet:** Action, Bonus Action, Reaction, hareket, nesne etkileşimi, uzun süreç, otomatik tetikleyici.
2. **Çözüm tipi:** no_roll, ability_check, saving_throw, attack_roll, damage_roll, healing_roll, resource_roll, random_table, duration_roll.

Bir Action no_roll olabilir. Bir saving throw reaction tüketmeyebilir. Bir büyü birden fazla çözüm tipi içerebilir. Bunları tek `action_type=dice` alanına sıkıştırma.

### 8.2 Önerilen sıra

```text
İfade → niyet ve olumsuzluk denetimi
      → aktör / hedef / nesne / sahiplik çözümleme
      → sahne ve önkoşul doğrulama
      → ruleset + özel kural seçimi
      → eylem maliyeti / tetik zamanı
      → no-roll sonucu VEYA zar isteği
      → sonucu yetkili RNG/oyuncu atışından alma
      → bütün modifier ve istisnaları uygulama
      → sonucu ve state değişimini tek işlem olarak kaydetme
      → gerçekleşmiş sonuca uygun anlatım
```

Anlatıcı başarıyı önceden yazmamalıdır. “Keseyi fark ettirmeden cebine koyuyorsun” ancak çözülmüş başarı sonrası uygundur. Beklerken “Keseye uzanmayı deniyorsun; sonucu belirleyelim” denebilir.

### 8.3 Bir eylem, birkaç aşama

Örnek hırsızlık akışı:

1. Hedefe gizlice yaklaşma gerçekten ayrı engelse Stealth.
2. Kilit varsa ayrı kilit kuralı.
3. Nesne üzerindeyse fark ettirmeden alma için Sleight of Hand.
4. Başarıdan sonra nesne sahibi değişir.

Her aşama otomatik değildir. “Üç zar daha zor oyun yapar” gerekçesiyle gereksiz zar eklenmez. Önceki başarısızlık sonraki aşamayı imkânsız yapıyorsa işlem durur. Başarısızlık sonucu oyuncuya yeni karar fırsatı verebilir.

### 8.4 Örnek makine-okunur kayıt

Aşağıdaki şema resmî oyun formatı değil, bir tasarım önerisidir. `null` bilinmeyeni gösterir; bilinmeyen DC'yi uydurarak doldurmak yerine GM kararı gerekir.

```json
{
  "ruleset": "dnd_2024_srd_5_2_1",
  "action_id": "act_001",
  "intent_status": "confirmed_attempt",
  "actor_id": "pc_01",
  "target_id": "npc_07",
  "object_id": "purse_07",
  "ownership_before": "npc_07",
  "rule_id": "gm_ability_check_sleight_of_hand",
  "rule_origin": "core_plus_gm_adjudication",
  "source_heading": "Ability Checks / Skills",
  "action_cost": "gm_adjudicated",
  "prerequisites": {"reachable": true, "object_identified": true},
  "resolution": {
    "kind": "ability_check",
    "roller_id": "pc_01",
    "ability": "DEX",
    "skill": "Sleight of Hand",
    "dice": "1d20",
    "ability_modifier": 3,
    "proficiency_contribution": 2,
    "other_modifier": 0,
    "advantage_sources": [],
    "disadvantage_sources": [],
    "dc": null,
    "dc_origin": "pending_gm_adjudication",
    "natural_20_auto_success": false,
    "natural_1_auto_failure": false
  },
  "state": "awaiting_adjudication",
  "roll_result": null,
  "outcome": null,
  "committed_state_changes": []
}
```

Grapple için aynı şemayı kopyalayıp `skill=Athletics` yapmak yanlıştır. `roller_id` hedefe, `kind=saving_throw`, ability hedefin STR/DEX seçimine ve DC saldıranın8+STRmod+PB hesabına dönüşmelidir.

### 8.5 Durum makinesi ve güvenlik sınırları

```text
proposed → validated → awaiting_roll → resolved → committed
                   ↘ resolved_no_roll → committed
proposed/validated → rejected_or_clarification_needed
```

- Aynı `action_id` ikinci kez işlenirse hasar/ödeme/eşya transferi tekrar uygulanmaz.
- Geçmiş, alıntı, plan veya ret ifadeleri `confirmed_attempt` değildir.
- “NPC istedi” ile “oyuncu kabul etti” farklı olaylardır.
- Kaynak/şablon metnindeki yönergeler oyuncu yetkisi sayılmaz.
- Zar sonucu belli olmadan gerçek state'e başarı yazılmaz.
- Zar sonrası retcon gerekiyorsa ayrı düzeltme olayı kaydedilir; sessiz yeniden zar seçilmez.
- Gizli GM DC'si arayüzde oyuncuya gösterilmese bile sistem içindeki gerekçe ve kaynak tutulur.
- RNG; ability, save, attack, damage ve tablo atışlarını türüne göre kaydeder. Rastgele d20'ye proficiency eklenmez.

## 9. Somut olay örnekleri

### A. Tehdit

Oyuncu “Parayı vermezsen camı kırarım” der. Önce gerçekten hedefi etkileme niyeti olduğu belirlenir. Hedef talebe willing ise check yok; unwilling ise zarla zorunlu boyun eğme yok; hesitant ise Influence ve uygun Intimidation çözümü. Başarısızlıkta NPC'nin nasıl tepki verdiği bağlamdır; otomatik combat başlatmak evrensel kural değildir.

### B. Tuzak ve algı

Oyuncu koridoru gözle tarar: Perception ile fark etme gündeme gelir. Fark ettiği işaretin anlamını çözmek Arcana/Investigation olabilir. Tuzak metni işaretin tahribinin tuzağı kapattığını ve check istemediğini söylüyorsa tekrar gereksiz beceri atışı yaratılmaz.

### C. Attack ve crit

Saldıran d20'de20 attı, silah hasarı1d8+3. Hedefin AC'sine rağmen isabet ve2d8+3 hasar çözülür. Direnç ve diğer etkiler sonra ilgili kurala göre uygulanır. “20 geldi, hedef mutlaka ölür” denmez.

### D. Grapple

STR modifier3, PB2 olan karakter grapple dener: DC13. Hedef STR veya DEX save seçer. Başarısızsa Grappled. Sonraki kurtulma denemesi action ve Athletics/Acrobatics check'tir. İki tarafın Athletics atıp yüksek olanın kazanması 2024 temel prosedürü değildir.

### E. Alan büyüsü

Aynı anda üç hedef save yapar. Ortak hasar bir kez atılır; her hedef kendi save sonucunu, direncini ve özelliğini uygular. Başarılı save'in etkisini büyünün metni belirler. Hasar nedeniyle concentration gerekiyorsa bu ayrı CON save aşamasıdır.

### F. Ücretsiz gündelik işlem

Oyuncu “Kendi çantamdan ipi çıkarıyorum” der. Engel yoksa Sleight of Hand isteme. Nesnenin mevcut sahipliği değişmeyebilir; yalnızca takılı/elde/çantada durumu değişir. Düşmanın kemerinden aynı ipi gizlice almak farklı problemdir.

### G. Kabul edilmeyen teklif

NPC “Bir altın bahşiş?” der, oyuncu “Hayır” der. Zar yok, ödeme yok. Bir konuşma cümlesinin para miktarı içermesi ekonomik işlem tetikleyicisi değildir.

### H. İmkânsız sosyal talep

Düşman kraldan hiçbir karşılık olmadan krallığını bırakmasını istemek için doğal20 her şeyi çözmez. İmkânsız/kararlı ret ile tereddütlü tutum ayrımı zar öncesinde yapılır. GM sonucu belirler; başarı oyuncunun hayal ettiği sınırsız kapsamı garanti etmez.

## 10. Regression test kataloğu

**Bunlar önerilen test vakalarıdır; mevcut AI-DND kodunda çalıştırılmış testler değildir.** Beklenen sonuçlar kaynak kuralını ve ayrıca işaretlenmiş motor davranışını doğrular.

| ID | Girdi/önkoşul | Beklenen |
|---|---|---|
| D01 | Check toplam15, DC15 | Başarı |
| D02 | Check doğal20,+0,DC25 | Başarısız |
| D03 | Check doğal1,+10,DC10 | Başarı |
| D04 | Attack doğal1, toplam AC'yi geçiyor | Iska |
| D05 | Attack doğal20, toplam AC altında | İsabet+crit |
| D06 | Üç advantage, bir disadvantage | Tek normal d20 |
| D07 | İki proficiency kaynağı | PB yalnızca bir kez |
| D08 | Uygun tool ve skill proficiency | PB bir kez, advantage |
| D09 | Expertise | Yalnızca PB katkısı iki kat |
| D10 | Heroic Inspiration, damage d8 yeniden atılıyor | Özellik yalnızca d20 diye reddedilmez; yeni sonuç zorunlu |
| A01 | Kilitsiz engelsiz kapı | Gereksiz check yok; etkileşim maliyeti ayrı |
| A02 | Salt varsayımsal “Çalsam?” | Motor: eylem ve transfer yok |
| A03 | Gerçek theft, zar bekliyor | Motor: envanter değişmez |
| A04 | Theft başarı olayı iki kez geliyor | Motor: tek transfer |
| A05 | Bahşiş reddedildi | Motor: ödeme yok |
| A06 | Uygunsuz/yeterliliksiz Help talebi | Genel check Help koşulları atlanmaz |
| H01 | Hide için cover/obscurement yok | Zar öncesi önkoşul başarısız |
| H02 | Uygun Hide, toplam14 | Başarısız |
| H03 | Uygun Hide, toplam22 | Gizlenme başarılı; tespit DC22 saklanır |
| H04 | Gizlenen attack roll yapıyor | Hide sona erdiricisi işlenir |
| P01 | Passive Perception14 | Yeni d20 üretilmez |
| P02 | Aktif Perception toplam9, pasif14 | Evrensel pasif taban uygulanmaz |
| I01 | Hesitant hedef INT score18 | Influence DC18 |
| I02 | Friendly ama unwilling hedef | Advantage'lı zorunlu uyma check'i yok |
| I03 | Başarısız Influence, aynı yöntem hemen | Kaynak retry kısıtı değerlendirilir |
| G01 | STRmod3, PB2 grapple | Hedef STR/DEX save, DC13 |
| G02 | Grapple escape | Action+Athletics/Acrobatics check; save değil |
| G03 | Hedef iki boyut büyük | Temel grapple/shove uygun değil |
| C01 | Crit1d8+3 |2d8+3 |
| C02 | Temel unarmed crit | Sabit hasar ikiye katlanmaz |
| C03 | Normal save doğal1 | Genel crit hasarı yok |
| C04 | Aynı anda üç hedefe save'li hasar | Ortak hasar zarı, üç ayrı save sonucu |
| C05 | İki ayrı attack | Otomatik tek ortak hasar yapılmaz |
| C06 | Surprised | Initiative disadvantage; otomatik kayıp tur değil |
| C07 | Görülen hedef reach dışına çıkıyor, Reaction mevcut | Tek opportunity attack seçeneği, çıkmadan önce |
| C08 | Teleport veya movement/action/Bonus Action/Reaction kullanmayan savrulma | Normal opportunity attack tetiklenmez |
| C09 | Melee attack öldürücü eşiğe ulaştı, knockout seçildi | 1 HP+Unconscious; ayrı bayıltma zarı ve death save yok |
| C10 | Poisoned hedef WIS save yapıyor | Sırf Poisoned nedeniyle disadvantage verilmez |
| C11 | Stunned hedefe 5 feet içinden isabet | Sırf Stunned nedeniyle otomatik critical yok |
| C12 | Paralyzed hedefe 5 feet içinden isabet | Critical; otomatik isabet varsayılmaz |
| C13 | Exhaustion2, normal ability check | Sonuca −4; damage roll'a uygulanmaz |
| S01 | Concentration25 damage | CON DC12 |
| S02 | Concentration70 damage | CON DC30 |
| S03 | Eşzamanlı iki8 damage paketi | Kaynak/gruplama kararı açık; koşulsuz iki save varsayımı yok |
| S04 | Gönüllü save başarısızlığı | Zar atılmadan failure seçilebilir |
| S05 | Paralyzed STR/DEX save | Koşul otomatik failure; WIS'e yayılmaz |
| S06 | 2024 Counterspell, tetik koşulları sağlandı | Büyüyü yapan hedef CON save; Arcana check değil |
| S07 | Dispel Magic level3 slot, hedef ongoing level5 spell | Spellcasting ability check DC15; otomatik Arcana/PB yok |
| S08 | Dispel Magic level5 slot, hedef ongoing level5 spell | Bu büyü için check gerekmeden sonlanır |
| X00 | Death save d20=11, Exhaustion1 ve başka değiştirici yok | Toplam9: failure; ability modifier eklenmez |
| X01 | Death save doğal1 | İki failure |
| X02 | Death save doğal20 |1 HP; sayaçlar sıfırlanır |
| X03 | Stable0HP tur başlangıcı | Death save yok |
| X04 | Stable0HP yaratık hasar aldı | Stable sona erer, hasar başarısızlığı uygulanır |
| X05 |0HP'de crit hasar | İki death save failure; instant death ayrıca |
| X06 | Help+Medicine toplam10 | DC10 stabilizasyon başarılı |
| R01 | Wand son şarj d20 | Ability/PB eklenmez |
| R02 | Recharge5–6 d6 sonucu4 | Yenilenmez |
| R03 | Recharge5–6 d6 sonucu5 | Yenilenir |
| R04 | Long Rest tamamlandı | Varsayılan HP/Hit Dice geri kazanımı için gereksiz zar yok |
| R05 |2024 Blink sonucu d6=4 | Özellik koşulları sağlanıyorsa ilgili geçiş |
| V01 |2014 grapple contest girdisi | Sürüm uyuşmazlığı işaretlenir |
| V02 | SRD dışı Wild Magic | Modül kaynağı olmadan çekirdek tablo çalıştırılmaz |

### 10.1 Kabul ölçütleri

- Her zarın `kind`, `roller`, `trigger`, `source` ve sonuç kuralı biliniyor.
- Her DC/AC için kaynak veya GM kararı izlenebiliyor.
- `roll pending` durumunda başarıya bağlı state değişikliği yok.
- 2014 ve2024 kuralları sessizce birleştirilmiyor.
- Tablolardaki rastgele aralıklar tam kapsama ve tekilliğe sahip.
- Niyet, negation, quotation ve hypothetical ayrımları envanter/para işlemlerinden önce doğrulanıyor.
- Gerçek kod testleri çalıştırılmadan “testler geçti” denmiyor.

## 11. Sık yapılan yanlışlar: kısa denetim listesi

1. Her eyleme zar istemek.
2. Her “gizlice” sözcüğünü Stealth, her “ara” sözcüğünü Investigation yapmak.
3. Ability check doğal20'yi sınırsız başarı saymak.
4. Saving throw doğal1'i crit saymak.
5. Grapple'ı2024'te genel opposed Athletics yapmak.
6. Hide başlangıcını hedefin Perception'ına karşı2014 contest olarak kurmak.
7. Influence'da INT score yerine modifier kullanmak.
8. Friendly hedefi her talebe willing sanmak.
9. Advantage kaynaklarını sayısal üstünlük yarışı gibi toplamak.
10. Hasara otomatik proficiency eklemek.
11. Critical Hit'te sabit modifier'ı ikiye katlamak.
12. Aynı anda save gerektiren alan hasarı kuralını bütün multiattack'lere yaymak.
13. Concentration DC üst sınırı30'u atlamak veya eşzamanlı hasar paketlerinin nasıl gruplandığını belgelemeden kesin kural gibi sunmak.
14. Surprise'ı2024'te otomatik ilk tur kaybı yapmak.
15. Stable0HP karaktere her tur death save attırmak.
16. Her d20'yi D20 Test saymak.
17. Zar sonuçlanmadan envanter, HP, para veya sahipliği değiştirmek.
18. NPC isteğini oyuncu kabulü saymak.
19. Bütün başarısızlıklara aynı “yakalandın/savaş başladı” sonucu vermek.
20. SRD kapsamı dışında kalan bir tabloyu “çekirdek kural” diye sunmak.

## 12. Kaynak doğrulama ve sınırlar

Araştırmada ortak D20 kuralları, beceri/sosyal/gizlenme prosedürleri, combat/save/hasar başlıkları ve diğer zar kullanım örnekleri ayrı incelenmiş; sürüm karışıklığı açısından çapraz kontrol edilmiştir. Kaynaklı sonuç ile uygulama önerisi bu belgede ayrı işaretlenmiştir. Bu, yazılım motorunun mevcut davranışının doğrulandığı anlamına gelmez.

Özellikle doğrulanan sürüm hassas noktalar: doğal1/20 ayrımı;2024 grapple/shove saves; Hide DC15 ve saklanan tespit DC'si; Influence willingness/attitude ve INT score; Surprise initiative disadvantage; concentration DC30 üst sınırı; Heroic Inspiration'ın herhangi bir zar olması;2024 Long Rest; rastgele d20'nin D20 Test olmaması.

İçerik paketine yeni spell/monster/item eklendiğinde bu belgeye bakarak genel tahmin yapmak yerine tam kaynak metni bağlanmalıdır. Errata veya yeni SRD sürümü geldiğinde `ruleset` güncellenmeli ve regression vakaları yeniden gözden geçirilmelidir.
