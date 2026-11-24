// Separate scope and confirmed structure for sample-driven exams.
const blueprintPanel=toolNode('section');blueprintPanel.className='panel';blueprintPanel.id='study-blueprints';
blueprintPanel.innerHTML=`<h2>样卷仿真考试</h2><p>上传老师的样卷，核对结构，选择仅依据样卷或结合课件章节生成新卷。题量与分值严格校验；相同考查方式不代表难度完全相同。</p>
<form id="blueprint-upload"><label>① 上传样卷（单份PDF/DOCX，或按页码命名的多张PNG/JPEG）<input id="blueprint-file" type="file" accept=".pdf,.docx,.png,.jpg,.jpeg" multiple required></label><button>保存样卷</button></form>
<div class="actions"><label>② 选择样卷<select id="blueprint-select"></select></label><button id="blueprint-refresh" type="button">刷新样卷与组卷进度</button></div>
<label class="outline-choice"><input id="blueprint-consent" type="checkbox">我同意将样卷或选定课件发送给已配置的AI服务，识别和分批组卷可能多次计费。</label>
<div class="actions"><button id="blueprint-analyze" type="button">识别样卷结构</button><a id="blueprint-original" hidden>下载原样卷核对</a></div>
<p id="blueprint-message" role="status"></p><div id="blueprint-editor"></div>
<fieldset><legend>③ 选择出题依据</legend><label>出题模式<select id="blueprint-mode"><option value="sample">仅依据样卷：识别知识点，生成同类新题</option><option value="course">样卷＋课件：用选定章节限定出题范围</option></select></label><p id="blueprint-mode-note"></p><div id="blueprint-scope"></div></fieldset>
<p>支持五种题型、每卷最多100题。暂不支持自动还原附图、共用材料和选答规则，请核对后调整结构。多选沿用原评分规则，简答按评分点分配本题分值。</p>
<button id="blueprint-generate" type="button">按已确认结构组卷</button><p id="blueprint-run-message" role="status" aria-live="polite"></p><div id="blueprint-runs"></div>`;
practicePanel.before(blueprintPanel);
let blueprintItems=[],blueprintRanges=[],blueprintToken=0,blueprintDirty=false,blueprintBusy=false,blueprintLoop=false,blueprintEditingId=null,blueprintLoopEpoch=0;
const blueprintSelected=()=>blueprintItems.find(b=>b.id===$('blueprint-select').value);
function blueprintStatus(text){$('blueprint-message').textContent=text;const local=$('blueprint-run-message');if(local)local.textContent=text;}
function updateBlueprintMode(){const sample=$('blueprint-mode').value==='sample';$('blueprint-scope').hidden=sample;$('blueprint-mode-note').textContent=sample?'无需上传课件。根据样卷知识点及同学科相关知识灵活出题，保持题型、题数与分值结构；不保证符合老师课件范围或与原卷难度完全一致。':'请选择已提取文字并保存的章节范围，新题知识依据限定在所选课件内。';}
$('blueprint-mode').onchange=updateBlueprintMode;
updateBlueprintMode();
function resetBlueprints(){blueprintLoopEpoch++;blueprintToken++;blueprintItems=[];blueprintRanges=[];blueprintDirty=false;blueprintLoop=false;blueprintEditingId=null;for(const id of ['blueprint-select','blueprint-editor','blueprint-runs','blueprint-scope'])$(id).replaceChildren();$('blueprint-consent').checked=false;$('blueprint-file').value='';$('blueprint-original').hidden=true;blueprintStatus('');}
async function loadBlueprints(courseId){
  const token=++blueprintToken;
  const [items,groups,runs]=await Promise.all([api(`/courses/${courseId}/blueprints`),api(`/courses/${courseId}/chapters`),api(`/courses/${courseId}/blueprint-runs`)]);
  if(activeCourse?.id!==courseId||token!==blueprintToken)return;
  const selected=$('blueprint-select').value,checked=new Set(Array.from($('blueprint-scope').querySelectorAll('input:checked'),n=>n.value));
  const hadScope=blueprintRanges.length>0;blueprintItems=items;blueprintRanges=groups.flatMap(g=>g.ranges);
  $('blueprint-select').replaceChildren();items.forEach(b=>$('blueprint-select').add(new Option(b.name,b.id)));
  if(items.some(b=>b.id===selected))$('blueprint-select').value=selected;
  $('blueprint-scope').replaceChildren();for(const r of blueprintRanges){const label=toolNode('label');label.className='outline-choice';const check=toolNode('input');check.type='checkbox';check.value=r.key;check.checked=hadScope?checked.has(r.key):true;label.append(check,`${r.title} · ${r.name} · ${r.start_location}—${r.end_location}`);$('blueprint-scope').append(label);}
  if(!blueprintRanges.length)$('blueprint-scope').textContent='请先提取课件文字并保存章节范围。';
  renderBlueprintEditor();renderBlueprintRuns(runs);
}
function renderBlueprintEditor(){
  const target=$('blueprint-editor');target.replaceChildren();blueprintDirty=false;const item=blueprintSelected();blueprintEditingId=item?.id;
  $('blueprint-original').hidden=!item;if(!item)return;
  $('blueprint-original').href=`/api/blueprints/${item.id}/original`;
  const data=item.draft.sections?item.draft:item.confirmed||{title:item.name,sections:[]};
  target.append(toolNode('p',item.confirmed?'已有确认结构。修改后须再次保存；历史组卷使用当时的结构快照。':'待确认：请核对题量、每小题分值和考试时间。'));
  if(data.recognition_note)target.append(toolNode('p',data.recognition_note));
  const warnings=Array.isArray(data.uncertain)?data.uncertain:[];for(const text of warnings)target.append(toolNode('p','待核对：'+String(text)));
  const form=toolNode('form'),meta=toolNode('div');meta.className='practice-counts';
  const title=toolField('试卷标题'),minutes=toolField('时长（分钟）'),total=toolField('总分');
  title.input.value=data.title||item.name;title.input.required=true;title.input.maxLength=150;
  for(const [f,v,max] of [[minutes,data.minutes,180],[total,data.total,1000]]){f.input.type='number';f.input.min=f===minutes?1:0.01;f.input.max=max;f.input.step=f===minutes?1:0.01;f.input.required=true;f.input.value=v??'';}
  meta.append(title.wrap,minutes.wrap,total.wrap);form.append(meta);const rows=toolNode('div');form.append(rows);const entries=[];
  const summary=toolNode('p');summary.setAttribute('role','status');
  const mismatch=toolNode('div');mismatch.className='blueprint-score-warning';mismatch.setAttribute('role','alert');
  const mismatchText=toolNode('p'),fixActions=toolNode('div');fixActions.className='actions';
  const scoreTotal=()=>Math.round(entries.reduce((sum,e)=>sum+Number(e.count.input.value||0)*Number(e.points.input.value||0),0)*100)/100;
  function refreshMismatch(){const sum=scoreTotal(),declared=Number(total.input.value);mismatch.hidden=!total.input.value||Math.round(sum*100)===Math.round(declared*100);mismatchText.textContent=`分值不一致：各题合计 ${sum} 分，声明总分 ${declared} 分，相差 ${Math.round(Math.abs(sum-declared)*100)/100} 分。当前不能保存确认，请对照原卷修正总分、题数或每题分值，或补充遗漏结构行。`;}
  fixActions.append(toolButton('修改声明总分',()=>{total.input.focus();total.input.select();}),toolButton('以当前合计作为总分',()=>{const sum=scoreTotal();if(sum<=0||sum>1000){blueprintStatus('合计须在0至1000分之间，请先检查结构行。');return;}if(confirm(`确认题数和每题分值均正确，将声明总分改为 ${sum} 分？此操作不会补回遗漏题目。`)){total.input.value=String(sum);blueprintDirty=true;tally();refreshMismatch();}}),toolButton('添加遗漏结构行',()=>{if(entries.length>=20){blueprintStatus('最多20行');return;}add();blueprintDirty=true;entries.at(-1).name.input.focus();refreshMismatch();}));mismatch.append(mismatchText,fixActions);
  function tally(){for(const e of entries){e.subtotal.textContent=e.count.input.value&&e.points.input.value?`本大题合计：${Math.round(Number(e.count.input.value)*Number(e.points.input.value)*100)/100} 分`:'本大题合计：待填写题数与每题分值';}const qs=entries.reduce((a,e)=>a+Number(e.count.input.value||0),0),points=entries.reduce((a,e)=>a+Number(e.count.input.value||0)*Number(e.points.input.value||0),0);summary.textContent=`当前合计 ${qs} 题 / ${Math.round(points*100)/100} 分；声明总分 ${total.input.value||'待填写'}。`;}
  function add(s={}){
    const box=toolNode('fieldset'),name=toolField('大题名称'),kind=toolField('题型','select'),count=toolField('小题数量'),points=toolField('每小题分值'),skill=toolField('考查方式（如：给出地址和掩码，计算网络地址）','textarea'),evidence=toolField('原卷依据 / 页码');
    kind.input.add(new Option('请选择题型',''));for(const [k,v] of Object.entries(practiceKinds))kind.input.add(new Option(v,k));kind.input.value=s.kind||'';kind.input.required=true;
    name.input.value=s.title||'';name.input.required=true;name.input.maxLength=100;skill.input.value=s.skill||'';skill.input.maxLength=1000;evidence.input.value=s.evidence||'';evidence.input.maxLength=1200;
    for(const [f,v] of [[count,s.count],[points,s.points]]){f.input.type='number';f.input.min=1;f.input.max=100;f.input.step=f===count?1:0.01;f.input.min=f===count?1:0.01;f.input.required=true;f.input.value=v??'';}
    const subtotal=toolNode('p');subtotal.className='blueprint-subtotal';const entry={box,name,kind,count,points,skill,evidence,subtotal};entries.push(entry);const layout=toolNode('div');layout.className='practice-counts';layout.append(name.wrap,kind.wrap,count.wrap,points.wrap);box.append(layout,subtotal,skill.wrap,evidence.wrap,toolButton('移除此行',()=>{entries.splice(entries.indexOf(entry),1);box.remove();blueprintDirty=true;tally();}));rows.append(box);tally();
  }
  (data.sections||[]).forEach(add);
  const confirmLabel=toolNode('label'),check=toolNode('input');check.type='checkbox';check.required=true;confirmLabel.className='outline-choice';confirmLabel.append(check,'我已对照原卷核对结构，并处理上述待核对项。');
  const actions=toolNode('div');actions.className='actions';const save=toolNode('button','保存并确认结构');save.className='primary';actions.append(toolButton('添加结构行',()=>{if(entries.length>=20){blueprintStatus('最多20行');return;}add();blueprintDirty=true;}),save);form.append(summary,confirmLabel,actions);target.append(form);tally();
  summary.after(mismatch);refreshMismatch();
  form.oninput=()=>{blueprintDirty=true;tally();refreshMismatch();};
  form.addEventListener('click',()=>queueMicrotask(refreshMismatch));
  form.onsubmit=async e=>{e.preventDefault();if(blueprintBusy)return;const course=activeCourse.id;
    const sections=entries.map(e=>({title:e.name.input.value,kind:e.kind.input.value,count:Number(e.count.input.value),points:Number(e.points.input.value),skill:e.skill.input.value,evidence:e.evidence.input.value}));
    if(Math.round(scoreTotal()*100)!==Math.round(Number(total.input.value)*100)){refreshMismatch();alert(mismatchText.textContent);mismatch.scrollIntoView({block:'center'});total.input.focus();return;}
    if(!sections.length||sections.reduce((n,s)=>n+s.count,0)>100){blueprintStatus('请核对结构：需要1—100题。');return;}
    save.disabled=true;blueprintBusy=true;
    try{const result=await api(`/blueprints/${item.id}`,{method:'PUT',body:JSON.stringify({revision:item.revision,blueprint:{title:title.input.value,minutes:Number(minutes.input.value),total:Number(total.input.value),sections}})});if(activeCourse?.id!==course)return;Object.assign(item,result);item.draft={};blueprintDirty=false;blueprintStatus('结构已确认，请在下方选择出题模式后组卷。');}
    catch(error){if(activeCourse?.id===course)blueprintStatus(error.message);}finally{save.disabled=false;blueprintBusy=false;}
  };
}
$('blueprint-upload').onsubmit=async e=>{e.preventDefault();if(blueprintBusy)return;const files=Array.from($('blueprint-file').files).sort((a,b)=>a.name.localeCompare(b.name,undefined,{numeric:true})),file=files[0],course=activeCourse?.id;if(!file||!course)return;if(file.size>15*1024*1024){blueprintStatus('文件不能超过15MB');return;}blueprintBusy=true;
  try{let result;if(files.length>1){if(files.length>12||files.some(f=>!['image/png','image/jpeg'].includes(f.type)||f.size>4*1024*1024)||files.reduce((n,f)=>n+f.size,0)>15*1024*1024)throw new Error('多张上传只支持PNG/JPEG，最多12张、每张4MB、合计15MB。');const pages=await Promise.all(files.map(f=>new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(new Error('图片读取失败'));reader.readAsDataURL(f);})));result=await api(`/courses/${course}/blueprint-photos`,{method:'POST',body:JSON.stringify({pages})});}else{result=await api(`/courses/${course}/blueprints?name=${encodeURIComponent(file.name)}`,{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file});}if(activeCourse?.id!==course)return;await loadBlueprints(course);$('blueprint-select').value=result.id;renderBlueprintEditor();blueprintStatus('样卷已保存，尚未调用AI；可识别结构或手动填写。');}catch(error){if(activeCourse?.id===course)blueprintStatus(error.message);}finally{blueprintBusy=false;}};
