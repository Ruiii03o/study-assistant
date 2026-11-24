// Functional additions only: reuse the existing paper layout and real controls.
function toolNode(tag,text=''){const n=document.createElement(tag);n.textContent=text;return n;}
function toolButton(text,action){const n=toolNode('button',text);n.type='button';n.onclick=action;return n;}
function toolField(label,tag='input'){const wrap=toolNode('label',label);const input=document.createElement(tag);wrap.append(input);return {wrap,input};}
function toolDownload(name,text){const url=URL.createObjectURL(new Blob([text],{type:'text/plain;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function toolDialog(title){const d=document.createElement('dialog');d.className='learning-dialog';d.style.cssText='max-width:780px;width:calc(100% - 32px);max-height:90vh;overflow:auto';const message=toolNode('p');message.setAttribute('role','status');const close=toolButton('关闭',()=>d.close());d.append(toolNode('h2',title),close,message);d.addEventListener('close',()=>d.remove());document.body.append(d);d.showModal();return {d,message,close};}

async function loadKnowledgeEdits(record,book,entries,draw){
  try {
    const notes=await api(`/learning-notes/${record.id}`);
    if(!book.isConnected)return;
    notes.forEach(note=>{const e=entries[note.point_index];if(e){e.savedNote=note;e.point.text=note.text;}});draw();
    const exportButton=toolButton('导出修订与个人批注',()=>{
      const lines=['# 过了么 · 我的复习笔记','知识点修订和重点标记由用户填写；AI原文与引用仍保留。',''];
      entries.forEach(e=>{lines.push('## '+e.title,e.savedNote?.important?'【我的重点】':'',e.point.text,'',e.savedNote?.note?'我的批注：'+e.savedNote.note:'','AI原文：'+e.originalText,'引用编号：'+e.point.source_ids.join('、'),'');});
      toolDownload('复习笔记.md',lines.join('\n'));
    });book.append(exportButton);
  }catch(e){if(book.isConnected)book.append(toolNode('p','个人笔记：'+e.message));}
}
function renderKnowledgeControls(record,entry,index,card,draw){
  if(entry.savedNote?.important)card.append(toolNode('strong','★ 我的重点'));
  if(entry.savedNote?.note)card.append(toolNode('p','我的批注：'+entry.savedNote.note));
  if(entry.savedNote){const original=document.createElement('details');original.append(toolNode('summary','查看原文'),toolNode('p',entry.originalText));card.append(original);}
  card.append(toolButton('编辑知识点 / 标记重点',async()=>{
    const {d,message,close}=toolDialog('我的修订与批注');message.textContent='正在加载最新笔记…';
    try{
      const all=await api(`/learning-notes/${record.id}`);if(!d.isConnected)return;
      const saved=all.find(n=>n.point_index===index);let dirty=false;
      const text=toolField('知识点内容（用户修订）','textarea');text.input.rows=7;text.input.maxLength=12000;text.input.value=saved?.text??entry.originalText;
      const note=toolField('个人批注','textarea');note.input.rows=4;note.input.maxLength=8000;note.input.value=saved?.note??'';
      const mark=toolField('标记为我的重点');mark.input.type='checkbox';mark.input.checked=!!saved?.important;
      const discard=()=>!dirty||confirm('修订尚未保存，确认放弃？');close.onclick=()=>{if(discard())d.close();};d.addEventListener('cancel',e=>{if(!discard())e.preventDefault();});
      [text.input,note.input,mark.input].forEach(n=>n.oninput=()=>{dirty=true;});
      const save=toolButton('保存修订',async()=>{
        save.disabled=true;message.textContent='正在保存…';
        const body={revision:saved?.revision??0,text:text.input.value,note:note.input.value,important:mark.input.checked};
        try{const result=await api(`/learning-notes/${record.id}/${index}`,{method:'PUT',body:JSON.stringify(body)});entry.savedNote={...body,revision:result.revision};entry.point.text=body.text;dirty=false;draw();d.close();}
        catch(e){message.textContent=e.message;}finally{save.disabled=false;}
      });
      d.append(toolNode('p','原文出处不随修订改变；个人重点与 AI 内容分开记录。'),text.wrap,note.wrap,mark.wrap,save);message.textContent='';
    }catch(e){message.textContent=e.message;}
  }));
}

const resourcesPanel=toolNode('section');resourcesPanel.className='panel';resourcesPanel.id='study-resources';
const resourceList=toolNode('div'),resourceMessage=toolNode('p');resourceMessage.setAttribute('role','status');
let resourceRequest=0;
async function loadResources(courseId){
  const token=++resourceRequest;resourceList.replaceChildren();resourceMessage.textContent='正在加载资源…';
  try{const items=await api(`/courses/${courseId}/resources`);if(token!==resourceRequest||activeCourse?.id!==courseId)return;
    items.forEach(item=>{const row=toolNode('article');const link=toolNode('a',item.title);link.href=item.url;link.target='_blank';link.rel='noopener noreferrer';
      row.append(link,toolNode('p',item.note),toolButton('移除收藏',async()=>{if(!confirm('移除这条资源收藏？'))return;try{await api(`/resources/${item.id}`,{method:'DELETE'});if(activeCourse?.id===courseId)await loadResources(courseId);}catch(e){resourceMessage.textContent=e.message;}}));resourceList.append(row);});
    resourceMessage.textContent=items.length?`已收藏 ${items.length} 条资源`:'暂无收藏。可保存教材配套网站、课程视频或检索结果的链接。';
  }catch(e){if(token===resourceRequest&&activeCourse?.id===courseId)resourceMessage.textContent=e.message;}
}
function resourceForm(){
  if(!activeCourse)return;const courseId=activeCourse.id;const {d,message}=toolDialog('收藏课程资源');const form=document.createElement('form');
  const title=toolField('标题'),url=toolField('网页链接'),note=toolField('备注','textarea');title.input.required=url.input.required=true;title.input.maxLength=150;url.input.type='url';url.input.maxLength=2000;note.input.maxLength=4000;
  const save=toolNode('button','保存收藏');form.append(title.wrap,url.wrap,note.wrap,save);d.append(form);
  form.onsubmit=async e=>{e.preventDefault();save.disabled=true;try{await api(`/courses/${courseId}/resources`,{method:'POST',body:JSON.stringify({title:title.input.value,url:url.input.value,note:note.input.value})});d.close();if(activeCourse?.id===courseId)await loadResources(courseId);}catch(e){message.textContent=e.message;}finally{save.disabled=false;}};
}
const resourceActions=toolNode('div');resourceActions.className='actions';resourceActions.append(toolButton('收藏链接',resourceForm),toolButton('刷新资源',()=>{if(activeCourse)loadResources(activeCourse.id);}));
resourcesPanel.append(toolNode('h2','课程资源库'),toolNode('p','保存你的学习链接'),resourceActions,resourceMessage,resourceList);
const resourceSearch=toolField('知识点');resourceSearch.input.type='search';resourceSearch.input.maxLength=25;resourceSearch.input.placeholder='例如：网络层';
const resourceSubject=toolField('学科');resourceSubject.input.maxLength=20;resourceSubject.input.required=true;resourceSubject.input.placeholder='例如：计算机网络';
const resourceScope=toolField('检索范围','select');resourceScope.input.add(new Option('主流学习平台','platforms'));resourceScope.input.add(new Option('公开网页','web'));
const resourceSearchResults=toolNode('div'),resourceSearchStatus=toolNode('p');resourceSearchStatus.setAttribute('role','status');
const resourceSearchForm=document.createElement('form');resourceSearch.input.required=true;
const resourceSearchButton=toolNode('button','搜索学习资源');
resourceSearchForm.append(resourceSubject.wrap,resourceSearch.wrap,resourceScope.wrap,toolNode('p','优先查找 B站、CSDN 和慕课资源。搜索与 AI 整理可能产生接口费用；相同检索10分钟内复用结果。'),resourceSearchButton);
resourcesPanel.append(toolNode('h3','按知识点找资源'),resourceSearchForm,resourceSearchStatus,resourceSearchResults);
let resourceSearchToken=0;
function resetResourceSearch(course){resourceSearchToken++;resourceSearchResults.replaceChildren();resourceSearchStatus.textContent='';resourceSearchButton.disabled=false;resourceSubject.input.value=course?.name?.slice(0,20)||'';resourceSearch.input.value='';}
resourceSearchForm.onsubmit=async event=>{
  event.preventDefault();if(!activeCourse||resourceSearchButton.disabled)return;
  const courseId=activeCourse.id,token=++resourceSearchToken;
  resourceSearchButton.disabled=true;resourceSearchResults.replaceChildren();resourceSearchStatus.textContent='正在搜索并整理资源，请稍候…';
  try{
    const data=await api(`/courses/${courseId}/resource-search`,{method:'POST',body:JSON.stringify({subject:resourceSubject.input.value.trim(),topic:resourceSearch.input.value.trim(),scope:resourceScope.input.value})});
    if(token!==resourceSearchToken||activeCourse?.id!==courseId)return;
    resourceSearchStatus.textContent=data.items.length?`找到 ${data.items.length} 条资源${data.cached?'（复用近期结果）':''}。${data.warning||''}`:'未找到符合范围的资源，可换一个知识点或选择“公开网页”。';
    for(const item of data.items){
      const card=toolNode('article');card.className='resource-result';
      const link=toolNode('a',item.title);link.href=item.url;link.target='_blank';link.rel='noopener noreferrer';
      const summary=toolNode('p',item.summary||'暂无摘要，请打开原网页查看。');
      const save=toolButton('收藏资源',async()=>{save.disabled=true;try{await api(`/courses/${courseId}/resources`,{method:'POST',body:JSON.stringify({title:item.title,url:item.url,note:`${item.source} · ${item.kind}\n${item.summary}`})});save.textContent='已收藏';if(activeCourse?.id===courseId)await loadResources(courseId);}catch(e){save.disabled=false;resourceSearchStatus.textContent=e.message;}});
      card.append(toolNode('span',`${item.source} · ${item.kind}`),toolNode('h4'),summary,toolNode('small',item.summary_basis+'；未核验完整视频或课程内容。'),save);card.querySelector('h4').append(link);resourceSearchResults.append(card);
    }
  }catch(e){if(token===resourceSearchToken&&activeCourse?.id===courseId)resourceSearchStatus.textContent=e.message;}
  finally{if(token===resourceSearchToken)resourceSearchButton.disabled=false;}
};
$('material-view').append(resourcesPanel);
const originalEnterCourse=enterCourse;
enterCourse=async function(course){resetResourceSearch(course);await originalEnterCourse(course);if(activeCourse?.id===course.id)loadResources(course.id);};
const originalToolsShowAuth=showAuth;
showAuth=function(){originalToolsShowAuth();$('material-view').hidden=true;document.querySelectorAll('dialog.learning-dialog').forEach(d=>{d.close();d.remove();});resourceRequest++;resourceList.replaceChildren();resourceMessage.textContent='';resetResourceSearch(null);};

const accountButton=toolButton('账户与管理',async()=>{
  const {d,message}=toolDialog('账户设置');
  try{const user=await api('/auth/me');if(!d.isConnected)return;d.append(toolNode('p',`当前用户：${user.username}`));
    const form=document.createElement('form'),old=toolField('原密码'),next=toolField('新密码（至少10位）');
    old.input.type=next.input.type='password';old.input.autocomplete='current-password';next.input.autocomplete='new-password';old.input.required=next.input.required=true;next.input.minLength=10;old.input.maxLength=next.input.maxLength=128;
    const save=toolNode('button','修改密码并重新登录');form.append(old.wrap,next.wrap,save);d.append(form);
    form.onsubmit=async e=>{e.preventDefault();save.disabled=true;try{await api('/auth/password',{method:'POST',body:JSON.stringify({old_password:old.input.value,new_password:next.input.value})});d.close();showAuth();$('auth-message').textContent='密码已修改，请重新登录。';}catch(e){message.textContent=e.message;}finally{save.disabled=false;}};
    if(user.role==='admin') d.append(toolButton('用户管理',openUserManagement));
  }catch(e){message.textContent=e.message;}
});$('logout').before(accountButton);

async function openUserManagement(){
  const {d,message}=toolDialog('用户管理');
  const list=toolNode('section');
  d.append(toolNode('p','查看账号及其权限，启用或停用普通用户。管理员权限仍通过本地维护命令设置。'),list);
  async function refresh(){
    const users=await api('/admin/users');
    if(!d.isConnected)return;
    list.replaceChildren();
    for(const user of users){
      const row=toolNode('div');row.className='admin-user-row';
      row.append(toolNode('strong',user.username),toolNode('span',user.role==='admin'?'管理员':'普通用户'),toolNode('span',user.active?'已启用':'已停用'));
      if(user.role!=='admin'){
        const action=toolButton(user.active?'停用账号':'启用账号',async()=>{
          if(!confirm(`确定${user.active?'停用':'启用'} ${user.username}？`))return;
          action.disabled=true;message.textContent='';
          try{await api(`/admin/users/${user.id}/active`,{method:'PUT',body:JSON.stringify({active:!user.active})});await refresh();}
          catch(e){message.textContent=e.message;action.disabled=false;}
        });row.append(action);
      }
      list.append(row);
    }
  }
  const refreshButton=toolButton('刷新用户列表',async()=>{refreshButton.disabled=true;try{await refresh();message.textContent='';}catch(e){message.textContent=e.message;}finally{refreshButton.disabled=false;}});
  d.append(refreshButton);
  try{await refresh();}catch(e){message.textContent=e.message;}
}
const adminUsersButton=toolButton('用户管理',openUserManagement);
adminUsersButton.id='admin-users-button';adminUsersButton.hidden=true;
$('logout').before(adminUsersButton);
const beforeAdminShowWorkspace=showWorkspace;
showWorkspace=async function(user){
  adminUsersButton.hidden=user.role!=='admin';
  await beforeAdminShowWorkspace(user);
};
const beforeAdminShowAuth=showAuth;
showAuth=function(){adminUsersButton.hidden=true;beforeAdminShowAuth();};

async function startMistakeVariant(item,button){
  if(!activeCourse||practiceDirty||practiceSaving){$('mistake-message').textContent='请先保存当前作答或评分，再生成变式。';return;}
  if(!confirm('将把本错题及其原文依据发送给已配置的 AI 生成一道新题，可能产生接口费用。继续？'))return;
  const courseId=activeCourse.id;button.disabled=true;
  try{const result=await api(`/practices/${item.practice_id}/variant`,{method:'POST',body:JSON.stringify({question_id:item.question.id,request_id:crypto.randomUUID()})});if(activeCourse?.id!==courseId)return;await loadPracticeHistory(courseId);if(activeCourse?.id===courseId){$('mistake-message').textContent=result.message||'已创建独立变式，成绩与原题重做分开统计。';await showPractice(result.id,courseId);}}
  catch(e){if(activeCourse?.id===courseId)$('mistake-message').textContent=e.message+'。网络中断时先刷新练习记录，确认是否已生成。';}finally{button.disabled=false;}
}

async function showMistakeKnowledge(item){
  const {d,message}=toolDialog('知识点梳理');message.textContent='正在整理本题已有的知识与来源…';
  try{
    const data=await api(`/practices/${item.practice_id}/knowledge/${item.question.id}`);
    if(!d.isConnected)return;
    d.append(toolNode('h3','本题知识与核对要点'));
    if(data.key_points.length){const list=toolNode('ul');data.key_points.forEach(point=>list.append(toolNode('li',point)));d.append(list);}
    d.append(toolNode('p',data.explanation));
    mountKnowledgeGuide(d,item);
    d.append(toolNode('h3','本题相关知识点'));
    if(!data.related_outline_points.length)d.append(toolNode('p','暂无精确关联的大纲知识点。'));
    data.related_outline_points.forEach(point=>d.append(toolNode('h4',point.title+(point.scope==='course_outline'?' · 课程大纲补充':'')),toolNode('p',point.text)));
    d.append(toolNode('h3','相关原文片段'));
    if(!data.focused_sources?.length)d.append(toolNode('p','暂无精确关联的原文片段，可展开完整来源查看。'));
    for(const source of data.focused_sources||[]){
      const section=toolNode('section');section.append(toolNode('h4',`${source.name} · ${source.location}`));
      const text=toolNode('pre');appendKnowledgeHighlight(text,source.text,data.highlight_terms||[]);section.append(text);d.append(section);
    }
    if(data.comparison_points?.length || data.comparison_sources?.length){
      const compare=toolNode('section');compare.append(toolNode('h3','相关概念对照'),toolNode('p','以下内容用于辅助理解，不作为本题答案的直接原文依据。'));
      for(const point of data.comparison_points||[])compare.append(toolNode('h4',point.title),toolNode('p',point.text));
      for(const source of data.comparison_sources||[]){const detail=document.createElement('details');detail.append(toolNode('summary',`${source.name} · ${source.location}`),toolNode('pre',source.text));compare.append(detail);}
      d.append(compare);
    }
    const full=document.createElement('details');full.append(toolNode('summary','查看完整来源'));
    data.sources.forEach(source=>{const detail=document.createElement('details');detail.append(toolNode('summary',`${source.name} · ${source.location}`),toolNode('pre',source.text));full.append(detail);});d.append(full);
    message.textContent=data.has_direct_source?'已按本题内容筛选相关知识与原文片段。':'引用资料中未找到直接说明本题的片段；下方保留题目解析与可匹配的相关内容。';
  }catch(e){message.textContent=e.message;}
}

function openManualPaper(){
  if(!activeCourse)return;
  if(practiceDirty||practiceSaving){$('practice-message').textContent='请先保存当前答案或人工评分，再创建试卷。';return;}
  const courseId=activeCourse.id;const {d,message,close}=toolDialog('手工组卷 / 参考试卷录入');
  let dirty=false;d.addEventListener('input',()=>{dirty=true;});
  const discard=()=>!dirty||confirm('试卷还未保存，确认放弃录入？');close.onclick=()=>{if(discard())d.close();};d.addEventListener('cancel',e=>{if(!discard())e.preventDefault();});
  d.append(toolNode('p','逐题录入并核对参考答案。单选/判断/填空各2分，多选3分，简答5分；1–20题；保存后形成固定试卷。无需调用 AI。已看过答案的自编试卷属于自测，不是盲测。'));
  const form=document.createElement('form'),title=toolField('试卷标题'),minutes=toolField('限时分钟（留空为普通练习）');title.input.required=true;title.input.maxLength=150;minutes.input.type='number';minutes.input.min=1;minutes.input.max=180;form.append(title.wrap,minutes.wrap);
  const rows=toolNode('div');form.append(rows);const questions=[];
  function addQuestion(seed){if(questions.length>=20){message.textContent='每份最多20题';return;}const section=toolNode('fieldset'),legend=toolNode('legend','题目');section.append(legend);
    const kind=toolField('题型','select');Object.entries(practiceKinds).forEach(([k,v])=>kind.input.add(new Option(v,k)));
    const prompt=toolField('题干','textarea'),options=toolField('选项：每行一个，单选/多选填2–6个','textarea'),answer=toolField('参考答案：选择题填 A 或 A,B；判断题填 正确/错误；主观题填完整答案','textarea'),explanation=toolField('解析','textarea'),points=toolField('填空/简答的评分要点：每行一点','textarea');
    prompt.input.required=answer.input.required=explanation.input.required=true;prompt.input.maxLength=3000;answer.input.maxLength=4000;explanation.input.maxLength=4000;options.input.maxLength=24000;points.input.maxLength=40000;
    const entry={section,kind,prompt,options,answer,explanation,points};questions.push(entry);
    if(seed){kind.input.value=seed.kind;prompt.input.value=seed.prompt;options.input.value=seed.options.join('\n');answer.input.value=seed.answer.join(seed.kind==='multiple'?',':'');explanation.input.value=seed.explanation;points.input.value=seed.key_points.join('\n');}
    section.append(kind.wrap,prompt.wrap,options.wrap,answer.wrap,explanation.wrap,points.wrap,toolButton('移除此题',()=>{questions.splice(questions.indexOf(entry),1);section.remove();}));rows.append(section);
  }
  addQuestion();const save=toolNode('button','确认答案并保存试卷');const paperActions=toolNode('div');paperActions.className='actions';paperActions.append(toolButton('＋ 添加题目',()=>addQuestion()),save);form.append(paperActions);d.append(form);const requestId=crypto.randomUUID();
  form.onsubmit=async e=>{e.preventDefault();if(!questions.length){message.textContent='至少需要一道题';return;}save.disabled=true;
    const paper={title:title.input.value,questions:questions.map(q=>({kind:q.kind.input.value,prompt:q.prompt.input.value,options:['single','multiple'].includes(q.kind.input.value)?q.options.input.value.split('\n').map(s=>s.trim()).filter(Boolean):[],answer:q.kind.input.value==='multiple'?q.answer.input.value.split(/[,，、\s]+/).filter(Boolean):[q.answer.input.value.trim()],explanation:q.explanation.input.value,key_points:q.points.input.value.split('\n').map(s=>s.trim()).filter(Boolean),source_ids:['MANUAL']}))};
    try{const result=await api(`/courses/${courseId}/manual-papers`,{method:'POST',body:JSON.stringify({paper,request_id:requestId,exam_minutes:minutes.input.value?Number(minutes.input.value):null})});d.close();if(activeCourse?.id===courseId){await loadPracticeHistory(courseId);await showPractice(result.id,courseId);}}
    catch(e){message.textContent=e.message+'。主观题需填写评分要点，多选答案用逗号分隔。';}finally{save.disabled=false;}
  };
}

async function openTextEditor(){
  if(!activeMaterial||!activeCourse)return;
  const mid=activeMaterial.id,courseId=activeCourse.id;const {d,message,close}=toolDialog('校对 / 人工录入资料文字');
  message.textContent='正在加载…';
  try{
    const state=await api(`/materials/${mid}/text-editor`);if(!d.isConnected)return;
    const units=state.units.length?state.units:[{location:'原文位置 1（人工录入）',text:''}];let dirty=false;
    const choose=toolField('原文位置','select'),text=toolField('该位置的文字','textarea');text.input.rows=14;text.input.maxLength=100000;
    let index=0;units.forEach((u,i)=>choose.input.add(new Option(u.location,String(i))));text.input.value=units[0].text;
    const retain=()=>{units[index].text=text.input.value;};
    choose.input.onchange=()=>{retain();index=Number(choose.input.value);text.input.value=units[index].text;};
    text.input.oninput=()=>{dirty=true;};const discard=()=>!dirty||confirm('校对文字尚未保存，确认放弃？');close.onclick=()=>{if(discard())d.close();};d.addEventListener('cancel',e=>{if(!discard())e.preventDefault();});
    d.append(toolNode('p','可粘贴你已识别并核对的文字。本入口不会调用 OCR；原文件保留，旧大纲与试题保持原快照。已有章节时不改变页数和位置。'),choose.wrap,text.wrap);
    if(!state.confirmed)d.append(toolButton('添加一个原文位置',()=>{retain();if(units.length>=2000){message.textContent='最多2000个位置';return;}units.push({location:`原文位置 ${units.length+1}（人工录入）`,text:''});index=units.length-1;choose.input.add(new Option(units[index].location,String(index)));choose.input.value=String(index);text.input.value='';dirty=true;}));
    const save=toolButton('保存校对文字',async()=>{retain();save.disabled=true;try{const result=await api(`/materials/${mid}/text-editor`,{method:'PUT',body:JSON.stringify({revision:state.revision,units})});dirty=false;d.close();if(activeCourse?.id===courseId){await loadMaterials(courseId);if(activeMaterial?.id===mid){const latest=await api(`/materials/${mid}`);if(activeMaterial?.id===mid){const position=$('unit-select').value;activeMaterial=latest;$('unit-select').replaceChildren();latest.units.forEach((u,i)=>$('unit-select').add(new Option(u.location,String(i))));$('unit-select').value=position||'0';showUnit();$('add-chapter').disabled=$('save-chapters').disabled=wholeButton.disabled=refreshButton.disabled=false;updateRangeSummary();$('detail-note').textContent=result.message;}}}}catch(e){message.textContent=e.message;}finally{save.disabled=false;}});d.append(save);message.textContent='';
  }catch(e){message.textContent=e.message;}
}
async function openChapterSuggestions(){
  if(!activeMaterial?.units.length)return;
  const material=activeMaterial,courseId=activeCourse.id;const {d,message}=toolDialog('AI 章节建议 · 需人工确认');
  const start=toolField('起始原文位置','select'),end=toolField('结束原文位置','select');material.units.forEach((u,i)=>{start.input.add(new Option(u.location,String(i)));end.input.add(new Option(u.location,String(i)));});end.input.value=String(material.units.length-1);
  d.append(toolNode('p','仅发送你选中的文字，每次最多300个位置、5万字符，可能产生接口费用。建议不会自动应用或保存；可分段生成并追加到范围编辑区。'),start.wrap,end.wrap);
  const resultArea=toolNode('div');const generate=toolButton('生成章节建议（可能收费）',async()=>{
    generate.disabled=true;resultArea.replaceChildren();message.textContent='正在生成建议…';
    try{const result=await api(`/materials/${material.id}/suggest-chapters`,{method:'POST',body:JSON.stringify({start:Number(start.input.value),end:Number(end.input.value)})});if(!d.isConnected)return;
      result.chapters.forEach(c=>resultArea.append(toolNode('p',`${c.title}：${material.units[c.unit_index].location} 至 ${material.units[c.end_unit_index].location}`)));
      resultArea.append(toolButton('追加到范围编辑区（尚未保存）',()=>{if(activeCourse?.id!==courseId||activeMaterial?.id!==material.id){message.textContent='已切换资料，请关闭后重新生成';return;}result.chapters.forEach(addChapterRow);updateRangeSummary();$('detail-note').textContent='已追加 AI 建议。请检查重叠范围、修改名称，点击“保存并确认章节”后生效。';d.close();}));message.textContent=result.message;
    }catch(e){message.textContent=e.message;}finally{generate.disabled=false;}
  });d.append(generate,resultArea);
}
const textTools=toolNode('div');textTools.className='actions';textTools.append(toolButton('校对 / 人工录入文字',openTextEditor),toolButton('AI 章节建议',()=>{if(!activeMaterial?.units.length){$('detail-note').textContent='请先提取或录入文字，再生成章节建议。';return;}openChapterSuggestions();}));$('detail-note').after(textTools);

function appendKnowledgeHighlight(node,text,terms){
  const matches=[];
  for(const term of terms){if(term.length<2)continue;let start=0,index;while((index=text.toLowerCase().indexOf(term.toLowerCase(),start))!==-1){matches.push([index,index+term.length]);start=index+term.length;}}
  matches.sort((a,b)=>a[0]-b[0]||b[1]-a[1]);let cursor=0;
  for(const [start,end] of matches){if(start<cursor)continue;node.append(document.createTextNode(text.slice(cursor,start)),toolNode('mark',text.slice(start,end)));cursor=end;}
  node.append(document.createTextNode(text.slice(cursor)));
}

function mountKnowledgeGuide(dialog,item){
  const box=toolNode('section'),content=toolNode('div'),status=toolNode('p');status.setAttribute('role','status');
  const path=`/practices/${item.practice_id}/knowledge-guide/${item.question.id}`;
  const actions=toolNode('div');actions.className='actions';
  const generate=toolButton('生成知识点讲解',async()=>{
    if(!confirm('将本题和相关资料发送给已配置的 AI 补充知识讲解，可能产生费用。生成后会保存，是否继续？'))return;
    generate.disabled=true;status.textContent='正在整理概念、方法对比和易混点…';
    try{const result=await api(path,{method:'POST'});if(box.isConnected)paint(result.guide);}
    catch(e){if(box.isConnected)status.textContent=e.message;}
    finally{generate.disabled=false;}
  });
  const refresh=toolButton('刷新讲解',()=>load());actions.append(generate,refresh);
  box.append(toolNode('h3','知识点讲解'),toolNode('p','围绕本题主题补充概念、方法对比与易混点。'),content,actions,status);dialog.append(box);
  function paint(guide){content.replaceChildren();generate.hidden=Boolean(guide);status.textContent='';
    if(!guide)return;
    content.append(toolNode('p','AI 补充讲解 · 非资料原文'),toolNode('h4',guide.title),toolNode('p',guide.overview));
    for(const concept of guide.concepts)content.append(toolNode('h4',concept.name),toolNode('p',concept.explanation));
    if(guide.differences.length){content.append(toolNode('h4','区别与易混点'));const list=toolNode('ul');guide.differences.forEach(t=>list.append(toolNode('li',t)));content.append(list);}
    if(guide.example)content.append(toolNode('h4','理解示例'),toolNode('p',guide.example));
    content.append(toolNode('h4','回到本题'),toolNode('p',guide.takeaway));
  }
  async function load(){refresh.disabled=true;try{const result=await api(path);if(!box.isConnected)return;paint(result.guide);generate.disabled=result.generating;if(result.generating)status.textContent='讲解正在生成，稍后点击刷新即可查看。';}catch(e){if(box.isConnected)status.textContent=e.message;}finally{refresh.disabled=false;}}
  load();
}
