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

// API helper
async function api(path,opts={}){
  const t=getToken();
  const h={'Content-Type':'application/json',...(opts.headers||{})};
  if(t)h['Authorization']='Bearer '+t;
  try{
    const r=await fetch('/api'+path,{...opts,headers:h});
    if(r.status===401){clearToken();location.reload();return null;}
    const d=await r.json();
    if(!r.ok)throw new Error(d.detail||d.error||'Request failed');
    return d;
  }catch(e){throw e;}
}

// Convert object-of-objects to array
function objToArray(obj){if(Array.isArray(obj))return obj;if(!obj)return[];return Object.values(obj);}

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

// Confirm
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

// ── Dashboard ─────────────────────────────────────────────────────────
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
        <div class="stat-card"><div class="stat-info"><h3>Websites</h3><div class="stat-value">${d.sites_count||0}</div></div><div class="stat-icon blue">&#127760;</div></div>
        <div class="stat-card"><div class="stat-info"><h3>Databases</h3><div class="stat-value">${d.databases_count||0}</div></div><div class="stat-icon green">&#128451;</div></div>
        <div class="stat-card"><div class="stat-info"><h3>SSL Certs</h3><div class="stat-value">${d.ssl_count||0}</div></div><div class="stat-icon purple">&#128274;</div></div>
        <div class="stat-card"><div class="stat-info"><h3>Backups</h3><div class="stat-value">${d.backups_count||0}</div></div><div class="stat-icon orange">&#128190;</div></div>
        <div class="stat-card"><div class="stat-info"><h3>Disk</h3><div class="stat-value">${d.disk_percent||0}%</div></div><div class="stat-icon red">&#128190;</div></div>
        <div class="stat-card"><div class="stat-info"><h3>Uptime</h3><div class="stat-value">${d.uptime_hours?d.uptime_hours.toFixed(0)+'h':'--'}</div></div><div class="stat-icon blue">&#9200;</div></div>`;
      renderGauges({cpu:d.cpu_percent||0,ram:d.memory_percent||0,disk:d.disk_percent||0});
    }
  }catch(e){}

  const al=$('#activityList');
  al.innerHTML='<div class="activity-item"><div class="activity-icon" style="background:var(--info);color:#fff">&#8505;</div><div class="activity-content"><div class="activity-text">System ready</div><div class="activity-time">Just now</div></div></div>';

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
    const d=await api('/monitor/processes?sort_by=cpu&limit=5');
    if(d&&d.processes){
      const tb=$('#procTable tbody');
      if(tb)tb.innerHTML=d.processes.map(p=>`<tr><td>${p.pid}</td><td class="truncate" style="max-width:180px">${p.name}</td><td>${(p.cpu_percent||0).toFixed(1)}</td><td>${(p.memory_percent||0).toFixed(1)}</td></tr>`).join('');
    }
  }catch(e){}
}

// ── Websites ──────────────────────────────────────────────────────────
async function loadWebsites(){
  const c=$('#content');
  c.innerHTML=`<div class="section-header"><h1 class="section-title">Websites</h1><button class="btn btn-primary" id="addSiteBtn">+ Add Website</button></div><div class="card"><div class="table-wrap"><table><thead><tr><th>Domain</th><th>Root</th><th>Server</th><th>Status</th><th>Actions</th></tr></thead><tbody id="siteList"></tbody></table></div></div>`;
  $('#addSiteBtn').onclick=()=>showAddSite();
  try{
    const d=await api('/sites');
    const sites=objToArray(d&&d.sites);
    const tb=$('#siteList');
    if(sites.length){
      tb.innerHTML=sites.map(s=>`<tr><td>${s.domain}</td><td class="font-mono text-sm">${s.web_root||'--'}</td><td>${s.server_type||'nginx'}</td><td><span class="badge ${s.enabled?'badge-success':'badge-neutral'}">${s.enabled?'Active':'Disabled'}</span></td><td><button class="btn btn-sm btn-ghost" onclick="siteToggle('${s.domain}',${!s.enabled})">${s.enabled?'Disable':'Enable'}</button> <button class="btn btn-sm btn-danger" onclick="siteDelete('${s.domain}')">Delete</button></td></tr>`).join('');
    }else{tb.innerHTML='<tr><td colspan="5"><div class="empty-state"><div class="icon">&#127760;</div><h3>No websites yet</h3><p>Create your first website to get started</p></div></td></tr>';}
  }catch(e){$('#siteList').innerHTML='<tr><td colspan="5" class="text-muted text-center">Failed to load websites</td></tr>';}
}

