const $ = (id) => document.getElementById(id);
let mode = 'login', courses = [], editing = null;
async function api(path, options = {}) {
  let response;
  try { response = await fetch('/api' + path, {credentials:'same-origin', headers:{'Content-Type':'application/json'}, ...options}); }
  catch { throw new Error('无法连接服务，请检查后端是否仍在运行。'); }
  const data = await response.json();
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith('/auth/')) showAuth();
    throw new Error(typeof data.detail === 'string' ? data.detail : Array.isArray(data.detail) ? data.detail.map(e=>`${(e.loc||[]).filter(x=>x!=='body').join(' / ')||'请求参数'}：${e.msg||'不符合要求'}`).join('；') : '输入不符合要求，请检查长度与格式。');
  }
  return data;
}
function showAuth() { activeCourse = activeMaterial = null; $('material-detail').hidden = true; $('material-list').replaceChildren(); $('workspace').hidden = true; $('auth').hidden = false; $('course-dialog').close(); courses = []; $('cards').replaceChildren(); }
function setMode(next) {
  mode = next; const login = mode === 'login';
  $('login-tab').classList.toggle('selected', login); $('register-tab').classList.toggle('selected', !login);
  $('auth-title').textContent = login ? '欢迎回来' : '创建你的学习空间';
  $('auth-subtitle').textContent = login ? '欢迎回来，今天再拿下一点。' : '建个账户，给期末留条后路。';
  $('auth-submit').textContent = login ? '登录' : '注册账户';
  $('password').autocomplete = login ? 'current-password' : 'new-password'; $('auth-message').textContent = '';
}
$('login-tab').onclick = () => setMode('login'); $('register-tab').onclick = () => setMode('register');
async function showWorkspace(user) {
  $('material-view').hidden = true; document.querySelector('#workspace > main').hidden = false;
  $('auth').hidden = true; $('workspace').hidden = false; $('username').textContent = user.username;
  $('search').value = ''; $('workspace-message').textContent = '';
  try { courses = await api('/courses'); renderCourses(); }
  catch (error) { $('workspace-message').textContent = error.message; }
}
$('auth-form').onsubmit = async (event) => {
  event.preventDefault(); $('auth-submit').disabled = true; $('login-tab').disabled = $('register-tab').disabled = true;
  $('auth-message').textContent = ''; const body = JSON.stringify(Object.fromEntries(new FormData(event.target)));
  try {
    if (mode === 'register') { await api('/auth/register', {method:'POST',body}); setMode('login'); $('auth-message').textContent = '注册成功，请使用刚才的账户登录。'; }
    else { const user = await api('/auth/login', {method:'POST',body}); $('password').value = ''; await showWorkspace(user); }
  } catch (error) { $('auth-message').textContent = error.message; }
  finally { $('auth-submit').disabled = false; $('login-tab').disabled = $('register-tab').disabled = false; }
};
$('logout').onclick = async () => {
  $('logout').disabled = true;
  try { await api('/auth/logout', {method:'POST'}); showAuth(); setMode('login'); }
  catch (error) { $('workspace-message').textContent = error.message; }
  finally { $('logout').disabled = false; }
};
function openCourse(course = null) {
  editing = course?.id ?? null; const form = $('course-form'); form.reset();
  form.elements.name.value = course?.name ?? ''; form.elements.description.value = course?.description ?? '';
  $('dialog-title').textContent = course ? '编辑课程' : '新建课程'; $('course-message').textContent = ''; $('course-dialog').showModal();
}
$('create').onclick = () => openCourse(); $('empty-create').onclick = () => openCourse();
$('close-dialog').onclick = () => $('course-dialog').close();
$('course-form').onsubmit = async (event) => {
  event.preventDefault(); $('course-submit').disabled = true; $('close-dialog').disabled = true;
  const id = editing; const values = Object.fromEntries(new FormData(event.target));
  try {
    const saved = await api(id === null ? '/courses' : '/courses/' + id, {method:id === null ? 'POST' : 'PUT', body:JSON.stringify(values)});
    if (id === null) courses.unshift(saved); else courses = courses.map(c => c.id === id ? {...c,...saved} : c);
    $('search').value = ''; renderCourses(); $('course-dialog').close(); $('workspace-message').textContent = '课程已保存。';
  } catch (error) { $('course-message').textContent = error.message; }
  finally { $('course-submit').disabled = false; $('close-dialog').disabled = false; }
};
function renderCourses() {
  const query = $('search').value.trim().toLowerCase();
  const visible = courses.filter(c => (c.name + ' ' + c.description).toLowerCase().includes(query));
  $('count').textContent = query ? `找到 ${visible.length} 门课程` : `共 ${courses.length} 门课程`;
  $('cards').replaceChildren();
  for (const course of visible) {
    const card = document.createElement('article'); card.className = 'card'; card.dataset.tone=String(Number(course.id)%4);
    const icon = document.createElement('div'); icon.className = 'course-icon'; icon.setAttribute('aria-hidden','true');
    const title = document.createElement('h2'); title.textContent = course.name;
    const desc = document.createElement('p'); desc.textContent = course.description || '还没有添加课程说明。';
    const button = document.createElement('button'); button.textContent = '编辑课程'; button.onclick = () => openCourse(course);
    const enter = document.createElement('button'); enter.className = 'primary'; enter.textContent = '进入课程'; enter.onclick = () => enterCourse(course);
    const remove = document.createElement('button'); remove.type='button'; remove.className='danger'; remove.textContent='删除课程'; remove.onclick=()=>deleteCourseDialog(course);
    const actions = document.createElement('div'); actions.className = 'actions'; actions.append(enter, button, remove);
    card.append(icon,title,desc,actions); $('cards').append(card);
  }
  $('empty').hidden = visible.length > 0; $('empty-create').hidden = courses.length > 0;
  $('empty-title').textContent = courses.length ? '没有匹配的课程' : '你的第一门课程，从这里开始';
  $('empty-text').textContent = courses.length ? '试试其他关键词，或清空搜索。' : '创建课程名称与说明，保存后可以随时回来编辑。';
}
$('search').oninput = renderCourses;
async function deleteCourseDialog(course) {
  const {d,message,close}=toolDialog('删除课程');
  message.setAttribute('role','status');message.textContent='正在核对删除范围……';
  try {
    const info=await api(`/courses/${course.id}/deletion-preview`);
    if(!d.isConnected)return;
    const c=info.counts;
    d.append(toolNode('p',`将永久删除“${info.name}”：${c.materials} 份资料、${c.outlines+c.outline_sessions} 份大纲（含存档）、${c.practices} 份练习/考试、${c.exam_blueprints} 份样卷、${c.resources} 条收藏。关联作答、错题、批注和学习统计一并删除，无法撤销。`));
    const form=toolNode('form'),field=toolField('请输入完整课程名称确认');field.input.required=true;field.input.autocomplete='off';
    const submit=toolNode('button','永久删除');submit.className='danger';submit.disabled=true;
    field.input.oninput=()=>{submit.disabled=field.input.value!==info.name;};
    form.append(field.wrap,submit);d.append(form);message.textContent='';field.input.focus();
    form.onsubmit=async e=>{
      e.preventDefault();if(field.input.value!==info.name)return;
      submit.disabled=true;close.disabled=true;field.input.disabled=true;
      try {
        const result=await api(`/courses/${course.id}`,{method:'DELETE',body:JSON.stringify({name:field.input.value})});
        courses=courses.filter(c=>c.id!==course.id);renderCourses();d.close();$('workspace-message').textContent=result.message;
      } catch(error){message.textContent=error.message;}
      finally{submit.disabled=field.input.value!==info.name;close.disabled=false;field.input.disabled=false;}
    };
  } catch(error){message.textContent=error.message;}
}
let activeCourse = null, activeMaterial = null;
$('workspace').append($('material-view'));
$('material-file').multiple = true;
$('upload-button').textContent = '批量上传';
const wholeButton = document.createElement('button'); wholeButton.type = 'button'; wholeButton.id = 'whole-material'; wholeButton.textContent = '整份资料作为一章';
$('add-chapter').before(wholeButton);
const rangeHelp = $('chapters-form').previousElementSibling;
rangeHelp.textContent = '每条范围包含起始和结束位置，无需逐页添加。同一章需要不连续的范围时，可添加多条并填写相同章节名。勾选表示纳入复习，修改后请保存。';
const rangeSummary = document.createElement('p'); rangeSummary.id = 'range-summary'; rangeSummary.setAttribute('aria-live','polite'); $('chapter-rows').after(rangeSummary);
const previewRangeButton = document.createElement('button'); previewRangeButton.type = 'button'; previewRangeButton.textContent = '预览已保存的复习内容';
const rangePreview = document.createElement('pre'); rangePreview.hidden = true;
const previewActions = document.createElement('div'); previewActions.className = 'actions range-preview-actions';
previewActions.append(previewRangeButton);
rangeSummary.after(previewActions, rangePreview);
previewRangeButton.onclick = async () => {
  if (!activeMaterial) return;
  const id = activeMaterial.id; previewRangeButton.disabled = true;
  try {
    const result = await api(`/materials/${id}/selected-content`);
    if (activeMaterial?.id !== id) return;
    rangePreview.hidden = false;
    rangePreview.textContent = result.units.length ? result.units.map(u => `${u.location}\n${u.text}`).join('\n\n') : '已保存的范围没有勾选任何内容。';
  } catch (e) { $('material-message').textContent = e.message; }
  finally { previewRangeButton.disabled = false; }
};
const refreshButton = document.createElement('button'); refreshButton.type = 'button'; refreshButton.id = 'refresh-text'; refreshButton.textContent = '更新文字提取（保留章节）'; $('detail-note').after(refreshButton);
refreshButton.onclick = async () => {
  if (!activeMaterial) return;
  const id = activeMaterial.id, courseId = activeCourse.id;
  refreshButton.disabled = true;
  try {
    await api(`/materials/${id}/refresh-text`, {method:'POST'});
    const latest = await api(`/materials/${id}`);
    if (activeMaterial?.id === id && activeCourse?.id === courseId) {
      activeMaterial.units = latest.units; showUnit();
      $('detail-note').textContent = '文字已重新提取；已保存章节和当前未保存的范围编辑均保留。已确认的图文校对保留；复杂图示可使用“原页对照与图文校对”。';
    }
  } catch (e) { $('material-message').textContent = e.message; }
  finally { refreshButton.disabled = activeMaterial?.status !== 'ready'; }
};
wholeButton.onclick = () => {
  if (!activeMaterial?.units.length) return;
  if ($('chapter-rows').children.length && !window.confirm('将当前范围替换为覆盖整份资料的一条范围？保存后才会更新已存设置。')) return;
  $('chapter-rows').replaceChildren();
  addChapterRow({title:activeMaterial.name.replace(/\.[^.]+$/, ''),unit_index:0,end_unit_index:activeMaterial.units.length-1,included:true});
};
document.querySelector('.sidebar-note').textContent = 'You will pass all exams!';
$('back-courses').onclick = () => {
  activeCourse = activeMaterial = null;
  $('material-view').hidden = true; document.querySelector('#workspace > main').hidden = false;
};
async function enterCourse(course) {
  activeCourse = course; activeMaterial = null;
  if (typeof resetMistakes === 'function') resetMistakes(course.id);
  document.querySelector('#workspace > main').hidden = true; $('material-view').hidden = false;
  $('material-course-title').textContent = course.name; $('material-detail').hidden = true;
  $('material-message').textContent = ''; $('upload-form').reset(); $('material-list').replaceChildren();
  try { await loadMaterials(course.id); } catch (e) { $('material-message').textContent = e.message; }
  if (activeCourse?.id === course.id) await loadOutlineWorkspace(course.id);
  if (activeCourse?.id === course.id) await loadPracticeHistory(course.id);
}
async function loadMaterials(courseId) {
  const items = await api(`/courses/${courseId}/materials`);
  if (activeCourse?.id !== courseId) return;
  $('material-list').replaceChildren();
  await renderOutlineMaterials(items);
  if (activeCourse?.id !== courseId) return;
  if (!items.length) { const p = document.createElement('p'); p.className = 'empty'; p.textContent = '还没有资料，上传第一份课件开始吧。'; $('material-list').append(p); }
  const statuses = {uploaded:'待解析', ready:'已提取文字', needs_ocr:'待接入 OCR', failed:'解析失败'};
  for (const item of items) {
    const row = document.createElement('article'); row.className = 'panel';
    const title = document.createElement('h3'); title.textContent = item.name;
    const note = document.createElement('p'); note.className = 'muted'; note.textContent = `${(item.size/1024).toFixed(1)} KB · ${item.confirmed ? '章节已确认' : statuses[item.status] || item.status}`;
    const actions = document.createElement('div'); actions.className = 'actions';
    const view = document.createElement('button'); view.textContent = '查看内容与章节';
    view.onclick = () => openMaterial(item.id, courseId).catch(e => { $('material-message').textContent = e.message; });
    const parse = document.createElement('button'); parse.textContent = '提取文字'; parse.disabled = !!item.confirmed;
    parse.onclick = async () => {
      parse.disabled = true; parse.textContent = '正在提取…';
      try { await api(`/materials/${item.id}/parse`, {method:'POST'}); await loadMaterials(courseId); await openMaterial(item.id, courseId); }
      catch (e) { $('material-message').textContent = e.message; }
      finally { parse.disabled = !!item.confirmed; parse.textContent = '提取文字'; }
    };
    const download = document.createElement('a'); download.href = `/api/materials/${item.id}/download`; download.textContent = '下载原文件';
    actions.append(parse, view, download); row.append(title,note,actions); $('material-list').append(row);
  }
}
$('upload-form').onsubmit = async (event) => {
  event.preventDefault(); const files = Array.from($('material-file').files), courseId = activeCourse?.id;
  if (!files.length || !courseId) return;
  $('upload-button').disabled = true; $('material-message').textContent = '正在上传，请稍候…';
  $('material-file').disabled = true;
  const failures = []; let succeeded = 0;
  try {
    for (const [index, file] of files.entries()) {
      if (activeCourse?.id !== courseId) break;
      $('material-message').textContent = `上传 ${index+1}/${files.length}：${file.name}`;
      try {
        if (file.size > 30*1024*1024) throw new Error('超过 30MB');
        await api(`/courses/${courseId}/materials?name=${encodeURIComponent(file.name)}`, {method:'POST', headers:{'Content-Type':'application/octet-stream'}, body:file});
        succeeded++;
      } catch (e) { failures.push(`${file.name}：${e.message}`); }
    }
    if (activeCourse?.id !== courseId) return;
    $('upload-form').reset(); $('material-message').textContent = `成功上传 ${succeeded} 份。请分别提取文字并设置章节范围。` + (failures.length ? `失败 ${failures.length} 份（仅需重试失败文件）：${failures.join('；')}` : ''); await loadMaterials(courseId);
  } catch (e) { $('material-message').textContent = e.message; }
  finally { $('upload-button').disabled = false; $('material-file').disabled = false; }
};
async function openMaterial(id, courseId) {
  if (activeCourse?.id !== courseId) return;
  rangePreview.hidden = true; rangePreview.textContent = '';
  activeMaterial = null; $('material-detail').hidden = true;
  const item = await api(`/materials/${id}`);
  if (activeCourse?.id !== courseId) return;
  activeMaterial = item; $('material-detail').hidden = false; $('detail-title').textContent = item.name;
  $('detail-note').textContent = item.message || '资料已保存，请先提取文字。';
  $('unit-select').replaceChildren();
  item.units.forEach((u,i) => $('unit-select').add(new Option(u.location, i)));
  showUnit(); $('chapter-rows').replaceChildren();
  item.chapters.forEach(addChapterRow);
  if (item.chapters.some(c => c.range_needs_review)) $('detail-note').textContent += ' 旧版章节只记录了起点，请补充结束位置后保存；系统未自动推测旧范围。';
  $('add-chapter').disabled = $('save-chapters').disabled = wholeButton.disabled = refreshButton.disabled = item.status !== 'ready';
  updateRangeSummary();
}
function showUnit() { $('unit-text').textContent = activeMaterial?.units[Number($('unit-select').value)]?.text || '此处暂无可预览的文字。'; }
$('unit-select').onchange = showUnit;
function addChapterRow(chapter = {title:'', unit_index:0, end_unit_index:0, included:true}) {
  const row = document.createElement('div'); row.className = 'chapter-row';
  const includeLabel = document.createElement('label'); const included = document.createElement('input'); included.type = 'checkbox'; included.checked = chapter.included; included.className = 'chapter-included'; includeLabel.append(included,' 纳入复习');
  const title = document.createElement('input'); title.className = 'chapter-title'; title.value = chapter.title; title.required = true; title.maxLength = 100; title.placeholder = '章节名称'; title.setAttribute('aria-label','章节名称');
  const unit = document.createElement('select'); unit.className = 'chapter-unit'; unit.setAttribute('aria-label','章节起始位置');
  activeMaterial.units.forEach((u,i) => unit.add(new Option(u.location,i))); unit.value = chapter.unit_index;
  const end = document.createElement('select'); end.className = 'chapter-end'; end.setAttribute('aria-label','范围结束位置');
  activeMaterial.units.forEach((u,i) => end.add(new Option(u.location,i))); end.value = chapter.end_unit_index ?? chapter.unit_index;
  const startLabel = document.createElement('label'); startLabel.append('从（含）',unit);
  const endLabel = document.createElement('label'); endLabel.append('到（含）',end);
  const remove = document.createElement('button'); remove.type = 'button'; remove.textContent = '移除'; remove.onclick = () => { row.remove(); updateRangeSummary(); };
  row.append(includeLabel,title,startLabel,endLabel,remove); $('chapter-rows').append(row);
  row.oninput = updateRangeSummary; row.onchange = updateRangeSummary;
  updateRangeSummary();
}
function updateRangeSummary() {
  const selected = new Set(); let invalid = false, ranges = 0;
  for (const row of $('chapter-rows').children) {
    const start = Number(row.querySelector('.chapter-unit').value), end = Number(row.querySelector('.chapter-end').value);
    row.querySelector('.chapter-end').setCustomValidity(end < start ? '结束位置不能早于起始位置' : '');
    if (end < start) { invalid = true; continue; }
    if (row.querySelector('.chapter-included').checked) { ranges++; for (let i=start;i<=end;i++) selected.add(i); }
  }
  rangeSummary.textContent = !$('chapter-rows').children.length ? '尚未设置复习范围。点击“添加章节”选择范围，或点击“整份资料作为一章”，然后保存并确认。' : invalid ? '请修正起止顺序：结束位置不能早于起始位置。' : `当前选中 ${ranges} 段范围，覆盖 ${selected.size} / ${activeMaterial?.units.length || 0} 个原文位置（重叠位置只计算一次）。${selected.size ? '' : '尚未选择复习内容。'}`;
}
$('add-chapter').onclick = () => { if ($('chapter-rows').children.length < 100) addChapterRow(); };
$('chapters-form').onsubmit = async (event) => {
  event.preventDefault(); if (!activeMaterial) return;
  const id = activeMaterial.id, courseId = activeCourse.id;
  const chapters = Array.from($('chapter-rows').children, row => ({title:row.querySelector('.chapter-title').value.trim(),unit_index:Number(row.querySelector('.chapter-unit').value),end_unit_index:Number(row.querySelector('.chapter-end').value),included:row.querySelector('.chapter-included').checked}));
  $('save-chapters').disabled = true;
  try {
    await api(`/materials/${id}/chapters`,{method:'PUT',body:JSON.stringify({chapters})});
    if (activeCourse?.id !== courseId) return;
    if (activeMaterial?.id === id) {
      activeMaterial.confirmed = 1; activeMaterial.chapters = chapters;
      rangePreview.hidden = true;
      $('detail-note').textContent = '复习范围已保存并确认。后续编辑需再次保存才会用于 AI 大纲。';
    }
    $('material-message').textContent = chapters.some(c => c.included) ? '复习范围已保存。可在下方 复习大纲整理中勾选这份资料。' : '范围已保存，但未勾选纳入复习的章节；请勾选后再次保存。';
    await loadMaterials(courseId);
  } catch (e) { $('material-message').textContent = e.message; }
  finally { $('save-chapters').disabled = activeMaterial?.status !== 'ready'; }
};
