const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
class Element {
  constructor(tag){this.tag=tag;this.children=[];this.attributes={};this.textContent='';this.classList={toggle:()=>{}};}
  append(...nodes){this.children.push(...nodes);}
  replaceChildren(...nodes){this.children=nodes;}
  setAttribute(key,value){this.attributes[key]=value;}
}
function setup(){const c=vm.createContext({document:{createElement:tag=>new Element(tag)}});vm.runInContext(fs.readFileSync('frontend/notebook.js','utf8'),c);return c;}
const record={id:'outline',sources:[{source_id:'S1',name:'book',location:'Page 1',text:'original text'}],result:{sections:[{title:'Chapter',points:[{text:'<script>literal text</script>',source_ids:['S1','S1']},{text:'Second point',source_ids:[]}]}]}};
test('knowledge cards show one point with bounded pagination and literal model text',()=>{
 const c=setup(),target=new Element('div');c.renderKnowledgeCards(record,target);
 const book=target.children[0],pages=book.children[2],nav=book.children[3];
 assert.equal(pages.children.length,1);assert.equal(pages.children[0].children[2].textContent,record.result.sections[0].points[0].text);
 assert.equal(nav.children[0].disabled,true);nav.children[2].onclick();assert.equal(nav.children[2].disabled,true);
 assert.equal(pages.children[0].children[2].textContent,'Second point');
 nav.children[2].onclick();assert.equal(pages.children[0].children[2].textContent,'Second point');
});
test('reverse shows original citations once and flipping back restores knowledge',()=>{
 const c=setup(),target=new Element('div');c.renderKnowledgeCards(record,target);
 const book=target.children[0],pages=book.children[2],flip=book.children[3].children[3];flip.onclick();
 assert.equal(pages.children[0].children.filter(n=>n.tag==='details').length,1);
 assert.equal(pages.children[0].children[3].children[1].textContent,'original text');
 flip.onclick();assert.equal(pages.children[0].children[2].textContent,record.result.sections[0].points[0].text);
});
test('expand all includes every point and saved position survives rerender',()=>{
 const c=setup(),target=new Element('div');c.renderKnowledgeCards(record,target);let book=target.children[0];
 book.children[3].children[2].onclick();book.children[0].children[1].onclick();assert.equal(book.children[2].children.length,2);assert.equal(book.children[3].hidden,true);
 const second=new Element('div');c.renderKnowledgeCards(record,second);book=second.children[0];assert.equal(book.children[1].children[0].value,'1');
});
test('empty result creates no empty book and source-less card remains usable',()=>{
 const c=setup(),target=new Element('div');c.renderKnowledgeCards({...record,result:{sections:[]}},target);assert.equal(target.children.length,0);
 c.renderKnowledgeCards(record,target);const book=target.children[0];book.children[3].children[2].onclick();book.children[3].children[3].onclick();assert.equal(book.children[2].children[0].children.at(-1).tag,'p');
});
