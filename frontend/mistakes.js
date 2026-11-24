const mistakesPanel = document.createElement('section'); mistakesPanel.className = 'panel';
mistakesPanel.innerHTML = `<h2>错题本 · 原题重做</h2>
  <p class="muted">收录已评分但未满分的题目（含部分得分）。AI 建议分、人工评分分别标明；待评分不视为答错。原题重做不调用 AI 出题，新的作答独立保存，不覆盖首次成绩。</p>
  <div class="mistake-filters"><label>题目搜索<input id="mistake-search" type="search" placeholder="题干或练习名称"></label>
  <label>状态<select id="mistake-state"><option value="needs_practice">最近未满分</option><option value="all">全部错题记录</option><option value="full_score">最近满分</option><option value="pending_review">重做待评分</option></select></label>
  <label>题型<select id="mistake-kind"><option value="all">全部题型</option></select></label>
  <button id="mistake-refresh" type="button">刷新错题本</button></div>
  <p id="mistake-summary"></p><p id="mistake-message" role="status"></p><div id="mistake-items"></div>`;
$('material-view').append(mistakesPanel);
let mistakesCourseId = null, mistakesData = null, mistakesRequest = 0;
const mistakeStarting = new Set();
for (const [kind,title] of Object.entries(practiceKinds)) $('mistake-kind').add(new Option(title,kind));
function resetMistakes(courseId) {
  if (mistakesCourseId === courseId) return;
  mistakesCourseId = courseId; mistakesData = null; mistakesRequest++;
  if (typeof mistakeScope !== 'undefined') mistakeScope = null;
  if (typeof resetReport === 'function') resetReport(courseId);
  $('mistake-items').replaceChildren(); $('mistake-summary').textContent = '';
  $('mistake-message').textContent = '正在加载错题本…';
  $('mistake-search').value = ''; $('mistake-state').value = 'needs_practice'; $('mistake-kind').value = 'all';
}
async function loadMistakes(courseId) {
  resetMistakes(courseId); const request = ++mistakesRequest;
  try {
    const scope = typeof mistakeScope !== 'undefined' ? mistakeScope : null;
    const [data, scopedRecord] = await Promise.all([api(`/courses/${courseId}/mistakes`), scope ? api(`/practices/${scope.id}`) : Promise.resolve(null)]);
    if (activeCourse?.id !== courseId || request !== mistakesRequest) return;
    if (scope && mistakeScope?.id === scope.id) mistakeScope = scopedRecord;
    mistakesData = data; $('mistake-message').textContent = ''; renderMistakes();
    if (typeof loadReport === 'function') await loadReport(courseId);
  } catch (error) {
    if (activeCourse?.id !== courseId || request !== mistakesRequest) return;
    $('mistake-message').textContent = '错题本刷新失败：'+error.message+'。请稍后重试。';
  }
}
function visibleMistakes(items, query, state, kind) {
  query = query.trim().toLowerCase();
  return items.filter(item => (state === 'all' || item.state === state) && (kind === 'all' || item.question.kind === kind)
    && (item.question.prompt+' '+item.practice_title).toLowerCase().includes(query));
}
function mistakeScore(score,mode,maxScore=2,variant=false) {
  if(variant) return variantVerdict(score,maxScore);
  if (score === null) return '待评分';
  return `${score} / ${maxScore}（${{automatic:'程序判分',self:'人工评分',ai:'AI 建议',blank:'未作答'}[mode] || mode}）`;
}
function renderMistakes() {
  if (!mistakesData) return;
  const scoped = typeof scopedMistakes === 'function' ? scopedMistakes(mistakesData, mistakeScope) : mistakesData;
  const summary = scoped.summary;
  $('mistake-summary').textContent = `共 ${summary.total} 道错题记录：最近未满分 ${summary.needs_practice} 道，最近满分 ${summary.full_score} 道，重做待评分 ${summary.pending_review} 道。另有 ${summary.ungraded_excluded} 道未评分题目暂未收录。`;
  const items = visibleMistakes(scoped.items,$('mistake-search').value,$('mistake-state').value,$('mistake-kind').value);
  if (typeof renderMistakeScope === 'function') renderMistakeScope();
  const target = $('mistake-items'); target.replaceChildren();
  for (const item of items) {
    const question = item.question, card = document.createElement('article'); card.className = 'mistake-card';
    if (typeof mistakeScope !== 'undefined' && mistakeScope) {
      const attempt=item.attempts.find(a=>a.practice_id===mistakeScope.id);
      if(attempt)card.append(practiceText('p','本次结果：'+mistakeScore(attempt.score,attempt.mode,item.question.max_score??2,Boolean(item.variant_of))));
    }
    card.append(practiceText('h3',`${practiceKinds[question.kind]} · ${question.prompt}`));
    card.append(practiceText('p',`原练习：${item.practice_title}`, 'muted'));
    card.append(practiceText('p',`首次：${mistakeScore(item.first_score,item.first_mode,question.max_score??2,Boolean(item.variant_of))}；最近：${mistakeScore(item.latest_score,item.latest_mode,question.max_score??2,Boolean(item.variant_of))}；已交卷重做 ${item.retry_count} 次。`));
    if (item.state === 'full_score') card.append(practiceText('p','最近一次达到满分，记录仍保留；原题熟悉度不等同于新题掌握程度。','muted'));
    if (item.state === 'pending_review') card.append(practiceText('p','最近一次重做尚未评分，请进入结果页完成 AI 辅助批改或人工评分。','muted'));
    const details = document.createElement('details'); details.append(practiceText('summary','查看原题解析、来源与作答记录'));
    question.options.forEach((option,i)=>details.append(practiceText('p',`${'ABCDEF'[i]}. ${option}`)));
    details.append(practiceText('p','参考答案：'+question.answer.join('；')),practiceText('p','解析：'+question.explanation));
    if (question.key_points.length) details.append(practiceText('p','核对要点：'+question.key_points.join('；')));
    for (const attempt of item.attempts) {
      details.append(practiceText('p',`${attempt.is_retry ? '重做' : '首次作答'} · ${new Date(attempt.submitted_at*1000).toLocaleString()} · ${mistakeScore(attempt.score,attempt.mode,question.max_score??2,Boolean(item.variant_of))}\n你的答案：${attempt.answer.join('；') || '未作答'}`));
    }
    const attemptActions=document.createElement('div');attemptActions.className='actions';details.append(attemptActions);
    for (const attempt of item.attempts) { const open=practiceText('button',attempt.is_retry?'查看本次重做':'查看首次作答');open.type='button';open.onclick=()=>showPractice(attempt.practice_id,activeCourse.id);attemptActions.append(open); }
    for (const source of item.sources) {
      const ref = document.createElement('details'); ref.append(practiceText('summary',`${source.source_id} · ${source.name} · ${source.location}（出题时原文）`),practiceText('pre',source.text)); details.append(ref);
    }
    card.append(details);
    const actions = document.createElement('div'); actions.className = 'actions';
    const view = practiceText('button','知识点梳理'); view.type = 'button'; view.onclick = () => showMistakeKnowledge(item);
    const retry = practiceText('button',item.pending_retry_id ? '继续未完成的重做' : item.state === 'full_score' ? '再次重做原题' : '原题重做','primary'); retry.type = 'button';
    retry.disabled = mistakeStarting.has(item.practice_id+':'+question.id); retry.onclick = () => startMistakeRetry(item);
    actions.append(view,retry);
    if(typeof startMistakeVariant === "function"){const variant=practiceText("button","变式练习");variant.type="button";variant.onclick=()=>startMistakeVariant(item,variant);actions.append(variant);} card.append(actions); target.append(card);
  }
  if (!items.length) target.append(practiceText('p',summary.total ? '没有符合当前筛选条件的题目。可切换为“全部错题记录”。' : '当前没有已评分的错题。先完成练习与评分后，再来查看。','muted'));
}
async function startMistakeRetry(item) {
  if (!activeCourse || practiceSaving) return;
  const key = item.practice_id+':'+item.question.id, courseId = activeCourse.id;
  if (mistakeStarting.has(key)) return;
  if (practiceDirty) { $('mistake-message').textContent = '请先保存当前答案或人工评分，再开始重做。'; return; }
  if (item.pending_retry_id) { await showPractice(item.pending_retry_id,courseId); return; }
  mistakeStarting.add(key); renderMistakes(); $('mistake-message').textContent = '正在准备原题重做，不会调用 AI 出题…';
  try {
    const result = await api(`/practices/${item.practice_id}/retry`,{method:'POST',body:JSON.stringify({question_ids:[item.question.id],request_id:crypto.randomUUID()})});
    if (activeCourse?.id !== courseId) return;
    await loadPracticeHistory(courseId);
    if (activeCourse?.id !== courseId) return;
    $('mistake-message').textContent = '原题已准备好。本次答案独立保存，原记录不变。';
    await showPractice(result.id,courseId);
  } catch (error) {
    if (activeCourse?.id === courseId) $('mistake-message').textContent = error.message+'。连接中断时请刷新错题本，可继续已创建的重做。';
  } finally { mistakeStarting.delete(key); if (activeCourse?.id === courseId) renderMistakes(); }
}
$('mistake-refresh').onclick = () => { if (activeCourse) loadMistakes(activeCourse.id); };
$('mistake-search').oninput = renderMistakes;
$('mistake-state').onchange = $('mistake-kind').onchange = renderMistakes;

