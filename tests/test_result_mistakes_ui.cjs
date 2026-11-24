const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const source=fs.readFileSync('frontend/result-mistakes.js','utf8');
function setup(){const c=vm.createContext({});vm.runInContext(source.slice(0,source.indexOf('function renderMistakeScope')),c);return c;}
test('counts partial results as mistakes, keeps pending distinct from correct',()=>{
 const c=setup();assert.deepEqual(JSON.parse(JSON.stringify(c.resultMistakeCounts({result:{questions:[{score:0,max_score:2},{score:1,max_score:2},{score:2,max_score:2},{score:null,max_score:5}]}}))),{wrong:2,pending:1});
});
test('attempt filter uses that submission even if a subsequent retry became correct',()=>{
 const c=setup(),item={question:{max_score:2},state:'full_score',attempts:[{practice_id:'old',score:0},{practice_id:'retry',score:2}]},data={items:[item],summary:{total:1}};
 const wrong=c.scopedMistakes(data,{id:'old'});assert.equal(wrong.items.length,1);assert.equal(wrong.items[0].state,'needs_practice');assert.equal(item.state,'full_score');
 assert.equal(c.scopedMistakes(data,{id:'retry'}).items.length,0);assert.equal(c.scopedMistakes(data,{id:'other'}).items.length,0);assert.equal(c.scopedMistakes(data,null),data);
});
test('navigation clears old filters, refreshes on every entry and preserves requested scope',()=>{
 const refs=Object.fromEntries(['mistake-search','mistake-state','mistake-kind','mistake-items','mistake-summary','mistake-message'].map(k=>[k,{value:'old',replaceChildren(){}}]));let loads=0;
 const c=vm.createContext({$:id=>refs[id],activeCourse:{id:3},navigateStudy(){},renderMistakeScope(){},loadMistakes(id){assert.equal(id,3);loads++;}});
 vm.runInContext('let mistakeScope=null;'+source.slice(source.indexOf('const resultNavigateStudy'),source.indexOf('async function openResultMistakes')),c);
 c.navigateStudy('mistakes',{mistakeScope:{id:'new'}});assert.equal(refs['mistake-state'].value,'needs_practice');assert.equal(vm.runInContext('mistakeScope.id',c),'new');
 c.navigateStudy('mistakes');assert.equal(refs['mistake-state'].value,'all');assert.equal(vm.runInContext('mistakeScope',c),null);assert.equal(loads,2);
});
