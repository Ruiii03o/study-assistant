const fs=require('node:fs'),vm=require('node:vm'),test=require('node:test'),assert=require('node:assert/strict');
const source=fs.readFileSync('frontend/blueprints.js','utf8');
class N {
 constructor(tag,text=''){this.tag=tag;this.textContent=text;this.children=[];this.value='';this.hidden=false;}
 append(...ns){for(const n of ns){this.children.push(n);if(typeof n==='object')n.parent=this;}}
 replaceChildren(){this.children=[];}
 setAttribute(){} add(n){this.append(n);} addEventListener(){} focus(){this.focused=true;} select(){} scrollIntoView(){}
 after(n){this.parent.append(n);} remove(){this.parent.children=this.parent.children.filter(n=>n!==this);}
}
function setup(){
 const nodes=[],calls=[],alerts=[],target=new N('div'),original=new N('a');
 const item={id:'b1',revision:1,name:'sample',draft:{title:'test',minutes:60,total:99.97,sections:[{title:'A',kind:'single',count:79,points:1.1}]}};
 const node=(...args)=>{const n=new N(...args);nodes.push(n);return n;};
 const c=vm.createContext({blueprintDirty:false,blueprintBusy:false,activeCourse:{id:1},blueprintSelected:()=>item,$:id=>id==='blueprint-editor'?target:original,toolNode:node,toolField:(title,tag='input')=>{const wrap=node('label',title),input=node(tag);wrap.append(input);return {wrap,input};},toolButton:(text,fn)=>{const n=node('button',text);n.onclick=fn;return n;},Option:function(text,value){this.value=value;this.textContent=text;},practiceKinds:{single:'单选'},blueprintStatus:()=>{},confirm:()=>true,alert:text=>alerts.push(text),api:async(...args)=>{calls.push(args);return {};},queueMicrotask:fn=>fn()});
 vm.runInContext(source.slice(source.indexOf('function renderBlueprintEditor'),source.indexOf("$('blueprint-upload').onsubmit")),c);c.renderBlueprintEditor();
 return {c,nodes,calls,alerts,form:nodes.find(n=>n.tag==='form')};
}
test('mismatched totals warn and prevent save without losing edits',async()=>{
 const {nodes,calls,alerts,form}=setup();await form.onsubmit({preventDefault(){}});
 assert.equal(calls.length,0);assert.equal(alerts.length,1);
 assert.equal(nodes.find(n=>n.className==='blueprint-score-warning').hidden,false);
 assert.equal(nodes.find(n=>n.tag==='label'&&n.textContent==='总分').children[0].value,99.97);
});
test('explicitly accepting computed total resolves warning and permits save',async()=>{
 const {nodes,calls,form}=setup();nodes.find(n=>n.textContent==='以当前合计作为总分').onclick();
 assert.equal(nodes.find(n=>n.className==='blueprint-score-warning').hidden,true);
 await form.onsubmit({preventDefault(){}});assert.equal(calls.length,1);
 assert.equal(JSON.parse(calls[0][1].body).blueprint.total,86.9);
});
test('add missing section keeps existing rows and focuses new title',()=>{
 const {nodes}=setup();nodes.find(n=>n.textContent==='添加遗漏结构行').onclick();
 const titles=nodes.filter(n=>n.tag==='label'&&n.textContent==='大题名称');assert.equal(titles.length,2);assert.equal(titles[0].children[0].value,'A');assert.equal(titles[1].children[0].focused,true);
});
