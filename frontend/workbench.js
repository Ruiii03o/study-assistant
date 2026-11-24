// Task pages keep their live DOM, drafts and filters while another page is shown.
const studyPages=new Map(),studyPositions=new Map();
let studyPage='materials',studySubpage='practice',studyOrigin=null,studyDialog=null,studyNav=null,studyCourse=null;
const studyLabels={materials:'资料',review:'复习',train:'练习与考试',mistakes:'错题本',report:'学习报告',answer:'答题'};
function studyKey(page){return `${activeCourse?.id}:${page}${page==='answer'?':'+practiceRecord?.id:''}`;}
function navigateStudy(page,{remember=true,subpage=null,restore=true}={}){
 if(!studyPages.has(page))return;
 if(remember)studyPositions.set(studyKey(studyPage),window.scrollY);
 studyPage=page;if(subpage)studySubpage=subpage;
 for(const [name,node] of studyPages)node.hidden=name!==page;
 for(const button of studyNav?.querySelectorAll('[data-page]')||[])button.setAttribute('aria-current',button.dataset.page===page?'page':'false');
 const train=studyPages.get('train');for(const node of train?.querySelectorAll('[data-train-page]')||[])node.hidden=node.dataset.trainPage!==studySubpage;
 for(const button of train?.querySelectorAll('[data-train-choice]')||[])button.setAttribute('aria-pressed',String(button.dataset.trainChoice===studySubpage));
 if(restore)window.scrollTo({top:studyPositions.get(studyKey(page))||0,behavior:'instant'});
 const intro=$('material-view').querySelector('.hero p');if(intro)intro.textContent={materials:'上传与整理资料，设置复习范围',review:'翻阅知识卡片，整理复习大纲',train:'按章节练习，或依据样卷进行仿真考试',mistakes:'回看错题，核对知识点并继续练习',report:'查看学习表现与信心分析',answer:'专心完成当前作答；切换页面不会暂停考试计时'}[page];
 const hint=$('study-location');if(hint)hint.textContent=`${activeCourse?.name||''} / ${studyLabels[page]}`;
 if(page==='report'&&activeCourse&&typeof loadReport==='function')loadReport(activeCourse.id);
}
function installStudyNavigation(){
 const view=$('material-view');if(studyNav?.isConnected||view.querySelector('.task-navigation'))return;
 const original=[...view.children];studyNav=practiceText('nav','','task-navigation');studyNav.setAttribute('aria-label','课程任务');
 for(const page of ['materials','review','train','mistakes','report']){const button=practiceText('button',studyLabels[page]);button.type='button';button.dataset.page=page;button.onclick=()=>navigateStudy(page);studyNav.append(button);}
 const resume=practiceText('button','返回当前答题');resume.type='button';resume.onclick=()=>{if(practiceRecord){navigateStudy('answer');$('practice-session').hidden=false;}else{navigateStudy('train');}};studyNav.append(resume);
 view.querySelector('.hero').after(studyNav);const location=practiceText('p','','study-location');location.id='study-location';studyNav.after(location);
 for(const key of Object.keys(studyLabels)){const page=practiceText('section','','task-page');page.id='task-'+key;page.setAttribute('aria-label',studyLabels[key]);page.hidden=key!=='materials';studyPages.set(key,page);view.append(page);}
 const train=studyPages.get('train'),choices=practiceText('div','','actions');
 for(const [key,label] of [['practice','专项练习'],['exam','样卷仿真']]){const button=practiceText('button',label);button.type='button';button.dataset.trainChoice=key;button.onclick=()=>navigateStudy('train',{subpage:key,restore:false});choices.append(button);}train.append(choices);
 const practiceGroup=practiceText('div'),examGroup=practiceText('div');practiceGroup.dataset.trainPage='practice';examGroup.dataset.trainPage='exam';train.append(practiceGroup,examGroup);
 const session=$('practice-session');studyPages.get('answer').append(session);
 for(const node of original){if(node.matches('header,.hero'))continue;
  if(node.querySelector('#outline-form'))studyPages.get('review').append(node);
  else if(node.querySelector('#practice-create-form'))practiceGroup.append(node);
  else if(node.querySelector('#blueprint-upload'))examGroup.append(node);
  else if(node.querySelector('#mistake-items'))studyPages.get('mistakes').append(node);
  else if(node.querySelector('#report-content'))studyPages.get('report').append(node);
  else studyPages.get('materials').append(node);
 }
 new MutationObserver(addQuestionNavigator).observe(session,{childList:true});addQuestionNavigator();navigateStudy('materials');
}
const taskEnterCourse=enterCourse;
enterCourse=async function(course){if(practiceRecord){try{await flushConfidence(practiceRecord.id);}catch(error){alert('请先保存信心记录：'+error.message);return;}}if(studyDialog){await closeStudyDialog();if(studyDialog)return;}studyCourse=course.id;studyOrigin=null;await taskEnterCourse(course);if(activeCourse?.id===course.id)navigateStudy('materials',{remember:false});};
const taskOpenMaterial=openMaterial;
openMaterial=async function(id,course){navigateStudy('materials');return taskOpenMaterial(id,course);};
function addStudyReturn(){
 if(!practiceRecord||!studyOrigin)return;
 const target=$('practice-session');target.querySelector('.task-return')?.remove();
 const bar=practiceText('div','','task-return actions');bar.append(practiceText('span',`来自${studyLabels[studyOrigin.page]}${studyOrigin.note?' · '+studyOrigin.note:''}`));
 const back=practiceText('button','返回'+studyLabels[studyOrigin.page]);back.type='button';back.onclick=()=>studyDialog?closeStudyDialog():navigateStudy(studyOrigin.page,{subpage:studyOrigin.subpage});bar.append(back);target.prepend(bar);
}
const taskRender=renderPracticeSession;
renderPracticeSession=function(){taskRender();addStudyReturn();};
const taskShowPractice=showPractice;
showPractice=async function(id,course){
 if(typeof flushConfidence==='function'&&practiceRecord){try{await flushConfidence(practiceRecord.id);}catch(error){$('practice-message').textContent='请先保存信心记录：'+error.message;return;}}
 if(studyPage==='answer')studyPositions.set(studyKey('answer'),window.scrollY);
 const origin=(studyPage==='answer'||studyPage==='train'&&studyOrigin?.note)?studyOrigin:{page:studyPage,subpage:studySubpage};
 await taskShowPractice(id,course);if(practiceRecord?.id!==id||activeCourse?.id!==course)return;
 studyOrigin=origin||{page:'train',subpage:'practice'};addStudyReturn();
 if(studyOrigin.page==='mistakes'&&practiceRecord.questions?.length===1&&practiceRecord.attempt_kind!=='exam'){
   if(!studyDialog){const d=document.createElement('dialog');d.className='single-question-dialog';d.setAttribute('aria-label','单题练习');const close=practiceText('button','返回错题本');close.type='button';close.onclick=closeStudyDialog;d.append(close,$('practice-session'));d.addEventListener('cancel',event=>{event.preventDefault();closeStudyDialog();});document.body.append(d);studyDialog=d;d.showModal();}
 }else navigateStudy('answer',{remember:studyPage!=='answer'});
};
async function closeStudyDialog(){
 if(!studyDialog)return;
 if(practiceSaving)return;
 if(practiceRecord?.status==='ready'&&practiceDirty){await savePractice(false);if(practiceDirty)return;}
 if(typeof flushConfidence==='function'&&practiceRecord){try{await flushConfidence(practiceRecord.id);}catch(error){alert('信心记录未保存：'+error.message);return;}}
 const d=studyDialog;studyDialog=null;studyPages.get('answer').append($('practice-session'));d.close();d.remove();navigateStudy(studyOrigin?.page||'mistakes');
 if(activeCourse)loadMistakes(activeCourse.id);
}

for(const id of ['logout','back-courses']){const before=$(id).onclick;$(id).onclick=async event=>{if(practiceRecord){try{await flushConfidence(practiceRecord.id);}catch(error){alert('信心记录尚未保存：'+error.message);return;}}return before?.(event);};}
