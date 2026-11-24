function renderStudyMath(node){
 if(typeof renderMathInElement!=='function'||!node)return;
 renderMathInElement(node,{delimiters:[{left:'$$',right:'$$',display:true},{left:'\\[',right:'\\]',display:true},{left:'\\(',right:'\\)',display:false},{left:'$',right:'$',display:false}],
  throwOnError:false,trust:false,strict:'ignore',maxExpand:1000,maxSize:20,
  ignoredTags:['script','noscript','style','textarea','code','option','input'],ignoredClasses:['katex','math-raw']});
}
let mathRenderTimer;
const mathObserver=new MutationObserver(records=>{
 if(records.every(r=>r.target.parentElement?.closest('.katex')))return;
 clearTimeout(mathRenderTimer);mathRenderTimer=setTimeout(()=>{
  mathObserver.disconnect();try{renderStudyMath(document.body);}finally{observeStudyMath();}
 },80);
});
function observeStudyMath(){mathObserver.observe(document.body,{childList:true,subtree:true,characterData:true});}
renderStudyMath(document.body);observeStudyMath();
