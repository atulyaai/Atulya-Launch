(function(){
'use strict';
const $=s=>document.querySelector(s);
const $$=s=>document.querySelectorAll(s);
const CE=(t,c,h)=>{const e=document.createElement(t);if(c)e.className=c;if(h)e.innerHTML=h;return e;};

let token=localStorage.getItem('token')||sessionStorage.getItem('token');
let currentUser=localStorage.getItem('user')||'admin';
let currentSection='dashboard';
let monitorInterval=null;
let wsConn=null;

// Auth
function getToken(){return localStorage.getItem('token')||sessionStorage.getItem('token');}
function setToken(t,rem){if(rem)localStorage.setItem('token',t);else sessionStorage.setItem('token',t);token=t;}
function clearToken(){localStorage.removeItem('token');sessionStorage.removeItem('token');localStorage.removeItem('user');token=null;}

// API
async function api(path,opts={}){
  const t=getToken();
  const h={'Content-Type':'application/json',...(opts.headers||{})};
  if(t)h['Authorization']='Bearer '+t;
  try{
    const r=await fetch('/api'+path,{...opts,headers:h});
    if(r.status===401){clearToken();location.reload();return null;}
    const d=await r.json();
    if(!r.ok)throw new Error(d.error||'Request failed');
    return d;
  }catch(e){throw e;}
}

// Toast
function toast(msg,type='info'){
  const c=$('#toastContainer');
  const icons={success:'&#10004;',danger:'&#10008;',warning:'&#9888;',info:'&#8505;'};
  const t=CE('div','toast toast-'+type);
  t.innerHTML=`<span class="toast-icon">${icons[type]||icons.info}</span><span class="toast-msg">${msg}</span><button class="toast-close">&times;</button>`;
  c.appendChild(t);
  t.querySelector('.toast-close').onclick=()=>removeToast(t);
  setTimeout(()=>removeToast(t),5000);
}
function removeToast(t){t.classList.add('removing');setTimeout(()=>t.remove(),300);}

// Modal
function showModal(title,bodyHtml,footerHtml=''){
  $('#modalTitle').textContent=title;
  $('#modalBody').innerHTML=bodyHtml;
  $('#modalFooter').innerHTML=footerHtml;
  $('#modalOverlay').classList.add('show');
}
function hideModal(){$('#modalOverlay').classList.remove('show');}

// Confirm dialog
function confirmAction(msg,cb){
  showModal('Confirm',`<p>${msg}</p>`,
    `<button class="btn btn-ghost" id="confirmCancel">Cancel</button>
     <button class="btn btn-danger" id="confirmOk">Confirm</button>`);
  $('#confirmCancel').onclick=hideModal;
  $('#confirmOk').onclick=()=>{hideModal();cb();};
}

// Router
function navigate(section){
  currentSection=section;
  $$('.nav-item[data-section]').forEach(n=>n.classList.toggle('active',n.dataset.section===section));
  const names={dashboard:'Dashboard',websites:'Websites',dns:'Domains',email:'Email',databases:'Databases',
    files:'File Manager',ssl:'SSL Certificates',backups:'Backups',firewall:'Firewall',cron:'Cron Jobs',
    apps:'App Installer',monitor:'System Monitor',settings:'Settings'};
  $('#breadcrumb').innerHTML=`<span>Home</span><span class="sep">/</span><span class="current">${names[section]||section}</span>`;
  if(monitorInterval){clearInterval(monitorInterval);monitorInterval=null;}
  if(wsConn){wsConn.close();wsConn=null;}
  const loaders={dashboard:loadDashboard,websites:loadWebsites,dns:loadDNS,email:loadEmail,
    databases:loadDatabases,files:loadFileManager,ssl:loadSSL,backups:loadBackups,
    firewall:loadFirewall,cron:loadCronJobs,apps:loadAppInstaller,monitor:loadSystemMonitor,settings:loadSettings};
  if(loaders[section])loaders[section]();
}

// Dashboard
async function loadDashboard(){
  const c=$('#content');
  c.innerHTML=`
    <div class="stats-grid" id="dashStats"></div>
    <div class="quick-actions" id="quickActions">
      <button class="quick-action" data-nav="websites"><span class="icon">&#127760;</span> Add Site</button>
      <button class="quick-action" data-nav="backups"><span class="icon">&#128190;</span> Create Backup</button>
      <button class="quick-action" data-nav="monitor"><span class="icon">&#128200;</span> View Processes</button>
      <button class="quick-action" data-nav="files"><span class="icon">&#128193;</span> File Manager</button>
    </div>
    <div class="gauges-grid mb-24" id="gauges"></div>
    <div class="grid-2">
      <div class="card">
        <div class="card-header"><span class="card-title">Recent Activity</span></div>
        <div class="activity-list" id="activityList"></div>
      </div>
      <div class="card">
        <div class="card-header"><span class="card-title">Top Processes</span></div>
        <div class="table-wrap"><table id="procTable"><thead><tr><th>PID</th><th>Name</th><th>CPU%</th><th>MEM%</th></tr></thead><tbody></tbody></table></div>
      </div>
    </div>`;
  $$('.quick-action[data-nav]').forEach(b=>b.onclick=()=>navigate(b.dataset.nav));
  try{
    const d=await api('/dashboard/stats');
    if(d){
      $('#dashStats').innerHTML=`
        <div class="stat-card"><div class="stat-info"><h3>Websites</h3><div class="stat-value">${d.sites||0}</div></div><div class="stat-icon blue">&#127760;</div></div>
        <div class="stat-card"><div class="stat-info"><h3>Databases</h3><div class="stat-value">${d.databases||0}</div></div><div class="stat-icon green">&#128451;</div></div>
        <div class="stat-card"><div class="stat-info"><h3>Email Accounts</h3><div class="stat-value">${d.emails||0}</div></div><div class="stat-icon orange">&#9993;</div></div>
        <div class="stat-card"><div class="stat-info"><h3>SSL Certs</h3><div class="stat-value">${d.ssl||0}</div></div><div class="stat-icon purple">&#128274;</div></div>
        <div class="stat-card"><div class="stat-info"><h3>Disk Usage</h3><div class="stat-value">${d.diskUsed||'--'}</div><div class="stat-change">${d.diskTotal||''} total</div></div><div class="stat-icon red">&#128190;</div></div>
        <div class="stat-card"><div class="stat-info"><h3>Uptime</h3><div class="stat-value">${d.uptime||'--'}</div></div><div class="stat-icon blue">&#9200;</div></div>`;
      $('#serverUptime').textContent='Uptime: '+d.uptime;
    }
  }catch(e){}

  try{
    const d=await api('/system/stats');
    if(d)renderGauges(d);
  }catch(e){renderGauges({cpu:0,ram:0,disk:0});}

  const al=$('#activityList');
  const activities=[
    {icon:'&#128274;',color:'var(--info)',text:'SSL renewed for example.com',time:'2 min ago'},
    {icon:'&#128190;',color:'var(--success)',text:'Backup completed successfully',time:'15 min ago'},
    {icon:'&#127760;',color:'var(--accent)',text:'New site "myapp" created',time:'1 hour ago'},
    {icon:'&#9888;',color:'var(--warning)',text:'High memory usage detected',time:'3 hours ago'},
    {icon:'&#128100;',color:'var(--text-muted)',text:'User logged in from 192.168.1.1',time:'5 hours ago'}
  ];
  al.innerHTML=activities.map(a=>`<div class="activity-item"><div class="activity-icon" style="background:${a.color}22;color:${a.color}">${a.icon}</div><div class="activity-content"><div class="activity-text">${a.text}</div><div class="activity-time">${a.time}</div></div></div>`).join('');

  loadProcesses();
  monitorInterval=setInterval(loadProcesses,5000);
}

function renderGauges(d){
  const g=$('#gauges');
  if(!g)return;
  const items=[
    {label:'CPU',value:d.cpu||0,color:'var(--accent)'},
    {label:'RAM',value:d.ram||0,color:'var(--success)'},
    {label:'Disk',value:d.disk||0,color:'var(--warning)'}
  ];
  g.innerHTML=items.map(i=>{
    const circ=2*Math.PI*42;
    const off=circ-(i.value/100)*circ;
    return `<div class="gauge-card"><div class="gauge"><svg width="100" height="100"><circle class="bg" cx="50" cy="50" r="42" stroke-width="8"/><circle class="fg" cx="50" cy="50" r="42" stroke-width="8" stroke="${i.color}" stroke-dasharray="${circ}" stroke-dashoffset="${off}"/></svg><div class="gauge-label" style="color:${i.color}">${Math.round(i.value)}%</div></div><div class="gauge-title">${i.label}</div></div>`;
  }).join('');
}

async function loadProcesses(){
  try{
    const d=await api('/system/processes');
    if(d&&d.processes){
      const tb=$('#procTable tbody');
      if(tb)tb.innerHTML=d.processes.slice(0,5).map(p=>`<tr><td>${p.pid}</td><td class="truncate" style="max-width:180px">${p.name}</td><td>${p.cpu.toFixed(1)}</td><td>${p.mem.toFixed(1)}</td></tr>`).join('');
    }
  }catch(e){}
}

// Websites
async function loadWebsites(){
  const c=$('#content');
  c.innerHTML=`<div class="section-header"><h1 class="section-title">Websites</h1><button class="btn btn-primary" id="addSiteBtn">+ Add Website</button></div><div class="card"><div class="table-wrap"><table><thead><tr><th>Domain</th><th>Root</th><th>Status</th><th>Actions</th></tr></thead><tbody id="siteList"></tbody></table></div></div>`;
  $('#addSiteBtn').onclick=()=>showAddSite();
  try{
    const d=await api('/websites');
    const tb=$('#siteList');
    if(d&&d.length){
      tb.innerHTML=d.map(s=>`<tr><td>${s.domain}</td><td class="font-mono text-sm">${s.root}</td><td><span class="badge badge-success">Active</span></td><td><button class="btn btn-sm btn-ghost" onclick="siteManage('${s.domain}')">Manage</button> <button class="btn btn-sm btn-danger" onclick="siteDelete('${s.domain}')">Delete</button></td></tr>`).join('');
    }else{tb.innerHTML='<tr><td colspan="4"><div class="empty-state"><div class="icon">&#127760;</div><h3>No websites yet</h3><p>Create your first website to get started</p></div></td></tr>';}
  }catch(e){$('#siteList').innerHTML='<tr><td colspan="4" class="text-muted text-center">Failed to load websites</td></tr>';}
}

function showAddSite(){
  showModal('Add Website',
    `<div class="form-group"><label>Domain Name</label><input class="form-control" id="newDomain" placeholder="example.com"></div>
     <div class="form-group"><label>Document Root</label><input class="form-control" id="newRoot" placeholder="/home/user/public_html"></div>
     <div class="form-group"><label>PHP Version</label><select class="form-control" id="newPhp"><option>8.2</option><option>8.1</option><option>8.0</option><option>7.4</option></select></div>`,
    `<button class="btn btn-ghost" onclick="hideModal()">Cancel</button><button class="btn btn-primary" id="createSiteBtn">Create</button>`);
  $('#createSiteBtn').onclick=async()=>{
    const domain=$('#newDomain').value.trim();
    const root=$('#newRoot').value.trim();
    if(!domain){toast('Enter a domain','warning');return;}
    try{await api('/websites',{method:'POST',body:JSON.stringify({domain,root,php:$('#newPhp').value})});hideModal();toast('Website created','success');loadWebsites();}catch(e){toast(e.message,'danger');}
  };
}
window.siteManage=function(d){toast('Managing '+d,'info');};
window.siteDelete=function(d){confirmAction('Delete website '+d+'?',async()=>{try{await api('/websites/'+d,{method:'DELETE'});toast('Deleted','success');loadWebsites();}catch(e){toast(e.message,'danger');}});};
window.hideModal=hideModal;

// DNS
async function loadDNS(){
  const c=$('#content');
  c.innerHTML=`<div class="section-header"><h1 class="section-title">DNS Management</h1><button class="btn btn-primary" id="addZoneBtn">+ Add Zone</button></div><div class="card"><div class="table-wrap"><table><thead><tr><th>Zone</th><th>Records</th><th>Status</th><th>Actions</th></tr></thead><tbody id="dnsList"></tbody></table></div></div>`;
  $('#addZoneBtn').onclick=()=>showAddZone();
  try{
    const d=await api('/dns/zones');
    const tb=$('#dnsList');
    if(d&&d.length){
      tb.innerHTML=d.map(z=>`<tr><td>${z.name}</td><td>${z.records||0} records</td><td><span class="badge badge-success">Active</span></td><td><button class="btn btn-sm btn-ghost" onclick="dnsManage('${z.name}')">Manage</button> <button class="btn btn-sm btn-danger" onclick="dnsDelete('${z.name}')">Delete</button></td></tr>`).join('');
    }else{tb.innerHTML='<tr><td colspan="4"><div class="empty-state"><div class="icon">&#9879;</div><h3>No DNS zones</h3><p>Add a domain zone to manage DNS records</p></div></td></tr>';}
  }catch(e){$('#dnsList').innerHTML='<tr><td colspan="4" class="text-muted text-center">Failed to load DNS zones</td></tr>';}
}

function showAddZone(){
  showModal('Add DNS Zone',
    `<div class="form-group"><label>Domain Name</label><input class="form-control" id="newZone" placeholder="example.com"></div>
     <div class="form-group"><label>Primary Nameserver</label><input class="form-control" id="newNs" placeholder="ns1.example.com"></div>`,
    `<button class="btn btn-ghost" onclick="hideModal()">Cancel</button><button class="btn btn-primary" id="createZoneBtn">Create</button>`);
  $('#createZoneBtn').onclick=async()=>{
    const name=$('#newZone').value.trim();
    if(!name){toast('Enter domain','warning');return;}
    try{await api('/dns/zones',{method:'POST',body:JSON.stringify({name,ns:$('#newNs').value.trim()})});hideModal();toast('Zone created','success');loadDNS();}catch(e){toast(e.message,'danger');}
  };
}
window.dnsManage=function(z){toast('Managing zone '+z,'info');};
window.dnsDelete=function(z){confirmAction('Delete zone '+z+'?',async()=>{try{await api('/dns/zones/'+z,{method:'DELETE'});toast('Deleted','success');loadDNS();}catch(e){toast(e.message,'danger');}});};

// Email
async function loadEmail(){
  const c=$('#content');
  c.innerHTML=`<div class="section-header"><h1 class="section-title">Email Accounts</h1><button class="btn btn-primary" id="addEmailBtn">+ Add Account</button></div><div class="card"><div class="table-wrap"><table><thead><tr><th>Email</th><th>Quota</th><th>Status</th><th>Actions</th></tr></thead><tbody id="emailList"></tbody></table></div></div>`;
  $('#addEmailBtn').onclick=()=>showAddEmail();
  try{
    const d=await api('/email/accounts');
    const tb=$('#emailList');
    if(d&&d.length){
      tb.innerHTML=d.map(e=>`<tr><td>${e.email}</td><td>${e.quota||'1 GB'}</td><td><span class="badge badge-success">Active</span></td><td><button class="btn btn-sm btn-ghost">Manage</button> <button class="btn btn-sm btn-danger" onclick="emailDelete('${e.email}')">Delete</button></td></tr>`).join('');
    }else{tb.innerHTML='<tr><td colspan="4"><div class="empty-state"><div class="icon">&#9993;</div><h3>No email accounts</h3><p>Create your first email account</p></div></td></tr>';}
  }catch(e){$('#emailList').innerHTML='<tr><td colspan="4" class="text-muted text-center">Failed to load email accounts</td></tr>';}
}

function showAddEmail(){
  showModal('Add Email Account',
    `<div class="form-group"><label>Email Address</label><input class="form-control" id="newEmail" placeholder="user@domain.com"></div>
     <div class="form-group"><label>Password</label><input type="password" class="form-control" id="newEmailPass" placeholder="Strong password"></div>
     <div class="form-group"><label>Quota (MB)</label><input type="number" class="form-control" id="newEmailQuota" value="1024"></div>`,
    `<button class="btn btn-ghost" onclick="hideModal()">Cancel</button><button class="btn btn-primary" id="createEmailBtn">Create</button>`);
  $('#createEmailBtn').onclick=async()=>{
    const email=$('#newEmail').value.trim();
    const pass=$('#newEmailPass').value;
    if(!email||!pass){toast('Fill all fields','warning');return;}
    try{await api('/email/accounts',{method:'POST',body:JSON.stringify({email,password:pass,quota:$('#newEmailQuota').value})});hideModal();toast('Email created','success');loadEmail();}catch(e){toast(e.message,'danger');}
  };
}
window.emailDelete=function(e){confirmAction('Delete email '+e+'?',async()=>{try{await api('/email/accounts/'+e,{method:'DELETE'});toast('Deleted','success');loadEmail();}catch(e){toast(e.message,'danger');}});};

// Databases
async function loadDatabases(){
  const c=$('#content');
  c.innerHTML=`<div class="section-header"><h1 class="section-title">Databases</h1><button class="btn btn-primary" id="addDbBtn">+ Create Database</button></div><div class="card"><div class="table-wrap"><table><thead><tr><th>Name</th><th>Tables</th><th>Size</th><th>Actions</th></tr></thead><tbody id="dbList"></tbody></table></div></div>`;
  $('#addDbBtn').onclick=()=>showAddDb();
  try{
    const d=await api('/databases');
    const tb=$('#dbList');
    if(d&&d.length){
      tb.innerHTML=d.map(db=>`<tr><td>${db.name}</td><td>${db.tables||0}</td><td>${db.size||'--'}</td><td><button class="btn btn-sm btn-ghost" onclick="dbManage('${db.name}')">Manage</button> <button class="btn btn-sm btn-success" onclick="dbBackup('${db.name}')">Backup</button> <button class="btn btn-sm btn-danger" onclick="dbDelete('${db.name}')">Delete</button></td></tr>`).join('');
    }else{tb.innerHTML='<tr><td colspan="4"><div class="empty-state"><div class="icon">&#128451;</div><h3>No databases</h3><p>Create your first database</p></div></td></tr>';}
  }catch(e){$('#dbList').innerHTML='<tr><td colspan="4" class="text-muted text-center">Failed to load databases</td></tr>';}
}

function showAddDb(){
  showModal('Create Database',
    `<div class="form-group"><label>Database Name</label><input class="form-control" id="newDbName" placeholder="my_database"></div>
     <div class="form-group"><label>Database User</label><input class="form-control" id="newDbUser" placeholder="db_user"></div>
     <div class="form-group"><label>Password</label><input type="password" class="form-control" id="newDbPass" placeholder="Strong password"></div>`,
    `<button class="btn btn-ghost" onclick="hideModal()">Cancel</button><button class="btn btn-primary" id="createDbBtn">Create</button>`);
  $('#createDbBtn').onclick=async()=>{
    const name=$('#newDbName').value.trim();
    if(!name){toast('Enter database name','warning');return;}
    try{await api('/databases',{method:'POST',body:JSON.stringify({name,user:$('#newDbUser').value.trim(),password:$('#newDbPass').value})});hideModal();toast('Database created','success');loadDatabases();}catch(e){toast(e.message,'danger');}
  };
}
window.dbManage=function(n){toast('Managing database '+n,'info');};
window.dbBackup=function(n){confirmAction('Backup database '+n+'?',async()=>{try{await api('/databases/'+n+'/backup',{method:'POST'});toast('Backup started','success');}catch(e){toast(e.message,'danger');}});};
window.dbDelete=function(n){confirmAction('Delete database '+n+'?',async()=>{try{await api('/databases/'+n,{method:'DELETE'});toast('Deleted','success');loadDatabases();}catch(e){toast(e.message,'danger');}});};

// File Manager
let fmPath='/';
async function loadFileManager(){
  const c=$('#content');
  c.innerHTML=`
    <div class="section-header"><h1 class="section-title">File Manager</h1></div>
    <div class="fm-toolbar">
      <div class="fm-breadcrumb" id="fmBreadcrumb"></div>
      <div class="fm-views">
        <button class="btn btn-sm btn-ghost" id="fmGridBtn" title="Grid View">&#9638;</button>
        <button class="btn btn-sm btn-ghost" id="fmListBtn" title="List View">&#9776;</button>
      </div>
      <button class="btn btn-sm btn-primary" id="fmUploadBtn">Upload</button>
      <button class="btn btn-sm btn-ghost" id="fmNewFolderBtn">New Folder</button>
      <button class="btn btn-sm btn-ghost" id="fmNewFileBtn">New File</button>
    </div>
    <div id="fmDropZone" class="fm-drop-zone hidden">Drop files here to upload</div>
    <div class="card"><div class="table-wrap"><table id="fmTable"><thead><tr><th>Name</th><th>Size</th><th>Permissions</th><th>Modified</th><th>Actions</th></tr></thead><tbody id="fmFiles"></tbody></table></div></div>
    <input type="file" id="fmFileInput" multiple style="display:none">`;
  fmPath='/';
  renderFmBreadcrumb();
  loadFmFiles();
  $('#fmUploadBtn').onclick=()=>$('#fmFileInput').click();
  $('#fmNewFolderBtn').onclick=()=>showFmNewFolder();
  $('#fmNewFileBtn').onclick=()=>showFmNewFile();
  $('#fmFileInput').onchange=e=>uploadFmFiles(e.target.files);
  const dz=$('#fmDropZone');
  const zone=c;
  zone.ondragover=e=>{e.preventDefault();dz.classList.remove('hidden');};
  zone.ondragleave=e=>{if(!zone.contains(e.relatedTarget))dz.classList.add('hidden');};
  zone.ondrop=e=>{e.preventDefault();dz.classList.add('hidden');uploadFmFiles(e.dataTransfer.files);};
}

function renderFmBreadcrumb(){
  const bc=$('#fmBreadcrumb');
  const parts=fmPath.split('/').filter(Boolean);
  let html=`<span class="fm-path-item" onclick="fmNav('/')">/</span>`;
  let p='';
  parts.forEach((part,i)=>{
    p+='/'+part;
    const pp=p;
    html+=`<span class="fm-path-sep">/</span><span class="fm-path-item" onclick="fmNav('${pp}')">${part}</span>`;
  });
  bc.innerHTML=html;
}

async function loadFmFiles(){
  try{
    const d=await api('/files/list?path='+encodeURIComponent(fmPath));
    const tb=$('#fmFiles');
    if(d&&d.files&&d.files.length){
      tb.innerHTML=d.files.map(f=>{
        const icon=f.isDir?'&#128193;':f.name.endsWith('.js')||f.name.endsWith('.py')?'&#128196;':'&#128196;';
        return `<tr oncontextmenu="fmCtx(event,'${f.name}',${f.isDir})">
          <td><span style="cursor:pointer" onclick="${f.isDir?"fmNav('"+fmPath+f.name+"/')":"fmOpen('"+f.name+"')"}">${icon} ${f.name}</span></td>
          <td>${f.isDir?'--':formatSize(f.size)}</td>
          <td class="font-mono text-sm">${f.perms||'--'}</td>
          <td class="text-sm">${f.modified||'--'}</td>
          <td><button class="btn btn-sm btn-ghost" onclick="fmRename('${f.name}')">Rename</button> <button class="btn btn-sm btn-danger" onclick="fmDelete('${f.name}',${f.isDir})">Delete</button></td></tr>`;
      }).join('');
    }else{tb.innerHTML='<tr><td colspan="5"><div class="empty-state"><div class="icon">&#128193;</div><h3>Empty folder</h3></div></td></tr>';}
  }catch(e){$('#fmFiles').innerHTML='<tr><td colspan="5" class="text-muted text-center">Failed to load files</td></tr>';}
}

function formatSize(b){if(!b)return'--';const u=['B','KB','MB','GB','TB'];let i=0;while(b>=1024&&i<u.length-1){b/=1024;i++;}return b.toFixed(i?1:0)+' '+u[i];}

window.fmNav=function(p){fmPath=p;renderFmBreadcrumb();loadFmFiles();};
window.fmOpen=function(n){toast('Opening '+n,'info');};
window.fmCtx=function(e,name,isDir){e.preventDefault();const m=$('#contextMenu');m.innerHTML=`
  <div class="context-menu-item" onclick="fmRename('${name}')">&#9998; Rename</div>
  <div class="context-menu-item" onclick="fmDownload('${name}')">&#11015; Download</div>
  <div class="context-menu-item" onclick="fmPerms('${name}')">&#9881; Permissions</div>
  <div class="context-menu-divider"></div>
  <div class="context-menu-item danger" onclick="fmDelete('${name}',${isDir})">&#128465; Delete</div>`;
  m.style.left=e.clientX+'px';m.style.top=e.clientY+'px';m.classList.add('show');
  const close=()=>{m.classList.remove('show');document.removeEventListener('click',close);};
  setTimeout(()=>document.addEventListener('click',close),0);
};

function showFmNewFolder(){
  showModal('New Folder',`<div class="form-group"><label>Folder Name</label><input class="form-control" id="newFolderName" placeholder="New folder"></div>`,
    `<button class="btn btn-ghost" onclick="hideModal()">Cancel</button><button class="btn btn-primary" id="createFolderBtn">Create</button>`);
  $('#createFolderBtn').onclick=async()=>{
    const name=$('#newFolderName').value.trim();
    if(!name){toast('Enter name','warning');return;}
    try{await api('/files/mkdir',{method:'POST',body:JSON.stringify({path:fmPath,name})});hideModal();toast('Folder created','success');loadFmFiles();}catch(e){toast(e.message,'danger');}
  };
}

function showFmNewFile(){
  showModal('New File',`<div class="form-group"><label>File Name</label><input class="form-control" id="newFileName" placeholder="file.txt"></div>`,
    `<button class="btn btn-ghost" onclick="hideModal()">Cancel</button><button class="btn btn-primary" id="createFileBtn">Create</button>`);
  $('#createFileBtn').onclick=async()=>{
    const name=$('#newFileName').value.trim();
    if(!name){toast('Enter name','warning');return;}
    try{await api('/files/create',{method:'POST',body:JSON.stringify({path:fmPath,name})});hideModal();toast('File created','success');loadFmFiles();}catch(e){toast(e.message,'danger');}
  };
}

async function uploadFmFiles(files){
  for(const f of files){
    const fd=new FormData();
    fd.append('file',f);
    fd.append('path',fmPath);
    try{await fetch('/api/files/upload',{method:'POST',headers:{'Authorization':'Bearer '+getToken()},body:fd});toast(f.name+' uploaded','success');}catch(e){toast('Upload failed','danger');}
  }
  loadFmFiles();
}

window.fmRename=function(n){
  showModal('Rename',`<div class="form-group"><label>New Name</label><input class="form-control" id="renameName" value="${n}"></div>`,
    `<button class="btn btn-ghost" onclick="hideModal()">Cancel</button><button class="btn btn-primary" id="renameBtn">Rename</button>`);
  $('#renameBtn').onclick=async()=>{
    const nn=$('#renameName').value.trim();
    if(!nn){toast('Enter name','warning');return;}
    try{await api('/files/rename',{method:'POST',body:JSON.stringify({path:fmPath,old:n,new:nn})});hideModal();toast('Renamed','success');loadFmFiles();}catch(e){toast(e.message,'danger');}
  };
};

window.fmDelete=function(n,isDir){confirmAction('Delete '+(isDir?'folder':'file')+' '+n+'?',async()=>{try{await api('/files/delete',{method:'POST',body:JSON.stringify({path:fmPath,name:n})});toast('Deleted','success');loadFmFiles();}catch(e){toast(e.message,'danger');}});};
window.fmDownload=function(n){window.open('/api/files/download?path='+encodeURIComponent(fmPath)+'&name='+encodeURIComponent(n),'_blank');};
window.fmPerms=function(n){
  showModal('Set Permissions',`<div class="form-group"><label>Permissions (e.g. 755)</label><input class="form-control" id="permVal" placeholder="755"></div>`,
    `<button class="btn btn-ghost" onclick="hideModal()">Cancel</button><button class="btn btn-primary" id="permBtn">Apply</button>`);
  $('#permBtn').onclick=async()=>{
    const perms=$('#permVal').value.trim();
    if(!perms){toast('Enter permissions','warning');return;}
    try{await api('/files/chmod',{method:'POST',body:JSON.stringify({path:fmPath,name:n,perms})});hideModal();toast('Permissions updated','success');loadFmFiles();}catch(e){toast(e.message,'danger');}
  };
};

// SSL
async function loadSSL(){
  const c=$('#content');
  c.innerHTML=`<div class="section-header"><h1 class="section-title">SSL Certificates</h1><button class="btn btn-primary" id="issueSslBtn">+ Issue Certificate</button></div><div class="card"><div class="table-wrap"><table><thead><tr><th>Domain</th><th>Issuer</th><th>Expires</th><th>Status</th><th>Actions</th></tr></thead><tbody id="sslList"></tbody></table></div></div>`;
  $('#issueSslBtn').onclick=()=>showIssueSsl();
  try{
    const d=await api('/ssl/certificates');
    const tb=$('#sslList');
    if(d&&d.length){
      tb.innerHTML=d.map(s=>{const exp=new Date(s.expires);const ok=exp>new Date();return`<tr><td>${s.domain}</td><td>${s.issuer||'Let\'s Encrypt'}</td><td>${s.expires||'--'}</td><td><span class="badge ${ok?'badge-success':'badge-danger'}">${ok?'Valid':'Expired'}</span></td><td><button class="btn btn-sm btn-ghost" onclick="sslRenew('${s.domain}')">Renew</button></td></tr>`;}).join('');
    }else{tb.innerHTML='<tr><td colspan="5"><div class="empty-state"><div class="icon">&#128274;</div><h3>No SSL certificates</h3><p>Issue a certificate for your domains</p></div></td></tr>';}
  }catch(e){$('#sslList').innerHTML='<tr><td colspan="5" class="text-muted text-center">Failed to load certificates</td></tr>';}
}

function showIssueSsl(){
  showModal('Issue SSL Certificate',
    `<div class="form-group"><label>Domain</label><input class="form-control" id="sslDomain" placeholder="example.com"></div>
     <div class="form-group"><label>Email</label><input class="form-control" id="sslEmail" placeholder="admin@example.com"></div>`,
    `<button class="btn btn-ghost" onclick="hideModal()">Cancel</button><button class="btn btn-primary" id="issueBtn">Issue</button>`);
  $('#issueBtn').onclick=async()=>{
    const domain=$('#sslDomain').value.trim();
    if(!domain){toast('Enter domain','warning');return;}
    try{await api('/ssl/issue',{method:'POST',body:JSON.stringify({domain,email:$('#sslEmail').value.trim()})});hideModal();toast('Certificate issued','success');loadSSL();}catch(e){toast(e.message,'danger');}
  };
}
window.sslRenew=function(d){confirmAction('Renew SSL for '+d+'?',async()=>{try{await api('/ssl/renew/'+d,{method:'POST'});toast('Renewal started','success');}catch(e){toast(e.message,'danger');}});};

// Backups
async function loadBackups(){
  const c=$('#content');
  c.innerHTML=`<div class="section-header"><h1 class="section-title">Backups</h1><div class="btn-group"><button class="btn btn-primary" id="createBackupBtn">+ Create Backup</button><button class="btn btn-ghost" id="scheduleBackupBtn">Schedule</button></div></div><div class="card"><div class="table-wrap"><table><thead><tr><th>Name</th><th>Size</th><th>Created</th><th>Actions</th></tr></thead><tbody id="backupList"></tbody></table></div></div>`;
  $('#createBackupBtn').onclick=()=>createBackup();
  $('#scheduleBackupBtn').onclick=()=>showScheduleBackup();
  try{
    const d=await api('/backups');
    const tb=$('#backupList');
    if(d&&d.length){
      tb.innerHTML=d.map(b=>`<tr><td>${b.name}</td><td>${b.size||'--'}</td><td>${b.created||'--'}</td><td><button class="btn btn-sm btn-success" onclick="restoreBackup('${b.name}')">Restore</button> <button class="btn btn-sm btn-danger" onclick="deleteBackup('${b.name}')">Delete</button></td></tr>`).join('');
    }else{tb.innerHTML='<tr><td colspan="4"><div class="empty-state"><div class="icon">&#128190;</div><h3>No backups</h3><p>Create your first backup</p></div></td></tr>';}
  }catch(e){$('#backupList').innerHTML='<tr><td colspan="4" class="text-muted text-center">Failed to load backups</td></tr>';}
}

async function createBackup(){
  try{await api('/backups',{method:'POST'});toast('Backup created','success');loadBackups();}catch(e){toast(e.message,'danger');}
}
function showScheduleBackup(){
  showModal('Schedule Backup',
    `<div class="form-group"><label>Frequency</label><select class="form-control" id="backupFreq"><option value="daily">Daily</option><option value="weekly">Weekly</option><option value="monthly">Monthly</option></select></div>
     <div class="form-group"><label>Time</label><input type="time" class="form-control" id="backupTime" value="02:00"></div>
     <div class="form-group"><label>Retain</label><input type="number" class="form-control" id="backupRetain" value="7"></div>`,
    `<button class="btn btn-ghost" onclick="hideModal()">Cancel</button><button class="btn btn-primary" id="saveScheduleBtn">Save</button>`);
  $('#saveScheduleBtn').onclick=async()=>{
    try{await api('/backups/schedule',{method:'POST',body:JSON.stringify({freq:$('#backupFreq').value,time:$('#backupTime').value,retain:$('#backupRetain').value})});hideModal();toast('Schedule saved','success');}catch(e){toast(e.message,'danger');}
  };
}
window.restoreBackup=function(n){confirmAction('Restore backup '+n+'? This will overwrite current data.',async()=>{try{await api('/backups/'+n+'/restore',{method:'POST'});toast('Restore started','success');}catch(e){toast(e.message,'danger');}});};
window.deleteBackup=function(n){confirmAction('Delete backup '+n+'?',async()=>{try{await api('/backups/'+n,{method:'DELETE'});toast('Deleted','success');loadBackups();}catch(e){toast(e.message,'danger');}});};

// Firewall
async function loadFirewall(){
  const c=$('#content');
  c.innerHTML=`<div class="section-header"><h1 class="section-title">Firewall</h1><button class="btn btn-primary" id="addFwRuleBtn">+ Add Rule</button></div><div class="card"><div class="table-wrap"><table><thead><tr><th>Port</th><th>Protocol</th><th>Action</th><th>Source</th><th>Description</th><th>Actions</th></tr></thead><tbody id="fwList"></tbody></table></div></div>`;
  $('#addFwRuleBtn').onclick=()=>showAddFwRule();
  try{
    const d=await api('/firewall/rules');
    const tb=$('#fwList');
    if(d&&d.length){
      tb.innerHTML=d.map(r=>`<tr><td>${r.port}</td><td>${r.protocol}</td><td><span class="badge ${r.action==='allow'?'badge-success':'badge-danger'}">${r.action}</span></td><td>${r.source||'Any'}</td><td>${r.description||'--'}</td><td><button class="btn btn-sm btn-danger" onclick="deleteFwRule(${r.id})">Delete</button></td></tr>`).join('');
    }else{tb.innerHTML='<tr><td colspan="6"><div class="empty-state"><div class="icon">&#128737;</div><h3>No firewall rules</h3><p>Add rules to secure your server</p></div></td></tr>';}
  }catch(e){$('#fwList').innerHTML='<tr><td colspan="6" class="text-muted text-center">Failed to load rules</td></tr>';}
}

function showAddFwRule(){
  showModal('Add Firewall Rule',
    `<div class="form-row">
      <div class="form-group"><label>Port</label><input class="form-control" id="fwPort" placeholder="80"></div>
      <div class="form-group"><label>Protocol</label><select class="form-control" id="fwProto"><option>tcp</option><option>udp</option><option>both</option></select></div>
    </div>
    <div class="form-row">
      <div class="form-group"><label>Action</label><select class="form-control" id="fwAction"><option value="allow">Allow</option><option value="deny">Deny</option></select></div>
      <div class="form-group"><label>Source</label><input class="form-control" id="fwSource" placeholder="0.0.0.0/0"></div>
    </div>
    <div class="form-group"><label>Description</label><input class="form-control" id="fwDesc" placeholder="HTTP traffic"></div>`,
    `<button class="btn btn-ghost" onclick="hideModal()">Cancel</button><button class="btn btn-primary" id="saveFwRuleBtn">Add Rule</button>`);
  $('#saveFwRuleBtn').onclick=async()=>{
    const port=$('#fwPort').value.trim();
    if(!port){toast('Enter port','warning');return;}
    try{await api('/firewall/rules',{method:'POST',body:JSON.stringify({port,policy:$('#fwProto').value,action:$('#fwAction').value,source:$('#fwSource').value.trim(),description:$('#fwDesc').value.trim()})});hideModal();toast('Rule added','success');loadFirewall();}catch(e){toast(e.message,'danger');}
  };
}
window.deleteFwRule=function(id){confirmAction('Delete this rule?',async()=>{try{await api('/firewall/rules/'+id,{method:'DELETE'});toast('Deleted','success');loadFirewall();}catch(e){toast(e.message,'danger');}});};

// Cron Jobs
async function loadCronJobs(){
  const c=$('#content');
  c.innerHTML=`<div class="section-header"><h1 class="section-title">Cron Jobs</h1><button class="btn btn-primary" id="addCronBtn">+ Add Job</button></div><div class="card"><div class="table-wrap"><table><thead><tr><th>Schedule</th><th>Command</th><th>Status</th><th>Actions</th></tr></thead><tbody id="cronList"></tbody></table></div></div>`;
  $('#addCronBtn').onclick=()=>showAddCron();
  try{
    const d=await api('/cron/jobs');
    const tb=$('#cronList');
    if(d&&d.length){
      tb.innerHTML=d.map(j=>`<tr><td class="font-mono text-sm">${j.schedule}</td><td class="font-mono text-sm truncate" style="max-width:300px">${j.command}</td><td><span class="badge ${j.enabled?'badge-success':'badge-neutral'}">${j.enabled?'Enabled':'Disabled'}</span></td><td><button class="btn btn-sm btn-ghost" onclick="editCron(${j.id})">Edit</button> <button class="btn btn-sm btn-danger" onclick="deleteCron(${j.id})">Delete</button></td></tr>`).join('');
    }else{tb.innerHTML='<tr><td colspan="4"><div class="empty-state"><div class="icon">&#9200;</div><h3>No cron jobs</h3><p>Schedule tasks to run automatically</p></div></td></tr>';}
  }catch(e){$('#cronList').innerHTML='<tr><td colspan="4" class="text-muted text-center">Failed to load cron jobs</td></tr>';}
}

function showAddCron(){
  showModal('Add Cron Job',
    `<div class="form-group"><label>Schedule (cron syntax)</label><input class="form-control" id="cronSched" placeholder="0 2 * * *"></div>
     <div class="form-group"><label>Command</label><textarea class="form-control" id="cronCmd" placeholder="/path/to/script.sh"></textarea></div>`,
    `<button class="btn btn-ghost" onclick="hideModal()">Cancel</button><button class="btn btn-primary" id="saveCronBtn">Add</button>`);
  $('#saveCronBtn').onclick=async()=>{
    const sched=$('#cronSched').value.trim();
    const cmd=$('#cronCmd').value.trim();
    if(!sched||!cmd){toast('Fill all fields','warning');return;}
    try{await api('/cron/jobs',{method:'POST',body:JSON.stringify({schedule:sched,command:cmd})});hideModal();toast('Job added','success');loadCronJobs();}catch(e){toast(e.message,'danger');}
  };
}
window.editCron=function(id){toast('Editing cron job '+id,'info');};
window.deleteCron=function(id){confirmAction('Delete this cron job?',async()=>{try{await api('/cron/jobs/'+id,{method:'DELETE'});toast('Deleted','success');loadCronJobs();}catch(e){toast(e.message,'danger');}});};

// App Installer
const APPS=[
  {id:'wordpress',name:'WordPress',desc:'Most popular CMS for blogs and websites',icon:'W',color:'#21759b'},
  {id:'nextcloud',name:'Nextcloud',desc:'Self-hosted file sync and share',icon:'N',color:'#0082c9'},
  {id:'phpmyadmin',name:'phpMyAdmin',desc:'Web-based MySQL administration',icon:'P',color:'#0068a6'},
  {id:'roundcube',name:'Roundcube',desc:'Webmail client with modern UI',icon:'R',color:'#2e6eb5'},
  {id:'ghost',name:'Ghost',desc:'Professional publishing platform',icon:'G',color:'#738a94'},
  {id:'gitlab',name:'GitLab CE',desc:'Complete DevOps platform',icon:'GL',color:'#fc6d26'},
  {id:'nodejs',name:'Node.js',desc:'JavaScript runtime for server apps',icon:'JS',color:'#68a063'},
  {id:'flask',name:'Python/Flask',desc:'Lightweight Python web framework',icon:'F',color:'#000'},
  {id:'docker',name:'Docker',desc:'Container platform for apps',icon:'D',color:'#2496ed'},
  {id:'portainer',name:'Portainer',desc:'Docker management web UI',icon:'Pt',color:'#13bef9'}
];

async function loadAppInstaller(){
  const c=$('#content');
  c.innerHTML=`<div class="section-header"><h1 class="section-title">App Installer</h1></div>
    <div class="tabs"><button class="tab active" data-tab="available">Available</button><button class="tab" data-tab="installed">Installed</button></div>
    <div class="app-grid" id="appGrid"></div>`;
  $$('.tab[data-tab]').forEach(t=>t.onclick=function(){
    $$('.tab[data-tab]').forEach(x=>x.classList.remove('active'));
    this.classList.add('active');
    renderApps(this.dataset.tab);
  });
  renderApps('available');
}

function renderApps(tab){
  const g=$('#appGrid');
  if(tab==='available'){
    g.innerHTML=APPS.map(a=>`<div class="app-card"><div class="app-card-header"><div class="app-icon" style="background:${a.color};color:#fff">${a.icon}</div><div><div class="app-name">${a.name}</div><div class="app-desc">${a.desc}</div></div></div><div class="app-card-footer"><button class="btn btn-sm btn-primary" onclick="installApp('${a.id}')">Install</button></div></div>`).join('');
  }else{
    g.innerHTML='<div class="empty-state" style="grid-column:1/-1"><div class="icon">&#128230;</div><h3>No apps installed</h3><p>Install an app from the Available tab</p></div>';
  }
}

window.installApp=function(id){
  const app=APPS.find(a=>a.id===id);
  if(!app)return;
  confirmAction(`Install ${app.name}?`,async()=>{
    toast(`Installing ${app.name}...`,'info');
    try{await api('/apps/install',{method:'POST',body:JSON.stringify({app:id})});toast(app.name+' installed','success');}catch(e){toast(e.message,'danger');}
  });
};

// System Monitor
async function loadSystemMonitor(){
  const c=$('#content');
  c.innerHTML=`<div class="section-header"><h1 class="section-title">System Monitor</h1></div>
    <div class="gauges-grid mb-24" id="monGauges"></div>
    <div class="grid-2 mb-24">
      <div class="card"><div class="card-header"><span class="card-title">Processes</span></div><div class="table-wrap"><table><thead><tr><th>PID</th><th>Name</th><th>CPU%</th><th>MEM%</th><th>Actions</th></tr></thead><tbody id="monProcs"></tbody></table></div></div>
      <div class="card"><div class="card-header"><span class="card-title">System Info</span></div><div id="sysInfo" style="font-size:13px;line-height:2"></div></div>
    </div>
    <div class="card"><div class="card-header"><span class="card-title">System Log</span></div><div class="log-viewer" id="sysLog">Loading...</div></div>`;
  refreshMonitor();
  monitorInterval=setInterval(refreshMonitor,5000);
  loadSysLog();
}

async function refreshMonitor(){
  try{
    const d=await api('/system/stats');
    if(d)renderGaugesEl('monGauges',d);
  }catch(e){}
  try{
    const d=await api('/system/processes');
    if(d&&d.processes){
      const tb=$('#monProcs');
      if(tb)tb.innerHTML=d.processes.map(p=>`<tr><td>${p.pid}</td><td class="truncate" style="max-width:160px">${p.name}</td><td>${p.cpu.toFixed(1)}</td><td>${p.mem.toFixed(1)}</td><td><button class="btn btn-sm btn-danger" onclick="killProc(${p.pid})">Kill</button></td></tr>`).join('');
    }
  }catch(e){}
  try{
    const d=await api('/system/info');
    if(d){
      const si=$('#sysInfo');
      if(si)si.innerHTML=`<div><strong>Hostname:</strong> ${d.hostname||'--'}</div><div><strong>OS:</strong> ${d.os||'--'}</div><div><strong>Kernel:</strong> ${d.kernel||'--'}</div><div><strong>CPU:</strong> ${d.cpuModel||'--'}</div><div><strong>RAM:</strong> ${d.ramTotal||'--'}</div><div><strong>Load:</strong> ${d.loadAvg||'--'}</div>`;
    }
  }catch(e){}
}

function renderGaugesEl(id,d){
  const g=$('#'+id);
  if(!g)return;
  const items=[{label:'CPU',value:d.cpu||0,color:'var(--accent)'},{label:'RAM',value:d.ram||0,color:'var(--success)'},{label:'Disk',value:d.disk||0,color:'var(--warning)'}];
  g.innerHTML=items.map(i=>{
    const circ=2*Math.PI*42;const off=circ-(i.value/100)*circ;
    return `<div class="gauge-card"><div class="gauge"><svg width="100" height="100"><circle class="bg" cx="50" cy="50" r="42" stroke-width="8"/><circle class="fg" cx="50" cy="50" r="42" stroke-width="8" stroke="${i.color}" stroke-dasharray="${circ}" stroke-dashoffset="${off}"/></svg><div class="gauge-label" style="color:${i.color}">${Math.round(i.value)}%</div></div><div class="gauge-title">${i.label}</div></div>`;
  }).join('');
}

async function loadSysLog(){
  try{
    const d=await api('/system/log');
    const el=$('#sysLog');
    if(el&&d&&d.lines){
      el.innerHTML=d.lines.map(l=>`<div class="log-line-${l.level||'info'}">${l.time} ${l.message}</div>`).join('');
      el.scrollTop=el.scrollHeight;
    }
  }catch(e){}
}

window.killProc=function(pid){confirmAction('Kill process '+pid+'?',async()=>{try{await api('/system/processes/'+pid+'/kill',{method:'POST'});toast('Process killed','success');refreshMonitor();}catch(e){toast(e.message,'danger');}});};

// Settings
async function loadSettings(){
  const c=$('#content');
  c.innerHTML=`<div class="section-header"><h1 class="section-title">Settings</h1></div>
    <div class="grid-2">
      <div class="card"><div class="card-header"><span class="card-title">Change Password</span></div>
        <div class="form-group"><label>Current Password</label><input type="password" class="form-control" id="curPass"></div>
        <div class="form-group"><label>New Password</label><input type="password" class="form-control" id="newPass"></div>
        <div class="form-group"><label>Confirm Password</label><input type="password" class="form-control" id="confirmPass"></div>
        <button class="btn btn-primary" id="changePassBtn">Update Password</button>
      </div>
      <div class="card"><div class="card-header"><span class="card-title">System Configuration</span></div>
        <div class="form-group"><label>Hostname</label><input class="form-control" id="setHostname" placeholder="server.example.com"></div>
        <div class="form-group"><label>Timezone</label><select class="form-control" id="setTz"><option>UTC</option><option>Asia/Kolkata</option><option>America/New_York</option><option>Europe/London</option></select></div>
        <div class="form-group"><label>Default PHP Version</label><select class="form-control" id="setPhp"><option>8.2</option><option>8.1</option><option>8.0</option><option>7.4</option></select></div>
        <button class="btn btn-primary" id="saveSettingsBtn">Save Settings</button>
      </div>
    </div>`;
  $('#changePassBtn').onclick=async()=>{
    const cur=$('#curPass').value;
    const np=$('#newPass').value;
    const cp=$('#confirmPass').value;
    if(!cur||!np){toast('Fill all fields','warning');return;}
    if(np!==cp){toast('Passwords do not match','warning');return;}
    try{await api('/settings/password',{method:'POST',body:JSON.stringify({current:cur,new:np})});toast('Password updated','success');$('#curPass').value='';$('#newPass').value='';$('#confirmPass').value='';}catch(e){toast(e.message,'danger');}
  };
  $('#saveSettingsBtn').onclick=async()=>{
    try{await api('/settings',{method:'POST',body:JSON.stringify({hostname:$('#setHostname').value.trim(),timezone:$('#setTz').value,php:$('#setPhp').value})});toast('Settings saved','success');}catch(e){toast(e.message,'danger');}
  };
}

// Init
function init(){
  if(!getToken()){
    $('#loginGate').classList.remove('hidden');
    $('#app').classList.add('hidden');
    $('#loginForm').addEventListener('submit',async e=>{
      e.preventDefault();
      const btn=$('#loginBtn');
      btn.disabled=true;btn.textContent='Signing in...';
      $('#loginError').classList.remove('show');
      try{
        const r=await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:$('#username').value.trim(),password:$('#password').value})});
        const d=await r.json();
        if(!r.ok)throw new Error(d.error||'Login failed');
        setToken(d.token,$('#remember').checked);
        localStorage.setItem('user',$('#username').value.trim());
        location.reload();
      }catch(err){$('#loginError').textContent=err.message;$('#loginError').classList.add('show');}
      finally{btn.disabled=false;btn.textContent='Sign In';}
    });
    return;
  }
  $('#loginGate').classList.add('hidden');
  $('#app').classList.remove('hidden');
  $('#menuUserName').textContent=currentUser;

  $$('.nav-item[data-section]').forEach(n=>n.onclick=()=>navigate(n.dataset.section));
  $('#menuToggle').onclick=()=>{$('#sidebar').classList.toggle('open');};
  $('#sidebarOverlay').onclick=()=>$('#sidebar').classList.remove('open');
  $('#modalClose').onclick=hideModal;
  $('#modalOverlay').onclick=e=>{if(e.target===e.currentTarget)hideModal();};
  $('#userBtn').onclick=()=>$('#userMenu').classList.toggle('show');
  document.addEventListener('click',e=>{if(!e.target.closest('#userBtn')&&!e.target.closest('#userMenu'))$('#userMenu').classList.remove('show');});
  $('#menuLogout').onclick=$('#sidebarLogout').onclick=()=>{clearToken();location.reload();};
  document.addEventListener('keydown',e=>{if(e.key==='Escape'){hideModal();$('#contextMenu').classList.remove('show');}});

  navigate('dashboard');
}

init();
})();
