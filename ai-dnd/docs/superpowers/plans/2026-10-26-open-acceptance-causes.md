# Açık Kabul Maddeleri: Uygulama Planı

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rerun5'te açık kalan iki ürün cümlesini, kayıtlı sahne gerçeğine bağlamak.

**Architecture:** Barmen cümlesi `npc_speech_boundary.drop_ungrounded_prop_sentences` ile süzülür. Kayıtlı bir eşyayı adlandıran cümle, o eşyanın kendi tarifinden en az bir içerik sözcüğü taşımazsa düşer. Tarifte olmayan somut bir ad (`ekmek`) aynı cümlede duramaz. F, Investigation zarının başarılı olmasına rağmen eşleşen özellik yoksa `_inspection_findings` miss döndürür; bu dönüş model çağrısından ve `create_features` izninden önce biter. Şehir bakışı ve ortam olayı bu turda gösterilmez.

**Tech Stack:** Python 3.14, unittest, mevcut `narration_claims.fold`. Canlı kanıt gerekirse `faz7_ah_live.py` ve `qwen3.5:9b-q4_K_M`.

## Global Constraints

- Python HP, zar, savaş, envanter, büyü, XP ve kalıcı dünya değişiminin sahibidir. Model metni dünya gerçeği değildir.
- `living_world.py` içindeki "Ahşap masa / kil bardak" tarifi silinmez. Bardak kelimesi yasaklanmaz.
- Prompt guard gevşetilmez. Yeni kural `game.py` içine ikinci bir özellik olarak yazılmaz; konuşma süzgeci `npc_speech_boundary.py` içindedir. `_inspection_findings` zaten bu miss'in sahibidir.
- Kapı 8008 kullanılmaz. 33 kapı yeşil boyanmaz. Canlı olay UNRESOLVED kalır.
- `player_line` istemi, `free_v1` ve v0.1 sahne sınırları bu planın dışındadır.
- Yeni test dosyası açılmaz. Ürün `.py` dosyaları CRLF kalır. `PYTHONUTF8=1`.
- Komutlar `C:\Users\Kadir\Desktop\AI-DND-v01-scene-truth\ai-dnd` içinden, `$env:PYTHONPATH='.'` ile çalışır.
- Commit adımı kullanıcı açıkça istemedikçe çalıştırılmaz.

## Nedenler

Bunlar plandan önce okunmuş kanıttır. Uygulayıcı yeniden keşfetmez.

- Barmen, rerun5 `H-barman`: `Bir barmen: “Günün gidişi, tezgâhın üzerinde dönen bardaklar kadar kaotik ama tatlı. Mutfaktan gelen o taze ekmek kokusu... işte bu kanıtta her gün aynı şeyi yaşıyorsun.”` Süpürge yok. `bardak`, `living_world.py` satır 1474-1476 tarifinin alias'ıdır: "Kenarında sıradan bir kil bardak duran sağlam bir masa." Cümle bu ilişkiyi taşımaz. `ekmek` hiçbir kayıtta yoktur. `_unregistered_held_object` yalnız `elindeki`/`elinde`/`tuttugu` ve `caydanlik`/`supurge`/`cekic` başlarına bakar; deneysel konuşma bu kapıya girmez.
- F, rerun5 terminali: Investigation, DC 15, D20 17, toplam 17, BAŞARILI, model çağrısı 2. Gösterilen `İncelemen başarılı. Neverwinter çevresine göz gezdiriyorsun...` `_fallback_narration` başarı koludur. `_inspection_findings` eşleşen özellik bulamayınca `None` döner. Yük arabası `ambient_event_catalog.py` içindeki `city_cart_wheel` tarifidir; uydurma değildir, yanlış turda gösterilmiştir.
- Küçük olay ve bileşik ilk engel ayrı mekanik değildir. İz silme ve nedenin yazılmaması rerun5 `H-return` ile durur. Bileşik ilk engel `api/tests/test_scene_compound_contract.py` `test_compound_stops_at_locked_entry` içindedir ve canlı betik bu cümleyi göndermez. Bu plan yeni olay türü veya yeni bileşik motor yazmaz. Task 3 yalnız bu iki kaydı yeniden çalıştırır.
- 33 kapı ürün kusuru değildir. `ai-dnd/run_tests.py` `os.name != "posix"` iken `Gate process-tree cleanup requires a POSIX runtime` verir. `FIRST_DIVERGENCE.md` F6. Bu plan koşucuyu değiştirmez.
- Canlı olay, `FIRST_DIVERGENCE.md`: H01–H05 girdisi okunmadı, çalışan sürecin kaynağı kanıtlanmadı. Yeni sentetik tur bunu kapatmaz.

---

### Task 1: Kayıtsız ilişki ve kayıtsız ekmek konuşmadan düşer

