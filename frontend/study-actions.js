const studyActionModes=new Map();
const beforeStudyActionsReport=renderReport;
renderReport=function(data){beforeStudyActionsReport(data);mountStudyActions(data.course.id);};
async function mountStudyActions(courseId){
 const host=toolNode('section');host.className='study-actions-panel';
 host.append(toolNode('h3','接下来复习什么'));
 const select=toolNode('select');select.setAttribute('aria-label','复习建议记录范围');
 for(const [value,label] of [['all','全部练习与考试'],['first','首次练习'],['exam','考试']])select.add(new Option(label,value));
 select.value=studyActionModes.get(courseId)||'all';
 const status=toolNode('p');status.setAttribute('role','status');const list=toolNode('div');list.className='study-action-list';
 host.append(select,status,list);$('report-content').prepend(host);let ticket=0;
 const current=()=>host.isConnected&&activeCourse?.id===courseId;
 async function draw(){const request=++ticket;list.replaceChildren();status.textContent='正在整理复习建议…';
  try{const data=await api(`/courses/${courseId}/study-actions?mode=${select.value}`);if(!current()||request!==ticket)return;
   status.textContent=data.items.length?`从 ${data.total} 道最近仍未完全答对的原题中，优先展示 ${data.items.length} 项。`:'当前没有需要优先回看的已评分错题。';
   for(const entry of data.items){
    const item=entry.item,q=item.question,card=toolNode('article');card.className='study-action-card';
    card.append(toolNode('h4',entry.points.length?entry.points[0].title:'回顾这道题'),toolNode('p',q.prompt));
    const confidence=entry.confidence?['不确定','有些把握','很有把握'][entry.confidence-1]:'未记录';
    const outcome=item.latest_score===0?'错误':'部分正确';
    card.append(toolNode('p',`${entry.category==='exam'?'考试':'首次练习'} · ${item.practice_title}；最近结果：${outcome}。首次作答信心：${confidence}。`,'muted'));
    const advice=entry.first_wrong&&entry.confidence===3?'先核对原解析与自己的判断依据，再用一道变式检查区别是否理解。':item.latest_score>0?'先补齐未得分的条件或步骤，再用一道变式练习巩固。':'先回顾相关定义与解题依据，再尝试一道不同情境的变式。';
    card.append(toolNode('p',advice));
    const focus=toolNode('details');focus.append(toolNode('summary','复习重点'));
    if(entry.points.length)entry.points.forEach(p=>focus.append(toolNode('p',p.text)));
    else if(q.key_points?.length)q.key_points.slice(0,3).forEach(p=>focus.append(toolNode('p',p)));
    else focus.append(toolNode('p',q.explanation));
    card.append(focus);
    const p=entry.progress,done=p.correct+p.partial+p.incorrect+p.pending;
    card.append(toolNode('p',done?`后续变式已作答 ${done} 道：答对 ${p.correct}，部分正确 ${p.partial}，答错 ${p.incorrect}，待评价 ${p.pending}。`:'尚未完成关联变式。','muted'));
    const message=toolNode('p');message.setAttribute('role','status');
    const actions=toolNode('div');actions.className='actions';
    const knowledge=toolButton('查看相关知识',()=>{if(current())showMistakeKnowledge(item);});
    const evidence=toolButton('查看依据题目',async()=>{
     if(!current())return;
     try{await showPractice(item.latest_practice_id,courseId);if(activeCourse?.id!==courseId||practiceRecord?.id!==item.latest_practice_id)return;
      const field=[...$('practice-session').querySelectorAll('[data-question-id]')].find(n=>n.dataset.questionId===q.id);field?.scrollIntoView({block:'center'});
     }catch(e){if(current())message.textContent=e.message;}
    });
    const variant=toolButton('练习相关新题（1道）',async()=>{
     if(!current()||variant.disabled)return;
     if(practiceDirty||practiceSaving){message.textContent='请先保存当前作答或评分，再开始新练习。';return;}
     if(!confirm('将根据这道题生成一道变式，可能产生 AI 接口费用。是否继续？'))return;
     variant.disabled=true;message.textContent='正在生成相关新题…';
     try{const result=await api(`/practices/${item.practice_id}/variant`,{method:'POST',body:JSON.stringify({question_id:q.id,request_id:crypto.randomUUID()})});if(!current())return;
      if(result.status==='failed'){message.textContent=result.message||'生成未完成，请稍后重试。';return;}
      studyOrigin={page:'report',note:'复习建议'};await showPractice(result.id,courseId);
     }catch(e){if(current())message.textContent=e.message;}
     finally{variant.disabled=false;}
    });
    actions.append(knowledge,variant,evidence);card.append(actions);
    for(const follow of entry.followups){const b=toolButton(follow.status==='ready'?'继续未完成的变式':'查看后续变式结果',async()=>{if(!current())return;try{await showPractice(follow.id,courseId);}catch(e){if(current())message.textContent=e.message;}});card.append(b);}
    card.append(message);list.append(card);
   }
  }catch(e){if(current()&&request===ticket){status.textContent='复习建议加载失败：'+e.message;list.append(toolButton('重新加载',draw));}}
 }
 select.onchange=()=>{studyActionModes.set(courseId,select.value);draw();};await draw();
}
