const test=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../frontend/report.js'),'utf8');
function setup() {
  const nodes=new Map();const get=id=>{if(!nodes.has(id))nodes.set(id,{textContent:'',disabled:false,replaceChildren(){}});return nodes.get(id);};
  const ctx=vm.createContext({$:get,reportCourseId:null,reportRequest:0,reportData:null,activeCourse:{id:1},renderReport:()=>{},practiceKinds:{single:'单选'},reportModes:{automatic:'程序判分'}});
  vm.runInContext(source.slice(0,source.indexOf('const reportPanel')),ctx);
  vm.runInContext(source.slice(source.indexOf('function resetReport('),source.indexOf('function reportTable(')),ctx);
  vm.runInContext(source.slice(source.indexOf('function metricRow('),source.indexOf('function renderReport(')),ctx);
  vm.runInContext(source.slice(source.indexOf('function markdownCell('),source.indexOf("$('report-refresh').onclick")),ctx);
  return {ctx,get};
}
test('zero rate differs from no graded data',()=>{
  const {ctx}=setup();assert.equal(ctx.reportRate({score_rate:0}),'0%');assert.equal(ctx.reportRate({score_rate:null}),'暂无评分');
});
test('late response from old course is ignored',async()=>{
  const {ctx}=setup();let resolve;ctx.api=()=>new Promise(r=>resolve=r);
  const request=ctx.loadReport(1);ctx.activeCourse={id:2};ctx.resetReport(2);resolve({course:{id:1}});await request;
  assert.equal(ctx.reportData,null);
});
test('newest refresh wins over an older response',async()=>{
  const {ctx}=setup();const pending=[];ctx.api=()=>new Promise(r=>pending.push(r));
  const first=ctx.loadReport(1),second=ctx.loadReport(1);
  pending[1]({course:{id:1},generated_at:2});await second;
  pending[0]({course:{id:1},generated_at:1});await first;assert.equal(ctx.reportData.generated_at,2);
});
test('failed refresh disables export of outdated data',async()=>{
  const {ctx,get}=setup();ctx.api=async()=>{throw new Error('offline');};
  await ctx.loadReport(1);assert.equal(get('report-export').disabled,true);assert.match(get('report-message').textContent,/offline/);
});
test('Markdown separates first and retry, escapes table text and includes methodology',()=>{
  const {ctx}=setup();
  const row={questions:1,graded:1,pending:0,earned:1,graded_max:2,score_rate:50,small_sample:true};
  const group={submitted_attempts:1,fully_scored_attempts:1,ready_attempts:0,totals:row,by_kind:[{...row,kind:'single'}],by_mode:[{...row,mode:'automatic'}],chapters:[{...row,title:'A|B\nC'}],recent:[]};
  const result=ctx.reportMarkdown({course:{name:'Test'},generated_at:1,first_attempts:group,retries:group,mistakes:{total:1,needs_practice:1,full_score:0,pending_review:0},suggestions:['Review'],methodology:['Pending scores excluded']});
  assert.match(result,/## 首次作答/);assert.match(result,/## 原题重做/);assert.ok(result.includes('A\\|B C'));assert.ok(result.includes('正确率＝完全正确题数÷已评分题数'));assert.ok(!result.includes('Pending scores excluded'));assert.ok(result.includes('统计说明'));
});

test('variant row uses counts and correctness instead of weighted points',()=>{
 const {ctx}=setup();const row={evaluation_mode:'correctness',questions:4,graded:3,pending:1,full_score:1,partial:1,zero:1,correct_rate:33.3,score_rate:50,earned:7,graded_max:14};
 assert.equal(ctx.reportRate(row),'33.3%');assert.deepEqual(JSON.parse(JSON.stringify(ctx.metricRow('变式',row))),['变式',4,3,1,1,1,1,'33.3%']);
});
