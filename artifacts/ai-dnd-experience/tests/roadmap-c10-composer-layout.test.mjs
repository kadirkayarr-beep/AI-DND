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
function style(selector,width){const out={};css.walkRules(rule=>{if(!rule.selectors.includes(selector))return;let p=rule.parent;while(p){if(p.type==='atrule'&&p.name==='media'){const min=p.params.match(/min-width:\s*(\d+)px/),max=p.params.match(/max-width:\s*(\d+)px/);if(min&&width<+min[1]||max&&width>+max[1])return;}p=p.parent;}rule.walkDecls(d=>out[d.prop]=d.value);});return out;}
test('desktop transcript wrapper owns usable nonshrinking space; inner scroll has no overflowing minimum',()=>{const wrapper=style('.design-preview.play-shell .transcript-region',1280),inner=style('.design-preview.play-shell .transcript-region > .transcript-scroll',1280);assert.equal(wrapper['min-height'],'320px');assert.equal(wrapper.flex,'1 0 320px');assert.equal(inner['min-height'],'0');assert.equal(wrapper.overflow,'hidden');assert.equal(inner['overflow-y'],'auto');});
test('tall desktop economy and notice keep all controls reachable through workspace scroll, not overlap or z-index masking',()=>{const workspace=style('.design-preview.play-shell .workspace-grid',1280),story=style('.design-preview.play-shell .story-column',1280);assert.equal(workspace['overflow-y'],'auto');assert.equal(story.flex,'1 0 auto');assert.equal(story.height,'auto');assert.equal(style('.design-preview.play-shell .turn-open-button',1280)['z-index'],undefined);});
test('mobile retains document flow without desktop fixed transcript minimum',()=>{const wrapper=style('.design-preview.play-shell .transcript-region',390),inner=style('.design-preview.play-shell .transcript-scroll',390);assert.equal(wrapper['min-height'],'0');assert.equal(inner['min-height'],'0');assert.equal(inner.overflow,'visible');assert.equal(style('.design-preview.play-shell .story-column',390).height,'auto');});
