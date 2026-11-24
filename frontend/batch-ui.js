let archivePreviewId=null,archivePreviewRequest=0;
let currentOutlineSession = null, sessionCourseId = null, sessionRequest = 0;
const sessionPanel = document.createElement('section');
sessionPanel.innerHTML = '<h3>当前复习大纲</h3><div id="outline-session-current"></div><h3>分批大纲存档</h3><div id="outline-session-history"></div><div id="outline-session-preview"></div>';
$('outline-message').after(sessionPanel);
function batchRangeText(range) { return `${range.name}：${range.start}${range.end === range.start ? '' : ' → '+range.end}`; }
function renderBatchProgress(parts, target) {
  const labels={pending:'待处理',running:'处理中',done:'已完成',failed:'失败，可重试'};
  for (const part of parts) {
    const row=document.createElement('details');row.className='batch-progress';
    const phase=part.kind ? ({read:'读取原文',reduce:'汇总知识',generate:'生成题目'}[part.kind]+' · ') : '';
    row.append(practiceText('summary',`${phase}第 ${part.seq} 批 · ${labels[part.status]}`));
    part.ranges.forEach(range=>row.append(practiceText('p',batchRangeText(range))));
    if (part.message) row.append(practiceText('p',part.message));
    if (part.status==='failed') row.open=true;
    target.append(row);
  }
}
function renderSession(record, target, active) {
  target.replaceChildren();
  if(record.title)target.append(practiceText('h3',record.title));
  target.append(practiceText('p',`已完成 ${record.completed_batches} / ${record.total_batches} 批；每批的具体起止范围见下方。${record.status==='archived' ? '此大纲已存档。' : '已完成内容即时保留，剩余批次不会被当成已处理。完成表示该范围已参与生成，不保证每个知识点都写入大纲。'}`));
  if (record.stale) target.append(practiceText('p','部分原资料已变化；这里保留处理时的原文与结果。','muted'));
  const completed=record.parts.filter(p=>p.status==='done');
  if (completed.length) {
    target.append(practiceText('h4','已经处理好的范围'));
    completed.forEach(part=>part.ranges.forEach(range=>target.append(practiceText('p',batchRangeText(range)))));
  }
  renderBatchProgress(record.parts,target);
  const actions=document.createElement('div');actions.className='actions';
  if (active) {
    const next=practiceText('button','继续处理下一批','primary');next.type='button';next.disabled=outlineBusy || record.pending_stale || record.parts.every(p=>p.status==='done') || record.parts.some(p=>p.status==='running');
    next.onclick=()=>continueOutlineSession(record.id);
    const append=practiceText('button','继续追加：选择新范围');append.type='button';append.onclick=()=>$('outline-form').scrollIntoView({behavior:'smooth'});
    const archive=practiceText('button','存档并清空当前大纲');archive.type='button';archive.disabled=outlineBusy || record.parts.some(p=>p.status==='running');archive.onclick=()=>archiveOutlineSession(record);
    const refresh=practiceText('button','刷新当前进度');refresh.type='button';refresh.onclick=()=>loadOutlineSessions(record.course_id);
    if(record.pending_stale){
      const update=practiceText('button','更新未完成批次');update.type='button';update.disabled=outlineBusy||record.parts.some(p=>p.status==='running');
      update.onclick=async()=>{if(outlineBusy)return;outlineBusy=true;update.disabled=true;
        try{await api(`/outline-sessions/${record.id}/refresh-pending`,{method:'POST'});$('outline-message').textContent='未完成批次已更新为校对后的文字，已完成内容保留。';}
        catch(e){$('outline-message').textContent=e.message;}
        finally{outlineBusy=false;await loadOutlineSessions(record.course_id);}
      };actions.append(update);
    }
    actions.append(next,append,archive,refresh);
    target.append(practiceText('p','追加资料：可回到上方上传新文件，提取文字并保存范围，再在大纲选章区勾选新内容并点击“追加所选范围”。已有资料的剩余部分不需要重新上传。当前大纲沿用首次设置的目标与详细程度。','muted'));
  }
  if (record.completed_batches) {
    const exp=practiceText('button','导出已完成的大纲');exp.type='button';exp.onclick=()=>exportSession(record);actions.append(exp);
  }
  target.append(actions);
  renderKnowledgeCards(record,target);
}
function exportSession(record) {
  const progressSection={title:`处理进度：已完成 ${record.completed_batches}/${record.total_batches} 批`,points:record.parts.flatMap(part=>part.ranges.map(range=>({text:`${part.status==='done'?'已完成':'未完成'}：${batchRangeText(range)}`,source_ids:[]})))};
  exportOutline({...record,result:{...record.result,sections:[progressSection,...record.result.sections]}});
}
async function loadOutlineSessions(courseId) {
  const request=++sessionRequest;
  if(sessionCourseId!==courseId){sessionCourseId=courseId;currentOutlineSession=null;$('outline-goal').value='';$('outline-level').value='精简';$('outline-session-current').replaceChildren();$('outline-session-preview').replaceChildren();}
  const rows=await api(`/courses/${courseId}/outline-sessions`);
  if(activeCourse?.id!==courseId || request!==sessionRequest)return;
  const active=rows.find(r=>r.status==='active');
  currentOutlineSession=active?.id || null;
  $('outline-session-history').replaceChildren();
  for(const row of rows.filter(r=>r.status==='archived')) {
    const button=practiceText('button',`${new Date(row.archived_at*1000).toLocaleString()} · ${row.title || row.goal || '复习大纲'} · 查看存档`);button.type='button';
    button.onclick=async()=>{const ticket=++archivePreviewRequest;archivePreviewId=row.id;try{const record=await api(`/outline-sessions/${row.id}`);if(activeCourse?.id===courseId&&ticket===archivePreviewRequest)renderSession(record,$('outline-session-preview'),false);}catch(e){if(activeCourse?.id===courseId&&ticket===archivePreviewRequest)$('outline-message').textContent=e.message;}};
    const remove=practiceText('button','删除','quiet');remove.type='button';
    remove.onclick=()=>deleteOutlineArchive(row,remove);
    const entry=practiceText('div','','actions');const rename=practiceText('button','重命名','quiet');rename.type='button';
    rename.onclick=async()=>{
      const title=askOutlineName(row.title||row.goal||'复习大纲');if(title===null)return;
      rename.disabled=true;
      try{await api(`/outline-sessions/${row.id}/name`,{method:'PATCH',body:JSON.stringify({title})});
        if(activeCourse?.id!==courseId)return;
        if(archivePreviewId===row.id){const record=await api(`/outline-sessions/${row.id}`);if(activeCourse?.id===courseId&&archivePreviewId===row.id)renderSession(record,$('outline-session-preview'),false);}
        await loadOutlineSessions(courseId);
      }catch(e){if(activeCourse?.id===courseId)$('outline-message').textContent=e.message;}finally{rename.disabled=false;}
    };
    entry.append(button,rename,remove);
    $('outline-session-history').append(entry);
  }
  $('outline-generate').textContent=active?'追加所选范围':'开始分批生成大纲';
  $('outline-goal').disabled=$('outline-level').disabled=!!active;
  if(active){
    $('outline-goal').value=active.goal;$('outline-level').value=active.detail;
    const record=await api(`/outline-sessions/${active.id}`);
    if(activeCourse?.id===courseId && request===sessionRequest)renderSession(record,$('outline-session-current'),true);
  }else $('outline-session-current').textContent='当前没有正在整理的大纲。选择范围后开始生成，或从存档中查看过去的复习内容。';
}
$('outline-form').onsubmit=async event=>{
  event.preventDefault();if(!activeCourse || outlineBusy || chaptersLoading)return;
  const courseId=activeCourse.id,keys=selectedChapterKeys();
  if(!keys.length){$('outline-message').textContent='请至少选择一个章节范围';return;}
  const ids=Array.from($('outline-materials').querySelectorAll('input:checked:not(:disabled)'),n=>n.value);
  outlineBusy=true;updateChapterSummary();$('outline-message').textContent='正在保存所选范围并安排批次…';
  try{
    const record=await api(`/courses/${courseId}/outline-sessions`,{method:'POST',body:JSON.stringify({material_ids:ids,chapter_keys:keys,goal:$('outline-goal').value,detail:$('outline-level').value})});
    if(activeCourse?.id!==courseId)return;
    currentOutlineSession=record.id;renderSession(record,$('outline-session-current'),true);$('outline-message').textContent=record.message;
    outlineBusy=false;
    await continueOutlineSession(record.id);
  }catch(e){if(activeCourse?.id===courseId)$('outline-message').textContent=e.message;}
  finally{outlineBusy=false;updateChapterSummary();if(activeCourse?.id===courseId)await loadOutlineSessions(courseId).catch(e=>{$('outline-message').textContent=e.message;});}
};
async function continueOutlineSession(id) {
  if(outlineBusy || !activeCourse)return;
  const courseId=activeCourse.id;outlineBusy=true;updateChapterSummary();$('outline-message').textContent='正在处理一个批次，完成后立即展示；其他批次可继续处理。';
  try{
    const record=await api(`/outline-sessions/${id}/next`,{method:'POST'});
    if(activeCourse?.id!==courseId)return;
    renderSession(record,$('outline-session-current'),true);
    $('outline-message').textContent=`已完成 ${record.completed_batches}/${record.total_batches} 批。`+(record.parts.some(p=>p.status==='failed')?'本批失败，前面已完成的内容保留，可重试。':record.completed_batches<record.total_batches?'下方已展示完成部分，可继续下一批，也可存档。':'所选范围处理完成。可追加其他范围或存档后开始新大纲。');
  }catch(e){if(activeCourse?.id===courseId)$('outline-message').textContent=e.message+'。请刷新当前进度，已完成批次会保留。';}
  finally{outlineBusy=false;updateChapterSummary();if(activeCourse?.id===courseId)await loadOutlineSessions(courseId).catch(()=>{});}
}
function askOutlineName(initial) {
  let value=initial.slice(0,100);
  while(true){
    const result=window.prompt('为这份复习大纲命名（1–100字）',value);
    if(result===null)return null;
    value=result.trim();
    if(value && value.length<=100)return value;
    window.alert('请输入1–100字的存档名称。');
  }
}
async function archiveOutlineSession(record) {
  if(outlineBusy)return;
  if(record.completed_batches<record.total_batches && !window.confirm('仍有未完成批次。存档将保留已完成内容和未完成范围标记，但不再继续处理；确定存档吗？'))return;
  const title=askOutlineName(record.title||record.goal||`${activeCourse?.name||'课程'} · ${new Date().toLocaleDateString()}复习大纲`);if(title===null)return;
  const courseId=record.course_id;outlineBusy=true;
  try{
    await api(`/outline-sessions/${record.id}/archive`,{method:'POST',body:JSON.stringify({title})});
    if(activeCourse?.id!==courseId)return;
    currentOutlineSession=null;$('outline-session-current').replaceChildren();$('outline-session-preview').replaceChildren();$('outline-result').hidden=true;
    $('outline-goal').value='';$('outline-message').textContent='已存档并清空当前大纲。可以重新选择范围开始新的复习。';
    await loadOutlineSessions(courseId);
  }catch(e){$('outline-message').textContent=e.message;}
  finally{outlineBusy=false;updateChapterSummary();}
}

