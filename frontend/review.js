function renderAIReview(field, question, grade, record) {
  if (!['self','ai'].includes(grade.mode)) return;
  const review = record.ai_reviews?.[question.id];
  const box = document.createElement('section'); box.className = 'ai-review';
  box.append(practiceText('h4','AI 辅助批改'));
  if (review?.status === 'ready') {
    box.append(practiceText('p',`AI 建议：${record.variant_of ? variantVerdict(review.feedback.score,grade.max_score??2) : `${review.feedback.score} / ${grade.max_score??2}`} · 模型：${review.model}`));
    box.append(practiceText('p',review.feedback.summary));
    const verdicts = {met:'达到',partial:'部分达到',missed:'未达到'};
    for (const point of review.feedback.points) {
      const item = document.createElement('details');
      item.append(practiceText('summary',`${verdicts[point.verdict]}：${point.key_point}`));
      item.append(practiceText('p',point.reason));
      item.append(practiceText('p',point.basis === 'general' ? '依据：一般学科知识，由 AI 判断，未声称来自课件，请人工核对。' : `依据：资料引用 ${point.source_ids.join('、')}，请展开下方原文核对。`, 'muted'));
      box.append(item);
    }
    if (grade.score !== review.feedback.score) {
      box.append(practiceText('p','当前分数保留你的人工评分；AI 建议未覆盖它。','muted'));
      const adopt = practiceText('button','将建议分填入人工评分'); adopt.type = 'button';
      adopt.onclick = () => { if(question.kind==='short' && question.scoring_version===2){field.querySelectorAll('[data-point-review-id]').forEach(select=>{select.value=review.feedback.points.find(p=>p.point_index===Number(select.dataset.pointIndex))?.verdict??'';});}else{field.querySelector('[data-review-id]').value = String(review.feedback.score);} markPracticeDirty(); };
      box.append(adopt);
    }
  } else {
    if (review?.message) box.append(practiceText('p',review.message));
    const button = practiceText('button',review?.status === 'running' ? '本题批改中，请刷新结果' : review?.status === 'failed' ? '重试本题 AI 批改' : 'AI 批改本题');
    button.type = 'button'; button.dataset.aiQuestion = question.id; button.disabled = review?.status === 'running';
    button.onclick = () => requestAIReview(question.id); box.append(button);
  }
  field.append(box);
}

async function requestAIReview(questionId) {
  if (practiceSaving || practiceRecord?.status !== 'submitted') return;
  if (practiceDirty) { $('practice-save-status').textContent = '请先保存人工评分，再请求 AI 批改，避免丢失未保存内容。'; return; }
  const record = practiceRecord, courseId = activeCourse.id;
  setPracticeSaving(true); $('practice-save-status').textContent = '正在批改本题，通常需要等待一段时间，请勿重复点击。';
  try {
    const result = await api(`/practices/${record.id}/ai-review`, {method:'POST',body:JSON.stringify({question_id:questionId})});
    if (activeCourse?.id !== courseId || practiceRecord?.id !== record.id) return;
    practiceRecord = result; renderPracticeSession();
    const review = result.ai_reviews?.[questionId];
    $('practice-save-status').textContent = review?.status === 'ready' ? '本题批改已保存。AI 仅为尚未评分的题目填入建议分；可人工修正并保存。' : review?.message || '批改仍在进行，请稍后刷新批改结果。';
    if (typeof loadMistakes === 'function') await loadMistakes(courseId);
  } catch (error) {
    if (activeCourse?.id === courseId && practiceRecord?.id === record.id) $('practice-save-status').textContent = error.message + '。网络断开时请先刷新批改结果；已完成的本题不会重复调用。';
  } finally {
    setPracticeSaving(false);
    $('practice-answer-form')?.querySelectorAll('[data-ai-question]').forEach(button => {
      button.disabled = practiceRecord?.ai_reviews?.[button.dataset.aiQuestion]?.status === 'running';
    });
  }
}