$('blueprint-select').onchange=()=>{if(blueprintBusy||(blueprintDirty&&!confirm('切换样卷会丢弃未保存的结构编辑，继续吗？'))){$('blueprint-select').value=blueprintEditingId;return;}renderBlueprintEditor();};
$('blueprint-refresh').onclick=async()=>{if(blueprintBusy)return;if(blueprintDirty&&!confirm('刷新会丢弃未保存的结构编辑，继续吗？'))return;try{await loadBlueprints(activeCourse.id);}catch(e){blueprintStatus(e.message);}};
$('blueprint-analyze').onclick=async()=>{const item=blueprintSelected(),course=activeCourse?.id;if(!item||blueprintBusy)return;if(!$('blueprint-consent').checked){blueprintStatus('请先勾选AI发送授权。');return;}if(blueprintDirty&&!confirm('识别结果会替换当前未保存的结构编辑，继续吗？'))return;blueprintBusy=true;blueprintStatus('正在识别样卷结构，请稍候……');
  try{const result=await api(`/blueprints/${item.id}/analyze`,{method:'POST'});if(activeCourse?.id!==course)return;Object.assign(item,result);renderBlueprintEditor();blueprintStatus('识别结果是草稿，请逐项核对后确认。');}catch(e){if(activeCourse?.id===course)blueprintStatus(e.message);}finally{blueprintBusy=false;}};
