function variantVerdict(score, maximum) { return score === null ? '待评价' : score >= maximum ? '正确' : score > 0 ? '部分正确' : '错误'; }
function variantSummary(result) {
  const graded=result.questions.filter(q=>q.score!==null), correct=graded.filter(q=>q.score>=q.max_score).length;
  const partial=graded.filter(q=>q.score>0&&q.score<q.max_score).length;
  return `正确 ${correct} 题 · 部分正确 ${partial} 题 · 错误 ${graded.length-correct-partial} 题 · 待评价 ${result.questions.length-graded.length} 题 · 正确率 ${graded.length ? Math.round(correct/graded.length*1000)/10+'%' : '—'}`;
}
const practiceKinds = {single:'单选', fill:'填空', short:'简答', multiple:'多选', true_false:'判断'};
const practicePanel = document.createElement('section'); practicePanel.className = 'panel';
practicePanel.innerHTML = `<h2>章节练习</h2>
  <p class="muted">独立选择本次练习范围，不影响上方大纲选章。默认单选 → 填空 → 简答，可调整五种题型的题量，总计 1–20 题。</p>
  <form id="practice-create-form">
    <fieldset><legend>练习章节</legend><div class="actions"><button type="button" id="practice-all">全选</button><button type="button" id="practice-none">清空选择</button></div><div id="practice-chapters"></div><p id="practice-scope" role="status"></p></fieldset>
    <div id="practice-counts" class="practice-counts"></div>
    <p class="muted">生成时会将选中范围的文字发送给已配置的 AI 服务，可能产生接口费用。大范围会先分批读取并汇总知识再出题，可能多次调用；格式校验失败时最多自动补题一次，仅补缺题。题量有限不保证每个知识点都有题。单选、判断、填空各 2 分，多选 3 分，简答 5 分；填空、简答交卷后可请求 AI 辅助批改，也可人工评分，评分来源分别标明。</p>
    <button id="practice-generate" class="primary" disabled>生成新练习</button>
  </form><p id="practice-message" role="status"></p>
  <div class="actions"><h3>练习记录</h3><button type="button" id="practice-refresh">刷新练习记录</button></div>
  <div id="practice-history"></div><section id="practice-session" hidden></section>`;
