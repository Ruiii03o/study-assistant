// All model and document strings are rendered as text, never as HTML.
const outlinePanel = document.createElement('section');
outlinePanel.className = 'panel';
outlinePanel.innerHTML = `<h2>复习大纲整理</h2>
  <p class="muted">先选择资料，再勾选本次要复习的章节。同名章节汇总展示，可展开选择其中的范围。本次选择不会修改资料中已保存的范围。</p>
  <div class="actions"><p id="ai-status" role="status"></p><button id="outline-refresh" type="button">刷新 AI 配置状态</button></div>
  <form id="outline-form"><fieldset><legend>选择资料（可多选）</legend><div id="outline-materials"></div></fieldset>
  <fieldset id="outline-chapter-fieldset"><legend>本次复习章节</legend><p class="muted">仅显示已保存、纳入复习且有文字的范围。同名合并仅用于展示，不代表内容已经去重；不同主题请在资料中使用不同章节名。</p><div class="actions"><button id="chapters-select-all" type="button">全选章节</button><button id="chapters-select-none" type="button">清空选择</button></div><div id="outline-chapters"></div><p id="outline-chapter-summary" role="status"></p></fieldset>
  <label>复习目标（选填）<textarea id="outline-goal" maxlength="1000" rows="2" placeholder="例如：梳理网络分层的作用，突出容易混淆的概念"></textarea></label>
  <label>详细程度<select id="outline-level"><option>精简</option><option>详细</option></select></label>
  <p class="muted">点击生成会将所选范围的提取文字发送给已配置的 AI 服务，并可能产生接口费用；不会发送未选择的原始文件。大范围将自动分批，每次处理一批并保留已完成内容；多批会产生多次调用费用。</p>
  <button id="outline-generate" class="primary" disabled>生成复习大纲</button></form>
  <p id="outline-message" role="status"></p>
  <div id="outline-history" hidden></div><section id="outline-result" hidden></section>`;
$('material-view').append(outlinePanel);
let outlineBusy = false, aiConfigured = false, outlineViewId = null;
let outlineCourseId = null;
document.querySelector('.sidebar-note').textContent = 'You will pass all exams!';
document.querySelector('.roadmap small').textContent = '今天学一点，上岸近一点';

async function renderOutlineMaterials(items) {
  const previous = new Map(Array.from($('outline-materials').querySelectorAll('input'), node => [node.value,node.checked]));
  const sameCourse = outlineCourseId === activeCourse?.id;
  outlineCourseId = activeCourse?.id;
  $('outline-materials').replaceChildren();
  for (const item of items) {
    const label = document.createElement('label'); label.className = 'outline-choice';
    const input = document.createElement('input'); input.type = 'checkbox'; input.value = item.id;
    input.disabled = !item.confirmed || item.status !== 'ready';
    input.onchange = renderChapterChoices;
    input.checked = !input.disabled && (sameCourse && previous.has(item.id) ? previous.get(item.id) : true);
    const reason = item.status !== 'ready' ? ({uploaded:'尚未提取文字', needs_ocr:'未提取到文字，需要 OCR', failed:'文字提取失败，请重试'}[item.status] || '文字尚未就绪') : !item.confirmed ? '文字已提取，尚未保存并确认范围' : '';
    label.append(input,document.createTextNode(item.name + (reason ? `（${reason}）` : '')));
    const row = document.createElement('div'); row.className = 'outline-material-row'; row.append(label);
    if (item.status === 'ready' && !item.confirmed) {
      const setup = document.createElement('button'); setup.type = 'button'; setup.textContent = '设置范围';
      const courseId = activeCourse.id;
      setup.onclick = async () => {
        try { await openMaterial(item.id, courseId); if (activeCourse?.id === courseId) $('material-detail').scrollIntoView({behavior:'smooth', block:'start'}); }
        catch (e) { $('outline-message').textContent = e.message; }
      };
      row.append(setup);
    }
    $('outline-materials').append(row);
  }
  if (!items.length) $('outline-materials').textContent = '上传资料后，将在这里选择生成范围。';
  await loadChapterChoices(activeCourse.id);
}

async function loadOutlineWorkspace(courseId) {
  outlineViewId = null; $('outline-result').hidden = true; $('outline-result').replaceChildren();
  $('outline-message').textContent = ''; $('outline-history').replaceChildren();
  aiConfigured = false; $('outline-generate').disabled = true;
  try {
    const [config, records] = await Promise.all([api('/ai/status'),api(`/courses/${courseId}/outlines`)]);
    if (activeCourse?.id !== courseId) return;
    aiConfigured = config.configured;
    $('ai-status').textContent = config.message + (config.model ? ` · 模型：${config.model}` : '。配置方法见项目 docs/ai-setup.md。');
    outlinePending = records.some(r => r.status === 'generating');
    updateChapterSummary();
    renderOutlineHistory(records, courseId);
    if (typeof loadOutlineSessions === 'function') await loadOutlineSessions(courseId);
  } catch (e) { if (activeCourse?.id === courseId) $('outline-message').textContent = e.message; }
}

