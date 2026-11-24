const reportMethodology = [
 '按当前课程已交卷、已保存的评分统计；首次练习、原题重做、变式和考试分别计算。',
 '正确率＝完全正确题数÷已评分题数；部分正确单列，待评分不计入分母，交卷后的空题计为错误。',
 '得分率＝已评分题目得分合计÷对应满分合计；评分更新后，报告同步更新。',
 '一道题可能关联多个章节，章节题数不直接相加。信心分析仅使用首次练习和考试中记录过信心的题目。'
];
const reportPanel = document.createElement('section'); reportPanel.className = 'panel';
reportPanel.innerHTML = `<h2>学习报告</h2>
  <p class="muted">根据本课程已保存的作答与评分计算，不调用 AI 生成统计。首次作答和原题重做分别展示；待评分不按零分计。</p>
  <div class="actions"><button id="report-refresh" type="button">刷新报告</button><button id="report-export" type="button" disabled>导出 Markdown 报告</button></div>
  <p id="report-message" role="status"></p><div id="report-content"></div>`;
$('material-view').append(reportPanel);
let reportData = null, reportCourseId = null, reportRequest = 0;
const reportModes = {automatic:'程序判分（客观题）', ai:'AI 建议分', self:'人工评分 / 待人工评分', blank:'主观题未作答'};
function resetReport(courseId) {
  if (reportCourseId === courseId) return;
  reportCourseId = courseId; reportData = null; reportRequest++;
  $('report-content').replaceChildren(); $('report-export').disabled = true;
  $('report-message').textContent = '正在加载学习报告…';
}
async function loadReport(courseId) {
  resetReport(courseId); const request = ++reportRequest;
  $('report-export').disabled = true;
  try {
    const data = await api(`/courses/${courseId}/report`);
    if (activeCourse?.id !== courseId || request !== reportRequest) return;
    reportData = data; renderReport(data); $('report-export').disabled = false;
    $('report-message').textContent = `更新于 ${new Date(data.generated_at*1000).toLocaleString()}；统计当前已保存评分。`;
  } catch (error) {
    if (activeCourse?.id === courseId && request === reportRequest) $('report-message').textContent = '报告刷新失败：'+error.message+'。下方如有内容，为上一次成功加载的结果。';
  }
}
function reportRate(row) { if(row.evaluation_mode==='correctness') return row.correct_rate===null ? '待评价' : `${row.correct_rate}%`; return row.score_rate === null ? '暂无评分' : `${row.score_rate}%`; }
function reportSample(row) { return !row.graded ? '暂无已评分题目' : row.small_sample ? '样本不足（<5题）' : '仅反映已练习题目'; }
function reportTable(headers, rows) {
  const wrap = document.createElement('div'); wrap.className = 'report-table-wrap';
  const table = document.createElement('table'); table.className = 'report-table';
  const head = document.createElement('thead'), tr = document.createElement('tr');
  headers.forEach(header=>{const cell=practiceText('th',header);cell.scope='col';tr.append(cell);}); head.append(tr);table.append(head);
  const body = document.createElement('tbody');
  rows.forEach(values=>{const row=document.createElement('tr');values.forEach(value=>row.append(practiceText('td',String(value))));body.append(row);});
  table.append(body); wrap.append(table); return wrap;
}
function metricRow(name,row) {
  if(row.evaluation_mode==='correctness') return [name,row.questions,row.graded,row.pending,row.full_score,row.partial,row.zero,reportRate(row)];
  return [name,row.questions,row.graded,row.pending,`${Number(row.earned.toFixed(2))} / ${Number(row.graded_max.toFixed(2))}`,reportRate(row)];
}
function renderReport(data) {
  const target=$('report-content');target.replaceChildren();
  target.append(practiceText('h3','作答概况'));
  target.append(reportTable(['记录类型','已交卷','全部题目已评分','未交卷','已作答题次 / 题次','已评分得分率'],[
    ['首次作答',data.first_attempts.submitted_attempts,data.first_attempts.fully_scored_attempts,data.first_attempts.ready_attempts,
      `${data.first_attempts.totals.questions-data.first_attempts.totals.unanswered} / ${data.first_attempts.totals.questions}`,reportRate(data.first_attempts.totals)],
    ['原题重做',data.retries.submitted_attempts,data.retries.fully_scored_attempts,data.retries.ready_attempts,
      `${data.retries.totals.questions-data.retries.totals.unanswered} / ${data.retries.totals.questions}`,reportRate(data.retries.totals)]
  ]));
  if (data.exams) target.append(reportTable(['限时考试','已交卷','全部题目已评分','未交卷','已评分得分率'],[
    ['独立统计',data.exams.submitted_attempts,data.exams.fully_scored_attempts,data.exams.ready_attempts,reportRate(data.exams.totals)]
  ]));
  const summary=data.mistakes;
  target.append(practiceText('p',`错题记录 ${summary.total} 道：最近未满分 ${summary.needs_practice} 道、最近满分 ${summary.full_score} 道、重做待评分 ${summary.pending_review} 道。最近满分不代表已掌握同类新题。`));
  target.append(practiceText('h3','下一步建议'));
  const list=document.createElement('ul');data.suggestions.forEach(text=>list.append(practiceText('li',text)));target.append(list);
  const headers=['分类','题次','已评分','待评分','得分 / 已评分满分','得分率'];
  for (const [label,group] of [['首次作答',data.first_attempts],['原题重做',data.retries],['限时考试',data.exams],['错题变式',data.variants]].filter(([,group])=>group)) {
    const groupHeaders=group.evaluation_mode==='correctness' ? ['分类','题次','已评价','待评价','正确','部分正确','错误','正确率'] : headers;
    const section=document.createElement('details');section.open=label==='首次作答';section.className='report-section';section.append(practiceText('summary',label+'详细统计'));
    section.append(practiceText('h3','题型表现'),reportTable(groupHeaders,group.by_kind.map(row=>metricRow(practiceKinds[row.kind],row))));
    section.append(practiceText('h3',group.evaluation_mode==='correctness'?'评价来源':'评分来源'),reportTable(groupHeaders,group.by_mode.map(row=>metricRow(reportModes[row.mode],row))));
    section.append(practiceText('h3','章节表现'));
    if (group.chapters.length) {
      section.append(practiceText('p','同一题可关联多个章节，章节题数不可相加作为总题数。同名章节按出题时名称汇总。','muted'));
      section.append(reportTable(groupHeaders,group.chapters.map(row=>metricRow(row.title,row))));
    } else section.append(practiceText('p','尚无已交卷题目可用于章节统计。','muted'));
    section.append(practiceText('h3','最近10次交卷'));
    if (!group.recent.length) section.append(practiceText('p','暂无交卷记录。','muted'));
    for (const row of group.recent) {
      const item=document.createElement('div');item.className='report-recent';
      const button=practiceText('button',row.title);button.type='button';button.onclick=()=>showPractice(row.id,data.course.id);
      item.append(button,practiceText('span',`${new Date(row.submitted_at*1000).toLocaleString()} · ${row.graded} 题已评分 / ${row.pending} 题待评分 · ${group.evaluation_mode==='correctness' ? '正确率' : '得分率'} ${reportRate(row)}`));section.append(item);
    }
    target.append(section);
  }
  const methodology=document.createElement('details');methodology.append(practiceText('summary','统计说明'));
  reportMethodology.forEach(text=>methodology.append(practiceText('p',text)));target.append(methodology);
}
function markdownCell(value) { return String(value).replace(/\\/g,'\\\\').replace(/\|/g,'\\|').replace(/[\r\n]+/g,' '); }
function reportMarkdown(data) {
  const lines=[`# 学习报告：${markdownCell(data.course.name)}`,'',`统计时间：${new Date(data.generated_at*1000).toLocaleString()}`,'','统计已保存的评分；首次作答与重做分别列出，待评分不按零分计。',''];
  const table=(headers,rows)=>{lines.push('| '+headers.map(markdownCell).join(' | ')+' |','| '+headers.map(()=> '---').join(' | ')+' |');rows.forEach(row=>lines.push('| '+row.map(markdownCell).join(' | ')+' |'));lines.push('');};
  for (const [label,group] of [['首次作答',data.first_attempts],['原题重做',data.retries],['限时考试',data.exams],['错题变式',data.variants]].filter(([,group])=>group)) {
    lines.push('## '+label,'',`已交卷 ${group.submitted_attempts} 次；全部评分完成 ${group.fully_scored_attempts} 次；未交卷 ${group.ready_attempts} 次。`,'');
    const headers=group.evaluation_mode==='correctness' ? ['分类','题次','已评价','待评价','正确','部分正确','错误','正确率'] : ['分类','题次','已评分','待评分','得分 / 已评分满分','得分率'];
    table(headers,[metricRow('合计',group.totals)]);
    lines.push('### 题型表现','');table(headers,group.by_kind.map(row=>metricRow(practiceKinds[row.kind],row)));
    lines.push('### 评分来源','');table(headers,group.by_mode.map(row=>metricRow(reportModes[row.mode],row)));
    lines.push('### 章节表现','');
    if (group.chapters.length) table(headers,group.chapters.map(row=>metricRow(row.title,row)));else lines.push('暂无数据。','');
    lines.push('### 最近10次交卷','');
    if (group.recent.length) table(['练习','时间','已评价','待评价',group.evaluation_mode==='correctness'?'正确率':'得分率'],group.recent.map(row=>[row.title,new Date(row.submitted_at*1000).toLocaleString(),row.graded,row.pending,reportRate(row)]));else lines.push('暂无记录。','');
  }
  const wrong=data.mistakes;
  lines.push('## 错题概况','',`共 ${wrong.total} 道：最近未满分 ${wrong.needs_practice} 道，最近满分 ${wrong.full_score} 道，重做待评分 ${wrong.pending_review} 道。`,'','## 下一步建议','');
  data.suggestions.forEach(text=>lines.push('- '+markdownCell(text)));lines.push('','## 统计说明','');
  reportMethodology.forEach(text=>lines.push('- '+markdownCell(text)));return lines.join('\n');
}
$('report-refresh').onclick=()=>{if(activeCourse)loadReport(activeCourse.id);};
$('report-export').onclick=()=>{
  if (!reportData || reportData.course.id!==activeCourse?.id || $('report-export').disabled) return;
  const url=URL.createObjectURL(new Blob([reportMarkdown(reportData)],{type:'text/markdown;charset=utf-8'}));
  const link=document.createElement('a');link.href=url;link.download=`学习报告-课程${reportData.course.id}.md`;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
};

