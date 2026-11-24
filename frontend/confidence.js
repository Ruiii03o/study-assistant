// Per-question confidence is separate from answer controls and grading.
const confidenceStates=new Map();
function confidenceState(id){if(!confidenceStates.has(id))confidenceStates.set(id,{values:{},revision:0,dirty:false,pending:null,loaded:false,error:'',edits:{}});return confidenceStates.get(id);}
async function flushConfidence(id){
  const state=confidenceStates.get(id);if(!state)return;
  if(state.pending){await state.pending;if(state.dirty)return flushConfidence(id);return;}
  if(!state.dirty)return;
  state.pending=(async()=>{while(state.dirty){const snapshot=JSON.stringify(state.values);try{
    const result=await api(`/practices/${id}/confidence`,{method:'PUT',body:JSON.stringify({revision:state.revision,values:JSON.parse(snapshot)})});
    state.revision=result.revision;state.dirty=JSON.stringify(state.values)!==snapshot;state.error='';if(!state.dirty)state.edits={};
  }catch(error){state.error=error.message;if(error.message.includes('记录已更新')){const latest=await api(`/practices/${id}/confidence`);state.revision=latest.revision;state.values=latest.values;for(const [key,value] of Object.entries(state.edits)){if(value===null)delete state.values[key];else state.values[key]=value;}}throw error;}}})();
  try{await state.pending;}finally{state.pending=null;}
}
const confidenceRender=renderPracticeSession;
renderPracticeSession=function(){confidenceRender();mountConfidence(practiceRecord);};
async function mountConfidence(record){
  if(record?.parent_id || record?.variant_of)return;
  if(!record?.questions?.length||!['ready','submitted'].includes(record.status))return;
  const host=$('practice-session'),state=confidenceState(record.id),fields=[...host.querySelectorAll('[data-question-id]')];
  if(!fields.length)return;
  try{if(!state.loaded){const saved=await api(`/practices/${record.id}/confidence`);if(practiceRecord?.id!==record.id)return;state.values=saved.values;state.revision=saved.revision;state.loaded=true;}}
  catch(error){if(practiceRecord?.id===record.id){const p=practiceText('p','信心记录加载失败：'+error.message);host.append(p);const retry=practiceText('button','重新加载信心记录');retry.type='button';retry.onclick=()=>{p.remove();retry.remove();mountConfidence(record);};host.append(retry);}return;}
  if(practiceRecord?.id!==record.id || !fields[0].isConnected)return;
  for(const field of fields){
    if(field.querySelector('.question-confidence'))continue;
    const id=field.dataset.questionId,box=practiceText('div','','question-confidence');
    box.setAttribute('role','group');box.setAttribute('aria-label','这题有多大把握');
    box.append(practiceText('span',record.status==='submitted'?'作答时的信心':'这题有多大把握？'));
    const status=practiceText('span','','confidence-status');status.setAttribute('role','status');
    const controls=[];
    const paint=()=>controls.forEach(([value,button])=>button.setAttribute('aria-pressed',String(state.values[id]===value)));
    for(const [value,label] of [[1,'不确定'],[2,'有些把握'],[3,'很有把握']]){
      const button=practiceText('button',label);button.type='button';button.disabled=record.status==='submitted';button.dataset.confidenceLocked=String(record.status==='submitted');controls.push([value,button]);
      button.onclick=async event=>{event.stopPropagation();if(record.status!=='ready')return;if(state.values[id]===value)delete state.values[id];else state.values[id]=value;state.edits[id]=state.values[id]??null;state.dirty=true;paint();status.textContent='保存中…';try{await flushConfidence(record.id);retry.hidden=true;status.textContent='已保存';}catch(error){retry.hidden=false;status.textContent='保存失败：'+error.message;}};box.append(button);
    }
    const retry=practiceText('button','重试保存');retry.type='button';retry.hidden=true;retry.onclick=async event=>{event.stopPropagation();try{await flushConfidence(record.id);retry.hidden=true;status.textContent='已保存';}catch(error){status.textContent=error.message;}};
    box.append(status,retry);if(record.status==='submitted'&&!state.values[id])status.textContent='未记录';paint();field.append(box);
  }
}
window.addEventListener('beforeunload',event=>{if([...confidenceStates.values()].some(s=>s.dirty)){event.preventDefault();event.returnValue='';}});
const confidenceAuth=showAuth;showAuth=function(){confidenceStates.clear();confidenceAuth();};
const confidenceReportSelections=new Map();
const confidenceReportRender=renderReport;
renderReport=function(data){confidenceReportRender(data);loadConfidenceReport(data.course.id);};
function confidenceInsights(group) {
 const items=group.items||[], totals={correct:0,partial:0,incorrect:0,pending:0};
 for(const item of items)if(item.outcome in totals)totals[item.outcome]++;
 const graded=totals.correct+totals.partial+totals.incorrect;
 const rules=[
  [3,'incorrect','优先复盘','核对解题依据与概念理解，找出与参考答案不同的判断。'],
  [2,'incorrect','优先复习','回看犹豫的条件和判断依据，再用同类题巩固。'],
  [1,'incorrect','补齐基础','回顾对应概念与例题，再尝试独立解答。'],
  [3,'partial','检查细节','对照评分点检查遗漏的条件、选项或步骤。'],
  [2,'partial','针对补强','保留正确思路，补齐尚未得分的部分。'],
  [1,'partial','分步巩固','区分已经答对和仍不清楚的部分，逐步补练。'],
  [1,'correct','验证理解','尝试解释解题依据，再用变式题确认理解。'],
  [2,'correct','增强把握','回顾当时的犹豫点，确认哪些依据支持正确答案。'],
  [3,'correct','保持巩固','这组题的表现与信心一致，可继续练习其他知识点或新题。']
 ];
 const advice=rules.flatMap(([level,outcome,title,text])=>{
  const matching=items.filter(item=>item.level===level&&item.outcome===outcome);
  return matching.length?[{level,outcome,title,text,items:matching}]:[];
 });
 return {totals,graded,advice};
}
function renderConfidenceInsights(view,group,courseId) {
 const {totals,graded,advice}=confidenceInsights(group);
 const section=practiceText('section','','confidence-insights');section.append(practiceText('h4','根据作答情况安排复习'));
 if(graded)section.append(practiceText('p',`当前记录中，已评分且记录信心的 ${graded} 道题：答对 ${totals.correct} 道，部分正确 ${totals.partial} 道，答错 ${totals.incorrect} 道。`));
 else section.append(practiceText('p',totals.pending?'已记录信心的题目尚待批改，批改后显示复习建议。':'暂无可分析的已评分信心记录。'));
 if(totals.pending)section.append(practiceText('p',`另有 ${totals.pending} 道待批改，暂不判断正误。`));
 const extra=document.createElement('details');extra.append(practiceText('summary','展开其余分析'));
 advice.forEach((entry,index)=>{
  const box=document.createElement('details');
  const level=['不确定','有些把握','很有把握'][entry.level-1],outcome={correct:'答对',partial:'部分正确',incorrect:'答错'}[entry.outcome];
  box.append(practiceText('summary',`${entry.title}：${level}，${outcome} ${entry.items.length} 道`),practiceText('p',entry.text));
  for(const item of entry.items){const button=practiceText('button',item.prompt);button.type='button';
   button.onclick=async()=>{await showPractice(item.practice_id,courseId);if(practiceRecord?.id!==item.practice_id)return;const field=[...$('practice-session').querySelectorAll('[data-question-id]')].find(n=>n.dataset.questionId===item.question_id);field?.scrollIntoView({block:'center'});};
   box.append(button);
  }
  (index<3?section:extra).append(box);
 });
 if(advice.length>3)section.append(extra);
 view.append(section);
}
async function loadConfidenceReport(courseId){
 const host=practiceText('section','','confidence-report');host.append(practiceText('h3','信心与答题结果'));$('report-content').append(host);
 try{const data=await api(`/courses/${courseId}/confidence-report`);if(activeCourse?.id!==courseId||!host.isConnected)return;
  const select=document.createElement('select');select.setAttribute('aria-label','信心分析记录类型');for(const [key,label] of [['first','首次练习'],['exam','考试']])select.add(new Option(label,key));select.value=confidenceReportSelections.get(courseId)||'first';host.append(select);
  const view=document.createElement('div');host.append(view);
  function draw(){view.replaceChildren();const group=data.groups[select.value];if(!group.items.length)view.append(practiceText('p','本类记录暂无信心数据。答题时在每题下方选择把握程度，交卷后即可分析。'));view.append(practiceText('p',`未记录信心 ${group.unrecorded} 题；正确率仅统计已评价且记录了信心的题，部分正确单列。`));
   for(const band of group.bands){const label=['不确定','有些把握','很有把握'][band.level-1];const row=practiceText('div','','confidence-band');row.append(practiceText('strong',label));const meter=document.createElement('progress');meter.max=100;meter.value=band.rate??0;meter.hidden=band.rate===null;meter.setAttribute('aria-label',label+'正确率');row.append(meter,practiceText('span',band.rate===null?'暂无已评价记录':`${band.rate}% · ${band.graded}题`));
    row.append(practiceText('small',`正确 ${band.correct} · 部分正确 ${band.partial} · 错误 ${band.incorrect} · 待评价 ${band.pending}`));
    const list=document.createElement('details');list.append(practiceText('summary','查看这些题'));for(const item of group.items.filter(i=>i.level===band.level)){const button=practiceText('button',`${{correct:'正确',partial:'部分正确',incorrect:'错误',pending:'待评价'}[item.outcome]} · ${item.prompt.slice(0,90)}`);button.type='button';button.onclick=async()=>{await showPractice(item.practice_id,courseId);const field=[...$('practice-session').querySelectorAll('[data-question-id]')].find(n=>n.dataset.questionId===item.question_id);field?.scrollIntoView({block:'center'});};list.append(button);}row.append(list);view.append(row);
   }
   renderConfidenceInsights(view,group,courseId);
  }select.onchange=()=>{confidenceReportSelections.set(courseId,select.value);draw();};draw();
 }catch(error){if(host.isConnected)host.append(practiceText('p','信心分析加载失败：'+error.message));}
}