$('blueprint-generate').onclick=async()=>{const item=blueprintSelected(),course=activeCourse?.id;if(blueprintBusy)return;if(!item?.confirmed||blueprintDirty){blueprintStatus('请先保存并确认当前结构。');return;}if(!$('blueprint-consent').checked){blueprintStatus('请先勾选AI发送授权。');return;}
  const mode=$('blueprint-mode').value,keys=new Set(mode==='course'?Array.from($('blueprint-scope').querySelectorAll('input:checked'),n=>n.value):[]),ranges=blueprintRanges.filter(r=>keys.has(r.key));if(mode==='course'&&!ranges.length){blueprintStatus('请选择课程范围，或切换为仅依据样卷。');return;}blueprintBusy=true;
  try{const health=await api('/health');if(mode==='sample'&&!health.capabilities?.includes('sample-only-exams'))throw new Error('后台仍在运行旧版本，尚不支持仅样卷模式。请停止当前 run.py 后重新运行，再刷新网页；本次未创建任务，也未调用 AI。');blueprintStatus('正在创建组卷任务……');await api(`/blueprints/${item.id}/runs`,{method:'POST',body:JSON.stringify({revision:item.revision,mode,material_ids:[...new Set(ranges.map(r=>r.material_id))],chapter_keys:[...keys],request_id:crypto.randomUUID()})});if(activeCourse?.id!==course)return;const runs=await api(`/courses/${course}/blueprint-runs`);if(activeCourse?.id!==course)return;renderBlueprintRuns(runs);blueprintStatus('组卷任务已建立，点击“继续分批组卷”开始。');}catch(e){if(activeCourse?.id===course)blueprintStatus(e.message);}finally{blueprintBusy=false;}};