function showAddSite(){
  showModal('Add Website',
    `<div class="form-group"><label>Domain Name</label><input class="form-control" id="newDomain" placeholder="example.com"></div>
     <div class="form-group"><label>Document Root (optional)</label><input class="form-control" id="newRoot" placeholder="/var/www/example.com/public"></div>
     <div class="form-group"><label>Enable PHP</label><select class="form-control" id="newPhp"><option value="false">No</option><option value="true">Yes</option></select></div>`,
    `<button class="btn btn-ghost" onclick="hideModal()">Cancel</button><button class="btn btn-primary" id="createSiteBtn">Create</button>`);
  $('#createSiteBtn').onclick=async()=>{
    const domain=$('#newDomain').value.trim();
    if(!domain){toast('Enter a domain','warning');return;}
    try{
      await api('/sites',{method:'POST',body:JSON.stringify({domain,web_root:$('#newRoot').value.trim()||null,php_enabled:$('#newPhp').value==='true'})});
      hideModal();toast('Website created','success');loadWebsites();
    }catch(e){toast(e.message,'danger');}
  };
}

window.siteToggle=function(d,en){confirmAction((en?'Enable':'Disable')+' website '+d+'?',async()=>{try{await api('/sites/'+d+'/'+(en?'enable':'disable'),{method:'PUT'});toast('Updated','success');loadWebsites();}catch(e){toast(e.message,'danger');}});};
window.siteDelete=function(d){confirmAction('Delete website '+d+'?',async()=>{try{await api('/sites/'+d,{method:'DELETE'});toast('Deleted','success');loadWebsites();}catch(e){toast(e.message,'danger');}});};
window.hideModal=hideModal;

// ── DNS ───────────────────────────────────────────────────────────────
async function loadDNS(){
  const c=$('#content');
  c.innerHTML=`<div class="section-header"><h1 class="section-title">DNS Management</h1><button class="btn btn-primary" id="addZoneBtn">+ Add Zone</button></div><div class="card"><div class="table-wrap"><table><thead><tr><th>Zone</th><th>Records</th><th>Actions</th></tr></thead><tbody id="dnsList"></tbody></table></div></div>`;
  $('#addZoneBtn').onclick=()=>showAddZone();
  try{
    const d=await api('/dns/zones');
    const zones=objToArray(d&&d.zones);
    const tb=$('#dnsList');
    if(zones.length){
      tb.innerHTML=zones.map(z=>{
        const recCount=objToArray(z.records).length;
        return `<tr><td>${z.name}</td><td>${recCount} records</td><td><button class="btn btn-sm btn-ghost" onclick="dnsManage('${z.name}')">Manage</button> <button class="btn btn-sm btn-danger" onclick="dnsDelete('${z.name}')">Delete</button></td></tr>`;
      }).join('');
    }else{tb.innerHTML='<tr><td colspan="3"><div class="empty-state"><div class="icon">&#9879;</div><h3>No DNS zones</h3><p>Add a domain zone to manage DNS records</p></div></td></tr>';}
  }catch(e){$('#dnsList').innerHTML='<tr><td colspan="3" class="text-muted text-center">Failed to load DNS zones</td></tr>';}
}

function showAddZone(){
  showModal('Add DNS Zone',
    `<div class="form-group"><label>Domain Name</label><input class="form-control" id="newZone" placeholder="example.com"></div>
     <div class="form-group"><label>Primary Nameserver</label><input class="form-control" id="newNs" placeholder="ns1.example.com"></div>`,
    `<button class="btn btn-ghost" onclick="hideModal()">Cancel</button><button class="btn btn-primary" id="createZoneBtn">Create</button>`);
  $('#createZoneBtn').onclick=async()=>{
    const name=$('#newZone').value.trim();
    if(!name){toast('Enter domain','warning');return;}
    try{await api('/dns/zones',{method:'POST',body:JSON.stringify({name,ns:$('#newNs').value.trim()||'ns1.'+name})});hideModal();toast('Zone created','success');loadDNS();}catch(e){toast(e.message,'danger');}
  };
}
window.dnsManage=function(z){toast('Managing zone '+z,'info');};
window.dnsDelete=function(z){confirmAction('Delete zone '+z+'?',async()=>{try{await api('/dns/zones/'+z,{method:'DELETE'});toast('Deleted','success');loadDNS();}catch(e){toast(e.message,'danger');}});};

