// Restore the session after all deferred UI modules have installed their handlers.
async function restoreSession(){
 try{
  const user=await api('/auth/me');
  await showWorkspace(user);
 }catch(error){
  showAuth();
  if(!error.message.includes('登录'))$('auth-message').textContent=error.message;
 }finally{$('loading').hidden=true;}
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',restoreSession,{once:true});
else restoreSession();
