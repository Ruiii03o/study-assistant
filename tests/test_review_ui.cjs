const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
function setup() {
  const status={textContent:''}, button={dataset:{aiQuestion:'Q2'},disabled:false}, calls=[];
  const ctx=vm.createContext({
    practiceSaving:false,practiceDirty:false,activeCourse:{id:1},practiceRecord:{id:'p1',status:'submitted'},
    $:id=>id==='practice-save-status'?status:{querySelectorAll:()=>[button]},
    setPracticeSaving:value=>{ctx.practiceSaving=value;},renderPracticeSession:()=>{},
    api:async(url,options)=>{calls.push({url,body:JSON.parse(options.body)});return {id:'p1',status:'submitted',ai_reviews:{Q2:{status:'ready'}}};}
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../frontend/review.js'),'utf8'),ctx);
  return {ctx,status,button,calls};
}
test('unsaved manual scores block AI request',async()=>{
  const {ctx,calls,status}=setup();ctx.practiceDirty=true;await ctx.requestAIReview('Q2');
  assert.equal(calls.length,0);assert.match(status.textContent,/先保存/);
});
test('review submits question identifier and updates saved record',async()=>{
  const {ctx,calls}=setup();await ctx.requestAIReview('Q2');
  assert.deepEqual(calls[0].body,{question_id:'Q2'});
  assert.equal(ctx.practiceRecord.ai_reviews.Q2.status,'ready');assert.equal(ctx.practiceSaving,false);
});
test('running response stays disabled and errors preserve previous record',async()=>{
  const {ctx,button}=setup();ctx.api=async()=>({id:'p1',status:'submitted',ai_reviews:{Q2:{status:'running'}}});
  await ctx.requestAIReview('Q2');assert.equal(button.disabled,true);
  const old=ctx.practiceRecord;ctx.api=async()=>{throw new Error('offline');};
  await ctx.requestAIReview('Q2');assert.equal(ctx.practiceRecord,old);assert.equal(ctx.practiceSaving,false);
});
test('late response cannot replace another practice',async()=>{
  const {ctx}=setup();let resolve;ctx.api=()=>new Promise(r=>resolve=r);
  const pending=ctx.requestAIReview('Q2');ctx.practiceRecord={id:'p2',status:'submitted'};
  resolve({id:'p1',ai_reviews:{}});await pending;assert.equal(ctx.practiceRecord.id,'p2');
});