// ── Email ─────────────────────────────────────────────────────────────
async function loadEmail(){
  const c=$('#content');
  c.innerHTML=`<div class="section-header"><h1 class="section-title">Email Accounts</h1><button class="btn btn-primary" id="addEmailBtn">+ Add Account</button></div><div class="card"><div class="table-wrap"><table><thead><tr><th>Email</th><th>Status</th><th>Actions</th></tr></thead><tbody id="emailList"></tbody></table></div></div>`;
  $('#addEmailBtn').onclick=()=>showAddEmail();
  try{
    const d=await api('/email/accounts');
    const accounts=objToArray(d&&d.accounts);
    const tb=$('#emailList');
    if(accounts.length){
      tb.innerHTML=accounts.map(e=>`<tr><td>${e.email||e.username}</td><td><span class="badge badge-success">Active</span></td><td><button class="btn btn-sm btn-danger" onclick="emailDelete('${e.email||e.username}')">Delete</button></td></tr>`).join('');
    }else{tb.innerHTML='<tr><td colspan="3"><div class="empty-state"><div class="icon">&#9993;</div><h3>No email accounts</h3><p>Create your first email account</p></div></td></tr>';}
  }catch(e){$('#emailList').innerHTML='<tr><td colspan="3" class="text-muted text-center">Failed to load email accounts</td></tr>';}
}

function showAddEmail(){
  showModal('Add Email Account',
    `<div class="form-group"><label>Email Address</label><input class="form-control" id="newEmail" placeholder="user@domain.com"></div>
     <div class="form-group"><label>Password</label><input type="password" class="form-control" id="newEmailPass" placeholder="Strong password"></div>`,
    `<button class="btn btn-ghost" onclick="hideModal()">Cancel</button><button class="btn btn-primary" id="createEmailBtn">Create</button>`);
  $('#createEmailBtn').onclick=async()=>{
    const email=$('#newEmail').value.trim();
    const pass=$('#newEmailPass').value;
    if(!email||!pass){toast('Fill all fields','warning');return;}
    try{await api('/email/accounts',{method:'POST',body:JSON.stringify({email,password:pass})});hideModal();toast('Email created','success');loadEmail();}catch(e){toast(e.message,'danger');}
  };
}
window.emailDelete=function(e){confirmAction('Delete email '+e+'?',async()=>{try{await api('/email/accounts/'+e,{method:'DELETE'});toast('Deleted','success');loadEmail();}catch(e){toast(e.message,'danger');}});};

// ── Databases ─────────────────────────────────────────────────────────
async function loadDatabases(){
  const c=$('#content');
  c.innerHTML=`<div class="section-header"><h1 class="section-title">Databases</h1><button class="btn btn-primary" id="addDbBtn">+ Create Database</button></div><div class="card"><div class="table-wrap"><table><thead><tr><th>Name</th><th>User</th><th>Type</th><th>Actions</th></tr></thead><tbody id="dbList"></tbody></table></div></div>`;
  $('#addDbBtn').onclick=()=>showAddDb();
  try{
    const d=await api('/databases');
    const dbs=objToArray(d&&d.databases);
    const tb=$('#dbList');
    if(dbs.length){
      tb.innerHTML=dbs.map(db=>`<tr><td>${db.name}</td><td>${db.user||'--'}</td><td>${db.type||'mysql'}</td><td><button class="btn btn-sm btn-success" onclick="dbBackup('${db.name}')">Backup</button> <button class="btn btn-sm btn-danger" onclick="dbDelete('${db.name}')">Delete</button></td></tr>`).join('');
    }else{tb.innerHTML='<tr><td colspan="4"><div class="empty-state"><div class="icon">&#128451;</div><h3>No databases</h3><p>Create your first database</p></div></td></tr>';}
  }catch(e){$('#dbList').innerHTML='<tr><td colspan="4" class="text-muted text-center">Failed to load databases</td></tr>';}
}

function showAddDb(){
  showModal('Create Database',
    `<div class="form-group"><label>Database Name</label><input class="form-control" id="newDbName" placeholder="my_database"></div>
     <div class="form-group"><label>Database User (optional)</label><input class="form-control" id="newDbUser" placeholder="Same as name"></div>
     <div class="form-group"><label>Password (auto-generated if empty)</label><input type="password" class="form-control" id="newDbPass" placeholder="Optional"></div>
     <div class="form-group"><label>Type</label><select class="form-control" id="newDbType"><option value="mysql">MySQL</option><option value="postgresql">PostgreSQL</option></select></div>`,
    `<button class="btn btn-ghost" onclick="hideModal()">Cancel</button><button class="btn btn-primary" id="createDbBtn">Create</button>`);
  $('#createDbBtn').onclick=async()=>{
    const name=$('#newDbName').value.trim();
    if(!name){toast('Enter database name','warning');return;}
    try{
      const body={name,db_type:$('#newDbType').value};
      const u=$('#newDbUser').value.trim();if(u)body.db_user=u;
      const p=$('#newDbPass').value;if(p)body.db_password=p;
      await api('/databases',{method:'POST',body:JSON.stringify(body)});
      hideModal();toast('Database created','success');loadDatabases();
    }catch(e){toast(e.message,'danger');}
  };
}
window.dbBackup=function(n){confirmAction('Backup database '+n+'?',async()=>{try{await api('/databases/'+n+'/backup',{method:'POST'});toast('Backup created','success');}catch(e){toast(e.message,'danger');}});};
window.dbDelete=function(n){confirmAction('Delete database '+n+'?',async()=>{try{await api('/databases/'+n,{method:'DELETE'});toast('Deleted','success');loadDatabases();}catch(e){toast(e.message,'danger');}});};

