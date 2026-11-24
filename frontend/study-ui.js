// Presentation helpers only: never save or submit answers from this module.
function answerIsPresent(field) {
  const text=field.querySelector('textarea');
  return text ? text.value.trim().length>0 : !!field.querySelector('input:checked');
}
function addQuestionNavigator() {
  const form=document.getElementById('practice-answer-form');
  if(!form || form.querySelector('.question-navigator') || practiceRecord?.status!=='ready')return;
  const fields=Array.from(form.querySelectorAll('[data-question-id]'));
  if(!fields.length)return;
  const nav=document.createElement('nav');nav.className='question-navigator';nav.setAttribute('aria-label','答题进度与题号导航');
  const info=document.createElement('div');info.className='question-progress';
  const title=document.createElement('strong');title.textContent='答题索引';
  const status=document.createElement('span');
  const hint=document.createElement('small');hint.textContent='填色并带点的题号表示已填写；保存状态请查看试卷底部。';
  info.append(title,status,hint);
  const numbers=document.createElement('div');numbers.className='question-numbers';
  const buttons=fields.map((field,i)=>{
    const button=document.createElement('button');button.type='button';button.textContent=String(i+1);
    button.onclick=()=>{
      const legend=field.querySelector('legend');
      if(legend){legend.tabIndex=-1;legend.focus({preventScroll:true});}
      field.scrollIntoView({behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'});
    };
    numbers.append(button);return button;
  });
  function update() {
    let answered=0;
    fields.forEach((field,i)=>{
      const present=answerIsPresent(field);answered+=Number(present);
      buttons[i].classList.toggle('is-answered',present);
      buttons[i].setAttribute('aria-label',`第 ${i+1} 题，${present?'已填写':'未填写'}`);
    });
    status.textContent=`已填写 ${answered} / ${fields.length} 题`;
  }
  nav.append(info,numbers);form.prepend(nav);
  form.addEventListener('input',update);form.addEventListener('change',update);
  // The existing "clear this question" action does not dispatch input events.
  form.addEventListener('click',()=>queueMicrotask(update));update();
}
function installStudyNavigation() {
  const view=document.getElementById('material-view');
  const nav=document.createElement('nav');nav.className='study-navigation';nav.setAttribute('aria-label','课程内快捷导航');
  const areas=[['upload-form','study-materials','资料与章节'],['outline-form','study-outline','复习大纲'],['practice-create-form','study-practice','专项练习'],['blueprint-upload','study-blueprints','样卷仿真'],['mistake-items','study-mistakes','错题本'],['report-content','study-report','学习报告'],['study-resources','study-resources','资源库']];
  areas.forEach(([child,id,label])=>{
    const panel=document.getElementById(child)?.closest('.panel');if(!panel)return;
    panel.id=id;panel.classList.add('study-section');
    const link=document.createElement('a');link.href='#'+id;link.textContent=label;
    link.onclick=event=>{
      event.preventDefault();
      nav.querySelectorAll('a').forEach(a=>a.removeAttribute('aria-current'));link.setAttribute('aria-current','location');
      panel.tabIndex=-1;panel.focus({preventScroll:true});panel.scrollIntoView({behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'});
    };
    nav.append(link);
  });
  view.querySelector('.hero').after(nav);
  const session=document.getElementById('practice-session');
  new MutationObserver(addQuestionNavigator).observe(session,{childList:true});
  addQuestionNavigator();
}
document.addEventListener('DOMContentLoaded',()=>installStudyNavigation());
