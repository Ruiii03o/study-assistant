const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const source=fs.readFileSync('frontend/workbench.js','utf8');
class Node{
 constructor(tag='div',id=''){this.tag=tag;this.id=id;this.children=[];this.dataset={};this.attrs={};this.hidden=false;this.className='';this.parent=null;}
 append(...nodes){for(const n of nodes){if(n.parent)n.parent.children=n.parent.children.filter(x=>x!==n);n.parent=this;this.children.push(n);}}
 after(n){const p=this.parent;if(n.parent)n.parent.children=n.parent.children.filter(x=>x!==n);n.parent=p;p.children.splice(p.children.indexOf(this)+1,0,n);}
 setAttribute(k,v){this.attrs[k]=v;}
 matches(s){if(s.includes(','))return s.split(',').some(x=>this.matches(x));if(s[0]==='#')return this.id===s.slice(1);if(s[0]==='.')return this.className.split(' ').includes(s.slice(1));if(s.startsWith('[data-')){const key=s.slice(6,-1).replace(/-([a-z])/g,(_,c)=>c.toUpperCase());return key in this.dataset;}return this.tag===s;}
 querySelectorAll(s){return this.children.flatMap(n=>[...(n.matches(s)?[n]:[]),...n.querySelectorAll(s)]);}
 querySelector(s){return this.querySelectorAll(s)[0]||null;}
}
function setup(){const view=new Node('main','material-view'),hero=new Node('section');hero.className='hero';hero.append(new Node('p'));view.append(new Node('header'),hero);
 const refs={};for(const [id,tag] of [['upload-form','form'],['outline-form','form'],['practice-create-form','form'],['blueprint-upload','form'],['mistake-items','div'],['report-content','div']]){const panel=new Node('section'),n=new Node(tag,id);panel.className='panel';panel.append(n);view.append(panel);refs[id]=n;}
 const session=new Node('section','practice-session');refs['practice-create-form'].parent.append(session);const detail=new Node('section','material-detail');detail.hidden=true;view.append(new Node('section','material-list'),detail,new Node('section','study-resources'));
 const win={scrollY:0,scrollTo(o){this.scrollY=o.top;}};const c=vm.createContext({$:id=>id===view.id?view:view.querySelector('#'+id),practiceText:(tag,text='',cls='')=>{const n=new Node(tag);n.textContent=text;n.className=cls;return n;},MutationObserver:class{observe(){}},addQuestionNavigator:()=>{},activeCourse:{id:1,name:'Course'},window:win});
 vm.runInContext(source.slice(0,source.indexOf('const taskEnterCourse')),c);c.installStudyNavigation();return {c,view,refs,win,detail};}
test('task pages separate materials, review and exam without discarding DOM',()=>{const {c,view,refs,detail}=setup();assert.equal(view.querySelector('#task-materials').hidden,false);assert.equal(view.querySelector('#task-review').hidden,true);assert.equal(detail.hidden,true);
 refs['outline-form'].draft='saved local edit';c.navigateStudy('review');assert.equal(view.querySelector('#task-materials').hidden,true);assert.equal(view.querySelector('#task-review').hidden,false);assert.equal(refs['outline-form'].draft,'saved local edit');assert.equal(refs['outline-form'].parent.parent.id,'task-review');
 c.navigateStudy('train',{subpage:'exam'});const groups=view.querySelector('#task-train').querySelectorAll('[data-train-page]');assert.equal(groups.find(n=>n.dataset.trainPage==='practice').hidden,true);assert.equal(groups.find(n=>n.dataset.trainPage==='exam').hidden,false);
 assert.equal(view.querySelector('#practice-session').parent.id,'task-answer');});
test('returning to a task restores position and keeps selections',()=>{const {c,win,refs}=setup();win.scrollY=320;refs['upload-form'].selected='material';c.navigateStudy('mistakes');win.scrollY=700;c.navigateStudy('materials');assert.equal(win.scrollY,320);assert.equal(refs['upload-form'].selected,'material');c.navigateStudy('mistakes');assert.equal(win.scrollY,700);});