let practiceBatchStop=false;
function renderPracticePipeline(record,target) {
  target.append(practiceText('p',`已完成 ${record.pipeline.done}/${record.pipeline.total} 个步骤。所有所选原文先分批读取，再合并知识摘要出题；摘要压缩可能遗漏细节，题量有限也不保证覆盖每个知识点。`));
  renderBatchProgress(record.pipeline.parts,target);
  const actions=document.createElement('div');actions.className='actions';
  const next=practiceText('button','继续分批读取并出题','primary');next.type='button';next.disabled=practiceSaving;next.onclick=()=>continuePracticePipeline();
  const pause=practiceText('button','本步完成后暂停');pause.type='button';pause.disabled=!practiceSaving;pause.onclick=()=>{practiceBatchStop=true;pause.textContent='本步完成后暂停';};
  const refresh=practiceText('button','刷新进度');refresh.type='button';refresh.disabled=practiceSaving;refresh.onclick=()=>showPractice(record.id,record.course_id);
  actions.append(next,pause,refresh);target.append(actions,practiceText('p','多批读取与知识汇总会产生多次 AI 调用费用。已完成步骤可恢复，失败只重试当前步骤。','muted'));
}
async function continuePracticePipeline() {
  if(practiceSaving || practiceRecord?.status!=='processing')return;
  const id=practiceRecord.id,courseId=activeCourse.id;practiceSaving=true;practiceBatchStop=false;renderPracticeSession();
  try{
    while(!practiceBatchStop && activeCourse?.id===courseId && practiceRecord?.id===id && practiceRecord.status==='processing'){
      const next=await api(`/practices/${id}/next`,{method:'POST'});
      if(activeCourse?.id!==courseId || practiceRecord?.id!==id)return;
      practiceRecord=next;renderPracticeSession();
      if(next.pipeline?.parts.some(p=>p.status==='failed'))break;
    }
    if(activeCourse?.id===courseId)await loadPracticeHistory(courseId);
  }catch(e){if(activeCourse?.id===courseId)$('practice-message').textContent=e.message+'。请刷新进度后继续，已完成步骤不会重做。';}
  finally{practiceSaving=false;if(activeCourse?.id===courseId && practiceRecord?.id===id)renderPracticeSession();}
}

async function deleteOutlineArchive(row,button){
 if(button.disabled)return;
 if(!window.confirm(`确定删除“${row.title||row.goal||'复习大纲'}”这份存档？大纲内容和关联批注将删除，无法恢复。上传资料、练习和错题记录不受影响。`))return;
 button.disabled=true;
 try{
  await api(`/outline-sessions/${row.id}`,{method:'DELETE'});
  if(activeCourse?.id!==row.course_id)return;
  if(archivePreviewId===row.id){archivePreviewRequest++;archivePreviewId=null;$('outline-session-preview').replaceChildren();}
  $('outline-message').textContent='大纲存档已删除';
  await loadOutlineSessions(row.course_id);
 }catch(e){if(activeCourse?.id===row.course_id)$('outline-message').textContent=e.message;}
 finally{button.disabled=false;}
}
