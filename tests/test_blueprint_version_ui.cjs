const fs=require('node:fs'),vm=require('node:vm'),test=require('node:test'),assert=require('node:assert/strict');
const source=fs.readFileSync('frontend/blueprints.js','utf8');
function setup(capabilities){
 const calls=[],messages=[],nodes={'blueprint-generate':{},'blueprint-consent':{checked:true},'blueprint-mode':{value:'sample'},'blueprint-scope':{querySelectorAll:()=>[]}};
 const ctx=vm.createContext({$:id=>nodes[id],blueprintSelected:()=>({id:'b1',revision:1,confirmed:{}}),activeCourse:{id:1},blueprintBusy:false,blueprintDirty:false,blueprintRanges:[],crypto:{randomUUID:()=> 'request-test-123456'},blueprintStatus:m=>messages.push(m),renderBlueprintRuns:()=>{},api:async(path)=>{calls.push(path);return path==='/health'?{capabilities}:[];}});
 vm.runInContext(source.slice(source.indexOf("$('blueprint-generate').onclick"),source.indexOf('function renderBlueprintRuns')),ctx);
 return {calls,messages,click:nodes['blueprint-generate'].onclick,ctx};
}
test('old running server is explained before creating sample task',async()=>{const s=setup(undefined);await s.click();assert.deepEqual(s.calls,['/health']);assert.match(s.messages.at(-1),/旧版本/);assert.equal(s.ctx.blueprintBusy,false);});
test('compatible server accepts task and refreshes progress',async()=>{const s=setup(['sample-only-exams']);await s.click();assert.deepEqual(s.calls,['/health','/blueprints/b1/runs','/courses/1/blueprint-runs']);assert.match(s.messages.at(-1),/已建立/);});
