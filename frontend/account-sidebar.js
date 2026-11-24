// Move existing controls so their permission checks and click handlers are retained.
const personalAccount=document.querySelector('#workspace > aside .account');
const accountIdentity=practiceText('div','','account-identity');
const accountRole=practiceText('span','管理员','account-role');accountRole.hidden=true;
accountIdentity.append($('username'),accountRole);
const accountActions=practiceText('div','','account-actions');
accountButton.textContent='账户设置';accountActions.append(accountButton,$('logout'));
const adminSection=practiceText('section','','account-admin-section');adminSection.hidden=true;
adminSection.setAttribute('aria-label','管理专区');
adminSection.append(practiceText('p','管理专区','account-section-label'),adminUsersButton);
personalAccount.replaceChildren(adminSection,accountIdentity,accountActions);
function syncAccountRole(user){
  const admin=user?.role==='admin';adminSection.hidden=!admin;accountRole.hidden=!admin;
}
const accountShowWorkspace=showWorkspace;
showWorkspace=async function(user){syncAccountRole(user);return accountShowWorkspace(user);};
const accountShowAuth=showAuth;
showAuth=function(...args){syncAccountRole(null);return accountShowAuth(...args);};
// The initial session request may have started before this deferred script loaded.
new MutationObserver(()=>{const admin=!adminUsersButton.hidden;adminSection.hidden=!admin;accountRole.hidden=!admin;})
  .observe(adminUsersButton,{attributes:true,attributeFilter:['hidden']});
adminSection.hidden=adminUsersButton.hidden;accountRole.hidden=adminUsersButton.hidden;