// ── File Manager ──────────────────────────────────────────────────────
let fmPath='/var/www';
async function loadFileManager(){
  const c=$('#content');
  c.innerHTML=`
    <div class="section-header"><h1 class="section-title">File Manager</h1></div>
    <div class="fm-toolbar">
      <div class="fm-breadcrumb" id="fmBreadcrumb"></div>
      <button class="btn btn-sm btn-primary" id="fmUploadBtn">Upload</button>
      <button class="btn btn-sm btn-ghost" id="fmNewFolderBtn">New Folder</button>
      <button class="btn btn-sm btn-ghost" id="fmNewFileBtn">New File</button>
    </div>
    <div id="fmDropZone" class="fm-drop-zone hidden">Drop files here to upload</div>
    <div class="card"><div class="table-wrap"><table id="fmTable"><thead><tr><th>Name</th><th>Size</th><th>Permissions</th><th>Modified</th><th>Actions</th></tr></thead><tbody id="fmFiles"></tbody></table></div></div>
    <input type="file" id="fmFileInput" multiple style="display:none">`;
  renderFmBreadcrumb();
  loadFmFiles();
  $('#fmUploadBtn').onclick=()=>$('#fmFileInput').click();
  $('#fmNewFolderBtn').onclick=()=>showFmNewFolder();
  $('#fmNewFileBtn').onclick=()=>showFmNewFile();
  $('#fmFileInput').onchange=e=>uploadFmFiles(e.target.files);
  const c2=c;
  c2.ondragover=e=>{e.preventDefault();$('#fmDropZone').classList.remove('hidden');};
  c2.ondragleave=e=>{if(!c2.contains(e.relatedTarget))$('#fmDropZone').classList.add('hidden');};
  c2.ondrop=e=>{e.preventDefault();$('#fmDropZone').classList.add('hidden');uploadFmFiles(e.dataTransfer.files);};
}

