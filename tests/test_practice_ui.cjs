// Exercise the real answer-save handlers without a browser. Layout is not covered.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname,'../frontend/practice.js'),'utf8');
const handlers = source.slice(source.indexOf('function collectPracticeAnswers()'),source.indexOf("window.addEventListener('beforeunload'"));
function setup() {
  const status = {textContent:''};
  const controls = [{disabled:false}];
  const fields = [
    {dataset:{questionId:'Q1'},querySelector:()=>null,querySelectorAll:()=>[{value:'A'}]},
    {dataset:{questionId:'Q2'},querySelector:()=>({value:'  Some answer  '})},
    {dataset:{questionId:'Q3'},querySelector:()=>({value:'  '})},
  ];
  const form = {querySelectorAll:selector => selector === '[data-question-id]' ? fields : controls};
  const calls = [];
  const context = vm.createContext({
    $:id=>id==='practice-save-status'?status:form,
    practiceSaving:false, practiceDirty:true, activeCourse:{id:1},
    practiceRecord:{id:'p1',status:'ready',revision:4,questions:[{id:'Q1'},{id:'Q2'},{id:'Q3'}]},
    window:{confirm:()=>true},
    api:async (url,options)=> { calls.push({url,body:JSON.parse(options.body)}); return {revision:5}; },
    renderPracticeSession:()=>{}, loadPracticeHistory:async()=>{},
  });
  vm.runInContext(handlers,context);
  return {context,status,controls,calls,form};
}
test('answers collect selected options and text, keeping blank answers empty', () => {
  const {context} = setup();
  assert.deepEqual(JSON.parse(JSON.stringify(context.collectPracticeAnswers())),{Q1:['A'],Q2:['  Some answer  '],Q3:[]});
});
test('saving uses server revision and only clears dirty after success', async () => {
  const {context,calls,controls,status} = setup(); await context.savePractice(false);
  assert.equal(calls[0].body.revision,4);
  assert.equal(context.practiceRecord.revision,5);
  assert.equal(context.practiceDirty,false);
  assert.equal(controls[0].disabled,false);
  assert.match(status.textContent,/已保存/);
});
test('save error retains answers and dirty state and unlocks controls', async () => {
  const {context,controls,status} = setup(); context.api = async()=>{throw new Error('conflict');};
  await context.savePractice(false);
  assert.equal(context.practiceRecord.revision,4);
  assert.equal(context.practiceDirty,true);
  assert.equal(controls[0].disabled,false);
  assert.match(status.textContent,/conflict/);
});
test('cancelled submission does not send a request', async () => {
  const {context,calls} = setup(); context.window.confirm=()=>false;
  await context.savePractice(true); assert.equal(calls.length,0);
});
test('late save response from another course cannot overwrite current record', async () => {
  const {context} = setup(); let resolve; context.api=()=>new Promise(r=>resolve=r);
  const saving=context.savePractice(false);
  context.activeCourse={id:2}; context.practiceRecord={id:'p2',revision:8};
  resolve({revision:5}); await saving;
  assert.equal(context.practiceRecord.id,'p2'); assert.equal(context.practiceRecord.revision,8);
});
test('self review skips unscored questions and submits numeric scores with revision', async () => {
  const {context,form,calls} = setup(); context.practiceRecord.status='submitted';
  const original=form.querySelectorAll;
  form.querySelectorAll=selector=>selector==='[data-review-id]' ? [{dataset:{reviewId:'Q2'},value:'2'},{dataset:{reviewId:'Q3'},value:''}] : selector==='[data-point-review-id]'?[]:original(selector);
  await context.saveSelfReview();
  assert.deepEqual(calls[0].body,{revision:4,scores:{Q2:2}});
});

test('short answers submit point verdicts rather than a client-calculated total',async()=>{
  const {context,form,calls}=setup();context.practiceRecord.status='submitted';
  form.querySelectorAll=selector=>selector==='[data-point-review-id]'?[
    {dataset:{pointReviewId:'Q3',pointIndex:'0'},value:'met'},
    {dataset:{pointReviewId:'Q3',pointIndex:'1'},value:'partial'},
    {dataset:{pointReviewId:'Q3',pointIndex:'2'},value:'missed'}]:[];
  await context.saveSelfReview();
  assert.deepEqual(calls[0].body,{revision:4,scores:{},point_verdicts:{Q3:['met','partial','missed']}});
});
test('incomplete short-answer rubric blocks saving and retains edits',async()=>{
  const {context,form,calls}=setup();context.practiceRecord.status='submitted';
  form.querySelectorAll=selector=>selector==='[data-point-review-id]'?[
    {dataset:{pointReviewId:'Q3',pointIndex:'0'},value:'met'},
    {dataset:{pointReviewId:'Q3',pointIndex:'1'},value:''}]:[];
  await context.saveSelfReview();assert.equal(calls.length,0);assert.equal(context.practiceDirty,true);
});

test('submission waits for confidence persistence before sending answers',async()=>{
 const {context,calls}=setup();let release;context.flushConfidence=()=>new Promise(r=>release=r);
 const save=context.savePractice(true);assert.equal(calls.length,0);release();await save;assert.equal(calls.length,1);assert.match(calls[0].url,/submit$/);
});
test('failed confidence save keeps answer submission pending',async()=>{
 const {context,calls,status}=setup();context.flushConfidence=async()=>{throw Error('offline');};await context.savePractice(true);assert.equal(calls.length,0);assert.match(status.textContent,/offline/);assert.equal(context.practiceDirty,true);
});