let blueprintRequestActive=false;
function renderBlueprintRuns(runs){
 const target=$('blueprint-runs');target.replaceChildren();target.append(toolNode('h3','仿真组卷进度'));
 for(const run of runs){
  const box=toolNode('section');box.className='batch-progress';
  const status=toolNode('p',`${run.done}/${run.total} 步 · ${run.status==='ready'?'试卷已就绪':run.status==='failed'?'本步失败，可重试':'待继续'}`),message=toolNode('p',run.message);
  message.setAttribute?.('role','status');
  box.append(toolNode('p',run.mode==='sample'?'样卷及相关知识 · 灵活出题':'样卷＋课件 · 限定章节范围'),status,message);
  const steps=toolNode('details');steps.append(toolNode('summary','查看分批范围与步骤'));for(const [i,step] of (run.steps||[]).entries()){steps.append(toolNode('p',`${i+1}. ${step.title} · ${step.done?'已完成':'待处理'}`));for(const warning of step.warnings||[])steps.append(toolNode('p',warning));}box.append(steps);
  if(run.practice_id)box.append(toolButton('打开仿真考试',()=>showPractice(run.practice_id,activeCourse.id)));
  else{
   const actions=toolNode('div');actions.className='actions';
   const go=toolButton('继续分批组卷',async()=>{
    if(blueprintRequestActive){message.textContent='当前请求尚未返回，请稍候；可停止后续自动组卷。';return;}
    if(!$('blueprint-consent').checked){message.textContent='请先勾选AI发送授权。';blueprintStatus(message.textContent);return;}
    const course=activeCourse.id,epoch=++blueprintLoopEpoch;blueprintLoop=true;blueprintRequestActive=true;go.disabled=true;let current=run;
    message.textContent='正在处理当前步骤，请稍候……';
    try{
     while(blueprintLoop&&epoch===blueprintLoopEpoch&&activeCourse?.id===course&&current.status!=='ready'){
      const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),210000);
      try{current=await api(`/blueprint-runs/${run.id}/next`,{method:'POST',signal:controller.signal});}finally{clearTimeout(timer);}
      if(activeCourse?.id!==course||epoch!==blueprintLoopEpoch)return;
      Object.assign(run,current);status.textContent=`${current.done}/${current.total} 步`;message.textContent=current.message;
      if(current.status==='failed'){blueprintStatus(current.message);break;}
     }
    }catch(e){if(activeCourse?.id===course){message.textContent=e.message+' 请先刷新进度确认后台结果，再决定是否重试。';run.message=message.textContent;blueprintStatus(message.textContent);}}
    finally{
     blueprintRequestActive=false;if(epoch===blueprintLoopEpoch)blueprintLoop=false;go.disabled=false;
     if(activeCourse?.id===course&&epoch===blueprintLoopEpoch){renderBlueprintRuns(runs);if(current.status==='ready')loadPracticeHistory(course).catch(e=>blueprintStatus(e.message));}
    }
   });
   const pause=toolButton('本步完成后暂停',()=>{blueprintLoop=false;message.textContent=blueprintRequestActive?'已请求暂停：当前AI请求返回并保存后停止，不再开始下一步。':'当前没有正在执行的请求，已暂停；可点击继续分批组卷。';blueprintStatus(message.textContent);});
   actions.append(go,pause);box.append(actions);
  }
  target.append(box);
 }
}
const beforeBlueprintEnter=enterCourse;enterCourse=async function(course){resetBlueprints();await beforeBlueprintEnter(course);if(activeCourse?.id===course.id)try{await loadBlueprints(course.id);}catch(e){if(activeCourse?.id===course.id)blueprintStatus(e.message);}};
const beforeBlueprintAuth=showAuth;showAuth=function(){resetBlueprints();beforeBlueprintAuth();};
