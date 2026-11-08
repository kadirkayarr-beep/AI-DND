import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {test} from 'node:test';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const postcss=createRequire(require.resolve('vite'))('postcss');
// CSS contract tests, not a substitute for parent-managed browser hit-testing.
// Native diagnostic02 supplies genuine geometry RED: wrapper height0, child320,
// button-center elementFromPoint=p.story-text; pointer click leaves composer absent.
const css=postcss.parse(await readFile('src/components/unwritten-play.css','utf8'));
function style(selector,width,height=800){const out={};css.walkRules(rule=>{if(!rule.selectors.includes(selector))return;let p=rule.parent;while(p){if(p.type==='atrule'&&p.name==='container'){const max=p.params.match(/max-height:\s*(\d+)px/);if(max&&height>+max[1])return;}if(p.type==='atrule'&&p.name==='media'){const min=p.params.match(/min-width:\s*(\d+)px/),max=p.params.match(/max-width:\s*(\d+)px/);if(min&&width<+min[1]||max&&width>+max[1])return;}p=p.parent;}rule.walkDecls(d=>out[d.prop]=d.value);});return out;}
// Actual C024 browser RED supersedes the earlier document-flow workaround:
// it prevented overlap but left the Send button outside a 1280x800 viewport.
const awaitSource=await readFile('src/pages/game-browser.tsx','utf8');
test('auxiliary actions have their own scroll allocation instead of pushing the story',()=>{
 const story=style('.design-preview.play-shell .story-column',1280);
 assert.equal(story.display,'grid'); assert.equal(story['min-height'],'0');
 assert.equal(style('.design-preview.play-shell .story-scene-context',1280)['overflow-y'],'auto');
 const source=awaitSource;
 assert.ok(source.includes('topControls={<>'));
 assert.ok(source.includes('className="story-reading-column"'));
});
test('transcript owns its allocation and cannot paint over the composer or opener',()=>{
 for(const width of [1280,375]) {
  const wrapper=style('.design-preview.play-shell .transcript-region',width);
  const inner=style('.design-preview.play-shell .transcript-region > .transcript-scroll',width);
  assert.equal(wrapper.overflow,'hidden'); assert.equal(inner['min-height'],'0');
  assert.equal(inner['overflow-y'],'auto');
  assert.equal(style('.design-preview.play-shell .turn-open-button',width)['z-index'],undefined);
 }
});
test('both story and composer stay within a bounded reading column on mobile',()=>{
 const reader=style('.design-preview.play-shell .story-reading-column',375);
 assert.equal(reader.display,'flex'); assert.equal(reader['min-height'],'0');
 assert.equal(reader.overflow,'hidden');
 assert.equal(style('.design-preview.play-shell .story-column',375)['grid-template-columns'],'minmax(0,1fr)');
});

test('short desktop keeps one full-height reading row; only mobile splits auxiliary rows',()=>{
 assert.equal(style('.design-preview.play-shell .story-column',1280,600)['grid-template-rows'],'minmax(0,1fr)');
 assert.equal(style('.design-preview.play-shell .story-column',375,476)['grid-template-rows'],'48px minmax(0,1fr)');
 assert.equal(style('.design-preview.play-shell .transcript-region',375,476)['min-height'],'48px');
 assert.equal(style('.design-preview.play-shell .transcript-region',375,812)['min-height'],'220px');
});

// Browser R1: desktop Send min-width96 exceeded its 70px grid track;
// mobile's 88px minimum overlapped the input by12px. Reserve the full track.
test('composer reserves the Send width without clipping or overlapping the input',()=>{
 for(const width of [1280,375]) {
  assert.equal(style('.design-preview.play-shell .command-box',width)['grid-template-columns'],'minmax(0,1fr) 96px');
  const send=style('.design-preview.play-shell .command-form > button[type="submit"]',width);
  assert.equal(send['min-width'],'0'); assert.equal(send.width,'100%');
 }
});
