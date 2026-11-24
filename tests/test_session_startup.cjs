const fs=require('node:fs'),vm=require('node:vm'),test=require('node:test'),assert=require('node:assert/strict');
const code=fs.readFileSync('frontend/session-startup.js','utf8');
function setup(state='loading'){
 let ready,resolve,reject;const calls=[],nodes={loading:{hidden:false},'auth-message':{textContent:''}};
 const response=new Promise((a,b)=>{resolve=a;reject=b;});
 const c=vm.createContext({document:{readyState:state,addEventListener:(type,fn,options)=>{assert.equal(type,'DOMContentLoaded');assert.equal(options.once,true);ready=fn;}},api:()=>{calls.push('request');return response;},showWorkspace:u=>calls.push('old'),showAuth:()=>calls.push('auth'),$:id=>nodes[id]});
 vm.runInContext(code,c);return {c,calls,nodes,resolve,reject,ready:()=>ready()};
}
test('automatic login waits for UI and resolves the current workspace handler after response',async()=>{
 const x=setup();assert.deepEqual(x.calls,[]);const pending=x.ready();x.c.showWorkspace=u=>x.calls.push(u.role);x.resolve({username:'rui',role:'admin'});await pending;assert.deepEqual(x.calls,['request','admin']);assert.equal(x.nodes.loading.hidden,true);
});
test('already loaded page restores ordinary user through same handler',async()=>{
 const x=setup('complete');x.c.showWorkspace=u=>x.calls.push(u.role);x.resolve({username:'student',role:'user'});await new Promise(r=>setImmediate(r));assert.deepEqual(x.calls,['request','user']);
});
test('expired session clears account UI and loading screen',async()=>{
 const x=setup();const pending=x.ready();x.reject(Error('请先登录'));await pending;assert.deepEqual(x.calls,['request','auth']);assert.equal(x.nodes.loading.hidden,true);
});
test('startup script follows permission and sidebar scripts',()=>{
 const html=fs.readFileSync('frontend/index.html','utf8');for(const name of ['learning-tools.js','account-sidebar.js','report.js'])assert.ok(html.indexOf('session-startup.js')>html.indexOf(name));assert.ok(!fs.readFileSync('frontend/report.js','utf8').includes('showWorkspace(await api('));
});