function renderOutlineHistory(records, courseId) {
  outlinePending = records.some(r => r.status === 'generating');
  updateChapterSummary();
  $('outline-history').replaceChildren();
  if (!records.length) { $('outline-history').textContent = '尚未生成大纲。配置 AI 并确认资料范围后即可开始。'; return; }
  for (const record of records) {
    const row = document.createElement('div'); row.className = 'outline-history-row';
    const button = document.createElement('button');
    const statuses = {ready:'已完成',generating:'生成中',failed:'失败'};
    button.textContent = `${new Date(record.created_at*1000).toLocaleString()} · ${record.detail} · ${statuses[record.status]}`;
    button.onclick = () => showOutline(record.id,courseId).catch(e => { $('outline-message').textContent = e.message; });
    const note = document.createElement('span'); note.textContent = record.goal || '按资料梳理知识';
    row.append(button,note); $('outline-history').append(row);
  }
}
$('outline-refresh').onclick = async () => {
  if (!activeCourse) return;
  const courseId = activeCourse.id;
  try { await loadMaterials(courseId); if (activeCourse?.id === courseId) await loadOutlineWorkspace(courseId); }
  catch (e) { $('outline-message').textContent = e.message; }
};
$('outline-form').onsubmit = async event => {
  event.preventDefault(); if (!activeCourse || outlineBusy) return;
  const courseId = activeCourse.id;
  const ids = Array.from($('outline-materials').querySelectorAll('input:checked:not(:disabled)'),node=>node.value);
  if (!ids.length) { $('outline-message').textContent = '请至少选择一份已确认范围的资料。'; return; }
  const chapterKeys = selectedChapterKeys();
  if (chaptersLoading || !chapterKeys.length) { $('outline-message').textContent = '请等待章节加载完成，并至少勾选一个章节范围。'; return; }
  outlineBusy = true; $('outline-generate').disabled = true;
  $('outline-message').textContent = '正在生成，通常需要等待一段时间。请勿重复提交；离开页面后可从生成记录查看结果。';
  try {
    const result = await api(`/courses/${courseId}/outlines`,{method:'POST',body:JSON.stringify({material_ids:ids,chapter_keys:chapterKeys,goal:$('outline-goal').value,detail:$('outline-level').value})});
    if (activeCourse?.id !== courseId) return;
    const records = await api(`/courses/${courseId}/outlines`);
    if (activeCourse?.id !== courseId) return;
    renderOutlineHistory(records,courseId);
    $('outline-message').textContent = result.status === 'ready' ? '大纲已生成并保存，可以查看来源或导出。' : result.message;
    await showOutline(result.id,courseId);
  } catch (e) { if (activeCourse?.id === courseId) $('outline-message').textContent = e.message + ' 如网络中断，请先刷新记录确认结果，再决定是否重试。'; }
  finally { outlineBusy = false; updateChapterSummary(); }
};

async function showOutline(id,courseId) {
  outlineViewId = id;
  const record = await api(`/outlines/${id}`);
  if (activeCourse?.id !== courseId || outlineViewId !== id) return;
  const target = $('outline-result'); target.replaceChildren(); target.hidden = false;
  const status = document.createElement('p'); status.className = 'muted';
  status.textContent = record.stale ? '资料文字或范围已变化：这是旧版本大纲，引用展示的是生成时的原文快照。需要最新内容时请重新生成。' : '引用可定位到生成时的原文。系统已检查引用位置存在，但内容准确性仍需核对。';
  target.append(status);
  if (record.status !== 'ready') { const p = document.createElement('p'); p.textContent = record.message || '生成仍在进行，请稍后刷新记录。'; target.append(p); return; }
  const title = document.createElement('h2'); title.textContent = record.result.title; target.append(title);
  if (record.selected_chapters?.length) {
    const scope = document.createElement('details'), heading = document.createElement('summary');
    heading.textContent = '查看本次选章记录（生成时快照）'; scope.append(heading);
    for (const item of record.selected_chapters) {
      const line = document.createElement('p'); line.textContent = `${item.title} · ${item.name} · ${item.start_location} 至 ${item.end_location}`; scope.append(line);
    }
    target.append(scope);
  }
  const exportButton = document.createElement('button'); exportButton.textContent = '导出 Markdown'; exportButton.onclick = () => exportOutline(record); target.append(exportButton);
  renderKnowledgeCards(record,target);
}

function exportOutline(record) {
  const lines = [`# ${record.result.title}`,'',`模型：${record.model}；生成时间：${new Date(record.created_at*1000).toLocaleString()}`,'', 'AI 生成内容，请结合来源核对。引用原文为生成时快照。',''];
  if (record.selected_chapters?.length) {
    lines.push('## 本次选章记录', '');
    record.selected_chapters.forEach(item => lines.push(`- ${item.title} · ${item.name} · ${item.start_location} 至 ${item.end_location}`));
    lines.push('');
  }
  for (const section of record.result.sections) {
    lines.push(`## ${section.title}`,'');
    section.points.forEach(point=>lines.push(`- ${point.text}（来源：${point.source_ids.join('、')}）`));
    lines.push('');
  }
  lines.push('## 来源原文','');
  record.sources.forEach(source=>lines.push(`### ${source.source_id} · ${source.name} · ${source.location}`,'',source.text,''));
  const url = URL.createObjectURL(new Blob([lines.join('\n')],{type:'text/markdown;charset=utf-8'}));
  const link = document.createElement('a'); link.href = url; link.download = `复习大纲-${record.id.slice(0,8)}.md`; document.body.append(link); link.click(); link.remove(); setTimeout(()=>URL.revokeObjectURL(url),1000);
}
