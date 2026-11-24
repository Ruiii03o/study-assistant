const test=require('node:test');const assert=require('node:assert/strict');const vm=require('node:vm');const fs=require('node:fs');const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../frontend/batch-ui.js'),'utf8');
function setup(){
  const status={textContent:''},calls=[];
  const ctx=vm.createContext({practiceSaving:false,practiceBatchStop:false,activeCourse:{id:1},practiceRecord:{id:'p1',status:'processing'},renderPracticeSession:()=>{},loadPracticeHistory:async()=>{},$:()=>status});
  vm.runInContext(source.slice(source.indexOf('async function continuePracticePipeline()')),ctx);
  vm.runInContext(source.slice(source.indexOf('function exportSession('),source.indexOf('async function loadOutlineSessions(')),ctx);
  vm.runInContext(source.slice(source.indexOf('function batchRangeText('),source.indexOf('function renderBatchProgress(')),ctx);
  return {ctx,calls,status};
}
test('pipeline runs successive steps until ready',async()=>{
  const {ctx}=setup();let count=0;ctx.api=async()=>({id:'p1',status:++count===2?'ready':'processing',pipeline:{parts:[{status:'done'}]}});
  await ctx.continuePracticePipeline();assert.equal(count,2);assert.equal(ctx.practiceRecord.status,'ready');assert.equal(ctx.practiceSaving,false);
});
test('failed step stops automatic loop without discarding saved progress',async()=>{
  const {ctx}=setup();let count=0;ctx.api=async()=>{count++;return {id:'p1',status:'processing',pipeline:{parts:[{status:'done'},{status:'failed'}]}};};
  await ctx.continuePracticePipeline();assert.equal(count,1);assert.equal(ctx.practiceRecord.pipeline.parts[0].status,'done');
});
test('pause completes current request and avoids starting another',async()=>{
  const {ctx}=setup();let count=0;ctx.api=async()=>{count++;ctx.practiceBatchStop=true;return {id:'p1',status:'processing',pipeline:{parts:[]}};};
  await ctx.continuePracticePipeline();assert.equal(count,1);assert.equal(ctx.practiceSaving,false);
});
test('late result does not replace another course',async()=>{
  const {ctx}=setup();let resolve;ctx.api=()=>new Promise(r=>resolve=r);const task=ctx.continuePracticePipeline();ctx.activeCourse={id:2};ctx.practiceRecord={id:'p2'};
  resolve({id:'p1',status:'ready'});await task;assert.equal(ctx.practiceRecord.id,'p2');
});
test('archive export marks unfinished ranges and only uses completed result',()=>{
  const {ctx}=setup();let saved;ctx.exportOutline=r=>saved=r;
  const range={name:'File',start:'Slide 1',end:'Slide 2'};
  ctx.exportSession({completed_batches:1,total_batches:2,parts:[{status:'done',ranges:[range]},{status:'pending',ranges:[{...range,start:'Slide 3',end:'Slide 3'}]}],result:{title:'Outline',sections:[{title:'Completed',points:[]}]},sources:[{source_id:'S1'}]});
  assert.match(saved.result.sections[0].points[1].text,/未完成/);assert.equal(saved.result.sections[1].title,'Completed');assert.equal(saved.sources.length,1);
});
