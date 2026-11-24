// Charts use persisted scores only; missing observations are never plotted as zero.
function targetPractice(title,kind){
  if(practiceDirty&&!confirm('当前作答尚未保存，是否只切换练习范围？未保存答案仍保留在原试卷中。'))return;
  const ranges=chapterGroups.flatMap(g=>g.ranges),matched=ranges.filter(r=>!title||r.title===title);
  if(!matched.length){alert('当前已保存章节中找不到对应范围，请先刷新资料与章节。');return;}
  practiceSelection=new Map(ranges.map(r=>[r.key,matched.some(m=>m.key===r.key)]));
  $('practice-mode').value='practice';$('practice-mode').onchange();
  for(const k of Object.keys(practiceKinds))$('practice-count-'+k).value=kind?(k===kind?5:0):({single:3,fill:1,short:1}[k]||0);
  if(typeof navigateStudy==='function'){studyOrigin={page:studyPage,subpage:studySubpage,note:title||'专项练习'};navigateStudy('train',{subpage:'practice'});}
  renderPracticeChapterChoices();practicePanel.scrollIntoView({block:'start',behavior:'auto'});$('practice-generate').focus();
  $('practice-message').textContent='已设置专项练习范围，请核对后点击生成；尚未调用AI。';
}
function metricBar(label,value,max=100,extra='',unit='%'){
  const row=toolNode('div');row.className='metric-bar-row';
  const text=toolNode('span',label),track=toolNode('div');track.className='metric-track';
  const fill=toolNode('span');fill.style.width=(value===null?0:Math.max(0,Math.min(100,value/max*100)))+'%';track.append(fill);track.setAttribute('aria-hidden','true');
  row.append(text,track,toolNode('span',value===null?'暂无评分':`${value}${unit}${extra}`));return row;
}
function drawDiagnostics(data){
  const host=toolNode('section');host.className='diagnostic-board';host.append(toolNode('h3','备考诊断 · 看完就知道练什么'));
  host.append(toolNode('p','以下为实际作答得分率，不是掌握概率。未练习、待评分和小样本分别标注；同名章节按名称汇总。'));
  const columns=toolNode('div');columns.className='diagnostic-grid';host.append(columns);
  const kinds=toolNode('section');kinds.className='diagnostic-card';kinds.append(toolNode('h4','题型表现（首次练习）'));
  for(const row of data.first_attempts.by_kind){const wrap=toolNode('div');wrap.append(metricBar(practiceKinds[row.kind],row.score_rate,100,` · ${row.graded}题`));const button=toolButton('专项练习',()=>targetPractice(null,row.kind));button.setAttribute('aria-label',`练习${practiceKinds[row.kind]}`);wrap.append(button);kinds.append(wrap);}
  const comparison=toolNode('section');comparison.className='diagnostic-card';comparison.append(toolNode('h4','原题熟悉，还是新题也会？'));
  for(const [name,group] of [['首次练习',data.first_attempts],['原题重做',data.retries],['变式新题',data.variants],['限时考试',data.exams]])if(group)comparison.append(metricBar(name+(group.evaluation_mode==='correctness'?'（正确率）':'（得分率）'),group.evaluation_mode==='correctness'?group.totals.correct_rate:group.totals.score_rate,100,` · ${group.totals.graded}题`));
  comparison.append(toolNode('p','不同题目集合的表现不可直接归因于能力变化。原题重做单独统计。'));columns.append(kinds,comparison);
  const heat=toolNode('section');heat.className='diagnostic-card';heat.append(toolNode('h4','章节 × 题型 · 点击格子准备专项练习'));
  const wrap=toolNode('div');wrap.className='report-table-wrap';const table=toolNode('table');table.className='report-table heat-table';
  const head=toolNode('tr');head.append(toolNode('th','章节'));for(const kind of Object.keys(practiceKinds))head.append(toolNode('th',practiceKinds[kind]));const thead=toolNode('thead');thead.append(head);table.append(thead);
  const names=[...new Set([...chapterGroups.map(g=>g.title),...data.first_attempts.chapters.map(r=>r.title)])],body=toolNode('tbody');
  for(const name of names){const row=toolNode('tr'),label=toolNode('th',name);label.scope='row';row.append(label);const chapter=data.first_attempts.chapters.find(r=>r.title===name);
    for(const kind of Object.keys(practiceKinds)){const metric=chapter?.by_kind?.find(r=>r.kind===kind),cell=toolNode('td'),rate=metric?.score_rate??null;
      const text=rate===null?(metric?.pending?'待评分':'未覆盖'):`${rate}% · ${metric.graded}题${metric.small_sample?'（样本少）':''}`;
      const button=toolButton(text,()=>targetPractice(name,kind));button.className=rate===null?'heat-empty':rate<60?'heat-low':rate<80?'heat-mid':'heat-high';button.setAttribute('aria-label',`${name}，${practiceKinds[kind]}，${text}，准备专项练习`);cell.append(button);row.append(cell);}
    body.append(row);
  }table.append(body);wrap.append(table);heat.append(wrap);if(!names.length)heat.append(toolNode('p','保存章节范围并完成练习后，这里会出现诊断。'));host.append(heat);
  return host;
}
const beforeDiagnosticReport=renderReport;renderReport=function(data){beforeDiagnosticReport(data);$('report-content').prepend(drawDiagnostics(data));};

const beforeDiagnosticChapters=loadChapterChoices;loadChapterChoices=async function(courseId){await beforeDiagnosticChapters(courseId);if(activeCourse?.id===courseId&&reportData?.course.id===courseId)renderReport(reportData);};