**Files:**
- Modify: `ai-dnd/npc_speech_boundary.py` (`strip_player_echo` fonksiyonundan hemen sonra)
- Modify: `ai-dnd/game.py` (deneysel `cleaned_spoken = npc_speech_boundary.strip_player_echo(...)` satırının hemen altı)
- Test: `ai-dnd/api/tests/test_bound_speech_label.py` (`PlayerQuoteTests`)

**Interfaces:**
- Consumes: `narration_claims.fold`
- Produces: `drop_ungrounded_prop_sentences(text: str, facts: list[dict]) -> str`. Her fact `name`, `description` ve `aliases` taşır. Eşleşmeyen cümleler atılır, kalanlar bir boşlukla birleşir.

- [ ] **Step 1: Write the failing test**

`PlayerQuoteTests` içine ekle:

```python
 def test_spinning_cups_and_bread_leave_the_barman_line(self):
  facts = [{
   "name": "Ahşap masa",
   "description": "Kenarında sıradan bir kil bardak duran sağlam bir masa.",
   "aliases": ["masa", "ahşap masa", "bardak", "kil bardak"],
  }]
  spoken = (
   "Günün gidişi, tezgâhın üzerinde dönen bardaklar kadar kaotik ama tatlı. "
   "Mutfaktan gelen o taze ekmek kokusu işte bu."
  )
  cleaned = npc_speech_boundary.drop_ungrounded_prop_sentences(spoken, facts)
  self.assertNotIn("bardak", cleaned.casefold())
  self.assertNotIn("ekmek", cleaned.casefold())
  kept = npc_speech_boundary.drop_ungrounded_prop_sentences(
   "Kenarında sıradan bir kil bardak duruyor.", facts
  )
  self.assertIn("bardak", kept.casefold())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest api.tests.test_bound_speech_label.PlayerQuoteTests.test_spinning_cups_and_bread_leave_the_barman_line -v`

Expected: FAIL with `AttributeError: module 'npc_speech_boundary' has no attribute 'drop_ungrounded_prop_sentences'`

- [ ] **Step 3: Write minimal implementation**

`npc_speech_boundary.py` içine, `strip_player_echo` tanımından sonra:

```python
_UNGROUNDED_NOUN = re.compile(r"(?<![\wçğıöşüÇĞİÖŞÜ])([\wçğıöşüÇĞİÖŞÜ]{5,})")


def drop_ungrounded_prop_sentences(text, facts):
    """Drop a spoken sentence that names a prop the scene cannot support.

    A registered prop must bring one content word from its own description.
    A sentence that names no registered prop still drops when it contains a
    concrete noun absent from every fact. Ordinary short words stay.
    """
    if not isinstance(text, str) or not text.strip():
        return text
    records = []
    packet = []
    for fact in facts or []:
        if not isinstance(fact, dict):
            continue
        labels = [fact.get("name") or "", *(fact.get("aliases") or [])]
        stems = [fold(label) for label in labels if isinstance(label, str) and label.strip()]
        description = fold(fact.get("description") or "")
        content = [
            word for word in description.split()
            if len(word) >= 5 and word not in stems
        ]
        records.append((stems, content))
        packet.extend(stems)
        packet.extend(description.split())
    packet_text = " ".join(packet)
    kept = []
    for sentence in re.split(r"(?<=[.!?])\s+", text.strip()):
        folded = fold(sentence)
        grounded = False
        names_prop = False
        for stems, content in records:
            if not any(stem and stem in folded for stem in stems):
                continue
            names_prop = True
            if any(word and word in folded for word in content):
                grounded = True
                break
        if names_prop and not grounded:
            continue
        foreign = False
        for match in _UNGROUNDED_NOUN.finditer(sentence):
            stem = fold(match.group(1))
            if len(stem) < 5 or stem in packet_text:
                continue
            if stem.endswith(("iyor", "uyor", "acak", "ecek")):
                continue
            foreign = True
            break
        if foreign and not names_prop:
            continue
        kept.append(sentence)
    return " ".join(kept).strip()
```

`game.py` içinde `strip_player_echo` çağrısının hemen altında, sahne gerçeklerini ver:

```python
                    cleaned_spoken = npc_speech_boundary.drop_ungrounded_prop_sentences(
                        cleaned_spoken,
                        [
                            {
                                "name": feature.get("name"),
                                "description": feature.get("description"),
                                "aliases": feature.get("aliases") or [],
                            }
                            for feature in living_world.visible_features(world_state)
                            if isinstance(feature, dict)
                        ],
                    )
```

