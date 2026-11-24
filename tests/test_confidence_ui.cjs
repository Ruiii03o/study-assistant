const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const source=fs.readFileSync('frontend/confidence.js','utf8');
function setup(api){const c=vm.createContext({api});vm.runInContext(source.slice(0,source.indexOf('const confidenceRender')),c);return c;}
test('rapid changes are serialized and final selection is saved',async()=>{
 const calls=[],pending=[];const c=setup((path,opt)=>{calls.push(JSON.parse(opt.body));return new Promise(resolve=>pending.push(resolve));});
 const state=c.confidenceState('p');state.values={Q1:1};state.dirty=true;
 const first=c.flushConfidence('p');state.values.Q1=3;state.values.Q2=2;state.dirty=true;const second=c.flushConfidence('p');
 pending.shift()({revision:1});await new Promise(r=>setImmediate(r));assert.equal(calls.length,2);assert.equal(calls[1].revision,1);assert.deepEqual(calls[1].values,{Q1:3,Q2:2});pending.shift()({revision:2});await Promise.all([first,second]);assert.equal(state.dirty,false);
});
test('failed save keeps local choice and can retry',async()=>{
 let fail=true;const c=setup(async()=>{if(fail)throw Error('offline');return {revision:1};});const state=c.confidenceState('p');state.values={Q1:3};state.dirty=true;
 await assert.rejects(c.flushConfidence('p'),/offline/);assert.equal(state.dirty,true);assert.equal(state.values.Q1,3);assert.equal(state.pending,null);
 fail=false;await c.flushConfidence('p');assert.equal(state.dirty,false);
});
test('conflict refresh preserves remote other questions and local changed question',async()=>{
 const c=setup(async(path,opt)=>{if(opt)throw Error('信心记录已更新');return {revision:3,values:{Q1:1,Q2:2}};});const state=c.confidenceState('p');state.values={Q1:3};state.edits={Q1:3};state.dirty=true;
 await assert.rejects(c.flushConfidence('p'));assert.equal(state.revision,3);assert.deepEqual(JSON.parse(JSON.stringify(state.values)),{Q1:3,Q2:2});
});

test('retry and variant do not mount controls or request confidence',async()=>{
 const c=vm.createContext({});
 vm.runInContext(source.slice(source.indexOf('async function mountConfidence'),source.indexOf("window.addEventListener")),c);
 await c.mountConfidence({parent_id:'original',status:'ready',questions:[{id:'Q1'}]});
 await c.mountConfidence({variant_of:'original:Q1',status:'submitted',questions:[{id:'Q1'}]});
});
