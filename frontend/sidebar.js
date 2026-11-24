// One existing sidebar serves both the course list and course tasks.
let courseSidebar=null,courseMenuOpen=false,courseSidebarCollapsed=false,courseMenuToggle=null,courseMenuShade=null;
const courseMedia=window.matchMedia('(max-width: 800px)');
const courseIcons={materials:'M4 5h6l2 2h8v12H4z',review:'M4 4h7l1 2 1-2h7v15h-7l-1 2-1-2H4z M12 6v15',train:'M8 4h8v3H8z M6 6H4v15h16V6h-2 M8 11h8 M8 15h5',mistakes:'M5 4h14v16H5z M9 8l6 6 M15 8l-6 6',report:'M4 4v16h16 M8 16v-5 M12 16V7 M16 16v-8'};
function sidebarIcon(key){const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('aria-hidden','true');const path=document.createElementNS(svg.namespaceURI,'path');path.setAttribute('d',courseIcons[key]);svg.append(path);return svg;}
function ensureCourseSidebar(){
 if(courseSidebar||!studyNav)return;
 const aside=$('workspace').querySelector(':scope > aside');if(!aside)return;
 aside.id='course-sidebar';courseSidebar=aside;
 const pane=practiceText('section','','course-sidebar-pane');pane.id='course-sidebar-pane';pane.hidden=true;
 const top=practiceText('div','','course-sidebar-top');
 const back=practiceText('button','← 我的课程','course-list-back');back.type='button';back.onclick=()=>{$('back-courses').click();};
 const close=practiceText('button','关闭菜单','course-menu-close');close.type='button';close.onclick=()=>setCourseMenu(false);top.append(back,close);
 const caption=practiceText('p','当前课程','course-sidebar-caption'),title=practiceText('h2','','course-sidebar-title');title.id='course-sidebar-title';pane.append(top,caption,title);
 const resume=studyNav.querySelector('button:not([data-page])');
 for(const button of studyNav.querySelectorAll('[data-page]')){const text=button.textContent;button.replaceChildren(sidebarIcon(button.dataset.page),practiceText('span',text));button.addEventListener('click',()=>setCourseMenu(false));}
 pane.append(studyNav);
 const continuation=practiceText('section','','course-continuation');continuation.id='course-continuation';continuation.hidden=true;
 if(resume){resume.id='course-resume';resume.replaceChildren(practiceText('span','继续答题'),practiceText('small','','course-resume-detail'));resume.addEventListener('click',()=>setCourseMenu(false));continuation.append(resume);}pane.append(continuation);
 aside.querySelector('.account').before(pane);
 const header=$('material-view').querySelector('header');courseMenuToggle=practiceText('button','课程菜单','course-menu-toggle');courseMenuToggle.type='button';courseMenuToggle.setAttribute('aria-controls','course-sidebar');courseMenuToggle.onclick=()=>{if(courseMedia.matches)setCourseMenu(!courseMenuOpen);else{courseSidebarCollapsed=!courseSidebarCollapsed;syncCourseSidebar();}};header.prepend(courseMenuToggle);
 courseMenuShade=practiceText('button','','course-menu-shade');courseMenuShade.type='button';courseMenuShade.hidden=true;courseMenuShade.setAttribute('aria-label','关闭课程菜单');courseMenuShade.tabIndex=-1;courseMenuShade.onclick=()=>setCourseMenu(false);document.body.append(courseMenuShade);
 aside.addEventListener('click',event=>{if(event.target.closest('.account button'))setCourseMenu(false,false);},true);
 document.addEventListener('keydown',event=>{
  if(!courseMenuOpen||!courseMedia.matches)return;
  if(event.key==='Escape'){event.preventDefault();setCourseMenu(false);}
  if(event.key==='Tab'){const nodes=[...aside.querySelectorAll('a,button,input,select')].filter(n=>!n.disabled&&n.getClientRects().length);const first=nodes[0],last=nodes.at(-1);if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}}
 });
 courseMedia.addEventListener('change',()=>{courseMenuOpen=false;syncCourseSidebar();});
 $('practice-session').addEventListener('click',()=>queueMicrotask(syncCourseContinuation));$('practice-session').addEventListener('input',syncCourseContinuation);$('practice-session').addEventListener('change',syncCourseContinuation);
 new MutationObserver(syncCourseContinuation).observe($('practice-session'),{childList:true});
}
function setCourseMenu(open,focus=true){courseMenuOpen=Boolean(open);syncCourseSidebar();if(courseMedia.matches&&focus){if(open){const selected=courseSidebar?.querySelector('[aria-current="page"]');(selected?.getClientRects().length?selected:courseSidebar?.querySelector('.course-menu-close'))?.focus();}else courseMenuToggle?.focus();}}
function syncCourseContinuation(){
 const box=$('course-continuation');if(!box)return;
 const record=practiceRecord,show=!!(activeCourse&&record?.course_id===activeCourse.id&&record.status==='ready');box.hidden=!show;
 if(!show)return;
 const fields=[...$('practice-session').querySelectorAll('[data-question-id]')];
 const total=record.questions?.length||Object.values(record.counts||{}).reduce((a,b)=>a+b,0);
 const done=fields.length?fields.filter(answerIsPresent).length:Object.values(record.answers||{}).filter(a=>a.some(v=>String(v).trim())).length;
 $('course-resume').setAttribute('aria-current',studyPage==='answer'?'page':'false');
 const text=$('course-resume').querySelector('small');text.textContent=record.attempt_kind==='exam'&&!record.started_at?`待开始 · ${total}题`:`已填写 ${done} / ${total} 题`;
}
function syncCourseSidebar(){
 ensureCourseSidebar();if(!courseSidebar)return;
 const inCourse=!!activeCourse&&!$('material-view').hidden;
 $('workspace').classList.toggle('course-mode',inCourse);
 $('course-sidebar-pane').hidden=!inCourse;
 if(!inCourse)courseMenuOpen=false;
 $('workspace').classList.toggle('course-menu-open',inCourse&&courseMenuOpen&&courseMedia.matches);
 $('workspace').classList.toggle('course-sidebar-collapsed',inCourse&&courseSidebarCollapsed&&!courseMedia.matches);
 courseMenuShade.hidden=!(inCourse&&courseMenuOpen&&courseMedia.matches);
 document.body.classList.toggle('course-menu-lock',!courseMenuShade.hidden);
 if(!courseMenuShade.hidden){courseSidebar.setAttribute('role','dialog');courseSidebar.setAttribute('aria-modal','true');courseSidebar.setAttribute('aria-label','课程导航');}else{courseSidebar.removeAttribute('role');courseSidebar.removeAttribute('aria-modal');courseSidebar.removeAttribute('aria-label');}
 courseMenuToggle.setAttribute('aria-expanded',String(courseMedia.matches?courseMenuOpen:!courseSidebarCollapsed));
 courseMenuToggle.textContent=courseMedia.matches?'☰ 课程菜单':courseSidebarCollapsed?'☰ 展开侧栏':'收起侧栏';
 $('course-sidebar-title').textContent=activeCourse?.name||'';
 if(inCourse){$('material-course-title').textContent=studyLabels[studyPage];const hint=$('study-location');if(hint)hint.hidden=true;}
 syncCourseContinuation();
}
const sideNavigate=navigateStudy;navigateStudy=function(...args){const result=sideNavigate(...args);syncCourseSidebar();return result;};
const sideAuth=showAuth;showAuth=function(...args){const result=sideAuth(...args);syncCourseSidebar();return result;};
const sideBack=$('back-courses').onclick;$('back-courses').onclick=async function(event){await sideBack?.(event);syncCourseSidebar();};
