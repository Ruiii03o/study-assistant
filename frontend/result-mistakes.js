// A result links to its own attempt; course navigation always opens the full history.
let mistakeScope = null;
function resultMistakeCounts(record) {
  const grades = record?.result?.questions || [];
  return {wrong: grades.filter(q => q.score != null && q.score < q.max_score).length,
    pending: grades.filter(q => q.score == null).length};
}
function scopedMistakes(data, record) {
  if (!record) return data;
  const items = data.items.flatMap(item => {
    const attempt = item.attempts.find(a => a.practice_id === record.id);
    if (!attempt || attempt.score == null || attempt.score >= (item.question.max_score ?? 2)) return [];
    return [{...item, state:'needs_practice'}];
  });
  return {items, summary:{total:items.length, needs_practice:items.length, full_score:0,
    pending_review:0, ungraded_excluded:resultMistakeCounts(record).pending}};
}
function renderMistakeScope() {
  let bar = $('mistake-scope');
  if (!bar) {bar=practiceText('div','','actions');bar.id='mistake-scope';$('mistake-summary').before(bar);}
  bar.replaceChildren();bar.hidden=!mistakeScope;
  if (!mistakeScope) return;
  const record=mistakeScope, counts=resultMistakeCounts(record);
  bar.append(practiceText('span',`本次练习：${record.title}`));
  const clear=practiceText('button','清除筛选 · 查看全部');clear.type='button';clear.onclick=()=>navigateStudy('mistakes');
  const back=practiceText('button','返回本次结果');back.type='button';back.onclick=()=>showPractice(record.id,record.course_id);
  bar.append(clear,back);
  $('mistake-summary').textContent=`本次已确认错题 ${counts.wrong} 道（含部分正确）`+(counts.pending?` · 待批改 ${counts.pending} 道` : counts.wrong?'':' · 本次全部答对');
}
const resultNavigateStudy=navigateStudy;
navigateStudy=function(page,options={}) {
  if(page==='mistakes') {
    if(activeCourse && typeof resetMistakes==='function')resetMistakes(activeCourse.id);
    mistakeScope=options.mistakeScope||null;
    $('mistake-search').value='';$('mistake-state').value=mistakeScope?'needs_practice':'all';$('mistake-kind').value='all';
    $('mistake-items').replaceChildren();$('mistake-summary').textContent='';
    renderMistakeScope();$('mistake-message').textContent='正在刷新错题本…';
  }
  resultNavigateStudy(page,options);
  if(page==='mistakes'&&activeCourse)loadMistakes(activeCourse.id);
};
async function openResultMistakes(record) {
  if(practiceSaving)return;
  if(practiceDirty) {await saveSelfReview();if(practiceDirty)return;}
  if(typeof studyDialog!=='undefined'&&studyDialog) {await closeStudyDialog();if(studyDialog)return;}
  if(activeCourse?.id!==record.course_id)return;
  navigateStudy('mistakes',{mistakeScope:record,restore:false});
}
function addResultMistakeLinks() {
  const record=practiceRecord;
  if(record?.status!=='submitted')return;
  const target=$('practice-session'),counts=resultMistakeCounts(record);
  const summary=practiceText('div','','actions result-mistake-summary');summary.setAttribute('role','status');
  summary.append(practiceText('span',counts.wrong?`本次错题 ${counts.wrong} 道（含部分正确）`:counts.pending?'已确认错题 0 道':'本次全部答对'));
  if(counts.pending)summary.append(practiceText('span',`待批改 ${counts.pending} 道`));
  const makeLink=()=>{const b=practiceText('button','查看本次错题');b.type='button';b.onclick=()=>openResultMistakes(record);return b;};
  if(counts.wrong)summary.append(makeLink());
  target.querySelector('.practice-score')?.after(summary);
  if(counts.wrong)target.querySelector('#practice-answer-form > .actions')?.append(makeLink());
}
const resultRenderPractice=renderPracticeSession;
renderPracticeSession=function(){resultRenderPractice();addResultMistakeLinks();};
