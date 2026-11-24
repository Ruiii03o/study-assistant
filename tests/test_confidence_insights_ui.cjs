const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const source=fs.readFileSync('frontend/confidence.js','utf8'),c=vm.createContext({});
vm.runInContext(source.slice(source.indexOf('function confidenceInsights'),source.indexOf('function renderConfidenceInsights')),c);
test('all nine confidence/outcome combinations receive advice, errors first',()=>{
 const items=[1,2,3].flatMap(level=>['correct','partial','incorrect'].map(outcome=>({level,outcome})));
 const r=c.confidenceInsights({items});assert.equal(r.advice.length,9);assert.equal(r.graded,9);
 assert.equal(r.advice[0].level,3);assert.equal(r.advice[0].outcome,'incorrect');
 assert.equal(r.advice.find(a=>a.level===2&&a.outcome==='correct').items.length,1);
});
test('screenshot example highlights medium-confidence mistakes and partial results',()=>{
 const r=c.confidenceInsights({items:[{level:1,outcome:'correct'},{level:1,outcome:'partial'},{level:2,outcome:'incorrect'},{level:2,outcome:'incorrect'},{level:3,outcome:'correct'}]});
 assert.equal(r.graded,5);assert.equal(r.advice[0].level,2);assert.equal(r.advice[0].items.length,2);assert.equal(r.totals.partial,1);
});
test('all correct has no error advice, pending and empty never count as mistakes',()=>{
 const r=c.confidenceInsights({items:Array.from({length:5},()=>({level:3,outcome:'correct'}))});assert.equal(r.advice.length,1);assert.equal(r.advice[0].outcome,'correct');
 const p=c.confidenceInsights({items:[{level:2,outcome:'pending'}]});assert.equal(p.graded,0);assert.equal(p.totals.pending,1);assert.equal(p.advice.length,0);
 assert.equal(c.confidenceInsights({items:[]}).advice.length,0);
});