$('material-view').append(practicePanel);
let practiceSelection = new Map(), practiceCourseId = null, practiceRecord = null;
let practiceGenerating = false, practicePending = false, practiceSaving = false, practiceDirty = false, practiceViewToken = 0;
for (const [kind, title] of Object.entries(practiceKinds)) {
  const label = document.createElement('label'); label.textContent = title + '题';
  const input = document.createElement('input'); input.type = 'number'; input.min = '0'; input.max = '20'; input.step = '1'; input.required = true;
  input.id = 'practice-count-' + kind; input.value = ({single:3,fill:2,short:1})[kind] || 0;
  input.oninput = updatePracticeAvailability; label.append(input); $('practice-counts').append(label);
}
function practiceRanges() { return chapterGroups.flatMap(g => g.ranges).filter(r => practiceSelection.get(r.key)); }
function updatePracticeAvailability() {
  const counts = Object.keys(practiceKinds).map(k => Number($('practice-count-'+k).value));
  const total = counts.reduce((a,b) => a+b, 0), ranges = practiceRanges();
  const valid = counts.every(n => Number.isInteger(n) && n >= 0 && n <= 20) && total >= 1 && total <= 20;
  $('practice-generate').disabled = !aiConfigured || chaptersLoading || !ranges.length || !valid || practiceGenerating || practicePending;
  $('practice-all').disabled = $('practice-none').disabled = chaptersLoading;
  $('practice-scope').textContent = chaptersLoading ? '请先等待章节加载完成。' : `已选 ${ranges.length} 段范围，来自 ${new Set(ranges.map(r=>r.material_id)).size} 份资料；本次 ${total} 题。` + (!valid ? '总题量须为 1–20 题。' : !aiConfigured ? '请先配置 AI 服务。' : '');
  if (!chaptersLoading && total < new Set(ranges.map(r=>r.title)).size) $('practice-scope').textContent += ' 题量少于所选章节数，无法保证每章都有一道题。';
}
function renderPracticeChapterChoices() {
  if (practiceCourseId !== activeCourse?.id) {
    practiceCourseId = activeCourse?.id; practiceSelection = new Map(); practicePending = false;
    practiceRecord = null; practiceDirty = false; practiceViewToken++;
    $('practice-session').hidden = true; $('practice-history').replaceChildren(); $('practice-message').textContent = '';
  }
  const next = new Map();
  for (const range of chapterGroups.flatMap(g=>g.ranges)) next.set(range.key, practiceSelection.has(range.key) ? practiceSelection.get(range.key) : true);
  practiceSelection = next;
  const target = $('practice-chapters');
  const expanded = new Set(Array.from(target.querySelectorAll('details[open]'), d=>d.dataset.title)); target.replaceChildren();
  for (const group of chapterGroups) {
    const card = document.createElement('section'); card.className = 'chapter-group';
    const label = document.createElement('label'); label.className = 'outline-choice';
    const check = document.createElement('input'); check.type = 'checkbox';
    const chosen = group.ranges.filter(r=>practiceSelection.get(r.key)).length;
    check.checked = chosen === group.ranges.length; check.indeterminate = chosen > 0 && chosen < group.ranges.length;
    label.append(check,document.createTextNode(`${group.title}（${group.ranges.length} 段范围）`));
    check.onchange = () => { group.ranges.forEach(r=>practiceSelection.set(r.key,check.checked)); renderPracticeChapterChoices(); };
    const details = document.createElement('details'); details.dataset.title = group.title; details.open = expanded.has(group.title);
    const summary = document.createElement('summary'); summary.textContent = '查看来源与范围'; details.append(summary);
    for (const range of group.ranges) {
      const row = document.createElement('label'); row.className = 'outline-choice';
      const input = document.createElement('input'); input.type = 'checkbox'; input.checked = practiceSelection.get(range.key);
      input.onchange = () => { practiceSelection.set(range.key,input.checked); renderPracticeChapterChoices(); };
      row.append(input,document.createTextNode(`${range.name} · ${range.start_location} 至 ${range.end_location}`)); details.append(row);
    }
    card.append(label,details); target.append(card);
  }
  if (!chapterGroups.length) target.textContent = '请先在资料中设置、勾选并保存章节范围。';
  updatePracticeAvailability();
}
for (const [id, value] of [['practice-all',true],['practice-none',false]]) {
  $(id).onclick = () => { practiceSelection.forEach((_,key)=>practiceSelection.set(key,value)); renderPracticeChapterChoices(); };
}
async function loadPracticeHistory(courseId) {
  try {
    const records = await api(`/courses/${courseId}/practices`);
    if (activeCourse?.id !== courseId) return;
    practicePending = records.some(r=>['generating','processing'].includes(r.status)); updatePracticeAvailability();
    $('practice-history').replaceChildren();
    const statuses = {processing:'分批处理中，可继续',generating:'生成中',ready:'继续作答',submitted:'查看结果',failed:'生成失败'};
    for (const record of records) {
      const row = document.createElement('div'); row.className = 'outline-history-row';
      const button = document.createElement('button'); button.type = 'button';
      button.textContent = `${new Date(record.created_at*1000).toLocaleString()} · ${record.attempt_kind === 'exam' ? '【限时考试】' : ''}${record.title || '章节练习'} · ${statuses[record.status]}`;
      button.onclick = () => showPractice(record.id,courseId); row.append(button); $('practice-history').append(row);
    }
    if (!records.length) $('practice-history').textContent = '还没有练习，选好章节和题量后即可生成。';
    if (typeof loadMistakes === 'function') await loadMistakes(courseId);
  } catch (error) { if (activeCourse?.id === courseId) $('practice-message').textContent = error.message; }
}
$('practice-refresh').onclick = () => { if (activeCourse) loadPracticeHistory(activeCourse.id); };
$('practice-create-form').onsubmit = async event => {
  event.preventDefault(); if (!activeCourse || $('practice-generate').disabled || practiceGenerating) return;
  if (practiceDirty && !window.confirm('当前答案尚未保存。生成并打开新练习会丢失未保存内容，是否继续？')) return;
  const courseId = activeCourse.id, ranges = practiceRanges();
  const counts = Object.fromEntries(Object.keys(practiceKinds).map(k=>[k,Number($('practice-count-'+k).value)]));
  practiceGenerating = true; updatePracticeAvailability();
  $('practice-message').textContent = '正在生成练习，请勿重复提交。离开后可从练习记录查看。';
  try {
    const result = await api(`/courses/${courseId}/practices`, {method:'POST',body:JSON.stringify({material_ids:[...new Set(ranges.map(r=>r.material_id))],chapter_keys:ranges.map(r=>r.key),counts,...(typeof examOptions === 'function' ? examOptions() : {}),request_id:crypto.randomUUID()})});
    if (activeCourse?.id !== courseId) return;
    await loadPracticeHistory(courseId);
    $('practice-message').textContent = result.status === 'ready' ? '练习已生成。请作答并保存，交卷后查看解析。' : result.message || '生成尚在进行，请稍后刷新记录。';
    await showPractice(result.id,courseId);
  } catch (error) {
    if (activeCourse?.id === courseId) {
      $('practice-message').textContent = error.message + '。如连接中断，请先刷新练习记录，确认结果后再生成，避免重复计费。';
      await loadPracticeHistory(courseId);
    }
  } finally { practiceGenerating = false; updatePracticeAvailability(); }
};
async function showPractice(id,courseId) {
  if (practiceSaving || activeCourse?.id !== courseId) return;
  if (practiceDirty && !window.confirm('当前答案尚未保存。确定放弃未保存内容并打开练习吗？')) return;
  const token = ++practiceViewToken;
  try {
    const record = await api(`/practices/${id}`);
    if (activeCourse?.id !== courseId || token !== practiceViewToken) return;
    practiceRecord = record; practiceDirty = false; renderPracticeSession();
    $('practice-session').scrollIntoView({behavior:'smooth',block:'start'});
  } catch (error) { if (activeCourse?.id === courseId) $('practice-message').textContent = error.message; }
}
function practiceText(tag, text, className) {
  const node = document.createElement(tag); node.textContent = text; if (className) node.className = className; return node;
}
function renderPracticeSession() {
  const record = practiceRecord, target = $('practice-session'); target.replaceChildren(); target.hidden = false;
  target.append(practiceText('h3',record.title || '章节练习'));
  if (typeof renderExam === 'function' && renderExam(record,target)) return;
  if (record.variant_of) target.append(practiceText('p','这是错题变式，按新题独立作答；报告与首次练习、原题重做分开统计。','muted'));
  if (record.parent_id) target.append(practiceText('p','这是原题重做，答案与得分单独保存，不覆盖首次作答。题目沿用原练习版本。','muted'));
  if (record.status === 'processing' && record.pipeline) { renderPracticePipeline(record,target); return; }
  if (record.pipeline && record.status === 'ready') target.append(practiceText('p',record.message,'muted'));
  if(record.status==='failed' && !record.variant_of && !record.parent_id && !record.pipeline) {
    const retry=practiceText('button',record.retained_questions ? '继续补齐练习' : '重试生成练习','primary');retry.type='button';
    retry.onclick=async()=>{
      if(!window.confirm('将使用原先选择的资料范围补题，保留合格题；最多追加一次纠错调用，可能产生AI费用。是否继续？'))return;
      retry.disabled=true;const courseId=record.course_id;
      try{const result=await api(`/practices/${record.id}/retry-generation`,{method:'POST'});if(activeCourse?.id===courseId && practiceRecord?.id===record.id){practiceRecord=result;renderPracticeSession();await loadPracticeHistory(courseId);}}
      catch(error){if(practiceRecord?.id===record.id)target.append(practiceText('p',error.message));}
      finally{retry.disabled=false;}
    };target.append(retry);
  }
  if (!['ready','submitted'].includes(record.status)) { target.append(practiceText('p',record.message || '正在生成，请稍后刷新练习记录。')); return; }
  target.append(practiceText('p',record.stale ? '资料已变化，本次练习仍使用生成时的题目与来源，不受后续编辑影响。' : record.model === 'manual' ? '用户录入的参考试卷，请自行核对答案与评分要点。' : 'AI 生成题目，请结合交卷后的来源核对。', 'muted'));
  const scope = document.createElement('details'); scope.append(practiceText('summary','本次练习范围（生成时快照）'));
  record.selected_chapters.forEach(r=>scope.append(practiceText('p',`${r.title} · ${r.name} · ${r.start_location} 至 ${r.end_location}`))); target.append(scope);
  const form = document.createElement('form'); form.id = 'practice-answer-form';
  const submitted = record.status === 'submitted';
  if (submitted) {
    const result = record.result;
    target.append(practiceText('p',record.variant_of ? variantSummary(result) : `客观题得分：${result.objective_score} / ${result.objective_max}。` + (result.pending_self_review ? `还有 ${result.pending_self_review} 道填空或简答待评分，暂不显示总分。` : `总分：${result.total_score} / ${result.max_score}${result.questions.some(q=>['self','ai'].includes(q.mode)) ? '（含人工评分或 AI 建议，请核对）' : ''}。`), 'practice-score'));
  } else target.append(practiceText('p',record.variant_of ? '变式练习不显示分值。提交后按正确、部分正确、错误评价；未作答题提交后记为错误。' : '修改后自动保存，也可点击“保存答案”；请以保存状态为准，重新打开可继续。交卷后答案锁定；空题按 0 分计。多选题：全对得满分、非空正确子集得一半分、错选或空白 0 分。每题分值见题号旁。','muted'));
  for (const [index,q] of record.questions.entries()) {
    const field = document.createElement('fieldset'); field.className = 'practice-question'; field.dataset.questionId = q.id;
    field.append(practiceText('legend',`${index+1}. ${practiceKinds[q.kind]}${record.variant_of ? '' : ` · ${q.max_score??2} 分`}`),practiceText('p',q.prompt));
    const answer = record.answers[q.id] || [];
    if (submitted) {
      field.append(practiceText('p','你的答案：' + (answer.join('；') || '未作答')));
      q.options.forEach((option,i)=>field.append(practiceText('p',`${'ABCDEF'[i]}. ${option}`)));
      field.append(practiceText('p','参考答案：'+q.answer.join('；')),practiceText('p','解析：'+q.explanation));
      if (q.key_points.length) field.append(practiceText('p','核对要点：'+q.key_points.join('；')));
      const grade = record.result.questions.find(r=>r.id === q.id);
      field.append(practiceText('p',record.variant_of ? variantVerdict(grade.score,grade.max_score) : grade.score === null ? '待评分' : `得分：${grade.score} / ${grade.max_score}（${grade.mode === 'self' ? '人工评分' : grade.mode === 'ai' ? 'AI 建议分' : grade.mode === 'blank' ? '空白答案' : '程序判分'}）`));
      if (['self','ai'].includes(grade.mode) && q.kind==='short' && q.scoring_version===2) {
        field.append(practiceText('p',record.variant_of ? '逐项核对：全部达到为正确，部分达到为部分正确，均未达到为错误。' : `共 ${q.key_points.length} 个评分要点，等权分配${q.max_score??5}分；达到得该点全分，部分达到得该点一半分。总分保留两位小数。`));
        q.key_points.forEach((point,i)=>{const label=practiceText('label',`${i+1}. ${point}`);const select=document.createElement('select');select.dataset.pointReviewId=q.id;select.dataset.pointIndex=String(i);for(const [value,text] of [['','暂不评分'],['met','达到'],['partial','部分达到'],['missed','未达到']])select.add(new Option(text,value));select.value=grade.point_verdicts?.[i]??'';label.append(select);field.append(label);});
      } else if (['self','ai'].includes(grade.mode)) {
        const label = practiceText('label','人工核对或修正分数：');
        const select = document.createElement('select'); select.dataset.reviewId = q.id;
        for (const [value,text] of (record.variant_of ? [['','待评价'],['0','错误'],[String((q.max_score??2)/2),'部分正确'],[String(q.max_score??2),'正确']] : manualScoreChoices(q.max_score??2))) select.add(new Option(text,value));
        select.options[0].disabled = grade.score !== null;
        select.value = grade.score === null ? '' : String(grade.score); label.append(select); field.append(label);
      }
      renderAIReview(field,q,grade,record);
      for (const ref of q.source_ids) {
        const source = record.sources.find(s=>s.source_id === ref); if (!source) continue;
        const detail = document.createElement('details'); detail.append(practiceText('summary',`${ref} · ${source.name} · ${source.location}`), practiceText('pre',source.text)); field.append(detail);
      }
    } else if (['fill','short'].includes(q.kind)) {
      const label = practiceText('label','你的答案'); const input = document.createElement('textarea'); input.maxLength = 4000; input.rows = q.kind === 'short' ? 5 : 2; input.value = answer[0] || ''; label.append(input); field.append(label);
    } else {
      const options = q.kind === 'true_false' ? ['正确','错误'] : q.options;
      options.forEach((option,i)=> {
        const label = document.createElement('label'); label.className = 'outline-choice';
        const input = document.createElement('input'); input.type = q.kind === 'multiple' ? 'checkbox' : 'radio'; input.name = q.id; input.value = q.kind === 'true_false' ? option : 'ABCDEF'[i]; input.checked = answer.includes(input.value);
        label.append(input,document.createTextNode(q.kind === 'true_false' ? option : `${input.value}. ${option}`)); field.append(label);
      });
      const clear = document.createElement('button'); clear.type = 'button'; clear.textContent = '清空本题'; clear.onclick = () => { field.querySelectorAll('input').forEach(n=>n.checked=false); markPracticeDirty(); }; field.append(clear);
    }
    form.append(field);
  }
  const actions = document.createElement('div'); actions.className = 'actions';
  if (!submitted) {
    const save = practiceText('button','保存答案'); save.type = 'button'; save.onclick = () => savePractice(false);
    const submit = practiceText('button','交卷并查看结果','primary'); submit.type = 'submit'; actions.append(save,submit);
    form.onsubmit = event => { event.preventDefault(); savePractice(true); };
  } else if (record.result.questions.some(q=>['self','ai'].includes(q.mode))) {
    const review = practiceText('button',record.variant_of ? '保存评价' : '保存人工评分','primary'); review.type = 'submit'; actions.append(review);
    form.onsubmit = event => { event.preventDefault(); saveSelfReview(); };
  } else form.onsubmit = event => event.preventDefault();
  if (submitted && record.result.questions.some(q=>['self','ai'].includes(q.mode))) {
    const refresh = practiceText('button','刷新批改结果'); refresh.type = 'button'; refresh.onclick = () => showPractice(record.id,record.course_id); actions.append(refresh);
    form.append(practiceText('p',record.variant_of ? 'AI 可根据参考答案与核对要点评价，也可人工修正；待评价题不计入正确率。AI 批改可能产生费用。' : '点击“AI 批改本题”会发送该题、已提交答案及其引用原文，可能产生接口费用。新版简答按各评分要点等权计分；填空保留全对2分、部分1分、未达到0分。旧题沿用原规则。AI只为尚未评分的题目填分，已有人工评分保留；AI判断可能有误，可人工修正。','muted'));
  }
  form.oninput = markPracticeDirty; form.onchange = markPracticeDirty;
  form.append(actions); target.append(form,practiceText('p',submitted ? '' : '尚无未保存修改。'));
  target.lastChild.id = 'practice-save-status'; target.lastChild.setAttribute('role','status');
}
function markPracticeDirty() { if (typeof queueExamSave === 'function') queueExamSave(); practiceDirty = true; $('practice-save-status').textContent = '有未保存的修改。'; }
function collectPracticeAnswers() {
  const answers = {};
  for (const field of $('practice-answer-form').querySelectorAll('[data-question-id]')) {
    const text = field.querySelector('textarea');
    answers[field.dataset.questionId] = text ? (text.value.trim() ? [text.value] : []) : Array.from(field.querySelectorAll('input:checked'),n=>n.value);
  }
  return answers;
}
function setPracticeSaving(value) {
  practiceSaving = value; $('practice-answer-form')?.querySelectorAll('input,textarea,select,button').forEach(n=>n.disabled=value||n.dataset?.confidenceLocked==='true');
}
async function savePractice(submit) {
  if (typeof examSavePromise !== 'undefined' && examSavePromise) await examSavePromise;
  if (practiceSaving || practiceRecord?.status !== 'ready') return;
  const record = practiceRecord, courseId = activeCourse.id;
  if(submit && typeof flushConfidence==='function'){try{await flushConfidence(record.id);}catch(error){$('practice-save-status').textContent='信心记录尚未保存：'+error.message;return;}if(practiceRecord?.id!==record.id)return;}
  const answers = collectPracticeAnswers();
  const blank = record.questions.filter(q=>!answers[q.id]?.length).length;
  if (submit && !window.confirm(`确定交卷吗？${blank ? `有 ${blank} 道题未作答，${record.variant_of ? '提交后记为错误' : '将按 0 分计'}。` : ''}交卷后答案不能修改。`)) return;
  setPracticeSaving(true);
  try {
    const result = await api(`/practices/${record.id}/${submit?'submit':'answers'}`, {method:submit?'POST':'PUT',body:JSON.stringify({revision:record.revision,answers})});
    if (activeCourse?.id !== courseId || practiceRecord?.id !== record.id) return;
    practiceDirty = false;
    if (!submit && result.status === 'submitted') { practiceRecord = await api(`/practices/${record.id}`); renderPracticeSession(); await loadPracticeHistory(courseId); }
    else if (submit) { practiceRecord = result; renderPracticeSession(); await loadPracticeHistory(courseId); }
    else { practiceRecord.answers = answers; practiceRecord.revision = result.revision; $('practice-save-status').textContent = '答案已保存，可稍后从练习记录继续。'; }
  } catch (error) {
    if (activeCourse?.id === courseId && practiceRecord?.id === record.id) $('practice-save-status').textContent = error.message + '。请保留当前内容；若交卷响应丢失，可再次交卷确认结果。';
  } finally { setPracticeSaving(false); }
}
async function saveSelfReview() {
  if (practiceSaving || practiceRecord?.status !== 'submitted') return;
  const record = practiceRecord, courseId = activeCourse.id;
  const scores = Object.fromEntries(Array.from($('practice-answer-form').querySelectorAll('[data-review-id]')).filter(n=>n.value !== '').map(n=>[n.dataset.reviewId,Number(n.value)]));
  const point_verdicts = {};
  for(const select of $('practice-answer-form').querySelectorAll('[data-point-review-id]')) {
    (point_verdicts[select.dataset.pointReviewId]??=[])[Number(select.dataset.pointIndex)]=select.value;
  }
  for(const [id,values] of Object.entries(point_verdicts)) {
    if(values.every(v=>!v)){delete point_verdicts[id];continue;}
    if(values.some(v=>!v)){$('practice-save-status').textContent='请评完该简答题的全部要点，再保存评分。';return;}
  }
  setPracticeSaving(true);
  try {
    const result = await api(`/practices/${record.id}/self-review`,{method:'PUT',body:JSON.stringify({revision:record.revision,scores,...(Object.keys(point_verdicts).length?{point_verdicts}:{})})});
    if (activeCourse?.id !== courseId || practiceRecord?.id !== record.id) return;
    practiceRecord = result; practiceDirty = false; renderPracticeSession(); $('practice-save-status').textContent = '人工评分已保存。';
    if (typeof loadMistakes === 'function') await loadMistakes(courseId);
  } catch (error) { if (practiceRecord?.id === record.id) $('practice-save-status').textContent = error.message; }
  finally { setPracticeSaving(false); }
}
window.addEventListener('beforeunload', event => { if (practiceDirty) { event.preventDefault(); event.returnValue = ''; } });
const practiceBack = $('back-courses').onclick;
$('back-courses').onclick = () => {
  if (practiceSaving || practiceDirty && !window.confirm('当前练习有未保存的修改，确定离开吗？')) return;
  practiceDirty = false; practiceViewToken++; practiceBack();
};
const practiceLogout = $('logout').onclick;
$('logout').onclick = () => {
  if (practiceSaving || practiceDirty && !window.confirm('当前练习有未保存的修改，确定退出吗？')) return;
  practiceDirty = false; practiceViewToken++; return practiceLogout();
};


function manualScoreChoices(maximum=2){return [['','暂不评分'],['0','0 分：未达到'],[String(maximum/2),`${maximum/2} 分：部分达到`],[String(maximum),`${maximum} 分：全部达到`]];}
