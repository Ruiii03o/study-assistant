const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('frontend/study-ui.js','utf8');
class Element{
 constructor(tag){this.tag=tag;this.children=[];this.attributes={};this.events={};this.classes=new Set();this.classList={toggle:(name,value)=>value?this.classes.add(name):this.classes.delete(name)};}
 append(...children){this.children.push(...children)}
 prepend(node){this.children.unshift(node)}
 setAttribute(k,v){this.attributes[k]=v}
 addEventListener(k,fn){this.events[k]=fn}
}
function setup(status='ready'){
 const form=new Element('form');let selected=false;const textarea={value:''};const legend={focus:()=>{legend.focused=true}};
 const fields=[{querySelector:q=>q==='textarea'?textarea:q==='legend'?legend:null,scrollIntoView:()=>{}},{querySelector:q=>q==='input:checked'&&selected?{}:null,scrollIntoView:()=>{}}];
 form.querySelector=q=>q==='.question-navigator'?form.children.find(n=>n.className==='question-navigator'):null;
 form.querySelectorAll=()=>fields;
 const document={getElementById:()=>form,createElement:t=>new Element(t),addEventListener:()=>{}};
 const c=vm.createContext({document,practiceRecord:{status},window:{matchMedia:()=>({matches:true})},queueMicrotask:fn=>fn()});vm.runInContext(source,c);
 return{c,form,textarea,legend,setSelected:value=>selected=value};
}
test('navigator distinguishes blank, whitespace and selected answers without submitting',()=>{
 const s=setup();s.c.addQuestionNavigator();const nav=s.form.children[0],status=nav.children[0].children[1],numbers=nav.children[1].children;
 assert.equal(numbers.length,2);assert.match(status.textContent,/0 \/ 2/);assert.equal(numbers[0].type,'button');
 s.textarea.value='   ';s.form.events.input();assert.match(status.textContent,/0 \/ 2/);
 s.textarea.value='answer';s.setSelected(true);s.form.events.change();assert.match(status.textContent,/2 \/ 2/);assert.equal(numbers[1].classes.has('is-answered'),true);
 s.setSelected(false);s.form.events.click();assert.match(status.textContent,/1 \/ 2/);
});
test('navigator focuses target and is only installed once',()=>{
 const s=setup();s.c.addQuestionNavigator();s.c.addQuestionNavigator();assert.equal(s.form.children.length,1);
 s.form.children[0].children[1].children[0].onclick();assert.equal(s.legend.focused,true);assert.equal(s.legend.tabIndex,-1);
});
test('submitted attempts do not receive editable-answer progress',()=>{
 const s=setup('submitted');s.c.addQuestionNavigator();assert.equal(s.form.children.length,0);
});
