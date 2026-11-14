// A1 Oturum 1 (book UI theme set): the three book themes, the drawing folder, the book shell and the base controls,
// rendered from the real modules (vite ssrLoadModule + renderToStaticMarkup, the pattern of tests/dilim0-ui.test.mjs).
// Keyboard movement comes from Radix (roving focus); here the roles and names it needs are pinned.
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import path from 'node:path';
import { after, before, test } from 'node:test';

process.env.PORT ||= '4192';
process.env.BASE_PATH ||= '/';
delete process.env.REPL_ID;

const root = path.join(process.cwd(), 'src');
const read = (rel) => readFileSync(path.join(root, rel), 'utf8');
const css = read('index.css');

let vite, React, render, tema, kitap, kontrol, yazma, ayar;
before(async () => {
  const { createServer } = await import('vite');
  vite = await createServer({ configFile: path.join(process.cwd(), 'vite.config.ts'),
    server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' });
  tema = await vite.ssrLoadModule('/src/lib/kitap-tema.ts');
  kitap = await vite.ssrLoadModule('/src/components/kitap/kitap-kabugu.tsx');
  kontrol = await vite.ssrLoadModule('/src/components/kitap/kontroller.tsx');
  yazma = await vite.ssrLoadModule('/src/components/kitap/yazma-alani.tsx');
  ayar = await vite.ssrLoadModule('/src/components/kitap/arayuz-ayarlari.tsx');
  React = await import('react');
  const { renderToStaticMarkup } = await import('react-dom/server');
  render = (type, props, ...children) => renderToStaticMarkup(React.createElement(type, props, ...children));
});
after(async () => { await vite?.close(); });

/** The rule block of one selector, comments removed. */
function block(selector) {
  const bare = css.replace(/\/\*[\s\S]*?\*\//g, '');
  const at = bare.indexOf(`${selector} {`);
  assert.notEqual(at, -1, `${selector} is missing from src/index.css`);
  return bare.slice(at, bare.indexOf('}', at));
}
const token = (body, name) => new RegExp(`${name}:\\s*([^;]+);`).exec(body)?.[1]?.trim();

// Decision document, section 5 (KITAP_YONU_TASLAK_KARARLARI_20261113.md), and kaynak/Main.dc.html for the rest.
const PALETTE = {
  gunduz: { '--sayfa': '#DCD8C8', '--murekkep': '#26211A', '--soluk': '#4A4439', '--hakem': '#1D5145', '--mum': '#603F08', '--cizgi': '#B4AE9B', '--bez': '#2D4A44', '--mum-cizgi': '#8C846E' },
  gece: { '--sayfa': '#D4C394', '--murekkep': '#1F1810', '--soluk': '#30281B', '--hakem': '#0F362E', '--mum': '#4D3003', '--cizgi': '#8E7F56', '--bez': '#1F2C29', '--mum-cizgi': '#75683F' },
  karanlik: { '--sayfa': '#11161B', '--murekkep': '#E6DFCE', '--soluk': '#A9A595', '--hakem': '#7DB5A8', '--mum': '#D9A441', '--cizgi': '#2E3840', '--bez': '#1B2C2A', '--mum-cizgi': 'transparent' },
};

test('three book themes carry the decision document values under [data-kitap-tema], the seal red is shared', () => {
  for (const [name, values] of Object.entries(PALETTE)) {
    const body = block(`[data-kitap-tema="${name}"]`);
    for (const [variable, value] of Object.entries(values)) {
      assert.equal(token(body, variable)?.toUpperCase(), value.toUpperCase(), `${name} ${variable}`);
    }
  }
  assert.equal(token(block('[data-kitap-tema]'), '--muhur')?.toUpperCase(), '#A8332E');
});

test('old screens are untouched: the book tokens never sit on :root and the --unw night base keeps its values', () => {
  const bare = css.replace(/\/\*[\s\S]*?\*\//g, '');
  for (const name of ['--sayfa', '--murekkep', '--soluk', '--mum', '--mum-cizgi', '--hakem']) {
    const rules = [...bare.matchAll(/([^{}]+)\{([^{}]*)\}/g)].filter(([, , body]) => new RegExp(`(^|[;\\s])${name}:`).test(body));
    assert.ok(rules.length > 0, `${name} is defined`);
    for (const [, selector] of rules) assert.match(selector.trim(), /^\[data-kitap-/, `${name} leaks outside the book scope: ${selector.trim()}`);
  }
  assert.equal(token(block(':root,\n:root[data-unw-theme="night"]'), '--unw-page'), '#11161B');
});

test('type: Literata body 19px (21px large), hand face per choice, paper grain tile per theme, effects off drops the grain', () => {
  const base = block('[data-kitap-tema]');
  assert.match(token(base, '--kitap-yazi') ?? '', /^'Literata'/);
  // 19px and 21px up to 1440px wide; --buyume (finding 5) is 0px there and grows the type only on wider screens.
  assert.equal(token(base, '--govde'), 'calc(19px + var(--buyume))');
  assert.equal(token(block('[data-kitap-boy="buyuk"]'), '--govde'), 'calc(21px + var(--buyume))');
  assert.match(token(base, '--buyume') ?? '', /^clamp\(0px, calc\(\(100vw - 1440px\) \* [0-9.]+\), [0-9]+px\)$/);
  assert.match(token(block('[data-kitap-el="b"]'), '--el-aile') ?? '', /^'Kalam'/);
  assert.match(token(block('[data-kitap-el="a"]'), '--el-aile') ?? '', /^'Charm'/);
  assert.match(token(block('[data-kitap-el="c"]'), '--el-aile') ?? '', /^'Bad Script'/);
  assert.equal(token(block('[data-kitap-el="b"]'), '--elb'), '20px');
  assert.equal(token(block('[data-kitap-el="a"]'), '--elb'), '23px');
  assert.equal(token(block('[data-kitap-el="c"]'), '--elb'), '21px');
  assert.match(token(block('[data-kitap-tema="gunduz"]'), '--tane') ?? '', /cizimler\/kagit-tanesi-koyu\.png/);
  assert.match(token(block('[data-kitap-tema="gece"]'), '--tane') ?? '', /cizimler\/kagit-tanesi-koyu\.png/);
  assert.match(token(block('[data-kitap-tema="karanlik"]'), '--tane') ?? '', /cizimler\/kagit-tanesi-acik\.png/);
  assert.equal(token(block('[data-kitap-tema][data-kitap-efekt="kapali"]'), '--tane'), 'none');
});

test('appearance choice: four options, story clock by default, the clock only decides when it is chosen', () => {
  assert.deepEqual(tema.GORUNUM_SECENEKLERI.map((s) => s.etiket), ['Hikâyedeki saati izle', 'Gündüz', 'Gece', 'Karanlık']);
  assert.equal(tema.VARSAYILAN_GORUNUM, 'saat');
  assert.equal(tema.kitapTemasi('saat', 'gunduz'), 'gunduz');
  assert.equal(tema.kitapTemasi('saat', 'gece'), 'gece');
  for (const secim of ['gunduz', 'gece', 'karanlik']) {
    assert.equal(tema.kitapTemasi(secim, 'gunduz'), secim);
    assert.equal(tema.kitapTemasi(secim, 'gece'), secim);
  }
  assert.deepEqual(tema.EL_YAZISI_SECENEKLERI.map((s) => s.deger), ['a', 'b', 'c']);
  assert.equal(tema.VARSAYILAN_EL, 'b');
});

test('book shell: cloth, two pages, ribbon drawing, the narrow screen keeps only the chosen page', () => {
  const html = render(kitap.KitapKabugu, { tema: 'gece', sol: 'SOL', sag: 'SAG', darEkranSayfasi: 'sag' });
  assert.match(html, /data-kitap-tema="gece"/);
  assert.match(html, /class="kitap-cilt"/);
  assert.match(html, /kitap-sayfa kitap-sayfa-sol kitap-darda-gizli/);
  assert.match(html, /kitap-sayfa kitap-sayfa-sag"/);
  assert.match(html, /role="img" aria-label="Kurdele ayraç"/);
});

test('bookmark tabs: a Radix tab list with a name, the open tab is announced as selected', () => {
  const html = render(kitap.Ayraclar, { deger: 'karakter', degisince() {}, ayraclar: [
    { deger: 'hikaye', etiket: 'Hikâye' }, { deger: 'karakter', etiket: 'Karakter' }, { deger: 'canta', etiket: 'Çanta' }] });
  assert.match(html, /role="tablist"[^>]*aria-label="Defter ayraçları"|aria-label="Defter ayraçları"[^>]*role="tablist"/);
  assert.match(html, /aria-selected="true"[^>]*>Karakter</);
  assert.equal((html.match(/role="tab"/g) ?? []).length, 3);
});

test('choice groups (appearance, layout, hand, size) are named radio groups with the chosen one checked', () => {
  const html = render(ayar.ArayuzAyarlari, { deger: { gorunum: 'saat', duzen: 'iki-sayfa', el: 'b', boy: 'normal' }, degisince() {} });
  assert.match(html, />Arayüz</);
  for (const name of ['Görünüm', 'Sayfa düzeni', 'El yazısı', 'Yazı boyu']) assert.match(html, new RegExp(`aria-label="${name}"`));
  assert.equal((html.match(/role="radio"/g) ?? []).length, 4 + 2 + 3 + 2);
  assert.match(html, /aria-checked="true"[^>]*>Hikâyedeki saati izle</);
  assert.doesNotMatch(html, /Cihaz ayarını izle/);
});

test('base controls: names, disabled, error text tied to the field, the seal stamp marks the chosen card', () => {
  const sayac = render(kontrol.Sayac, { etiket: 'Şifa iksiri', deger: 0, min: 0, max: 3, degisince() {} });
  assert.match(sayac, /aria-label="Şifa iksiri azalt"[^>]*disabled|disabled[^>]*aria-label="Şifa iksiri azalt"/);
  assert.match(sayac, /aria-label="Şifa iksiri artır"/);
  assert.match(sayac, /aria-live="polite"/);

  const kutu = render(kontrol.SayiKutusu, { etiket: 'Kuvvet', deger: '21', hata: '3 ile 20 arası olmalı.', degisince() {} });
  assert.match(kutu, /aria-invalid="true"/);
  const describedBy = /aria-describedby="([^"]+)"/.exec(kutu)?.[1];
  assert.ok(describedBy && kutu.includes(`id="${describedBy}"`), 'error message is tied to the field');

  const kart = render(kontrol.SecimKartlari, { etiket: 'Tür', deger: 'ejderhasoyu', degisince() {}, secenekler: [
    { deger: 'insan', baslik: 'İnsan', aciklama: 'Becerikli.' }, { deger: 'ejderhasoyu', baslik: 'Ejderhasoyu', aciklama: 'Ejderha kanı.' }] });
  assert.match(kart, /role="radiogroup"/);
  assert.equal((kart.match(/aria-label="Seçildi"/g) ?? []).length, 1);

  assert.match(render(kontrol.OnayKutusu, { etiket: 'Zarları göster', isaretli: true, degisince() {} }), /role="checkbox"[^>]*aria-checked="true"|aria-checked="true"[^>]*role="checkbox"/);
  assert.match(render(kontrol.Anahtar, { etiket: 'Müzik', acik: false, degisince() {} }), /role="switch"/);
  assert.match(render(kontrol.AcilirListe, { etiket: 'Zar takımı', deger: 'kemik', degisince() {}, secenekler: [{ deger: 'kemik', etiket: 'Kemik' }] }), /role="combobox"/);
  assert.match(render(kontrol.KitapDugme, { tur: 'ana', disabled: true }, 'Gönder'), /<button[^>]*disabled/);
  assert.match(render(kontrol.BosSatirlar, { satir: 3, etiket: 'Henüz yazılmadı' }), /aria-label="Henüz yazılmadı"/);
  assert.match(render(kontrol.Yukleniyor, { etiket: 'Sayfa yazılıyor' }), /role="status"/);
  assert.match(render(kontrol.BolumBasligi, { duzey: 2 }, 'Açık işler'), /<h2[^>]*>Açık işler<\/h2>/);
});

test('writing line: pen nib, the hand face, three modes, the microphone sits left of Gönder and hides without support', () => {
  const html = render(yazma.YazmaAlani, { kip: 'yap', kipDegisince() {}, metin: '', metinDegisince() {}, gonder() {}, mikrofonDestegi: true });
  assert.match(html, /aria-label="Ne yapıyorsun\?"/);
  assert.match(html, /aria-label="Söyleyiş biçimi"/);
  for (const kip of ['yap', 'söyle', 'anlatıcıya sor']) assert.match(html, new RegExp(`role="radio"[^>]*>${kip}<`));
  assert.ok(html.indexOf('Sesle yaz') < html.indexOf('>Gönder<'), 'microphone before Gönder');
  const yok = render(yazma.YazmaAlani, { kip: 'yap', kipDegisince() {}, metin: '', metinDegisince() {}, gonder() {}, mikrofonDestegi: false });
  assert.doesNotMatch(yok, /Sesle yaz/);
});

/** Every file of the book set except the drawing folder (Kadir, 13 Nov 2026: drawing colours stay as drawn). */
function bookFiles() {
  const out = [];
  const walk = (dir) => {
    for (const name of readdirSync(dir)) {
      const full = path.join(dir, name);
      if (statSync(full).isDirectory()) { if (name !== 'cizimler') walk(full); } else out.push(full);
    }
  };
  walk(path.join(root, 'components', 'kitap'));
  out.push(path.join(root, 'lib', 'kitap-tema.ts'), path.join(root, 'pages', 'kitap-galerisi.tsx'));
  return out;
}

test('no hand-written colour, raw select, checkbox, alert or full-page filter outside src/index.css and the drawing folder', () => {
  for (const file of bookFiles()) {
    const text = readFileSync(file, 'utf8');
    const rel = path.relative(root, file);
    assert.doesNotMatch(text, /#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(/, `${rel} has a colour code`);
    assert.doesNotMatch(text, /<select\b|type=["']checkbox["']|\balert\(/, `${rel} uses a raw browser control`);
    assert.doesNotMatch(text, /feTurbulence|(^|[;{\s])filter\s*:/m, `${rel} applies a filter`);
  }
});

test('drawing folder: the taken drawings and the two grain tiles exist, the pen nib takes --mum, a source note names each', () => {
  const dir = path.join(root, 'components', 'kitap', 'cizimler');
  for (const name of ['kalem-ucu.tsx', 'kurdele.tsx', 'secim-damgasi.tsx', 'kagit-tanesi-acik.png', 'kagit-tanesi-koyu.png', 'KAYNAK.md']) {
    assert.ok(statSync(path.join(dir, name)).isFile(), `${name} is missing`);
  }
  assert.match(readFileSync(path.join(dir, 'kalem-ucu.tsx'), 'utf8'), /var\(--mum\)/);
  const note = readFileSync(path.join(dir, 'KAYNAK.md'), 'utf8');
  for (const name of ['kalem-ucu.tsx', 'kurdele.tsx', 'secim-damgasi.tsx', 'kagit-tanesi-acik.png', 'kagit-tanesi-koyu.png']) assert.match(note, new RegExp(name.replace('.', '\\.')));
});

test('the gallery route exists only in development and is loaded lazily', () => {
  const shell = read('app-shell.tsx');
  assert.match(shell, /import\.meta\.env\.DEV/);
  assert.match(shell, /lazy\(\(\) => import\(["']\.\/pages\/kitap-galerisi["']\)\)/);
  assert.match(shell, /path="\/galeri"/);
});

test('the A1 book faces never swap in late: font-display optional, so story text cannot jump when a font arrives late', () => {
  const fontCss = read('fonts/fonts.css');
  const faces = [...fontCss.matchAll(/@font-face\s*\{([^}]*)\}/g)].map(([, body]) => ({
    family: /font-family:\s*'([^']+)'/.exec(body)?.[1], display: /font-display:\s*(\w+)/.exec(body)?.[1] }));
  const book = faces.filter((f) => ['Literata', 'Kalam', 'Charm', 'Bad Script'].includes(f.family));
  assert.equal(book.length, 12);
  for (const f of book) assert.equal(f.display, 'optional', `${f.family} must not swap`);
});

// Review fixes (separate-eye review of the A1 gallery, findings 1-8; Kadir: "1-8'i düzelt").
const kitapCss = () => read('components/kitap/kitap.css');
const kural = (text, selector) => {
  const bare = text.replace(/\/\*[\s\S]*?\*\//g, '');
  const at = bare.indexOf(`${selector} {`);
  assert.notEqual(at, -1, `${selector} is missing`);
  return bare.slice(at, bare.indexOf('}', at));
};

test('finding 1: the default hand and the body face are preloaded, and no hand falls back to the system cursive face', () => {
  const html = readFileSync(path.join(process.cwd(), 'index.html'), 'utf8');
  // latin and latin-ext: Turkish ş, ğ, İ live in latin-ext, so without it those letters fell back to Georgia (measured).
  for (const file of ['kalam/YA9dr0Wd4kDdMthROCc.woff2', 'kalam/YA9dr0Wd4kDdMthfOCfzsw.woff2',
    'literata/or3PQ6P12-iJxAIgLa78DkTtAoDhk0oVpaK3YLanFLHpPf2TbLi4J_HWTA.woff2', 'literata/or3PQ6P12-iJxAIgLa78DkTtAoDhk0oVpaK3YLanFLHpPf2TbLi4J__WTFCW.woff2',
    'literata/or3NQ6P12-iJxAIgLYT1PLs1a-t7PU0AbeE9KPxYzNiCp1OUedn8VrLmTkiS.woff2', 'literata/or3NQ6P12-iJxAIgLYT1PLs1a-t7PU0AbeE9KPxYzNiCp1OUedn8VrLmQEiSh8g.woff2']) {
    assert.match(html, new RegExp(`<link rel="preload" href="/src/fonts/${file.replace(/[.]/g, '\.')}" as="font" type="font/woff2" crossorigin`), `${file} is not preloaded`);
  }
  for (const selector of ['[data-kitap-tema]', '[data-kitap-el="a"]', '[data-kitap-el="b"]', '[data-kitap-el="c"]']) {
    const value = token(block(selector), '--el-aile') ?? '';
    assert.doesNotMatch(value, /cursive|Comic Sans/, `${selector} falls back to a system cursive face`);
    assert.match(value, /'Literata'/, `${selector} falls back to Literata`);
  }
});

test('finding 2: the writing field grows with its text, and on the phone Gönder is a 44px return key that keeps its name', () => {
  assert.doesNotMatch(kural(kitapCss(), '.kitap-yaz-girdi'), /(^|[;\s])height:\s*50px/);
  const html = render(yazma.YazmaAlani, { kip: 'yap', kipDegisince() {}, metin: '', metinDegisince() {}, gonder() {}, mikrofonDestegi: true });
  assert.match(html, /class="[^"]*kitap-gonder-simge[^"]*"/);
  assert.match(html, /<span class="kitap-gonder-metin">Gönder<\/span>/);
});

test('findings 3 and 4: the gallery story keeps one writing field and the hand-off rule lives in code', () => {
  assert.equal(tema.hikayeTekAkista('hikaye', false), false);
  assert.equal(tema.hikayeTekAkista('karakter', false), true);
  assert.equal(tema.hikayeTekAkista('hikaye', true), true);
  assert.equal(tema.hikayeTekAkista('canta', true), true);
});

test('finding 5: on wide screens the type grows with the book and the text column stays near 45 letters', () => {
  const base = block('[data-kitap-tema]');
  assert.match(token(base, '--buyume') ?? '', /^clamp\(0px,/);
  assert.equal(token(base, '--govde'), 'calc(19px + var(--buyume))');
  assert.equal(token(block('[data-kitap-boy="buyuk"]'), '--govde'), 'calc(21px + var(--buyume))');
  assert.match(kural(kitapCss(), '.kitap-satir'), /grid-template-columns:\s*minmax\(0,\s*var\(--sutun-metin\)\)/);
  assert.equal(token(base, '--sutun-metin'), '22em');
});

test('finding 6: the ribbon hangs below the book', () => {
  // Round 3: the tail hangs 4px longer (40 to 44), and the drawing's own SARKMA matches the box (2px above + 42).
  assert.match(kural(kitapCss(), '.kitap-kurdele'), /height:\s*calc\(100% \+ 44px\)/);
  assert.match(kurdeleKod(), /const SARKMA = 42;/);
});

test('findings 7 and 8: a disabled checked box loses its fill; an error is a double rule with a referee note, a disabled field keeps the dashed rule', () => {
  const css = kitapCss();
  assert.match(kural(css, ".kitap-onay-kutu:disabled[data-state='checked']"), /background:\s*none/);
  assert.match(kural(css, ".kitap-sayi-girdi[aria-invalid='true']"), /border-bottom:\s*3px double/);
  assert.match(kural(css, '.kitap-alan-hata'), /color:\s*var\(--hakem\)/);
  assert.match(kural(css, '.kitap-sayi-girdi:disabled'), /dashed/);
});

test('finding 9: setting labels carry no explanation text in brackets (T12)', () => {
  assert.doesNotMatch(read('pages/kitap-galerisi.tsx'), /etiket="[^"]*\(/);
});

// Realism pass (Kadir, 14 Nov 2026, after approving f22bc5ba): cloth weave, page block, page bulge light, ink and
// depth come from tokens; effects off turns every added layer flat, and no layer is a filter.
test('realism layers are tokens, each one switched off with effects off', () => {
  const base = block('[data-kitap-tema]');
  for (const name of ['--cilt-dokuma', '--kabarma', '--murekkep-golge', '--golge-temas']) assert.ok(token(base, name), `${name} is missing`);
  const off = block('[data-kitap-tema][data-kitap-efekt="kapali"]');
  for (const name of ['--tane', '--cilt-dokuma', '--murekkep-golge']) assert.equal(token(off, name), 'none', `${name} stays on with effects off`);
  assert.equal(token(off, '--kabarma'), 'transparent');
  const css = kitapCss();
  assert.match(kural(css, '.kitap-cilt'), /var\(--cilt-dokuma\)/);
  assert.match(kural(css, '.kitap-p'), /text-shadow:\s*var\(--murekkep-golge\)/);
  assert.doesNotMatch(css, /(^|[;{\s])(filter|backdrop-filter)\s*:/m);
});

// Kadir, 14 Nov 2026: a far more realistic ribbon (a new design is allowed) and the reading lamp of the draft with
// realistic light. Lamp rules: lit at night only (T7: not by day), dark theme only when asked (G10 is Kadir's call).
test('ribbon: satin body with a woven rib, a headband at the spine top and a V-cut tail hanging below', () => {
  const html = render(kitap.KitapKabugu, { tema: 'gece', sol: 'SOL', sag: 'SAG' });
  assert.match(html, /role="img" aria-label="Kurdele ayraç"/);
  assert.match(html, /<pattern id="kurdele-dokuma-[^"]+"/);
  assert.match(html, /class="kitap-kurdele-uc"/);
  assert.match(html, /class="kitap-kapitalbant"/);
});

test('reading lamp: drawn at night, never by day, in the dark theme only when asked; its light lives in tokens', () => {
  const gece = render(kitap.KitapKabugu, { tema: 'gece', sol: 'SOL', sag: 'SAG' });
  assert.match(gece, /class="kitap-lamba"/);
  assert.match(gece, /aria-label="Okuma ışığı yanıyor"/);
  assert.match(gece, /class="kitap-lamba-hale"/);
  assert.doesNotMatch(render(kitap.KitapKabugu, { tema: 'gunduz', sol: 'SOL', sag: 'SAG' }), /class="kitap-lamba|Okuma ışığı/);
  assert.doesNotMatch(render(kitap.KitapKabugu, { tema: 'karanlik', sol: 'SOL', sag: 'SAG' }), /class="kitap-lamba|Okuma ışığı/);
  assert.match(render(kitap.KitapKabugu, { tema: 'karanlik', sol: 'SOL', sag: 'SAG', lambaKaranlikta: true }), /class="kitap-lamba"/);
  for (const name of ['--isik-cilt', '--lamba-hale', '--lamba-havuz']) assert.ok(token(block('[data-kitap-tema="gece"]'), name), `${name} is missing at night`);
  // Review 11 (Kadir, 14 Nov 2026): an electric bulb gives a still light; no breathing animation at all.
  assert.doesNotMatch(kural(kitapCss(), '.kitap-lamba-hale'), /animation/);
  assert.doesNotMatch(kitapCss(), /kitap-lamba-nefes/);
  const dir = path.join(root, 'components', 'kitap', 'cizimler');
  assert.ok(statSync(path.join(dir, 'okuma-lambasi.tsx')).isFile());
  assert.match(readFileSync(path.join(dir, 'KAYNAK.md'), 'utf8'), /okuma-lambasi\.tsx/);
});

// Two independent reviews (Opus, Fable) after 8c5ac10d; Kadir: fix all 15, the nice-to-haves included.
const kurdeleKod = () => read('components/kitap/cizimler/kurdele.tsx');
const medya = (css, sorgu) => {
  const at = css.indexOf(`@media ${sorgu} {`);
  assert.notEqual(at, -1, `@media ${sorgu} is missing`);
  let derinlik = 0;
  for (let i = css.indexOf('{', at); i < css.length; i++) {
    if (css[i] === '{') derinlik++;
    if (css[i] === '}' && --derinlik === 0) return css.slice(at, i);
  }
  return css.slice(at);
};

test('review 1, 5, 6, 12: phone ribbon is a short straight tail, the body curves wider, the headband has no red, the rib is soft', () => {
  const dar = medya(kitapCss(), '(max-width: 767px)');
  assert.match(dar, /\.kitap-kurdele-govde\s*\{\s*display:\s*none/);
  const kod = kurdeleKod();
  assert.match(kod, /const GENLIK = (\d+(\.\d+)?)/);
  assert.ok(Number(/const GENLIK = (\d+(?:\.\d+)?)/.exec(kod)[1]) >= 7, 'the S-curve swings at least 7 units');
  const bant = kod.slice(kod.indexOf('kitap-kapitalbant'));
  assert.doesNotMatch(bant, /#8E2A24|#A8332E|#B4443B/i, 'the headband carries a red stripe');
  assert.match(kod, /opacity="\.0[0-9]"[^>]*\/>\s*<rect[^>]*opacity="\.0[0-9]"/, 'rib lines are soft (opacity below .1)');
  assert.doesNotMatch(kod, /<g transform="rotate\(7/, 'the tail falls clearly to the side');
});

test('review 2, 10: the lamp leaves room for the tabs and scales with the book', () => {
  const orta = medya(kitapCss(), '(min-width: 768px) and (max-width: 1179px)');
  assert.match(orta, /\.kitap-lamba\s*\{\s*display:\s*none/);
  const base = block('[data-kitap-tema]');
  assert.match(token(base, '--lamba-en') ?? '', /calc\(96px \+ var\(--buyume\)/);
  assert.match(token(base, '--kurdele-en') ?? '', /calc\(40px \+ var\(--buyume\)/);
  assert.match(kural(kitapCss(), '.kitap-lamba'), /width:\s*var\(--lamba-en\)/);
});

test('review 3, 13, 14: the light falls on the pages, the halo sits under the shade, the dark-theme lamp lights its page', () => {
  const gece = block('[data-kitap-tema="gece"]');
  assert.match(token(gece, '--isik-sol') ?? '', /^radial-gradient\(ellipse 60% 44% at 100% 0%, rgba\(255, 226, 168, 0\.4/);
  assert.match(token(gece, '--lamba-havuz') ?? '', /rgba\(255, 190, 105, 0\.1\)/);
  assert.match(kural(kitapCss(), '.kitap-lamba-hale'), /border-radius:\s*50%/);
  // Halo centre just below the bulb (round 3: the bulb moved down to 0.582 of the lamp width; the halo moved with it).
  assert.match(kural(kitapCss(), '.kitap-lamba-hale'), /top:\s*calc\(var\(--lamba-en\) \* 0\.725 - var\(--lamba-en\) \* 0\.95\)/);
  const karanlik = block('[data-kitap-tema="karanlik"][data-kitap-lamba="acik"]');
  assert.match(token(karanlik, '--isik-sol') ?? '', /rgba\(255, 214, 150, 0\.1[0-9]/);
});

test('review 7, 8: effects off flattens the lamp light and every added shadow; the cloth weave is irregular', () => {
  const off = block('[data-kitap-tema][data-kitap-efekt="kapali"]');
  for (const name of ['--lamba-havuz', '--isik-cilt', '--lamba-hale']) assert.equal(token(off, name), 'none', `${name} with effects off`);
  for (const name of ['--golge-temas', '--cilt-kenar-golge']) assert.equal(token(off, name), '0 0 0 transparent', `${name} with effects off`);
  assert.equal(token(off, '--sayfa-blok-golge'), 'transparent');
  const dokuma = token(block('[data-kitap-tema]'), '--cilt-dokuma') ?? '';
  assert.match(dokuma, /1px 3px/);
  assert.match(dokuma, /1px 4px/);
  assert.match(dokuma, /87deg/);
  assert.match(kural(kitapCss(), '.kitap-cilt::after'), /background-image:\s*var\(--tane\)/);
});

test('review 9: checkbox and switch rows and the number field are 44px touch targets', () => {
  const onay = render(kontrol.OnayKutusu, { etiket: 'Zarları göster', isaretli: true, degisince() {} });
  assert.match(onay, /^<label class="kitap-onay"[^>]*>.*role="checkbox".*<\/label>$/s);
  const anahtar = render(kontrol.Anahtar, { etiket: 'Müzik', acik: false, degisince() {} });
  assert.match(anahtar, /^<label class="kitap-onay"[^>]*>.*role="switch".*<\/label>$/s);
  assert.match(kural(kitapCss(), '.kitap-onay'), /min-height:\s*var\(--dokunma\)/);
  assert.match(kural(kitapCss(), '.kitap-sayi-girdi'), /height:\s*var\(--dokunma\)/);
});

test('review 15: in the gallery, a hand-picked look offers a way back to the story clock', () => {
  assert.match(read('pages/kitap-galerisi.tsx'), /Saate dön/);
});

test('narrow two-page books (768-1179px) put the margin note under its line, so the text column is not squeezed', () => {
  const orta = medya(kitapCss(), '(min-width: 768px) and (max-width: 1179px)');
  assert.match(orta, /\.kitap-satir\s*\{\s*grid-template-columns:\s*minmax\(0,\s*1fr\)/);
  assert.match(orta, /\.kitap-satir > \.kitap-kenar-metin\s*\{\s*padding-left:\s*26px/);
});

test('story lines never shrink in the scrolling page: a long story scrolls instead of hiding its first lines', () => {
  assert.match(kural(kitapCss(), '.kitap-akis > *'), /flex:\s*0 0 auto/);
});

// Kadir, 14 Nov 2026 (screenshot): the ribbon broke where it left the page; the lamp looked "made in Paint".
test('ribbon is one piece drawn at its measured height: it bends over the page edge and hangs without a joint', () => {
  const kod = kurdeleKod();
  assert.match(kod, /ResizeObserver/, 'the ribbon measures its own height');
  assert.match(kod, /className="kitap-kurdele-uc"/, 'the tail is part of the same drawing');
  assert.doesNotMatch(kod, /<svg className="kitap-kurdele-uc"/, 'the tail is no longer a separate drawing');
  assert.doesNotMatch(kod, /preserveAspectRatio="none"/, 'no stretching: the curve and the rib keep their shape');
  assert.match(kod, /className="kitap-kurdele-kisa"/, 'a short tail drawing for the phone');
  assert.match(kitapCss(), /\.kitap-kurdele-kisa\s*\{\s*display:\s*none/);
});

test('reading lamp drawing: shaded brass tube, coiled gooseneck, lit shade interior, bright bulb, a beam of light', () => {
  const kod = read('components/kitap/cizimler/okuma-lambasi.tsx');
  for (const parca of ['lamba-boru', 'lamba-kafa', 'lamba-ic', 'lamba-ampul', 'lamba-kiskac', 'lamba-vida']) {
    assert.ok(kod.includes('`' + parca + '-'), `${parca} gradient is missing`);
  }
  assert.match(kod, /strokeDasharray/, 'the gooseneck shows its coils');
  const html = render(kitap.KitapKabugu, { tema: 'gece', sol: 'SOL', sag: 'SAG' });
  assert.match(html, /class="kitap-lamba-huzme"/);
  assert.ok(token(block('[data-kitap-tema="gece"]'), '--lamba-huzme'), '--lamba-huzme is missing at night');
  assert.equal(token(block('[data-kitap-tema][data-kitap-efekt="kapali"]'), '--lamba-huzme'), 'none');
});

test('a scrolled page fades its top line out instead of cutting it (draft mask), using a token colour', () => {
  assert.match(kural(kitapCss(), '.kitap-akis'), /mask-image:\s*linear-gradient\(to bottom, transparent 0, transparent 3px, var\(--sayfa\) 20px\)/);
});

// Third review round (Opus, Fable) on 72a51bab; Kadir: "Hepsini düzelt".
const lambaKod = () => read('components/kitap/cizimler/okuma-lambasi.tsx');

test('round 3, finding 1: the lamp never reaches past the top of the window, at any width the book grows to', () => {
  // The lamp box: top = 66px - en * K; the drawing is 100 units wide, so one unit is en / 100.
  const ust = kural(kitapCss(), '.kitap-lamba');
  const K = Number(/top:\s*calc\(66px - var\(--lamba-en\) \* ([\d.]+)\)/.exec(ust)?.[1]);
  assert.ok(K > 0, 'lamp top formula not found');
  const en = /calc\((\d+)px \+ var\(--buyume\) \* ([\d.]+)\)/.exec(token(block('[data-kitap-tema]'), '--lamba-en') ?? '');
  assert.ok(en, '--lamba-en formula not found');
  const enBuyuk = Number(en[1]) + 4 * Number(en[2]); // --buyume tops out at 4px
  // The highest drawn point: the smallest y of any path coordinate, less half of the widest neck stroke.
  const kod = lambaKod();
  const boyun = /const boyun = '([^']+)'/.exec(kod)?.[1] ?? '';
  const yler = [...boyun.matchAll(/(-?[\d.]+)[ ,](-?[\d.]+)/g)].map((m) => Number(m[2]));
  const kalin = Math.max(...[...kod.matchAll(/d=\{boyun\}[^>]*strokeWidth="([\d.]+)"/g)].map((m) => Number(m[1])));
  const tepe = Math.min(...yler) - kalin / 2;
  const ekranda = 66 - K * enBuyuk + (tepe / 100) * enBuyuk;
  assert.ok(ekranda >= 4, `the lamp top is ${ekranda.toFixed(1)}px from the window top at the widest book (needs >= 4)`);
  // ...and the lamp is larger than before, so its detail reads (round 3, nice-to-have).
  assert.ok(Number(en[1]) >= 96, 'the lamp is at least 96px wide at 1440');
});

test('round 3, finding 2: on the phone the ribbon tail comes out from under the page and hangs over the cover edge', () => {
  const dar = medya(kitapCss(), '(max-width: 767px)');
  assert.match(dar, /\.kitap-kurdele\s*\{[^}]*z-index:\s*-1/, 'the tail starts under the page');
  assert.doesNotMatch(kurdeleKod(), /rotate\(10 14 0\)/, 'no tilted loose stub');
});

test('round 3, finding 3: the beam has no hard edges (no polygon clip; a soft conic mask)', () => {
  const huzme = kural(kitapCss(), '.kitap-lamba-huzme');
  assert.doesNotMatch(huzme, /clip-path/);
  assert.match(huzme, /mask-image:\s*conic-gradient\(/);
});

test('round 3, finding 4: at 768-1179px the writing line keeps one row: Gönder is the return key, the modes do not wrap', () => {
  const orta = medya(kitapCss(), '(min-width: 768px) and (max-width: 1179px)');
  assert.match(orta, /\.kitap-gonder-simge\s*\{\s*display:\s*block/);
  assert.match(orta, /\.kitap-gonder-metin\s*\{[^}]*clip-path:\s*inset\(50%\)/);
  assert.match(orta, /\.kitap-kipler[^{]*\{[^}]*white-space:\s*nowrap/);
});

test('round 3, finding 5: the heading side note is not a <p> (it may hold a badge, which is a div)', async () => {
  const html = render(kontrol.BolumBasligi, { yan: "not" }, "Başlık");
  assert.doesNotMatch(html, /<p class="kitap-bolum-yan"/);
  assert.match(html, /<div class="kitap-bolum-yan"/);
});

test('round 3, finding 6: a focused tab also gets a ring in the desk colour around it', () => {
  assert.match(kural(kitapCss(), '.kitap-ayrac:focus-visible'), /box-shadow:\s*0 0 0 2px var\(--masa-yazi\)/);
});

test('round 3, findings 7 and 12: the satin follows the ribbon (bands along it), and the tail has a lit rim', () => {
  const kod = kurdeleKod();
  assert.match(kod, /className="kitap-kurdele-serit"/, 'satin bands along the ribbon');
  assert.doesNotMatch(kod, /<path d=\{govde\} fill=\{`url\(#\$\{saten\}\)`\}/, 'no box-wide gradient on the body');
  assert.match(kod, /className="kitap-kurdele-uc-kenar"/, 'the V tail has a lit rim against the dark desk');
});

test('round 3, finding 8: the lamp clamp has jaws, the neck has a brown outline, not a black one', () => {
  const kod = lambaKod();
  assert.match(kod, /id=\{cene\}/, 'clamp jaws');
  assert.doesNotMatch(kod, /stroke="#24180A"/, 'no near-black cartoon outline on the neck');
});

test('round 3, finding 9: the "Yeni iş" badge has no gold frame', () => {
  const yeni = kural(kitapCss(), '.kitap-rozet-yeni');
  assert.doesNotMatch(yeni, /border-color:\s*var\(--mum\)/);
  assert.match(yeni, /border:\s*none/);
});

test('round 3, finding 10: the headband is a thin band, not a pill', () => {
  assert.match(kurdeleKod(), /<svg className="kitap-kapitalbant" width="26" height="5"/);
});

test('round 3, finding 11: without the lamp (under 1180px) the night pages keep no lamp hot spot', () => {
  const dar = medya(css, '(max-width: 1179px)');
  assert.match(dar, /\[data-kitap-tema="gece"\]\s*\{[^}]*--isik-cilt:\s*none/);
  assert.match(dar, /\[data-kitap-tema="gece"\]\s*\{[^}]*--lamba-havuz:\s*none/);
  assert.doesNotMatch(dar, /0\.4\)/, 'the 0.4 hot spot is gone');
  assert.match(dar, /\[data-kitap-tema="karanlik"\]\[data-kitap-lamba="acik"\]\s*\{[^}]*--isik-sol:\s*none/);
});

test('round 3, findings 13 and 14: the gallery note is current; a field error carries a mark, not only colour', () => {
  assert.doesNotMatch(read('pages/kitap-galerisi.tsx'), /lamba Oturum 2'de/);
  const html = render(kontrol.SayiKutusu, { etiket: 'Zekâ', deger: '21', hata: 'Olmaz.', degisince: () => {} });
  assert.match(html, /class="[^"]*kitap-alan-hata-simge"/);
});

// Kadir, 14 Nov 2026 (screenshot): "kenar ışık çizgisi de kurdelenin dışına taşıyor", "renkte sorun var". A line
// stroked on the ribbon's edge lies half outside it, and a pale pink line over the red reads as another colour.
const kurdeleCizimleri = () => {
  const html = render(kitap.KitapKabugu, { tema: 'gece', sol: 'SOL', sag: 'SAG' });
  return ['kitap-kurdele-govde', 'kitap-kurdele-kisa'].map((ad) => {
    const bas = html.indexOf(`<svg class="${ad}"`);
    assert.ok(bas >= 0, `${ad} is drawn`);
    return { ad, svg: html.slice(bas, html.indexOf('</svg>', bas)) };
  });
};

test('ribbon: every line (sheen, outline, rim) is drawn inside the ribbon shape, none beside it', () => {
  for (const { ad, svg } of kurdeleCizimleri()) {
    const kirpma = svg.match(/<clipPath id="([^"]+)">/);
    assert.ok(kirpma, `${ad}: the ribbon shape is a clip path`);
    // Split at each clipped group: every piece but the first starts inside a group and leaves it at its first </g>.
    const [once, ...gruplar] = svg.split(`<g clip-path="url(#${kirpma[1]})">`);
    const icinde = gruplar.map((g) => g.slice(0, g.indexOf('</g>'))).join('');
    const disinda = once + gruplar.map((g) => g.slice(g.indexOf('</g>'))).join('');
    assert.match(icinde, /stroke="/, `${ad}: the lines are inside the clipped group`);
    assert.doesNotMatch(disinda, /stroke="/, `${ad}: no line outside the clipped group`);
  }
});

test('ribbon: its lines are a satin red or a dark shade, never a pale pink; the bends are shade only', () => {
  for (const { ad, svg } of kurdeleCizimleri()) {
    const renkler = [...svg.matchAll(/stroke="#([0-9A-Fa-f]{6})"/g)].map((m) => m[1]);
    assert.ok(renkler.length > 0, `${ad}: has lines`);
    for (const renk of renkler) {
      const [r, g, b] = [0, 2, 4].map((i) => parseInt(renk.slice(i, i + 2), 16));
      assert.ok(r < 0x40 || (g <= r * 0.4 && b <= r * 0.4), `${ad}: #${renk} is a pale line colour`);
    }
  }
  const kivrim = kurdeleCizimleri()[0].svg.match(/<linearGradient id="kurdele-kivrim-[\s\S]*?<\/linearGradient>/);
  assert.ok(kivrim, 'the bend overlay is there');
  for (const m of kivrim[0].matchAll(/stop-color="([^"]+)"/g)) assert.equal(m[1], '#000', 'the bend is shade only');
});
