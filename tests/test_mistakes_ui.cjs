const test=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../frontend/mistakes.js'),'utf8');
function setup() {
  const status={textContent:''},requests=[],opened=[];
  const ctx=vm.createContext({
    activeCourse:{id:1},practiceSaving:false,practiceDirty:false,mistakeStarting:new Set(),
    $:()=>status,renderMistakes:()=>{},loadPracticeHistory:async()=>{},
    showPractice:async(id,course)=>opened.push({id,course}),crypto:{randomUUID:()=>'test-retry-123456789'},
    api:async(url,options)=>{requests.push({url,body:JSON.parse(options.body)});return {id:'retry1'};}
  });
  vm.runInContext(source.slice(source.indexOf('function visibleMistakes('),source.indexOf('function renderMistakes(')),ctx);
  vm.runInContext(source.slice(source.indexOf('async function startMistakeRetry('),source.indexOf("$('mistake-refresh').onclick")),ctx);
  return {ctx,status,requests,opened};
}
test('filters combine state, kind and case insensitive search',()=>{
  const {ctx}=setup();
  const items=[{practice_title:'Network',question:{prompt:'TCP basics',kind:'single'},state:'full_score'},
    {practice_title:'Network',question:{prompt:'UDP basics',kind:'short'},state:'needs_practice'}];
  assert.equal(ctx.visibleMistakes(items,' tcp ','all','single').length,1);
  assert.equal(ctx.visibleMistakes(items,'network','needs_practice','short').length,1);
  assert.equal(ctx.visibleMistakes(items,'','pending_review','all').length,0);
  assert.equal(ctx.mistakeScore(null,'self'),'待评分');
});
test('unsaved work blocks retry creation',async()=>{
  const {ctx,requests,status}=setup();ctx.practiceDirty=true;
  await ctx.startMistakeRetry({practice_id:'p1',question:{id:'Q1'}});
  assert.equal(requests.length,0);assert.match(status.textContent,/先保存/);
});
test('pending retry is resumed without another creation request',async()=>{
  const {ctx,requests,opened}=setup();
  await ctx.startMistakeRetry({practice_id:'p1',question:{id:'Q1'},pending_retry_id:'old-retry'});
  assert.equal(requests.length,0);assert.deepEqual(opened,[{id:'old-retry',course:1}]);
});
test('creation sends selected question and opens new attempt',async()=>{
  const {ctx,requests,opened}=setup();
  await ctx.startMistakeRetry({practice_id:'p1',question:{id:'Q4'}});
  assert.deepEqual(requests[0].body,{question_ids:['Q4'],request_id:'test-retry-123456789'});
  assert.deepEqual(opened,[{id:'retry1',course:1}]);assert.equal(ctx.mistakeStarting.size,0);
});
test('late response does not open a retry in a different course',async()=>{
  const {ctx,opened}=setup();let resolve;ctx.api=()=>new Promise(r=>resolve=r);
  const promise=ctx.startMistakeRetry({practice_id:'p1',question:{id:'Q4'}});
  ctx.activeCourse={id:2};resolve({id:'retry1'});await promise;
  assert.equal(opened.length,0);assert.equal(ctx.mistakeStarting.size,0);
});
