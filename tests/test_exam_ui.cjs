const fs=require('node:fs'),vm=require('node:vm'),test=require('node:test'),assert=require('node:assert/strict');
const source=fs.readFileSync('frontend/exams.js','utf8');
test('countdown uses server anchor, rounds up and never becomes negative',()=>{
  const code=source.slice(source.indexOf('function examRemaining'),source.indexOf('function renderExam'));
  const c=vm.createContext({});vm.runInContext(code,c);
  assert.equal(c.examRemaining(1060,1000,500),60);
  assert.equal(c.examRemaining(1060,1000,59000),1);
  assert.equal(c.examRemaining(1060,1000,90000),0);
});
function context(api) {
  const status={textContent:''};
  const c=vm.createContext({api,practiceRecord:{id:'p',course_id:1,attempt_kind:'exam',status:'ready',revision:1},practiceDirty:true,practiceSaving:false,
    activeCourse:{id:1},examEditVersion:1,examSavePromise:null,examAutosaveTimer:null,
    collectPracticeAnswers:()=>({Q1:['A']}),$:id=>id==='material-view'?{hidden:false}:status,
    setTimeout:()=>1,clearTimeout:()=>{}});
  vm.runInContext(source.slice(source.indexOf('async function autoSaveExam')),c);return c;
}
test('autosave preserves input edited while request is in flight',async()=>{
  let resolve;const c=context(()=>new Promise(r=>resolve=r));const pending=c.autoSaveExam();
  assert.equal(c.practiceSaving,true);c.examEditVersion=2;resolve({revision:2});await pending;
  assert.equal(c.practiceRecord.revision,2);assert.equal(c.practiceDirty,true);assert.equal(c.practiceSaving,false);
});
test('autosave clears dirty only after successful save; errors preserve it',async()=>{
  const c=context(async()=>({revision:2}));await c.autoSaveExam();assert.equal(c.practiceDirty,false);
  const fail=context(async()=>{throw Error('offline')});await fail.autoSaveExam();assert.equal(fail.practiceDirty,true);assert.equal(fail.practiceSaving,false);
});
test('late autosave cannot update another course',async()=>{
  let resolve;const c=context(()=>new Promise(r=>resolve=r));const pending=c.autoSaveExam();
  c.activeCourse={id:2};resolve({revision:2});await pending;assert.equal(c.practiceRecord.revision,1);assert.equal(c.practiceDirty,true);
});

test('ordinary practice also auto-saves without replacing live inputs',async()=>{
  const c=context(async()=>({revision:2}));c.practiceRecord.attempt_kind='practice';await c.autoSaveExam();assert.equal(c.practiceDirty,false);assert.equal(c.practiceRecord.revision,2);
});
test('ordinary practice edits during auto-save stay dirty for next save',async()=>{
  let resolve;const c=context(()=>new Promise(r=>resolve=r));c.practiceRecord.attempt_kind='practice';const pending=c.autoSaveExam();c.examEditVersion++;resolve({revision:2});await pending;assert.equal(c.practiceDirty,true);
});
