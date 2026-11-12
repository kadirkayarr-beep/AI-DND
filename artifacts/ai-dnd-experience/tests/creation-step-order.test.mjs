import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

// Plan part B: creation runs Tür -> Sınıf -> Geçmiş. The human's extra origin feat must differ from the
// background's feat, so its picker and its validation live in the Geçmiş step, after the background is known.
const source = await readFile('src/components/character-creation-screen.tsx', 'utf8');
const between = (start, end) => {
  const from = source.indexOf(start);
  assert.ok(from >= 0, `${start} present`);
  const to = source.indexOf(end, from + start.length);
  return source.slice(from, to < 0 ? undefined : to);
};

test('steps run species, class, background, then the unchanged rest', () => {
  const ids = [...between('const STEPS = [', '] as const').matchAll(/id: '([a-z]+)'/g)].map(m => m[1]);
  assert.deepEqual(ids, ['species', 'class', 'background', 'abilities', 'choices', 'equipment', 'identity', 'review']);
  assert.match(source, /initialStep = 'species'/);
});
test('step labels and headings are renumbered', () => {
  assert.match(source, /id: 'species', label: '1\. Tür'/);
  assert.match(source, /id: 'class', label: '2\. Sınıf'/);
  assert.match(source, /id: 'background', label: '3\. Geçmiş'/);
  assert.match(between("currentStep === 'species' && (", 'cc-step-title-text'), /Adım 1/);
  assert.match(between("currentStep === 'class' && (", 'cc-step-title-text'), /Adım 2/);
  assert.match(between("currentStep === 'background' && (", 'cc-step-title-text'), /Adım 3/);
});
test('the human extra feat picker is in the background step, not the species step', () => {
  const species = between("currentStep === 'species' && (", "currentStep === 'abilities'");
  const background = between("currentStep === 'background' && (", "currentStep === 'abilities'");
  assert.doesNotMatch(species, /section-species-bonus-feat/);
  assert.match(background, /section-species-bonus-feat/);
});
test('species validity no longer needs the feat; background validity needs it when the species grants one', () => {
  const valid = between('const isStepValid', 'const getStepValidationHint');
  const speciesCase = between("case 'species':", "case 'abilities':");
  assert.doesNotMatch(speciesCase, /speciesBonusFeat/);
  const backgroundCase = valid.slice(valid.indexOf("case 'background':"), valid.indexOf("case 'species':"));
  assert.match(backgroundCase, /origin_feat_bonus_count/);
  assert.match(backgroundCase, /speciesBonusFeat/);
});
test('the feat hint moved with it', () => {
  const hints = between('const getStepValidationHint', "case 'abilities':");
  const backgroundHint = hints.slice(hints.indexOf("case 'background':"), hints.indexOf("case 'species':"));
  assert.match(backgroundHint, /geçmiş hünerinden farklı bir ek Başlangıç Hüneri/);
  assert.doesNotMatch(hints.slice(hints.indexOf("case 'species':")), /geçmiş hünerinden farklı/);
});

test('the class reset and the species/background reset touch disjoint choices, so neither erases the other in the new order', () => {
  const effect = (deps) => {
    const end = source.indexOf(`}, [${deps}]);`);
    assert.ok(end > 0, `effect with deps [${deps}] present`);
    return source.slice(source.lastIndexOf('useEffect(() => {', end), end);
  };
  const setters = (body) => new Set([...body.matchAll(/\b(set[A-Z]\w+)\(/g)].map(m => m[1]));
  const classReset = setters(effect('characterClass'));
  const originReset = setters(effect('background, species'));
  assert.ok(classReset.size > 0 && originReset.size > 0);
  assert.deepEqual([...classReset].filter(name => originReset.has(name)), []);
  assert.ok(originReset.has('setSpeciesBonusFeat') && originReset.has('setSelectedSpeciesSkills'));
});
test('the creation payload is assembled from state at submit time, so step order cannot change it', () => {
  const submit = between('const handleSubmit', 'onCreate(');
  assert.match(submit, /species_bonus_feat: speciesBonusFeat \|\| undefined/);
  assert.doesNotMatch(submit, /currentStep/);
});
