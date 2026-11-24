// Deadlines are enforced by the server; this timer is only a display.
const examSettings = document.createElement('div');
examSettings.className = 'practice-counts';
examSettings.innerHTML = `<label>训练方式<select id="practice-mode"><option value="practice">章节练习</option><option value="exam">自选限时练习</option></select></label><label id="exam-duration-label" hidden>考试时长（分钟）<input id="exam-minutes" type="number" min="1" max="180" value="30" step="1"></label>`;
$('practice-create-form').prepend(examSettings);
$('exam-minutes').disabled = true;
$('practice-mode').onchange = () => {
  const enabled=$('practice-mode').value==='exam';
  $('exam-duration-label').hidden=!enabled; $('exam-minutes').disabled=!enabled;
  $('practice-generate').textContent=enabled ? '生成限时练习' : '生成新练习';
};
let examTimer = null, examAutosaveTimer = null, examSavePromise = null, examEditVersion = 0;
function examOptions() {
  if ($('practice-mode').value !== 'exam') return {};
  const minutes = Number($('exam-minutes').value);
  if (!Number.isInteger(minutes) || minutes < 1 || minutes > 180) throw new Error('考试时长须为 1–180 分钟的整数');
  return {exam_minutes:minutes};
}
function examRemaining(deadline, serverTime, elapsedMs) { return Math.max(0, Math.ceil(deadline-serverTime-elapsedMs/1000)); }
function renderExam(record, target) {
  clearInterval(examTimer); clearTimeout(examAutosaveTimer);
  if (record.attempt_kind !== 'exam') return false;
  target.append(practiceText('p',`限时模拟考试 · ${record.duration_seconds/60} 分钟 · 分值以本卷题目为准，详见题号旁。考试与普通练习分别统计。`));
  if (record.status === 'submitted') {
    target.append(practiceText('p',record.submission_reason === 'timeout' ? '考试时间已到，已按最后成功保存的答案交卷。' : '本次考试已交卷。'));
    return false;
  }
  if (record.status !== 'ready') return false;
  if (record.started_at == null) {
    target.append(practiceText('p','试卷已准备好。点击开始考试后显示题目并计时；刷新或离开页面不会暂停。作答会自动保存，断网时未保存的修改无法计入到时交卷。'));
    const start = practiceText('button','开始考试','primary'); start.type='button';
    start.onclick=async()=>{
      start.disabled=true;
      try {
        const result=await api(`/practices/${record.id}/start-exam`,{method:'POST'});
        if(practiceRecord?.id!==record.id || activeCourse?.id!==record.course_id)return;
        practiceRecord=result;practiceDirty=false;renderPracticeSession();
      } catch(error) { start.disabled=false;target.append(practiceText('p',error.message)); }
    };
    target.append(start);return true;
  }
  const clock=practiceText('p','','practice-score'); target.append(clock);
  const anchor=performance.now(); let finishing=false;
  const tick=async()=>{
    if(practiceRecord?.id!==record.id || activeCourse?.id!==record.course_id || $('material-view').hidden) {clearInterval(examTimer);return;}
    const seconds=examRemaining(record.deadline,record.server_time,performance.now()-anchor);
    clock.textContent=`剩余时间 ${Math.floor(seconds/60)}:${String(seconds%60).padStart(2,'0')} · 修改后自动保存`;
    if(seconds || finishing)return;
    $('practice-answer-form')?.querySelectorAll('input,textarea,button').forEach(n=>n.disabled=true);
    clock.textContent='时间已到，正在确认交卷结果；未保存的答案不计入成绩。';
    if(practiceSaving)return;
    finishing=true;
    try {
      const latest=await api(`/practices/${record.id}`);
      if(practiceRecord?.id!==record.id || activeCourse?.id!==record.course_id)return;
      if(latest.status==='submitted') {practiceRecord=latest;practiceDirty=false;renderPracticeSession();await loadPracticeHistory(record.course_id);}
    } catch(error) {clock.textContent='到时交卷结果暂未获取：'+error.message+'。恢复连接后自动重试。';}
    finally {finishing=false;}
  };
  examTimer=setInterval(tick,1000);tick();return false;
}
function queueExamSave() {
  if(practiceRecord?.status!=='ready' || (practiceRecord.attempt_kind==='exam' && practiceRecord.started_at==null))return;
  examEditVersion++;clearTimeout(examAutosaveTimer);
  examAutosaveTimer=setTimeout(autoSaveExam,800);
}
async function autoSaveExam() {
  if(practiceRecord?.status!=='ready' || !practiceDirty || !activeCourse || $('material-view').hidden)return;
  if(practiceSaving) {examAutosaveTimer=setTimeout(autoSaveExam,800);return;}
  const record=practiceRecord, version=examEditVersion, answers=collectPracticeAnswers();
  practiceSaving=true;
  examSavePromise=(async()=>{
    try {
      const result=await api(`/practices/${record.id}/answers`,{method:'PUT',body:JSON.stringify({revision:record.revision,answers})});
      if(practiceRecord?.id!==record.id || activeCourse?.id!==record.course_id)return;
      if(result.status==='submitted') {
        practiceRecord=await api(`/practices/${record.id}`);practiceDirty=false;renderPracticeSession();await loadPracticeHistory(record.course_id);return;
      }
      record.revision=result.revision;record.answers=answers;
      practiceDirty=version!==examEditVersion;
      $('practice-save-status').textContent=practiceDirty ? '正在保存后续修改…' : '答案已自动保存。';
    } catch(error) {
      if(practiceRecord?.id===record.id) $('practice-save-status').textContent='自动保存失败：'+error.message+'。请保留页面；如在其他页面作答，请关闭其他页面后重新打开本次练习或考试。';
    } finally {practiceSaving=false;examSavePromise=null;}
  })();
  await examSavePromise;
  if(practiceDirty && practiceRecord?.id===record.id) examAutosaveTimer=setTimeout(autoSaveExam,3000);
}