function renderFmBreadcrumb(){
  const bc=$('#fmBreadcrumb');
  const parts=fmPath.split('/').filter(Boolean);
  let html=`<span class="fm-path-item" onclick="fmNav('/')">/</span>`;
  let p='';
  parts.forEach(part=>{
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
    const files=d&&d.files?d.files:[];
    if(files.length){
      tb.innerHTML=files.map(f=>{
        const icon=f.is_dir||f.isDir?'&#128193;':'&#128196;';
        const name=f.name;
        const isDir=f.is_dir||f.isDir;
        return `<tr>
          <td><span style="cursor:pointer" onclick="${isDir?"fmNav('"+fmPath.replace(/\/$/,'')+'/'+name+"/')":"fmView('"+name+"')"}">${icon} ${name}</span></td>
          <td>${isDir?'--':formatSize(f.size||0)}</td>
          <td class="font-mono text-sm">${f.perms||f.mode||'--'}</td>
          <td class="text-sm">${f.modified||'--'}</td>
          <td><button class="btn btn-sm btn-ghost" onclick="fmRename('${name}')">Rename</button> <button class="btn btn-sm btn-danger" onclick="fmDelete('${name}',${isDir})">Delete</button></td></tr>`;
      }).join('');
    }else{tb.innerHTML='<tr><td colspan="5"><div class="empty-state"><div class="icon">&#128193;</div><h3>Empty folder</h3></div></td></tr>';}
  }catch(e){$('#fmFiles').innerHTML='<tr><td colspan="5" class="text-muted text-center">Failed to load files</td></tr>';}
}

function formatSize(b){if(!b)return'--';const u=['B','KB','MB','GB','TB'];let i=0;while(b>=1024&&i<u.length-1){b/=1024;i++;}return b.toFixed(i?1:0)+' '+u[i];}

window.fmNav=function(p){fmPath=p;renderFmBreadcrumb();loadFmFiles();};
window.fmView=function(n){toast('Viewing '+n,'info');};
window.fmRename=function(n){
  showModal('Rename',`<div class="form-group"><label>New Name</label><input class="form-control" id="renameName" value="${n}"></div>`,
    `<button class="btn btn-ghost" onclick="hideModal()">Cancel</button><button class="btn btn-primary" id="renameBtn">Rename</button>`);
  $('#renameBtn').onclick=async()=>{
    const nn=$('#renameName').value.trim();
    if(!nn){toast('Enter name','warning');return;}
    try{await api('/files/rename',{method:'POST',body:JSON.stringify({path:fmPath,new_name:nn,old_name:n})});hideModal();toast('Renamed','success');loadFmFiles();}catch(e){toast(e.message,'danger');}
  };
};
window.fmDelete=function(n,isDir){confirmAction('Delete '+(isDir?'folder':'file')+' '+n+'?',async()=>{try{await api('/files/delete?path='+encodeURIComponent(fmPath.replace(/\/$/,'')+'/'+n),{method:'DELETE'});toast('Deleted','success');loadFmFiles();}catch(e){toast(e.message,'danger');}});};
window.fmDownload=function(n){window.open('/api/files/download?path='+encodeURIComponent(fmPath.replace(/\/$/,'')+'/'+n),'_blank');};
window.fmPerms=function(n){
  showModal('Set Permissions',`<div class="form-group"><label>Permissions (e.g. 755)</label><input class="form-control" id="permVal" placeholder="755"></div>`,
    `<button class="btn btn-ghost" onclick="hideModal()">Cancel</button><button class="btn btn-primary" id="permBtn">Apply</button>`);
  $('#permBtn').onclick=async()=>{
    const perms=$('#permVal').value.trim();
    if(!perms){toast('Enter permissions','warning');return;}
    try{await api('/files/chmod',{method:'POST',body:JSON.stringify({path:fmPath,mode:perms,name:n})});hideModal();toast('Permissions updated','success');loadFmFiles();}catch(e){toast(e.message,'danger');}
  };
};

function showFmNewFolder(){
  showModal('New Folder',`<div class="form-group"><label>Folder Name</label><input class="form-control" id="newFolderName" placeholder="New folder"></div>`,
    `<button class="btn btn-ghost" onclick="hideModal()">Cancel</button><button class="btn btn-primary" id="createFolderBtn">Create</button>`);
  $('#createFolderBtn').onclick=async()=>{
    const name=$('#newFolderName').value.trim();
    if(!name){toast('Enter name','warning');return;}
    try{await api('/files/mkdir',{method:'POST',body:JSON.stringify({path:fmPath.replace(/\/$/,'')+'/'+name})});hideModal();toast('Folder created','success');loadFmFiles();}catch(e){toast(e.message,'danger');}
  };
}

function showFmNewFile(){
  showModal('New File',`<div class="form-group"><label>File Name</label><input class="form-control" id="newFileName" placeholder="file.txt"></div>`,
    `<button class="btn btn-ghost" onclick="hideModal()">Cancel</button><button class="btn btn-primary" id="createFileBtn">Create</button>`);
  $('#createFileBtn').onclick=async()=>{
    const name=$('#newFileName').value.trim();
    if(!name){toast('Enter name','warning');return;}
    try{await api('/files/write',{method:'POST',body:JSON.stringify({path:fmPath.replace(/\/$/,'')+'/'+name,content:''})});hideModal();toast('File created','success');loadFmFiles();}catch(e){toast(e.message,'danger');}
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

// ── SSL ───────────────────────────────────────────────────────────────
async function loadSSL(){
  const c=$('#content');
  c.innerHTML=`<div class="section-header"><h1 class="section-title">SSL Certificates</h1><button class="btn btn-primary" id="issueSslBtn">+ Issue Certificate</button></div><div class="card"><div class="table-wrap"><table><thead><tr><th>Domain</th><th>Expires</th><th>Status</th><th>Actions</th></tr></thead><tbody id="sslList"></tbody></table></div></div>`;
  $('#issueSslBtn').onclick=()=>showIssueSsl();
  try{
    const d=await api('/ssl/certificates');
    const certs=objToArray(d&&d.certificates);
    const tb=$('#sslList');
    if(certs.length){
      tb.innerHTML=certs.map(s=>{
        const exp=s.expires_at||s.expires;
        const ok=exp&&new Date(exp)>new Date();
        return `<tr><td>${s.domain}</td><td>${exp||'--'}</td><td><span class="badge ${ok?'badge-success':'badge-danger'}">${ok?'Valid':'Unknown'}</span></td><td><button class="btn btn-sm btn-ghost" onclick="sslRenew('${s.domain}')">Renew</button></td></tr>`;
      }).join('');
    }else{tb.innerHTML='<tr><td colspan="4"><div class="empty-state"><div class="icon">&#128274;</div><h3>No SSL certificates</h3><p>Issue a certificate for your domains</p></div></td></tr>';}
  }catch(e){$('#sslList').innerHTML='<tr><td colspan="4" class="text-muted text-center">Failed to load certificates</td></tr>';}
}

function showIssueSsl(){
  showModal('Issue SSL Certificate',
    `<div class="form-group"><label>Domain</label><input class="form-control" id="sslDomain" placeholder="example.com"></div>
     <div class="form-group"><label>Email</label><input class="form-control" id="sslEmail" placeholder="admin@example.com"></div>`,
    `<button class="btn btn-ghost" onclick="hideModal()">Cancel</button><button class="btn btn-primary" id="issueBtn">Issue</button>`);
  $('#issueBtn').onclick=async()=>{
    const domain=$('#sslDomain').value.trim();
    const email=$('#sslEmail').value.trim();
    if(!domain||!email){toast('Fill all fields','warning');return;}
    try{await api('/ssl/issue',{method:'POST',body:JSON.stringify({domain,email})});hideModal();toast('Certificate issued','success');loadSSL();}catch(e){toast(e.message,'danger');}
  };
}
window.sslRenew=function(d){confirmAction('Renew SSL for '+d+'?',async()=>{try{await api('/ssl/renew/'+d,{method:'POST'});toast('Renewal started','success');}catch(e){toast(e.message,'danger');}});};

// ── Backups ───────────────────────────────────────────────────────────
async function loadBackups(){
  const c=$('#content');
  c.innerHTML=`<div class="section-header"><h1 class="section-title">Backups</h1><div class="btn-group"><button class="btn btn-primary" id="createBackupBtn">+ Create Backup</button></div></div><div class="card"><div class="table-wrap"><table><thead><tr><th>Name</th><th>Created</th><th>Actions</th></tr></thead><tbody id="backupList"></tbody></table></div></div>`;
  $('#createBackupBtn').onclick=()=>createBackup();
  try{
    const d=await api('/backups');
    const backups=objToArray(d&&d.backups);
    const tb=$('#backupList');
    if(backups.length){
      tb.innerHTML=backups.map(b=>`<tr><td>${b.name}</td><td>${b.created_at||'--'}</td><td><button class="btn btn-sm btn-success" onclick="restoreBackup('${b.name}')">Restore</button> <button class="btn btn-sm btn-danger" onclick="deleteBackup('${b.name}')">Delete</button></td></tr>`).join('');
    }else{tb.innerHTML='<tr><td colspan="3"><div class="empty-state"><div class="icon">&#128190;</div><h3>No backups</h3><p>Create your first backup</p></div></td></tr>';}
  }catch(e){$('#backupList').innerHTML='<tr><td colspan="3" class="text-muted text-center">Failed to load backups</td></tr>';}
}

async function createBackup(){
  try{await api('/backups/create',{method:'POST'});toast('Backup created','success');loadBackups();}catch(e){toast(e.message,'danger');}
}
window.restoreBackup=function(n){confirmAction('Restore backup '+n+'?',async()=>{try{await api('/backups/'+n+'/restore',{method:'POST'});toast('Restore started','success');}catch(e){toast(e.message,'danger');}});};
window.deleteBackup=function(n){confirmAction('Delete backup '+n+'?',async()=>{try{await api('/backups/'+n,{method:'DELETE'});toast('Deleted','success');loadBackups();}catch(e){toast(e.message,'danger');}});};

// ── Firewall ──────────────────────────────────────────────────────────
async function loadFirewall(){
  const c=$('#content');
  c.innerHTML=`<div class="section-header"><h1 class="section-title">Firewall</h1><button class="btn btn-primary" id="addFwRuleBtn">+ Add Rule</button></div><div class="card"><div class="table-wrap"><table><thead><tr><th>Port</th><th>Protocol</th><th>Action</th><th>Source</th><th>Actions</th></tr></thead><tbody id="fwList"></tbody></table></div></div>`;
  $('#addFwRuleBtn').onclick=()=>showAddFwRule();
  try{
    const d=await api('/firewall/rules');
    const rules=d&&d.rules?d.rules:[];
    const tb=$('#fwList');
    if(rules.length){
      tb.innerHTML=rules.map(r=>`<tr><td>${r.port||r.dport||'--'}</td><td>${r.protocol||r.proto||'tcp'}</td><td><span class="badge ${(r.action||'ACCEPT')==='ACCEPT'?'badge-success':'badge-danger'}">${r.action||r.policy||'allow'}</span></td><td>${r.source||r.saddr||'Any'}</td><td><button class="btn btn-sm btn-danger" onclick="deleteFwRule('${r.id||r.num||''}')">Delete</button></td></tr>`).join('');
    }else{tb.innerHTML='<tr><td colspan="5"><div class="empty-state"><div class="icon">&#128737;</div><h3>No firewall rules</h3><p>Add rules to secure your server</p></div></td></tr>';}
  }catch(e){$('#fwList').innerHTML='<tr><td colspan="5" class="text-muted text-center">Failed to load rules</td></tr>';}
}

function showAddFwRule(){
  showModal('Add Firewall Rule',
    `<div class="form-row">
      <div class="form-group"><label>Port</label><input class="form-control" id="fwPort" placeholder="80"></div>
      <div class="form-group"><label>Protocol</label><select class="form-control" id="fwProto"><option>tcp</option><option>udp</option></select></div>
    </div>
    <div class="form-group"><label>Action</label><select class="form-control" id="fwAction"><option value="allow">Allow</option><option value="deny">Deny</option></select></div>`,
    `<button class="btn btn-ghost" onclick="hideModal()">Cancel</button><button class="btn btn-primary" id="saveFwRuleBtn">Add Rule</button>`);
  $('#saveFwRuleBtn').onclick=async()=>{
    const port=$('#fwPort').value.trim();
    if(!port){toast('Enter port','warning');return;}
    try{await api('/firewall/rules',{method:'POST',body:JSON.stringify({port,protocol:$('#fwProto').value,action:$('#fwAction').value})});hideModal();toast('Rule added','success');loadFirewall();}catch(e){toast(e.message,'danger');}
  };
}
window.deleteFwRule=function(id){confirmAction('Delete this rule?',async()=>{try{await api('/firewall/rules/'+id,{method:'DELETE'});toast('Deleted','success');loadFirewall();}catch(e){toast(e.message,'danger');}});};

// ── Cron Jobs ─────────────────────────────────────────────────────────
async function loadCronJobs(){
  const c=$('#content');
  c.innerHTML=`<div class="section-header"><h1 class="section-title">Cron Jobs</h1><button class="btn btn-primary" id="addCronBtn">+ Add Job</button></div><div class="card"><div class="table-wrap"><table><thead><tr><th>Schedule</th><th>Command</th><th>Status</th><th>Actions</th></tr></thead><tbody id="cronList"></tbody></table></div></div>`;
  $('#addCronBtn').onclick=()=>showAddCron();
  try{
    const d=await api('/cron/jobs');
    const jobs=d&&d.jobs?d.jobs:[];
    const tb=$('#cronList');
    if(jobs.length){
      tb.innerHTML=jobs.map(j=>`<tr><td class="font-mono text-sm">${j.schedule||j.time||'--'}</td><td class="font-mono text-sm truncate" style="max-width:300px">${j.command||'--'}</td><td><span class="badge ${j.enabled!==false?'badge-success':'badge-neutral'}">${j.enabled!==false?'Enabled':'Disabled'}</span></td><td><button class="btn btn-sm btn-danger" onclick="deleteCron('${j.id||j.num||''}')">Delete</button></td></tr>`).join('');
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
window.deleteCron=function(id){confirmAction('Delete this cron job?',async()=>{try{await api('/cron/jobs/'+id,{method:'DELETE'});toast('Deleted','success');loadCronJobs();}catch(e){toast(e.message,'danger');}});};

// ── App Installer ─────────────────────────────────────────────────────
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
  try{
    const d=await api('/apps/available');
    window._availableApps=d&&d.apps?d.apps:[];
  }catch(e){window._availableApps=[];}
  renderApps('available');
}

function renderApps(tab){
  const g=$('#appGrid');
  if(tab==='available'){
    const apps=window._availableApps||[];
    if(!apps.length){g.innerHTML='<div class="empty-state" style="grid-column:1/-1"><div class="icon">&#128230;</div><h3>Loading apps...</h3></div>';return;}
    g.innerHTML=apps.map(a=>`<div class="app-card"><div class="app-card-header"><div class="app-icon" style="background:var(--accent);color:#fff">${(a.name||'?')[0]}</div><div><div class="app-name">${a.name}</div><div class="app-desc">${a.description||''}</div><div class="app-desc" style="font-size:11px;color:var(--text-muted)">v${a.version||'?'}</div></div></div><div class="app-card-footer">${a.installed?'<span class="badge badge-success">Installed</span>':`<button class="btn btn-sm btn-primary" onclick="installApp('${a.slug}')">Install</button>`}</div></div>`).join('');
  }else{
    g.innerHTML='<div class="empty-state" style="grid-column:1/-1"><div class="icon">&#128230;</div><h3>Check installed apps</h3></div>';
  }
}

window.installApp=function(slug){
  confirmAction('Install this app?',async()=>{
    toast('Installing...','info');
    try{await api('/apps/install',{method:'POST',body:JSON.stringify({slug})});toast('App installed','success');loadAppInstaller();}catch(e){toast(e.message,'danger');}
  });
};

// ── System Monitor ────────────────────────────────────────────────────
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
    const d=await api('/monitor/status');
    if(d){
      renderGaugesEl('monGauges',{cpu:d.cpu?d.cpu.percent:0,ram:d.memory?d.memory.percent:0,disk:d.disk?d.disk.percent:0});
      const si=$('#sysInfo');
      if(si&&d.uptime){
        si.innerHTML=`<div><strong>Uptime:</strong> ${d.uptime.uptime_hours?d.uptime.uptime_hours.toFixed(1)+' hours':'--'}</div>
          <div><strong>CPU Cores:</strong> ${d.cpu?d.cpu.count:'--'}</div>
          <div><strong>RAM:</strong> ${d.memory?((d.memory.used/1073741824).toFixed(1)+' GB / '+(d.memory.total/1073741824).toFixed(1)+' GB'):'--'}</div>
          <div><strong>Disk:</strong> ${d.disk?((d.disk.used/1073741824).toFixed(1)+' GB / '+(d.disk.total/1073741824).toFixed(1)+' GB'):'--'}</div>`;
      }
    }
  }catch(e){}
  try{
    const d=await api('/monitor/processes?sort_by=cpu&limit=10');
    if(d&&d.processes){
      const tb=$('#monProcs');
      if(tb)tb.innerHTML=d.processes.map(p=>`<tr><td>${p.pid}</td><td class="truncate" style="max-width:160px">${p.name}</td><td>${(p.cpu_percent||0).toFixed(1)}</td><td>${(p.memory_percent||0).toFixed(1)}</td><td><button class="btn btn-sm btn-danger" onclick="killProc(${p.pid})">Kill</button></td></tr>`).join('');
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
    const d=await api('/monitor/logs/system?lines=30');
    const el=$('#sysLog');
    if(el&&d&&d.lines){
      el.innerHTML=d.lines.map(l=>`<div class="log-line">${typeof l==='string'?l:JSON.stringify(l)}</div>`).join('');
      el.scrollTop=el.scrollHeight;
    }
  }catch(e){}
}

window.killProc=function(pid){confirmAction('Kill process '+pid+'?',async()=>{try{await api('/monitor/processes/'+pid+'/kill',{method:'POST'});toast('Process killed','success');refreshMonitor();}catch(e){toast(e.message,'danger');}});};

// ── Settings ──────────────────────────────────────────────────────────
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
      <div class="card"><div class="card-header"><span class="card-title">System Info</span></div>
        <div id="settingsInfo" style="font-size:13px;line-height:2">Loading...</div>
      </div>
    </div>`;
  $('#changePassBtn').onclick=async()=>{
    const cur=$('#curPass').value;
    const np=$('#newPass').value;
    const cp=$('#confirmPass').value;
    if(!cur||!np){toast('Fill all fields','warning');return;}
    if(np!==cp){toast('Passwords do not match','warning');return;}
    try{await api('/settings/password',{method:'POST',body:JSON.stringify({current_password:cur,new_password:np})});toast('Password updated','success');$('#curPass').value='';$('#newPass').value='';$('#confirmPass').value='';}catch(e){toast(e.message,'danger');}
  };
  try{
    const d=await api('/system/info');
    const el=$('#settingsInfo');
    if(el&&d)el.innerHTML=`<div><strong>Hostname:</strong> ${d.hostname||'--'}</div><div><strong>OS:</strong> ${d.os||d.platform||'--'}</div><div><strong>Kernel:</strong> ${d.kernel||d.release||'--'}</div><div><strong>Python:</strong> ${d.python_version||'--'}</div>`;
  }catch(e){}
}

// ── Init ──────────────────────────────────────────────────────────────
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
        if(!r.ok)throw new Error(d.detail||d.error||'Login failed');
        setToken(d.access_token,$('#remember').checked);
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
