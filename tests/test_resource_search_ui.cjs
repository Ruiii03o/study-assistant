const fs=require('node:fs'),vm=require('node:vm'),test=require('node:test'),assert=require('node:assert/strict');
const source=fs.readFileSync('frontend/learning-tools.js','utf8');
const code=source.slice(source.indexOf('resourceSearchForm.onsubmit='),source.indexOf("$('material-view').append(resourcesPanel)"));
class N{constructor(tag,text=''){this.tag=tag;this.textContent=text;this.children=[];}append(...n){this.children.push(...n);}replaceChildren(){this.children=[];}querySelector(tag){return this.children.find(n=>n.tag===tag);}}
function setup(api){const c=vm.createContext({api,activeCourse:{id:1},resourceSearchToken:0,resourceSearchButton:{},resourceSearchForm:{},resourceSearchResults:new N('div'),resourceSearchStatus:new N('p'),resourceSubject:{input:{value:'网络'}},resourceSearch:{input:{value:'路由'}},resourceScope:{input:{value:'platforms'}},toolNode:(...a)=>new N(...a),toolButton:(text,fn)=>Object.assign(new N('button',text),{onclick:fn}),loadResources:async()=>{}});vm.runInContext(code,c);return c;}
test('search renders source links and saves exact retrieved URL',async()=>{
 const calls=[];const c=setup(async(path,options)=>{calls.push([path,JSON.parse(options.body)]);return {items:[{id:1,title:'Network',url:'https://www.bilibili.com/video/BV1',source:'哔哩哔哩',kind:'视频',summary:'摘要',summary_basis:'搜索摘要'}]};});
 await c.resourceSearchForm.onsubmit({preventDefault(){}});
 const card=c.resourceSearchResults.children[0],link=card.querySelector('h4').children[0];assert.equal(link.href,'https://www.bilibili.com/video/BV1');assert.equal(link.rel,'noopener noreferrer');
 await card.children.at(-1).onclick();assert.equal(calls[1][1].url,link.href);assert.equal(card.children.at(-1).textContent,'已收藏');
});
test('late search response never fills a different course',async()=>{let resolve;const c=setup(()=>new Promise(r=>resolve=r));const pending=c.resourceSearchForm.onsubmit({preventDefault(){}});c.activeCourse={id:2};c.resourceSearchToken++;resolve({items:[]});await pending;assert.equal(c.resourceSearchResults.children.length,0);});
test('search failure shows message and re-enables retry',async()=>{const c=setup(async()=>{throw Error('offline')});await c.resourceSearchForm.onsubmit({preventDefault(){}});assert.equal(c.resourceSearchStatus.textContent,'offline');assert.equal(c.resourceSearchButton.disabled,false);});
