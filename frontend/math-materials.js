// Save each page against its latest material revision; failed pages retain their drafts.
async function saveMathDrafts(items,request,onResult){
 const results=[];
 for(const item of items){
  let result;
  try{
   const latest=await request(item.base+'/analysis');
   if(latest.busy)throw Error('本页正在识别，请稍后重试');
   if(latest.draft?.id!==item.draft_id)throw Error('本页草稿已变化，请刷新后核对');
   await request(item.base+'/analysis',{method:'PUT',body:JSON.stringify({revision:latest.revision,draft_id:item.draft_id,text:item.text})});
   result={...item,ok:true};
  }catch(e){result={...item,ok:false,error:e.message};}
  results.push(result);onResult(result);
 }
 return results;
}
async function openMathMaterials(){
 if(!activeMaterial?.units?.length)return;
 const material=activeMaterial,mid=material.id;
 const {d,message,close}=toolDialog('数学资料识别与校对');d.classList.add('math-material-dialog');
 let running=false,saving=false,stop=false,current=null,currentState=null,currentDraft=null,dirty=false;
 const edits=new Map();
 const start=toolField('起始页','select'),end=toolField('结束页','select');
 material.units.forEach((u,i)=>{start.input.add(new Option(u.location,String(i)));end.input.add(new Option(u.location,String(i)));});
 start.input.value=$('unit-select').value;end.input.value=String(material.units.length-1);
 const consent=toolNode('label'),agree=toolNode('input');agree.type='checkbox';consent.append(agree,' 将所选页图片发送给已配置的视觉模型，逐页识别可能产生费用。');
 const rows=toolNode('div'),editor=toolNode('section');editor.hidden=true;
 const image=toolNode('img');image.className='source-page-image';image.alt='当前校对页原图';
 const text=toolField('识别文字与LaTeX公式（可修改）','textarea');text.input.rows=18;
 const preview=toolNode('div');preview.className='math-preview';
 const uncertainty=toolNode('p');
 const columns=toolNode('div');columns.className='math-review-columns';const right=toolNode('div');right.append(text.wrap,uncertainty,toolNode('h4','公式预览'),preview);columns.append(image,right);
 const repaint=()=>{preview.textContent=text.input.value;renderStudyMath(preview);};text.input.oninput=()=>{dirty=true;if(currentDraft)edits.set(current,{id:currentDraft.id,text:text.input.value});repaint();};
 const base=i=>`/materials/${mid}/pages/${i}`;
 function canLeave(){return !saving&&(!edits.size||confirm('还有未保存的修改，是否关闭？'));}
 close.onclick=()=>{if(!canLeave())return;stop=true;d.close();};d.addEventListener('cancel',e=>{if(!canLeave())e.preventDefault();else stop=true;});
 async function review(i){
  if(saving)return;
  try{const state=await api(base(i)+'/analysis');if(!d.isConnected||!d.open||saving)return;
   current=i;currentState=state;currentDraft=state.draft?.id?state.draft:null;
   const edited=edits.get(i);
   text.input.value=edited&&currentDraft&&edited.id===currentDraft.id?edited.text:(currentDraft?.text||state.text);dirty=edited?.id===currentDraft?.id&&!!edited;editor.hidden=false;
   image.src='/api'+base(i)+'/image?v='+Date.now();image.hidden=!state.has_image;
   uncertainty.textContent=currentDraft?.uncertain?.length?'待核对：'+currentDraft.uncertain.join('；'):'';
   save.disabled=!currentDraft;repaint();editor.scrollIntoView({block:'start'});
  }catch(e){message.textContent=e.message;}
 }
 const save=toolButton('确认本页并保存',async()=>{
  if(!currentDraft||saving)return;if(running){message.textContent='请先暂停识别，等本页完成后再保存校对。';return;}saving=true;save.disabled=true;text.input.disabled=true;
  try{const latest=await api(base(current)+'/analysis');await api(base(current)+'/analysis',{method:'PUT',body:JSON.stringify({revision:latest.revision,draft_id:currentDraft.id,text:text.input.value})});
   edits.delete(current);dirty=false;currentDraft=null;if(activeMaterial?.id===mid){activeMaterial.units[current].text=text.input.value.trim();showUnit();}
   message.textContent='本页已保存。大纲生成将使用校对后的文字；旧失败批次可更新未完成范围。';
  }catch(e){message.textContent=e.message;save.disabled=false;}finally{saving=false;text.input.disabled=false;}
 });editor.append(columns,save);
 const run=toolButton('开始／继续识别所选页',async()=>{
  if(running||saving||!agree.checked)return;
  if(Number(start.input.value)>Number(end.input.value)){message.textContent='结束页不能早于起始页';return;}
  running=true;stop=false;bulk.disabled=true;run.disabled=true;pause.disabled=false;start.input.disabled=end.input.disabled=true;
  rows.replaceChildren();
  try{for(let i=Number(start.input.value);i<=Number(end.input.value);i++){
   if(stop||!d.open)break;
   const line=toolNode('div');line.className='actions';const label=toolNode('span',material.units[i].location+'：处理中');line.append(label);rows.append(line);
   try{let state=await api(base(i)+'/analysis');
    if(!state.has_image){if(!state.can_render_pdf)throw Error('请先通过原页对照功能添加该页图片');await api(base(i)+'/render',{method:'POST',body:JSON.stringify({revision:state.revision})});state=await api(base(i)+'/analysis');}
    if(state.busy)throw Error('本页正在识别，请稍后继续');
    if(state.reviewed_math){label.textContent=material.units[i].location+'：已校对保存';}
    else {if(!state.draft?.id||state.draft.mode!=='math')await api(base(i)+'/analyze',{method:'POST',body:JSON.stringify({revision:state.revision,mode:'math'})});label.textContent=material.units[i].location+'：草稿已保存，待校对';}
    line.append(toolButton('校对本页',()=>review(i)));
   }catch(e){label.textContent=material.units[i].location+'：'+e.message;message.textContent='已完成页面的草稿保留。再次继续会跳过已有数学草稿和已校对页。';break;}
  }}finally{running=false;bulk.disabled=false;run.disabled=!agree.checked;pause.disabled=true;start.input.disabled=end.input.disabled=false;}
 });
 const pause=toolButton('本页完成后暂停',()=>{stop=true;});pause.disabled=true;run.disabled=true;agree.onchange=()=>{run.disabled=running||!agree.checked;};
 const existing=toolButton('查看所选起始页草稿',()=>review(Number(start.input.value)));
 const includeLabel=toolNode('label'),include=toolNode('input');include.type='checkbox';
 includeLabel.append(include,' 同时保存有待核对内容的页面');
 const bulk=toolButton('保存所选范围全部识别结果',async()=>{
  if(running||saving){message.textContent='请等待当前识别或保存完成。';return;}
  const first=Number(start.input.value),last=Number(end.input.value);
  if(first>last){message.textContent='结束页不能早于起始页';return;}
  saving=true;bulk.disabled=run.disabled=save.disabled=true;text.input.disabled=true;
  start.input.disabled=end.input.disabled=include.disabled=true;
  const items=[],failures=[],skipped=[];let uncertainCount=0,already=0;
  rows.replaceChildren();message.textContent='正在汇总待保存页面…';
  const show=(i,label)=>{const line=toolNode('div');line.className='actions';line.append(toolNode('span',material.units[i].location+'：'+label),toolButton('查看本页',()=>review(i)));rows.append(line);};
  try{
   for(let i=first;i<=last;i++){
    try{
     const state=await api(base(i)+'/analysis'),draft=state.draft;
     if(state.busy)throw Error('正在识别，请稍后重试');
     if(state.reviewed_math&&!draft?.id){already++;continue;}
     if(!draft?.id||draft.mode!=='math'){skipped.push(i);show(i,'暂无数学识别草稿，已跳过');continue;}
     const edit=edits.get(i);
     if(edit&&edit.id!==draft.id)throw Error('草稿已更新，保留的手动修改需要重新核对');
     const value=edit?edit.text:draft.text;
     const uncertain=!!draft.uncertain?.length||/待核对|待确认/.test(value);
     if(uncertain){uncertainCount++;if(!include.checked){skipped.push(i);show(i,'有待核对内容，已跳过');continue;}}
     items.push({index:i,base:base(i),draft_id:draft.id,text:value});
    }catch(e){failures.push(i);show(i,e.message);}
   }
   if(!items.length){message.textContent=`没有可批量保存的页面：已保存 ${already} 页，跳过 ${skipped.length} 页，读取失败 ${failures.length} 页。`;return;}
   if(!confirm(`所选范围有 ${items.length} 页可保存；${uncertainCount} 页有待核对内容${include.checked?'（将一并保存）':'（已跳过）'}。保存后将用于复习与出题，是否继续？`)){message.textContent='未保存，识别草稿和手动修改均保留。';return;}
   let saved=0;
   const result=await saveMathDrafts(items,api,r=>{
    if(r.ok){saved++;edits.delete(r.index);material.units[r.index].text=r.text.trim();if(current===r.index){dirty=false;currentDraft=null;}show(r.index,'已保存');}
    else show(r.index,'保存失败：'+r.error);
    message.textContent=`正在保存：已成功 ${saved} / ${items.length} 页`;
   });
   if(activeMaterial?.id===mid)showUnit();
   const failed=result.filter(r=>!r.ok).length+failures.length;
   message.textContent=`保存完成：成功 ${saved} 页，原已保存 ${already} 页，跳过 ${skipped.length} 页，失败 ${failed} 页。`+(failed?'再次点击批量保存即可重试失败页面。':'可返回复习大纲，更新未完成批次后继续生成。');
  }catch(e){message.textContent=e.message;}
  finally{saving=false;bulk.disabled=false;run.disabled=!agree.checked;save.disabled=!currentDraft;text.input.disabled=false;start.input.disabled=end.input.disabled=include.disabled=false;}
 });
 const actions=toolNode('div');actions.className='actions';actions.append(run,pause,existing);
 const saveActions=toolNode('div');saveActions.className='actions';saveActions.append(bulk,includeLabel);
 d.append(toolNode('p','PDF自动转换原页图片。先识别草稿，可逐页校对或批量保存；需要支持图片输入的模型。'),start.wrap,end.wrap,consent,actions,saveActions,rows,editor);
}
const mathMaterialButton=toolButton('数学资料识别与校对',openMathMaterials);
pageVisionButton.after(mathMaterialButton);
