// Selection state tests without a browser; layout is not covered here.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
function setup() {
  const nodes = new Map();
  const get = id => { if (!nodes.has(id)) nodes.set(id, {textContent:'', disabled:false, querySelectorAll:() => [{value:'a'}, {value:'b'}]}); return nodes.get(id); };
  const context = vm.createContext({$:get, activeCourse:{id:1}, aiConfigured:true, outlineBusy:false});
  let code = fs.readFileSync(path.join(__dirname,'../frontend/chapters.js'),'utf8');
  code = code.slice(0, code.indexOf('(async () => { try { await showWorkspace'));
  vm.runInContext(code, context);
  const run = code => vm.runInContext(code, context);
  run(`chapterGroups = [{title:'Shared',ranges:[
    {key:'a1', material_id:'a', unit_index:0,end_unit_index:2},
    {key:'a2', material_id:'a', unit_index:1,end_unit_index:3},
    {key:'b1', material_id:'b', unit_index:0,end_unit_index:0}]}];
    chapterSelection = new Map([['a1',true],['a2',true],['b1',true]]); chaptersLoading = false;`);
  return {get,context,run};
}
test('selection counts overlapping positions once per file', () => {
  const {get,run} = setup(); run('updateChapterSummary()');
  assert.match(get('outline-chapter-summary').textContent, /覆盖 5 个/);
  assert.equal(get('outline-generate').disabled,false);
});
test('hidden file selections never reach generation and remain recoverable', () => {
  const {get,run} = setup(); get('outline-materials').querySelectorAll = () => [{value:'a'}];
  assert.equal(run('JSON.stringify(selectedChapterKeys())'),'["a1","a2"]');
  assert.equal(run("chapterSelection.get('b1')"),true);
});
test('no selection, loading, pending generation, or missing config blocks generation', () => {
  for (const state of ['chapterSelection.clear()', 'chaptersLoading=true', 'outlinePending=true', 'aiConfigured=false']) {
    const {get,run} = setup(); run(state+';updateChapterSummary()');
    assert.equal(get('outline-generate').disabled,true);
  }
});
test('loading failure clears stale selections and blocks submission', async () => {
  const {get,context,run} = setup(); context.api = async () => { throw new Error('offline'); };
  await run('loadChapterChoices(1)');
  assert.equal(run('selectedChapterKeys().length'),0);
  assert.equal(get('outline-generate').disabled,true);
  assert.match(get('outline-chapters').textContent,/offline/);
});
test('late response from old course cannot replace current chapter list', async () => {
  const {context,run} = setup(); let resolve;
  context.api = () => new Promise(r => resolve=r);
  const loading = run('loadChapterChoices(1)');
  run('activeCourse={id:2};chapterGroups=[{title:"New",ranges:[]}]');
  resolve([{title:'Old',ranges:[]}]); await loading;
  assert.equal(run('chapterGroups[0].title'),'New');
});
