const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
test('account controls retain handlers and admin group follows session role',async()=>{
 const node=()=>({hidden:false,children:[],append(...nodes){this.children.push(...nodes);},replaceChildren(...nodes){this.children=nodes;},setAttribute(){}});
 const account=node(),username=node(),logout=node(),settings=node(),admin=node();admin.hidden=true;
 const handler=()=>{};settings.onclick=handler;admin.onclick=handler;
 const c=vm.createContext({document:{querySelector:()=>account},$:id=>id==='username'?username:logout,
 practiceText:()=>node(),accountButton:settings,adminUsersButton:admin,showWorkspace:async()=>{},showAuth(){},MutationObserver:class{observe(){}}});
 vm.runInContext(fs.readFileSync('frontend/account-sidebar.js','utf8'),c);
 assert.equal(account.children.length,3);assert.equal(account.children[0].hidden,true);
 assert.equal(account.children[1].children[0],username);assert.equal(account.children[2].children[0],settings);assert.equal(settings.onclick,handler);
 await c.showWorkspace({role:'admin'});assert.equal(account.children[0].hidden,false);assert.equal(account.children[1].children[1].hidden,false);
 await c.showWorkspace({role:'user'});assert.equal(account.children[0].hidden,true);
 await c.showWorkspace({role:'admin'});c.showAuth();assert.equal(account.children[0].hidden,true);
});
