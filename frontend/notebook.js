// Shared by current, archived and legacy outlines. All model text stays textContent.
const notebookPositions = new Map();
function notebookNode(tag, text, className) {
  const node=document.createElement(tag);node.textContent=text;
  if(className)node.className=className;return node;
}
function renderKnowledgeCards(record,target) {
  const entries=record.result.sections.flatMap((section,chapterIndex)=>section.points.map(point=>({title:section.title,point:{...point},originalText:point.text,chapterIndex})));
  if(!entries.length)return;
  const sources=new Map(record.sources.map(source=>[source.source_id,source]));
  const key=record.id || target.id;
  let index=Math.min(notebookPositions.get(key)||0,entries.length-1), flipped=false, listMode=false;
  const book=document.createElement('section');book.className='knowledge-book';book.setAttribute('aria-label','知识点翻页卡片');
  const header=document.createElement('div');header.className='notebook-toolbar';
  header.append(notebookNode('span','知识手札','eyebrow'));
  const mode=notebookNode('button','展开全部');mode.type='button';mode.setAttribute('aria-pressed','false');header.append(mode);
  const label=notebookNode('label','跳转知识点');label.className='notebook-index';
  const select=document.createElement('select');
  entries.forEach((entry,i)=>{const option=notebookNode('option',`${i+1}. ${entry.title} · ${entry.point.text.slice(0,36)}`);option.value=String(i);select.append(option);});label.append(select);
  const pages=document.createElement('div');pages.className='notebook-pages';
  const navigation=document.createElement('div');navigation.className='notebook-navigation';
  const previous=notebookNode('button','← 上一页'),next=notebookNode('button','下一页 →'),flip=notebookNode('button','翻看背面 · 原文出处');
  [previous,next,flip].forEach(button=>button.type='button');
  const counter=notebookNode('span','');counter.setAttribute('aria-live','polite');
  navigation.append(previous,counter,next,flip);
  function citations(entry,card) {
    const refs=[...new Set(entry.point.source_ids)].map(id=>sources.get(id)).filter(Boolean);
    if(!refs.length)card.append(notebookNode('p','该知识点暂无可显示的原文引用。','muted'));
    refs.forEach(source=>{
      const detail=document.createElement('details');detail.open=true;
      detail.append(notebookNode('summary',`${source.source_id} · ${source.name} · ${source.location}`),notebookNode('pre',source.text));card.append(detail);
    });
  }
  function cardFor(entry,i,back,all) {
    const card=document.createElement('article');card.className='knowledge-page'+(back?' is-back':'');card.setAttribute('data-tone',String(entry.chapterIndex%4));
    card.append(notebookNode('div',`NOTE ${String(i+1).padStart(2,'0')} / ${String(entries.length).padStart(2,'0')}`,'page-number'),notebookNode('h3',entry.title));
    if(back) {card.append(notebookNode('p','循着批注，回到原文。','hand-note'));citations(entry,card);}
    else {card.append(notebookNode('p',entry.point.text,'knowledge-text'));if(all)citations(entry,card);else card.append(notebookNode('span','看懂一点，心里稳一点。','hand-note'));}
    if(typeof renderKnowledgeControls === "function" && record.id) renderKnowledgeControls(record,entry,i,card,draw);
    return card;
  }
  function draw() {
    notebookPositions.set(key,index);pages.replaceChildren();select.value=String(index);
    book.classList.toggle('all-pages',listMode);navigation.hidden=label.hidden=listMode;
    if(listMode)entries.forEach((entry,i)=>pages.append(cardFor(entry,i,false,true)));
    else pages.append(cardFor(entries[index],index,flipped,false));
    previous.disabled=index===0;next.disabled=index===entries.length-1;
    counter.textContent=`${index+1} / ${entries.length} · ${flipped?'原文出处':'知识点'}`;
    flip.textContent=flipped?'翻回正面 · 知识点':'翻看背面 · 原文出处';
    flip.setAttribute('aria-pressed',String(flipped));
  }
  function move(delta) {index=Math.max(0,Math.min(entries.length-1,index+delta));flipped=false;draw();}
  previous.onclick=()=>move(-1);next.onclick=()=>move(1);flip.onclick=()=>{flipped=!flipped;draw();};
  select.onchange=()=>{index=Number(select.value);flipped=false;draw();};
  mode.onclick=()=>{listMode=!listMode;mode.textContent=listMode?'返回翻页':'展开全部';mode.setAttribute('aria-pressed',String(listMode));draw();};
  book.append(header,label,pages,navigation);target.append(book);draw();
  if(typeof loadKnowledgeEdits === "function" && record.id) loadKnowledgeEdits(record,book,entries,draw);
}
