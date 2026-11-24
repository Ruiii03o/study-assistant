let chapterGroups = [], chapterSelection = new Map(), chapterCourseId = null;
let chaptersLoading = true, chapterRequest = 0, outlinePending = false;

async function loadChapterChoices(courseId) {
  const request = ++chapterRequest;
  if (chapterCourseId !== courseId) {
    chapterSelection = new Map(); aiConfigured = false; outlinePending = false; chapterGroups = [];
    chapterCourseId = courseId;
  }
  chaptersLoading = true; updateChapterSummary();
  $('outline-chapters').textContent = '正在加载已保存的章节…';
  if (typeof renderPracticeChapterChoices === 'function') renderPracticeChapterChoices();
  try {
    const groups = await api(`/courses/${courseId}/chapters`);
    if (activeCourse?.id !== courseId || request !== chapterRequest) return;
    chapterGroups = groups;
    const next = new Map();
    for (const group of groups) for (const range of group.ranges) {
      next.set(range.key, chapterSelection.has(range.key) ? chapterSelection.get(range.key) : true);
    }
    chapterSelection = next; chaptersLoading = false; renderChapterChoices();
    renderPracticeChapterChoices();
  } catch (error) {
    if (activeCourse?.id !== courseId || request !== chapterRequest) return;
    chapterGroups = []; chapterSelection.clear();
    if (typeof renderPracticeChapterChoices === 'function') renderPracticeChapterChoices();
    $('outline-chapters').textContent = '章节加载失败：' + error.message + '。请点击“刷新记录与配置状态”重试。';
    updateChapterSummary();
  }
}

function visibleChapterGroups() {
  const materials = new Set(Array.from($('outline-materials').querySelectorAll('input:checked:not(:disabled)'), n => n.value));
  return chapterGroups.map(group => ({...group, ranges:group.ranges.filter(r => materials.has(r.material_id))})).filter(group => group.ranges.length);
}
function selectedChapterKeys() {
  return visibleChapterGroups().flatMap(g => g.ranges).filter(r => chapterSelection.get(r.key)).map(r => r.key);
}
function updateChapterSummary() {
  const groups = visibleChapterGroups();
  const chosen = groups.flatMap(g => g.ranges).filter(r => chapterSelection.get(r.key));
  const positions = new Set();
  for (const range of chosen) for (let i = range.unit_index; i <= range.end_unit_index; i++) positions.add(`${range.material_id}:${i}`);
  const count = groups.filter(g => g.ranges.some(r => chapterSelection.get(r.key))).length;
  $('outline-chapter-summary').textContent = chaptersLoading ? '章节尚未就绪，暂不能生成。' : `本次选择 ${count} 个章节、${chosen.length} 段范围，覆盖 ${positions.size} 个原文位置（同一文件的重叠位置只计一次）。`;
  $('outline-generate').disabled = !aiConfigured || outlineBusy || outlinePending || chaptersLoading || !chosen.length;
  $('chapters-select-all').disabled = $('chapters-select-none').disabled = chaptersLoading || !groups.length;
  if (typeof updatePracticeAvailability === 'function') updatePracticeAvailability();
}
function renderChapterChoices() {
  if (chaptersLoading) { updateChapterSummary(); return; }
  const target = $('outline-chapters');
  const expanded = new Set(Array.from(target.querySelectorAll('details[open]'), d => d.dataset.title));
  target.replaceChildren();
  const groups = visibleChapterGroups();
  for (const group of groups) {
    const card = document.createElement('section'); card.className = 'chapter-group';
    const label = document.createElement('label'); label.className = 'outline-choice';
    const check = document.createElement('input'); check.type = 'checkbox';
    const count = group.ranges.filter(r => chapterSelection.get(r.key)).length;
    check.checked = count === group.ranges.length; check.indeterminate = count > 0 && count < group.ranges.length;
    label.append(check, document.createTextNode(`${group.title}（${group.ranges.length} 段范围 / ${new Set(group.ranges.map(r => r.material_id)).size} 份资料）`));
    check.onchange = () => { group.ranges.forEach(r => chapterSelection.set(r.key, check.checked)); renderChapterChoices(); };
    const details = document.createElement('details'); details.dataset.title = group.title; details.open = expanded.has(group.title);
    const summary = document.createElement('summary'); summary.textContent = '展开查看来源与范围'; details.append(summary);
    for (const range of group.ranges) {
      const row = document.createElement('label'); row.className = 'outline-choice';
      const input = document.createElement('input'); input.type = 'checkbox'; input.checked = chapterSelection.get(range.key);
      input.onchange = () => { chapterSelection.set(range.key, input.checked); renderChapterChoices(); };
      row.append(input, document.createTextNode(`${range.name} · ${range.start_location} 至 ${range.end_location}`)); details.append(row);
    }
    card.append(label, details); target.append(card);
  }
  if (!groups.length) target.textContent = '当前资料没有可选章节。请先选择资料，并在资料中添加、勾选范围后保存确认。';
  updateChapterSummary();
}
for (const [id, selected] of [['chapters-select-all', true], ['chapters-select-none', false]]) {
  $(id).onclick = () => { visibleChapterGroups().forEach(g => g.ranges.forEach(r => chapterSelection.set(r.key, selected))); renderChapterChoices(); };
}