`living_world` bu fonksiyonda zaten içe aktarılmış olmalıdır. Değilse fonksiyonun mevcut importlarının yanına `import living_world` ekle. Başka bir çağrı ekleme.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest api.tests.test_bound_speech_label.PlayerQuoteTests api.tests.test_identity_entity_acceptance.IdentityBoundaryTests -v`

Expected: PASS. Eski gülüş ve kimlik testleri de geçer.

- [ ] **Step 5: Commit**

Kullanıcı bu planda commit istemedi. Diff'i bırak ve dur.

---

### Task 2: Adı geçmeyen başarılı inceleme şehir bakışı olmaz

**Files:**
- Modify: `ai-dnd/game.py` (`_inspection_findings`, `return None` satırından hemen önce)
- Test: `ai-dnd/api/tests/test_identity_entity_acceptance.py` (`IdentityBoundaryTests`)

**Interfaces:**
- Consumes: mevcut `_inspection_findings(player_input, outcome)` ve `_normalize_turkish_typos`
- Produces: eşleşen özellik yokken ve metin `incel` veya `arastir` içerirken `{"target_kind": "feature", "target_id": None, "target_name": None, "found": False, "text": "Bu bakışla adlandırdığın ayrıntı seçilmiyor."}`

- [ ] **Step 1: Write the failing test**

`IdentityBoundaryTests` içine ekle. Oturum `game.create_session(seed=2108)` ile zaten vardır. Şehirde "Tezgâhın altı" diye bir özellik ekleme.

```python
    def test_successful_search_of_an_absent_counter_is_a_miss(self):
        findings = self.session._inspection_findings(
            "Tezgâhın altını sistemli inceliyorum.", "success"
        )
        self.assertIsNotNone(findings)
        self.assertFalse(findings["found"])
        self.assertIn("seçilmiyor", findings["text"])
        self.assertNotIn("yük arabası", findings["text"])
        self.assertNotIn("İncelemen başarılı", findings["text"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest api.tests.test_identity_entity_acceptance.IdentityBoundaryTests.test_successful_search_of_an_absent_counter_is_a_miss -v`

Expected: FAIL because `findings` is `None`.

- [ ] **Step 3: Write minimal implementation**

`_inspection_findings` içinde iz kolundan sonra, son `return None` öncesine:

```python
    if re.search(r"\b(?:incel|arastir)\w*", text):
        return {
            "target_kind": "feature",
            "target_id": None,
            "target_name": None,
            "found": False,
            "text": "Bu bakışla adlandırdığın ayrıntı seçilmiyor.",
        }
```

`text` bu fonksiyonda zaten tırnak dışı ve yazım düzeltmesi görmüş Türkçe metindir. Kapı ve iz kolları daha yukarıda döndüğü için değişmez. "Çevreme bakıyorum" `incel`/`arastir` içermez; bu kola girmez.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest api.tests.test_identity_entity_acceptance.IdentityBoundaryTests api.tests.test_bound_speech_label.PlayerQuoteTests -v`

Expected: PASS. `test_named_table_beats_the_shorter_masa_alias` hâlâ "bardak"sız miss döndürür, çünkü masa alias'ı daha önce eşleşir.

- [ ] **Step 5: Commit**

Kullanıcı bu planda commit istemedi. Diff'i bırak ve dur.

---

### Task 3: Küçük olay ve bileşik engel yeni mekanik değildir

**Files:**
- Test: `ai-dnd/api/tests/test_scene_compound_contract.py`
- Test: `ai-dnd/api/tests/test_scene_small_events_contract.py`
- Modify: `C:\Users\Kadir\Desktop\AI_DND_ARASTIRMA_MERKEZI_20261025\01_GUNCEL\scene-truth-20261025\FINAL_ACCEPTANCE.md` yalnız bu iki satırın sonucu için

**Interfaces:**
- Consumes: mevcut testler. Yeni fonksiyon yok.
- Produces: kabul notunda bu iki maddenin test kimliği. İkisi de kırmızıysa yeni özellik yazma; kırmızı assertion'ın sahibi modülde dur.

- [ ] **Step 1: Run the existing contracts**

Run: `python -m unittest api.tests.test_scene_compound_contract api.tests.test_scene_small_events_contract -v`

Expected: PASS. Kilitli bileşik `giremiyorsun` der, oturma yazmaz, durum `partial` kalır. Küçük olay testleri iz veya yüzey eşyasını bir kez değiştirir ve nedeni oyuncu paketine yazmaz.

- [ ] **Step 2: Record only what the run showed**

PASS ise `FINAL_ACCEPTANCE.md` açık listesinden "Küçük olay ve bileşik ilk engel" satırını kaldır ve kapanan listeye test dosyalarının adını yaz. FAIL ise o dosyadaki kırmızı assertion'ı Task 1-2 biçiminde ayrı bir turda düzelt; bu planda ikinci bir olay türü ekleme.

- [ ] **Step 3: Commit**

Kullanıcı bu planda commit istemedi. Diff'i bırak ve dur.

---

## Bu planda yapılmayanlar

- `run_tests.py` POSIX kontrolü kalkmaz. 33 kapı ancak yerli bir Linux kopyasında koşar. `/mnt/c` üzerinde değil.
- H01–H05 olmadan canlı olay kapanmaz.
- `player_line` istemi, `free_v1` ve v0.1 sahne sınırları yazılmaz.
- Canlı rerun6, Task 1 ve Task 2 birim testleri geçtikten sonra ayrıca istenir. Birim test geçti diye rerun5 cümlesi kendiliğinden değişmiş sayılmaz.
