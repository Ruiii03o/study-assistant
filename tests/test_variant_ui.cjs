const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const source=fs.readFileSync('frontend/practice.js','utf8');
const ctx=vm.createContext({});vm.runInContext(source.slice(0,source.indexOf('const practiceKinds')),ctx);
test('variant correctness is unweighted and pending excluded',()=>{
 const text=ctx.variantSummary({questions:[{score:1,max_score:1},{score:2,max_score:4},{score:0,max_score:5},{score:null,max_score:5}]});
 assert.match(text,/正确率 33.3%/);assert.match(text,/部分正确 1 题/);assert.match(text,/待评价 1 题/);assert.doesNotMatch(text,/得分|总分/);
 assert.equal(ctx.variantVerdict(null,2),'待评价');assert.equal(ctx.variantVerdict(0,2),'错误');
});
test('ungraded variants have unknown correctness',()=>assert.match(ctx.variantSummary({questions:[{score:null,max_score:2}]}),/正确率 —/));

test('submitted variant renders no question score or total',()=>{
 class Node {constructor(){this.children=[];this.dataset={};this.textContent='';}append(...xs){this.children.push(...xs);}replaceChildren(){this.children=[];}get lastChild(){return this.children.at(-1);}setAttribute(){} }
 const target=new Node();const record={variant_of:'old:Q1',title:'变式练习',status:'submitted',selected_chapters:[],model:'test',questions:[{id:'Q1',kind:'single',prompt:'知识问题',options:['甲','乙'],answer:['A'],explanation:'解释',key_points:[],source_ids:[],max_score:1.1}],answers:{Q1:['A']},result:{questions:[{id:'Q1',score:1.1,max_score:1.1,mode:'automatic'}]}};
 const c=vm.createContext({document:{createElement:()=>new Node()},$:()=>target,practiceRecord:record,practiceKinds:{single:'单选'},renderAIReview:()=>{},markPracticeDirty:()=>{}});
 vm.runInContext(source.slice(0,source.indexOf('const practiceKinds')),c);
 vm.runInContext(source.slice(source.indexOf('function practiceText('),source.indexOf('function markPracticeDirty(')),c);
 c.renderPracticeSession();const flatten=n=>n.textContent+' '+n.children.map(flatten).join(' ');const rendered=flatten(target);
 assert.match(rendered,/正确率 100%/);assert.doesNotMatch(rendered,/得分：|总分：|1.1 分/);
});
