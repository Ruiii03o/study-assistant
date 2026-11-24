/* Image analysis is always a draft until explicitly reviewed and saved. */
async function openPageVision() {
  if (!activeMaterial) return;
  const mid=activeMaterial.id, index=Number($('unit-select').value);
  const location=activeMaterial.units[index]?.location || '当前页';
  const base=`/materials/${mid}/pages/${index}`;
  const {d,message}=toolDialog(`原页对照与图文校对 · ${location}`);
  let state, draft=null, busy=false;
  function notify(text,error=false){message.textContent=text;message.style.color=error?'':'var(--muted, #666)';}
  function recover(error){notify(error.message,true);refresh.hidden=false;}
  const note=toolNode('p','此处只处理当前页。请添加这张幻灯片的完整原页图片；图示识别需配置支持图片输入的模型。');
  const img=toolNode('img'); img.alt=`${location}原页图片`; img.className='source-page-image'; img.hidden=true;
  const raw=toolNode('details'), rawTitle=toolNode('summary','未经整理的提取文字'), rawText=toolNode('pre'); raw.append(rawTitle,rawText);
  const original=toolNode('details'), originalTitle=toolNode('summary','当前用于复习和出题的文字'), originalText=toolNode('pre'); original.append(originalTitle,originalText);
  const picker=toolField('添加或更换当前页图片（PNG/JPEG，最多4MB）'); picker.input.type='file';picker.input.accept='image/png,image/jpeg';
  const consent=toolNode('label'), agree=toolNode('input'); agree.type='checkbox';consent.append(agree,' 我同意将本页图片和文字发送给已配置的AI服务进行识别，可能产生费用。');
  const edit=toolField('识别草稿（请对照原图校对后再保存）','textarea'); edit.input.rows=14;edit.wrap.hidden=true;
  const mode=toolField('识别模式','select');mode.input.add(new Option('普通图文','general'));mode.input.add(new Option('数学公式与正文','math'));
  const preview=toolNode('div');preview.className='math-preview';preview.hidden=true;
  edit.input.oninput=()=>{preview.textContent=edit.input.value;renderStudyMath(preview);};
  const renderPDF=toolButton('从PDF生成本页图片',async()=>{if(busy||!state)return;setBusy(true);try{await api(base+'/render',{method:'POST',body:JSON.stringify({revision:state.revision})});await load();}catch(e){recover(e);}finally{setBusy(false);}});
  const uncertain=toolNode('div');uncertain.setAttribute('role','status');
  const save=toolButton('确认校对并保存',async()=>{
    if(busy || !draft || !state)return;
    setBusy(true);
    try {
      const result=await api(base+'/analysis',{method:'PUT',body:JSON.stringify({revision:state.revision,draft_id:draft.id,text:edit.input.value})});
      // Update only this preview: never rebuild unsaved chapter-range controls.
      if(activeMaterial?.id===mid) {activeMaterial.units[index].text=edit.input.value.trim();showUnit();}
      notify('已保存'); draft=null;edit.wrap.hidden=true;uncertain.replaceChildren();await load();
    } catch(e) {recover(e);} finally {setBusy(false);}
  });
  const analyze=toolButton('识别本页图文',async()=>{
    if(busy || !agree.checked || !state?.has_image)return;
    setBusy(true);message.textContent='正在识别本页，请稍候。结果不会自动覆盖资料。';
    try {refresh.hidden=true;showDraft(await api(base+'/analyze',{method:'POST',body:JSON.stringify({revision:state.revision,mode:mode.input.value})}));message.textContent='识别完成，请核对文字与图示解读；下列待核对项不会自动加入资料。';}
    catch(e) {recover(e);} finally {setBusy(false);}
  });
  const refresh=toolButton('重新获取识别结果',async()=>{if(busy)return;setBusy(true);try{await load();if(!state.busy)notify(draft?'识别结果已更新':'状态已更新');}catch(e){recover(e);}finally{setBusy(false);}});
  refresh.hidden=true;
  function setBusy(value){busy=value;picker.input.disabled=value;analyze.disabled=value || !agree.checked || !state?.has_image || state?.busy;save.disabled=value || !draft;refresh.disabled=value;}
  function showDraft(value){
    draft=value?.id?value:null;edit.wrap.hidden=!draft;preview.hidden=!draft;uncertain.replaceChildren();
    if(draft){edit.input.value=draft.text+(draft.diagram?'\n\n【AI图示解读，保存前请核对】\n'+draft.diagram:'');
      if(draft.uncertain?.length){uncertain.append(toolNode('strong','需要对照原图核对（未加入草稿正文）'));const list=toolNode('ul');draft.uncertain.forEach(t=>list.append(toolNode('li',t)));uncertain.append(list);}}
    preview.textContent=draft?edit.input.value:'';if(typeof renderStudyMath==='function')renderStudyMath(preview);
    setBusy(busy);
  }
  async function load(){
    state=await api(base+'/analysis');if(!d.isConnected)return;
    renderPDF.hidden=!state.can_render_pdf;
    rawText.textContent=state.raw_text;originalText.textContent=state.text;
    img.hidden=!state.has_image;if(state.has_image)img.src='/api'+base+'/image?v='+Date.now();
    showDraft(state.draft);refresh.hidden=!state.busy;if(state.busy)notify('本页正在识别，可稍后获取结果。');
  }
  agree.onchange=()=>setBusy(busy);
  picker.input.onchange=async()=>{
    const file=picker.input.files[0];if(!file || !state)return;
    if(file.size>4*1024*1024 || !['image/png','image/jpeg'].includes(file.type)){message.textContent='请选择不超过4MB的PNG或JPEG图片。';return;}
    setBusy(true);
    try{
      const data=await new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result);r.onerror=()=>reject(new Error('图片读取失败'));r.readAsDataURL(file);});
      const result=await api(base+'/image',{method:'PUT',body:JSON.stringify({data,revision:state.revision})});
      message.textContent=result.message;await load();
    }catch(e){recover(e);}finally{setBusy(false);}
  };
  const actions=toolNode('div');actions.className='page-vision-actions';actions.append(renderPDF,analyze,refresh,save);
  d.insertBefore(note,message);d.insertBefore(raw,message);d.insertBefore(original,message);d.insertBefore(img,message);d.insertBefore(picker.wrap,message);d.insertBefore(mode.wrap,message);d.insertBefore(consent,message);d.insertBefore(actions,message);d.insertBefore(edit.wrap,message);d.insertBefore(preview,message);d.insertBefore(uncertain,message);
  setBusy(true);try{await load();}catch(e){recover(e);}finally{setBusy(false);}
}
const pageVisionButton=toolButton('原页对照与图文校对',openPageVision);
$('unit-text').insertAdjacentElement('afterend',pageVisionButton);
