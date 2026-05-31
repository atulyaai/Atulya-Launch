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
    apps:'App Installer',monitor:'System Monitor',settings:'Settings',
    ssh:'SSH Keys',subdomains:'Subdomains',redirects:'Redirects',php:'PHP Manager',
    dkim:'DKIM / SPF / DMARC',twofa:'Two-Factor Auth',gitdeploy:'Git Deployment',
    staging:'Staging',errorpages:'Error Pages',quotas:'Disk Quotas',
    apitokens:'API Tokens',backups3:'S3 Backups',statuspage:'Status Page',
    ftp:'FTP Accounts',webmail:'Webmail',autoresponders:'Autoresponders',spam:'Spam Filter',
    docker:'Docker',nodeapps:'Node.js Apps',pythonapps:'Python Apps',
    audit:'Audit Log',sessions:'Sessions',loginhistory:'Login History',
    wildcardssl:'Wildcard SSL',csr:'CSR Generator',modsecurity:'WAF (ModSecurity)',
    fail2ban:'Fail2Ban',portscan:'Port Scan',sslautorenew:'SSL Auto Renew',
    ssldetails:'SSL Details',letsencryptwildcard:'Let\'s Encrypt WC',
    mailinglists:'Mailing Lists',emailrouting:'Email Routing',emailalerts:'Email Alerts',
    emailforwarding:'Email Forwarding',phpmyadmin:'phpMyAdmin',dbusers:'DB Users',
    remotedb:'Remote DB',dbimportexport:'DB Import/Export',dbschedulebackup:'DB Backup Schedule',
    rediscache:'Redis Cache',nginxcache:'NGINX Cache',opencache:'LiteSpeed',
    cloudflare:'Cloudflare',clouddns:'Cloud DNS',dnsimportexport:'DNS Import/Export',
    servercontrol:'Server Controls',timezone:'Timezone',ipv6:'IPv6',networkstats:'Network Stats',
    vpn:'VPN',healthdashboard:'Health Dashboard',ipaccess:'IP Access',sshaccess:'SSH Access',
    sftpisolation:'SFTP Isolation',sshterminal:'SSH Terminal',migration:'Migration',
    plugins:'Plugins',backupencryption:'Backup Encryption',cloudbackup:'Cloud Backup',
    filecompress:'File Compress',fileshare:'File Share',notifications:'Notifications',
    passwordpolicy:'Password Policy',multiuser:'Multi-User',resourcehistory:'Resource History',
    bandwidth:'Bandwidth',cronscheduler:'Cron Templates',csrf:'CSRF Tokens',
    hotlink:'Hotlink Protection',bandwidthlimit:'Bandwidth Limit'};
  $('#breadcrumb').innerHTML=`<span>Home</span><span class="sep">/</span><span class="current">${names[section]||section}</span>`;
  if(monitorInterval){clearInterval(monitorInterval);monitorInterval=null;}
  if(wsConn){wsConn.close();wsConn=null;}
  const loaders={dashboard:loadDashboard,websites:loadWebsites,dns:loadDNS,email:loadEmail,
    databases:loadDatabases,files:loadFileManager,ssl:loadSSL,backups:loadBackups,
    firewall:loadFirewall,cron:loadCronJobs,apps:loadAppInstaller,monitor:loadSystemMonitor,settings:loadSettings,
    ssh:loadSSH,subdomains:loadSubdomains,redirects:loadRedirects,php:loadPHP,
    dkim:loadDKIM,twofa:load2FA,gitdeploy:loadGitDeploy,staging:loadStaging,
    errorpages:loadErrorPages,quotas:loadQuotas,apitokens:loadApiTokens,
    backups3:loadBackups3,statuspage:loadStatusPage,
    ftp:loadFTP,webmail:loadWebmail,autoresponders:loadAutoresponders,spam:loadSpam,
    docker:loadDocker,nodeapps:loadNodeApps,pythonapps:loadPythonApps,
    audit:loadAudit,sessions:loadSessions,loginhistory:loadLoginHistory,
    wildcardssl:loadWildcardSSL,csr:loadCSR,modsecurity:loadModSecurity,
    fail2ban:loadFail2Ban,portscan:loadPortScan,sslautorenew:loadSSLAutoRenew,
    ssldetails:loadSSLDetails,letsencryptwildcard:loadLetsEncryptWC,
    mailinglists:loadMailingLists,emailrouting:loadEmailRouting,emailalerts:loadEmailAlerts,
    emailforwarding:loadEmailForwarding,phpmyadmin:loadPhpMyAdmin,dbusers:loadDBUsers,
    remotedb:loadRemoteDB,dbimportexport:loadDBImportExport,dbschedulebackup:loadDBScheduleBackup,
    rediscache:loadRedisCache,nginxcache:loadNginxCache,opencache:loadLiteSpeed,
    cloudflare:loadCloudflare,clouddns:loadCloudDNS,dnsimportexport:loadDNSImportExport,
    servercontrol:loadServerControl,timezone:loadTimezone,ipv6:loadIPv6,networkstats:loadNetworkStats,
    vpn:loadVPN,healthdashboard:loadHealthDashboard,ipaccess:loadIPAccess,sshaccess:loadSSHAccess,
    sftpisolation:loadSFTPIsolation,sshterminal:loadSSHTerminal,migration:loadMigration,
    plugins:loadPlugins,backupencryption:loadBackupEncryption,cloudbackup:loadCloudBackup,
    filecompress:loadFileCompress,fileshare:loadFileShare,notifications:loadNotifications,
    passwordpolicy:loadPasswordPolicy,multiuser:loadMultiUser,resourcehistory:loadResourceHistory,
    bandwidth:loadBandwidth,cronscheduler:loadCronTemplates,csrf:loadCSRF,
    hotlink:loadHotlinkProtection,bandwidthlimit:loadBandwidthLimit,
    cms_installer:loadCMSInstaller,security_advisor:loadSecurityAdvisor,antivirus:loadAntivirus,
    reseller:loadReseller,analytics:loadAnalytics};
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
    try{await api('/dns/zones',{method:'POST',body:JSON.stringify({domain:name,nameservers:[$('#newNs').value.trim()||'ns1.'+name]})});hideModal();toast('Zone created','success');loadDNS();}catch(e){toast(e.message,'danger');}
  };
}
window.dnsManage=async function(zone){
  const c=$('#content');
  c.innerHTML=`<div class="section-header"><h1 class="section-title">DNS Records: ${zone}</h1><button class="btn btn-ghost" id="dnsBackBtn">&larr; Back to Zones</button></div>
    <div class="card mb-24"><div class="card-header"><span class="card-title">Add Record</span></div>
      <div class="form-row">
        <div class="form-group"><label>Type</label><select class="form-control" id="recType"><option>A</option><option>AAAA</option><option>CNAME</option><option>MX</option><option>TXT</option><option>NS</option></select></div>
        <div class="form-group"><label>Name</label><input class="form-control" id="recName" placeholder="www"></div>
      </div>
      <div class="form-row">
        <div class="form-group"><label>Value</label><input class="form-control" id="recValue" placeholder="1.2.3.4"></div>
        <div class="form-group"><label>TTL</label><input class="form-control" id="recTtl" type="number" value="3600"></div>
      </div>
      <button class="btn btn-primary" id="addRecBtn">Add Record</button>
    </div>
    <div class="card"><div class="table-wrap"><table><thead><tr><th>Type</th><th>Name</th><th>Value</th><th>TTL</th><th>Actions</th></tr></thead><tbody id="recList"></tbody></table></div></div>`;
  $('#dnsBackBtn').onclick=()=>loadDNS();
  async function loadRecords(){
    try{
      const d=await api('/dns/zones/'+encodeURIComponent(zone)+'/records');
      const recs=objToArray(d&&d.records);
      const tb=$('#recList');
      if(recs.length){
        tb.innerHTML=recs.map(r=>`<tr><td><span class="badge badge-info">${r.type}</span></td><td class="font-mono text-sm">${r.name}</td><td class="font-mono text-sm truncate" style="max-width:250px">${r.content}</td><td>${r.ttl||3600}</td><td><button class="btn btn-sm btn-danger" onclick="dnsDelRec('${zone}',${r.id})">Delete</button></td></tr>`).join('');
      }else{tb.innerHTML='<tr><td colspan="5"><div class="empty-state"><div class="icon">&#9879;</div><h3>No records</h3><p>Add DNS records for this zone</p></div></td></tr>';}
    }catch(e){$('#recList').innerHTML='<tr><td colspan="5" class="text-muted text-center">Failed to load records</td></tr>';}
  }
  loadRecords();
  $('#addRecBtn').onclick=async()=>{
    const type=$('#recType').value,name=$('#recName').value.trim(),content=$('#recValue').value.trim(),ttl=parseInt($('#recTtl').value)||3600;
    if(!name||!content){toast('Fill all fields','warning');return;}
    try{await api('/dns/zones/'+encodeURIComponent(zone)+'/records',{method:'POST',body:JSON.stringify({type,name,content,ttl})});toast('Record added','success');$('#recName').value='';$('#recValue').value='';loadRecords();}catch(e){toast(e.message,'danger');}
  };
};
window.dnsDelRec=function(zone,id){confirmAction('Delete this record?',async()=>{try{await api('/dns/zones/'+encodeURIComponent(zone)+'/records/'+id,{method:'DELETE'});toast('Deleted','success');window.dnsManage(zone);}catch(e){toast(e.message,'danger');}});};
window.dnsDelete=function(z){confirmAction('Delete zone '+z+'?',async()=>{try{await api('/dns/zones/'+z,{method:'DELETE'});toast('Deleted','success');loadDNS();}catch(e){toast(e.message,'danger');}});};

// ── Email ─────────────────────────────────────────────────────────────
async function loadEmail(){
  const c=$('#content');
  c.innerHTML=`<div class="section-header"><h1 class="section-title">Email</h1><button class="btn btn-primary" id="addEmailBtn">+ Add Account</button></div>
    <div class="tabs"><button class="tab active" data-etab="accounts">Accounts</button><button class="tab" data-etab="aliases">Aliases</button><button class="tab" data-etab="forwarders">Forwarders</button></div>
    <div id="emailTabContent"></div>`;
  $$('.tab[data-etab]').forEach(t=>t.onclick=function(){
    $$('.tab[data-etab]').forEach(x=>x.classList.remove('active'));
    this.classList.add('active');
    renderEmailTab(this.dataset.etab);
  });
  renderEmailTab('accounts');
  $('#addEmailBtn').onclick=()=>showAddEmail();
}

async function renderEmailTab(tab){
  const el=$('#emailTabContent');
  if(tab==='accounts'){
    try{
      const d=await api('/email/accounts');
      const accounts=objToArray(d&&d.accounts);
      if(accounts.length){
        el.innerHTML=`<div class="card"><div class="table-wrap"><table><thead><tr><th>Email</th><th>Quota</th><th>Actions</th></tr></thead><tbody>${accounts.map(e=>`<tr><td>${e.email||e.username}</td><td>${e.quota_mb||1024} MB</td><td><button class="btn btn-sm btn-danger" onclick="emailDelete('${e.email||e.username}')">Delete</button></td></tr>`).join('')}</tbody></table></div></div>`;
      }else{el.innerHTML='<div class="card"><div class="empty-state"><div class="icon">&#9993;</div><h3>No email accounts</h3><p>Create your first email account</p></div></div>';}
    }catch(e){el.innerHTML='<div class="card text-muted text-center">Failed to load accounts</div>';}
  }else if(tab==='aliases'){
    try{
      const d=await api('/email/aliases');
      const aliases=objToArray(d&&d.aliases);
      el.innerHTML=`<div class="card mb-16"><div class="form-row"><div class="form-group"><label>Source</label><input class="form-control" id="aliasSrc" placeholder="alias@domain.com"></div><div class="form-group"><label>Destination</label><input class="form-control" id="aliasDst" placeholder="target@domain.com"></div></div><button class="btn btn-primary" id="addAliasBtn">Add Alias</button></div>
        <div class="card"><div class="table-wrap"><table><thead><tr><th>Source</th><th>Destination</th><th>Actions</th></tr></thead><tbody id="aliasList"></tbody></table></div></div>`;
      const tb=$('#aliasList');
      if(aliases.length){
        tb.innerHTML=aliases.map(a=>`<tr><td>${a.source||Object.keys(d.aliases).find(k=>d.aliases[k]===a)||'--'}</td><td>${typeof a==='string'?a:a.destination||'--'}</td><td><button class="btn btn-sm btn-danger" onclick="emailDeleteAlias('${a.source||Object.keys(d.aliases).find(k=>d.aliases[k]===a)}')">Delete</button></td></tr>`).join('');
      }else{tb.innerHTML='<tr><td colspan="3"><div class="empty-state"><p>No aliases configured</p></div></td></tr>';}
      $('#addAliasBtn').onclick=async()=>{
        const src=$('#aliasSrc').value.trim(),dst=$('#aliasDst').value.trim();
        if(!src||!dst){toast('Fill all fields','warning');return;}
        try{await api('/email/aliases',{method:'POST',body:JSON.stringify({source:src,destination:dst})});toast('Alias created','success');renderEmailTab('aliases');}catch(e){toast(e.message,'danger');}
      };
    }catch(e){el.innerHTML='<div class="card text-muted text-center">Failed to load aliases</div>';}
  }else if(tab==='forwarders'){
    try{
      const d=await api('/email/forwarders');
      const fwds=objToArray(d&&d.forwarders);
      el.innerHTML=`<div class="card mb-16"><div class="form-row"><div class="form-group"><label>Source</label><input class="form-control" id="fwdSrc" placeholder="info@domain.com"></div><div class="form-group"><label>Forward To</label><input class="form-control" id="fwdDst" placeholder="external@gmail.com"></div></div><button class="btn btn-primary" id="addFwdBtn">Add Forwarder</button></div>
        <div class="card"><div class="table-wrap"><table><thead><tr><th>Source</th><th>Forward To</th><th>Actions</th></tr></thead><tbody id="fwdList"></tbody></table></div></div>`;
      const tb=$('#fwdList');
      if(fwds.length){
        tb.innerHTML=fwds.map(f=>`<tr><td>${f.source||Object.keys(d.forwarders).find(k=>d.forwarders[k]===f)||'--'}</td><td>${typeof f==='string'?f:f.destination||'--'}</td><td><button class="btn btn-sm btn-danger" onclick="emailDeleteFwd('${f.source||Object.keys(d.forwarders).find(k=>d.forwarders[k]===f)}')">Delete</button></td></tr>`).join('');
      }else{tb.innerHTML='<tr><td colspan="3"><div class="empty-state"><p>No forwarders configured</p></div></td></tr>';}
      $('#addFwdBtn').onclick=async()=>{
        const src=$('#fwdSrc').value.trim(),dst=$('#fwdDst').value.trim();
        if(!src||!dst){toast('Fill all fields','warning');return;}
        try{await api('/email/forwarders',{method:'POST',body:JSON.stringify({source:src,destination:dst})});toast('Forwarder created','success');renderEmailTab('forwarders');}catch(e){toast(e.message,'danger');}
      };
    }catch(e){el.innerHTML='<div class="card text-muted text-center">Failed to load forwarders</div>';}
  }
}
window.emailDeleteAlias=function(a){confirmAction('Delete alias '+a+'?',async()=>{try{await api('/email/aliases/'+encodeURIComponent(a),{method:'DELETE'});toast('Deleted','success');renderEmailTab('aliases');}catch(e){toast(e.message,'danger');}});};
window.emailDeleteFwd=function(f){confirmAction('Delete forwarder '+f+'?',async()=>{try{await api('/email/forwarders/'+encodeURIComponent(f),{method:'DELETE'});toast('Deleted','success');renderEmailTab('forwarders');}catch(e){toast(e.message,'danger');}});};

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
          <td><button class="btn btn-sm btn-ghost" onclick="fmRename('${name}')">Rename</button> <button class="btn btn-sm btn-ghost" onclick="fmPerms('${name}')">Perms</button> ${!isDir?`<button class="btn btn-sm btn-ghost" onclick="fmDownload('${name}')">&#8681;</button>`:''} <button class="btn btn-sm btn-danger" onclick="fmDelete('${name}',${isDir})">Delete</button></td></tr>`;
      }).join('');
    }else{tb.innerHTML='<tr><td colspan="5"><div class="empty-state"><div class="icon">&#128193;</div><h3>Empty folder</h3></div></td></tr>';}
  }catch(e){$('#fmFiles').innerHTML='<tr><td colspan="5" class="text-muted text-center">Failed to load files</td></tr>';}
}

function formatSize(b){if(!b)return'--';const u=['B','KB','MB','GB','TB'];let i=0;while(b>=1024&&i<u.length-1){b/=1024;i++;}return b.toFixed(i?1:0)+' '+u[i];}

window.fmNav=function(p){fmPath=p;renderFmBreadcrumb();loadFmFiles();};
window.fmView=async function(n){
  const filePath=fmPath.replace(/\/$/,'')+'/'+n;
  try{
    const d=await api('/files/read?path='+encodeURIComponent(filePath));
    if(d){
      showModal('Edit: '+n,
        `<div class="form-group"><textarea class="form-control" id="fmViewContent" style="min-height:400px;font-family:var(--font-mono);font-size:13px;white-space:pre">${(d.content||'').replace(/</g,'&lt;').replace(/>/g,'&gt;')}</textarea></div>`,
        `<button class="btn btn-ghost" onclick="hideModal()">Cancel</button><button class="btn btn-primary" id="fmSaveBtn">Save</button>`);
      $('#fmSaveBtn').onclick=async()=>{
        try{await api('/files/write',{method:'POST',body:JSON.stringify({path:filePath,content:$('#fmViewContent').value})});hideModal();toast('File saved','success');}catch(e){toast(e.message,'danger');}
      };
    }
  }catch(e){toast('Failed to load file: '+e.message,'danger');}
};
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
  c.innerHTML=`<div class="section-header"><h1 class="section-title">Backups</h1><div class="btn-group"><button class="btn btn-primary" id="createBackupBtn">+ Create Backup</button></div></div>
    <div class="grid-2 mb-24">
      <div class="card"><div class="card-header"><span class="card-title">Backup Schedule</span></div>
        <div class="form-group"><label>Interval</label><select class="form-control" id="bkpInterval"><option value="daily">Daily</option><option value="weekly">Weekly</option><option value="monthly">Monthly</option><option value="none">Disabled</option></select></div>
        <div class="form-group"><label>Time</label><input class="form-control" id="bkpTime" type="time" value="02:00"></div>
        <div class="form-group"><label>Keep Days</label><input class="form-control" id="bkpKeep" type="number" value="30"></div>
        <button class="btn btn-primary" id="bkpSaveSchedBtn">Save Schedule</button>
        <div id="bkpSchedStatus" class="mt-16 text-sm text-muted"></div>
      </div>
      <div class="card"><div class="card-header"><span class="card-title">Backups</span></div><div class="table-wrap"><table><thead><tr><th>Name</th><th>Created</th><th>Actions</th></tr></thead><tbody id="backupList"></tbody></table></div></div>
    </div>`;
  $('#createBackupBtn').onclick=()=>createBackup();
  try{
    const sd=await api('/backups/schedule');
    if(sd&&sd.schedule){
      $('#bkpInterval').value=schedule.interval||'none';
      $('#bkpTime').value=schedule.time||'02:00';
      $('#bkpKeep').value=schedule.keep_days||30;
      $('#bkpSchedStatus').innerHTML=`Schedule: <span class="badge badge-success">${schedule.enabled?'Active':'Disabled'}</span>`;
    }
  }catch(e){}
  $('#bkpSaveSchedBtn').onclick=async()=>{
    try{await api('/backups/schedule',{method:'POST',body:JSON.stringify({interval:$('#bkpInterval').value,time:$('#bkpTime').value,keep_days:parseInt($('#bkpKeep').value)||30,enabled:$('#bkpInterval').value!=='none'})});toast('Schedule saved','success');}catch(e){toast(e.message,'danger');}
  };
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
    <div class="tabs"><button class="tab active" data-mtab="overview">Overview</button><button class="tab" data-mtab="services">Services</button><button class="tab" data-mtab="updates">Updates</button></div>
    <div id="monTabContent"></div>`;
  $$('.tab[data-mtab]').forEach(t=>t.onclick=function(){
    $$('.tab[data-mtab]').forEach(x=>x.classList.remove('active'));
    this.classList.add('active');
    renderMonTab(this.dataset.mtab);
  });
  renderMonTab('overview');
}

async function renderMonTab(tab){
  const el=$('#monTabContent');
  if(tab==='overview'){
    el.innerHTML=`<div class="gauges-grid mb-24" id="monGauges"></div>
      <div class="grid-2 mb-24">
        <div class="card"><div class="card-header"><span class="card-title">Processes</span></div><div class="table-wrap"><table><thead><tr><th>PID</th><th>Name</th><th>CPU%</th><th>MEM%</th><th>Actions</th></tr></thead><tbody id="monProcs"></tbody></table></div></div>
        <div class="card"><div class="card-header"><span class="card-title">System Info</span></div><div id="sysInfo" style="font-size:13px;line-height:2"></div></div>
      </div>
      <div class="card"><div class="card-header"><span class="card-title">System Log</span></div><div class="log-viewer" id="sysLog">Loading...</div></div>`;
    refreshMonitor();
    monitorInterval=setInterval(refreshMonitor,5000);
    loadSysLog();
  }else if(tab==='services'){
    if(monitorInterval){clearInterval(monitorInterval);monitorInterval=null;}
    el.innerHTML=`<div class="card"><div class="table-wrap"><table><thead><tr><th>Name</th><th>Active</th><th>Sub</th><th>Description</th><th>Actions</th></tr></thead><tbody id="svcList"></tbody></table></div></div>`;
    try{
      const d=await api('/system/services');
      const svcs=objToArray(d&&d.services);
      const tb=$('#svcList');
      if(svcs.length){
        tb.innerHTML=svcs.map(s=>`<tr><td class="font-mono text-sm">${s.name}</td><td><span class="badge ${s.active==='active'?'badge-success':'badge-neutral'}">${s.active}</span></td><td>${s.sub||'--'}</td><td class="truncate" style="max-width:250px">${s.description||''}</td><td><button class="btn btn-sm btn-success" onclick="svcAction('${s.name}','start')">Start</button> <button class="btn btn-sm btn-warning" onclick="svcAction('${s.name}','stop')">Stop</button> <button class="btn btn-sm btn-ghost" onclick="svcAction('${s.name}','restart')">Restart</button></td></tr>`).join('');
      }else{tb.innerHTML='<tr><td colspan="5"><div class="empty-state"><div class="icon">&#9881;</div><h3>No services found</h3></div></td></tr>';}
    }catch(e){$('#svcList').innerHTML='<tr><td colspan="5" class="text-muted text-center">Failed to load services</td></tr>';}
  }else if(tab==='updates'){
    if(monitorInterval){clearInterval(monitorInterval);monitorInterval=null;}
    el.innerHTML=`<div class="card"><div class="card-header"><span class="card-title">Available Updates</span></div><div id="updatesList">Loading...</div></div>`;
    try{
      const d=await api('/system/updates');
      const el2=$('#updatesList');
      if(d.updates&&d.updates.length){
        el2.innerHTML=`<div class="mb-16"><span class="badge badge-warning">${d.count} packages</span> can be updated</div><div style="font-family:var(--font-mono);font-size:13px;max-height:400px;overflow-y:auto">${d.updates.map(u=>`<div style="padding:4px 0;border-bottom:1px solid var(--border)">${u}</div>`).join('')}</div>`;
      }else{el2.innerHTML='<div class="empty-state"><div class="icon">&#10004;</div><h3>System is up to date</h3></div>';}
    }catch(e){$('#updatesList').innerHTML='<div class="text-muted text-center">Failed to check updates</div>';}
  }
}

window.svcAction=function(name,action){confirmAction(action.charAt(0).toUpperCase()+action.slice(1)+' service '+name+'?',async()=>{try{await api('/system/services/'+name+'/'+action,{method:'POST'});toast('Service '+action+'ed','success');renderMonTab('services');}catch(e){toast(e.message,'danger');}});};

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

// ── SSH Keys ──────────────────────────────────────────────────────────
async function loadSSH(){
  const c=$('#content');
  c.innerHTML=`<div class="section-header"><h1 class="section-title">SSH Keys</h1><button class="btn btn-primary" id="addSshBtn">+ Add Key</button></div><div class="card"><div class="table-wrap"><table><thead><tr><th>Name</th><th>Fingerprint</th><th>Actions</th></tr></thead><tbody id="sshList"></tbody></table></div></div>`;
  $('#addSshBtn').onclick=()=>showAddSsh();
  try{
    const d=await api('/ssh/keys');
    const keys=objToArray(d&&d.keys);
    const tb=$('#sshList');
    if(keys.length){
      tb.innerHTML=keys.map(k=>`<tr><td>${k.name||'--'}</td><td class="font-mono text-sm">${k.fingerprint}</td><td><button class="btn btn-sm btn-ghost" onclick="verifySsh('${k.fingerprint}')">Verify</button> <button class="btn btn-sm btn-danger" onclick="deleteSsh('${k.fingerprint}')">Delete</button></td></tr>`).join('');
    }else{tb.innerHTML='<tr><td colspan="3"><div class="empty-state"><div class="icon">&#128273;</div><h3>No SSH keys</h3><p>Add your public key for remote access</p></div></td></tr>';}
  }catch(e){$('#sshList').innerHTML='<tr><td colspan="3" class="text-muted text-center">Failed to load SSH keys</td></tr>';}
}
function showAddSsh(){
  showModal('Add SSH Key',
    `<div class="form-group"><label>Name (optional)</label><input class="form-control" id="sshKeyName" placeholder="my-laptop"></div>
     <div class="form-group"><label>Public Key</label><textarea class="form-control" id="sshPubKey" placeholder="ssh-rsa AAAA..." rows="3"></textarea></div>`,
    `<button class="btn btn-ghost" onclick="hideModal()">Cancel</button><button class="btn btn-primary" id="saveSshBtn">Add</button>`);
  $('#saveSshBtn').onclick=async()=>{
    const key=$('#sshPubKey').value.trim();
    if(!key){toast('Enter a public key','warning');return;}
    try{await api('/ssh/keys',{method:'POST',body:JSON.stringify({public_key:key,name:$('#sshKeyName').value.trim()||null})});hideModal();toast('Key added','success');loadSSH();}catch(e){toast(e.message,'danger');}
  };
}
window.verifySsh=function(fp){confirmAction('Verify key '+fp+'?',async()=>{try{const d=await api('/ssh/keys/'+fp+'/verify');toast(d.valid?'Key is valid':'Key invalid',d.valid?'success':'danger');}catch(e){toast(e.message,'danger');}});};
window.deleteSsh=function(fp){confirmAction('Delete SSH key '+fp+'?',async()=>{try{await api('/ssh/keys/'+fp,{method:'DELETE'});toast('Deleted','success');loadSSH();}catch(e){toast(e.message,'danger');}});};

// ── Subdomains ────────────────────────────────────────────────────────
async function loadSubdomains(){
  const c=$('#content');
  c.innerHTML=`<div class="section-header"><h1 class="section-title">Subdomains</h1><button class="btn btn-primary" id="addSubBtn">+ Add Subdomain</button></div><div class="card"><div class="table-wrap"><table><thead><tr><th>Subdomain</th><th>Domain</th><th>Target</th><th>Actions</th></tr></thead><tbody id="subList"></tbody></table></div></div>`;
  $('#addSubBtn').onclick=()=>showAddSub();
  try{
    const d=await api('/subdomains');
    const subs=objToArray(d&&d.subdomains);
    const tb=$('#subList');
    if(subs.length){
      tb.innerHTML=subs.map(s=>`<tr><td>${s.subdomain}</td><td>${s.domain}</td><td class="font-mono text-sm truncate" style="max-width:200px">${s.target}</td><td><button class="btn btn-sm btn-danger" onclick="deleteSub('${s.id||''}')">Delete</button></td></tr>`).join('');
    }else{tb.innerHTML='<tr><td colspan="4"><div class="empty-state"><div class="icon">&#9879;</div><h3>No subdomains</h3><p>Create subdomains to organize your sites</p></div></td></tr>';}
  }catch(e){$('#subList').innerHTML='<tr><td colspan="4" class="text-muted text-center">Failed to load subdomains</td></tr>';}
}
function showAddSub(){
  showModal('Add Subdomain',
    `<div class="form-group"><label>Domain</label><input class="form-control" id="subDomain" placeholder="example.com"></div>
     <div class="form-group"><label>Subdomain</label><input class="form-control" id="subName" placeholder="blog"></div>
     <div class="form-group"><label>Target</label><input class="form-control" id="subTarget" placeholder="http://127.0.0.1:3000"></div>`,
    `<button class="btn btn-ghost" onclick="hideModal()">Cancel</button><button class="btn btn-primary" id="saveSubBtn">Create</button>`);
  $('#saveSubBtn').onclick=async()=>{
    const d=$('#subDomain').value.trim(),n=$('#subName').value.trim(),t=$('#subTarget').value.trim();
    if(!d||!n||!t){toast('Fill all fields','warning');return;}
    try{await api('/subdomains',{method:'POST',body:JSON.stringify({domain:d,subdomain:n,target:t})});hideModal();toast('Created','success');loadSubdomains();}catch(e){toast(e.message,'danger');}
  };
}
window.deleteSub=function(id){confirmAction('Delete this subdomain?',async()=>{try{await api('/subdomains/'+id,{method:'DELETE'});toast('Deleted','success');loadSubdomains();}catch(e){toast(e.message,'danger');}});};

// ── Redirects ─────────────────────────────────────────────────────────
async function loadRedirects(){
  const c=$('#content');
  c.innerHTML=`<div class="section-header"><h1 class="section-title">URL Redirects</h1><button class="btn btn-primary" id="addRedirBtn">+ Add Redirect</button></div><div class="card"><div class="table-wrap"><table><thead><tr><th>From</th><th>To</th><th>Type</th><th>Actions</th></tr></thead><tbody id="redirList"></tbody></table></div></div>`;
  $('#addRedirBtn').onclick=()=>showAddRedir();
  try{
    const d=await api('/redirects');
    const redirs=objToArray(d&&d.redirects);
    const tb=$('#redirList');
    if(redirs.length){
      tb.innerHTML=redirs.map(r=>`<tr><td class="font-mono text-sm truncate" style="max-width:200px">${r.from_url}</td><td class="font-mono text-sm truncate" style="max-width:200px">${r.to_url}</td><td><span class="badge badge-success">${r.type||302}</span></td><td><button class="btn btn-sm btn-danger" onclick="deleteRedir('${r.id||''}')">Delete</button></td></tr>`).join('');
    }else{tb.innerHTML='<tr><td colspan="4"><div class="empty-state"><div class="icon">&#8594;</div><h3>No redirects</h3><p>Set up URL redirects for your domains</p></div></td></tr>';}
  }catch(e){$('#redirList').innerHTML='<tr><td colspan="4" class="text-muted text-center">Failed to load redirects</td></tr>';}
}
function showAddRedir(){
  showModal('Add Redirect',
    `<div class="form-group"><label>From URL</label><input class="form-control" id="redirFrom" placeholder="/old-page"></div>
     <div class="form-group"><label>To URL</label><input class="form-control" id="redirTo" placeholder="https://example.com/new-page"></div>
     <div class="form-group"><label>Type</label><select class="form-control" id="redirType"><option value="302">302 Temporary</option><option value="301">301 Permanent</option><option value="307">307 Temporary</option></select></div>`,
    `<button class="btn btn-ghost" onclick="hideModal()">Cancel</button><button class="btn btn-primary" id="saveRedirBtn">Create</button>`);
  $('#saveRedirBtn').onclick=async()=>{
    const f=$('#redirFrom').value.trim(),t=$('#redirTo').value.trim();
    if(!f||!t){toast('Fill all fields','warning');return;}
    try{await api('/redirects',{method:'POST',body:JSON.stringify({from_url:f,to_url:t,redirect_type:parseInt($('#redirType').value)})});hideModal();toast('Created','success');loadRedirects();}catch(e){toast(e.message,'danger');}
  };
}
window.deleteRedir=function(id){confirmAction('Delete this redirect?',async()=>{try{await api('/redirects/'+id,{method:'DELETE'});toast('Deleted','success');loadRedirects();}catch(e){toast(e.message,'danger');}});};

// ── PHP Manager ───────────────────────────────────────────────────────
async function loadPHP(){
  const c=$('#content');
  c.innerHTML=`<div class="section-header"><h1 class="section-title">PHP Manager</h1></div>
    <div class="grid-2">
      <div class="card"><div class="card-header"><span class="card-title">PHP Versions</span></div><div id="phpVersions">Loading...</div></div>
      <div class="card"><div class="card-header"><span class="card-title">Domain Settings</span></div>
        <div class="form-group"><label>Domain</label><input class="form-control" id="phpDomain" placeholder="example.com"></div>
        <div class="form-group"><label>PHP Version</label><select class="form-control" id="phpVersion"></select></div>
        <button class="btn btn-primary" id="phpSaveBtn">Apply</button>
        <div id="phpSettings" class="mt-16"></div>
      </div>
    </div>`;
  try{
    const d=await api('/php/versions');
    const verEl=$('#phpVersions');
    if(d){
      verEl.innerHTML=`<div><strong>Current:</strong> ${d.current||'--'}</div><div class="mt-8"><strong>Available:</strong> ${(d.versions||[]).map(v=>v.version).join(', ')||'--'}</div>`;
      const sel=$('#phpVersion');
      (d.versions||[]).forEach(v=>{sel.innerHTML+=`<option value="${v.version}">${v.version}</option>`;});
    }
  }catch(e){$('#phpVersions').innerHTML='Failed to load versions';}
  $('#phpSaveBtn').onclick=async()=>{
    const domain=$('#phpDomain').value.trim();
    if(!domain){toast('Enter a domain','warning');return;}
    try{
      await api('/php/config/'+domain,{method:'PUT',body:JSON.stringify({version:$('#phpVersion').value})});
      const d2=await api('/php/settings/'+domain);
      if(d2){
        const s=$('#phpSettings');
        s.innerHTML=`<h4 style="margin-top:16px">php.ini Settings</h4><div class="form-group"><label>memory_limit</label><input class="form-control" id="phpMemLimit" value="${d2.settings.memory_limit||'256M'}"></div><div class="form-group"><label>upload_max_filesize</label><input class="form-control" id="phpUploadMax" value="${d2.settings.upload_max_filesize||'64M'}"></div><div class="form-group"><label>post_max_size</label><input class="form-control" id="phpPostMax" value="${d2.settings.post_max_size||'64M'}"></div><button class="btn btn-primary" id="phpSettingsSaveBtn">Save Settings</button>`;
        $('#phpSettingsSaveBtn').onclick=async()=>{
          try{await api('/php/settings/'+domain,{method:'PUT',body:JSON.stringify({memory_limit:$('#phpMemLimit').value,upload_max_filesize:$('#phpUploadMax').value,post_max_size:$('#phpPostMax').value})});toast('Settings saved','success');}catch(e){toast(e.message,'danger');}
        };
      }
      toast('PHP version set','success');
    }catch(e){toast(e.message,'danger');}
  };
}

// ── DKIM / SPF / DMARC ───────────────────────────────────────────────
async function loadDKIM(){
  const c=$('#content');
  c.innerHTML=`<div class="section-header"><h1 class="section-title">DKIM / SPF / DMARC</h1></div>
    <div class="card mb-24"><div class="card-header"><span class="card-title">Status</span></div><div id="dkimStatus">Loading...</div></div>
    <div class="card mb-24"><div class="card-header"><span class="card-title">Generate Keys</span></div>
      <div class="form-group"><label>Domain</label><input class="form-control" id="dkimDomain" placeholder="example.com"></div>
      <div class="form-group"><label>Selector</label><input class="form-control" id="dkimSelector" value="default"></div>
      <button class="btn btn-primary" id="dkimGenBtn">Generate DKIM Keys</button>
    </div>
    <div class="card"><div class="card-header"><span class="card-title">DNS Records</span></div><div id="dkimRecords">Generate keys first</div></div>`;
  try{
    const d=await api('/dkim/status');
    $('#dkimStatus').innerHTML=`<div><strong>Enabled:</strong> ${d.enabled?'Yes':'No'}</div><div><strong>Domain:</strong> ${d.domain||'--'}</div><div><strong>Key Exists:</strong> ${d.key_exists?'Yes':'No'}</div>`;
    if(d.enabled){
      const d2=await api('/dkim/records');
      if(d2&&d2.records){
        const recs=d2.records;
        $('#dkimRecords').innerHTML=`<table class="table-wrap" style="width:100%"><thead><tr><th>Type</th><th>Name</th><th>Value</th></tr></thead><tbody><tr><td>DKIM</td><td class="font-mono text-sm">${recs.dkim.name}</td><td class="font-mono text-sm truncate" style="max-width:300px">${recs.dkim.value}</td></tr><tr><td>SPF</td><td class="font-mono text-sm">${recs.spf.name}</td><td class="font-mono text-sm truncate" style="max-width:300px">${recs.spf.value}</td></tr><tr><td>DMARC</td><td class="font-mono text-sm">${recs.dmarc.name}</td><td class="font-mono text-sm truncate" style="max-width:300px">${recs.dmarc.value}</td></tr></tbody></table>`;
      }
    }
  }catch(e){$('#dkimStatus').innerHTML='Failed to load status';}
  $('#dkimGenBtn').onclick=async()=>{
    const domain=$('#dkimDomain').value.trim();
    if(!domain){toast('Enter a domain','warning');return;}
    try{await api('/dkim/generate',{method:'POST',body:JSON.stringify({domain,selector:$('#dkimSelector').value.trim()||'default'})});toast('Keys generated','success');loadDKIM();}catch(e){toast(e.message,'danger');}
  };
}

// ── Two-Factor Auth ───────────────────────────────────────────────────
async function load2FA(){
  const c=$('#content');
  c.innerHTML=`<div class="section-header"><h1 class="section-title">Two-Factor Authentication</h1></div>
    <div class="card mb-24"><div class="card-header"><span class="card-title">Status</span></div><div id="twofaStatus">Loading...</div></div>
    <div class="grid-2">
      <div class="card"><div class="card-header"><span class="card-title">Enable 2FA</span></div>
        <p class="text-muted mb-16">Generate a TOTP secret to use with your authenticator app.</p>
        <button class="btn btn-primary" id="twofaEnableBtn">Enable 2FA</button>
        <div id="twofaQr" class="mt-16"></div>
        <div id="twofaVerify" class="mt-16" style="display:none">
          <div class="form-group"><label>Enter Code</label><input class="form-control" id="twofaCode" placeholder="000000"></div>
          <button class="btn btn-success" id="twofaVerifyBtn">Verify & Enable</button>
        </div>
      </div>
      <div class="card"><div class="card-header"><span class="card-title">Disable 2FA</span></div>
        <div class="form-group"><label>Current Code</label><input class="form-control" id="twofaDisableCode" placeholder="000000"></div>
        <button class="btn btn-danger" id="twofaDisableBtn">Disable 2FA</button>
        <div class="mt-16"><button class="btn btn-ghost" id="twofaBackupBtn">Generate Backup Codes</button></div>
        <div id="twofaBackupCodes" class="mt-16"></div>
      </div>
    </div>`;
  try{
    const d=await api('/2fa/status');
    $('#twofaStatus').innerHTML=`<div><strong>Enabled:</strong> ${d.enabled?'Yes':'No'}</div>`;
  }catch(e){$('#twofaStatus').innerHTML='Failed to load status';}
  let pendingSecret='';
  $('#twofaEnableBtn').onclick=async()=>{
    try{const d=await api('/2fa/enable',{method:'POST'});pendingSecret=d.secret;$('#twofaQr').innerHTML=`<div class="mb-8"><strong>Secret:</strong> <code>${d.secret}</code></div><div class="text-muted text-sm">Add this to your authenticator app</div>`;$('#twofaVerify').style.display='block';}catch(e){toast(e.message,'danger');}
  };
  $('#twofaVerifyBtn').onclick=async()=>{
    try{await api('/2fa/verify',{method:'POST',body:JSON.stringify({code:$('#twofaCode').value.trim()})});toast('2FA enabled','success');load2FA();}catch(e){toast(e.message,'danger');}
  };
  $('#twofaDisableBtn').onclick=async()=>{
    try{await api('/2fa/disable',{method:'POST',body:JSON.stringify({code:$('#twofaDisableCode').value.trim()})});toast('2FA disabled','success');load2FA();}catch(e){toast(e.message,'danger');}
  };
  $('#twofaBackupBtn').onclick=async()=>{
    try{const d=await api('/2fa/backup-codes');$('#twofaBackupCodes').innerHTML=`<div class="mb-8"><strong>Backup Codes:</strong></div><div style="font-family:monospace;font-size:13px;background:var(--bg-alt);padding:12px;border-radius:8px">${d.backup_codes.join('<br>')}</div><div class="text-muted text-sm mt-8">Save these codes. They will not be shown again.</div>`;}catch(e){toast(e.message,'danger');}
  };
}

// ── Git Deployment ────────────────────────────────────────────────────
async function loadGitDeploy(){
  const c=$('#content');
  c.innerHTML=`<div class="section-header"><h1 class="section-title">Git Deployment</h1><button class="btn btn-primary" id="gitCloneBtn">+ Clone Repo</button></div><div class="card"><div class="table-wrap"><table><thead><tr><th>Repo</th><th>Branch</th><th>Status</th><th>Actions</th></tr></thead><tbody id="gitList"></tbody></table></div></div>`;
  $('#gitCloneBtn').onclick=()=>showGitClone();
  try{
    const d=await api('/git/repos');
    const repos=objToArray(d&&d.repos);
    const tb=$('#gitList');
    if(repos.length){
      tb.innerHTML=repos.map(r=>`<tr><td class="truncate" style="max-width:200px">${r.url||r.path}</td><td>${r.branch||'main'}</td><td><span class="badge ${r.status==='clean'?'badge-success':r.status==='dirty'?'badge-warning':'badge-neutral'}">${r.status}</span></td><td><button class="btn btn-sm btn-ghost" onclick="gitPull('${r.id}')">Pull</button> <button class="btn btn-sm btn-ghost" onclick="gitLog('${r.id}')">Log</button> <button class="btn btn-sm btn-ghost" onclick="gitWebhook('${r.id}')">Webhook</button></td></tr>`).join('');
    }else{tb.innerHTML='<tr><td colspan="4"><div class="empty-state"><div class="icon">&#128187;</div><h3>No repositories</h3><p>Clone a Git repository to deploy</p></div></td></tr>';}
  }catch(e){$('#gitList').innerHTML='<tr><td colspan="4" class="text-muted text-center">Failed to load repos</td></tr>';}
}
function showGitClone(){
  showModal('Clone Repository',
    `<div class="form-group"><label>Repository URL</label><input class="form-control" id="gitUrl" placeholder="https://github.com/user/repo.git"></div>
     <div class="form-group"><label>Target Path</label><input class="form-control" id="gitTarget" placeholder="/var/www/mysite"></div>
     <div class="form-group"><label>Branch</label><input class="form-control" id="gitBranch" value="main"></div>`,
    `<button class="btn btn-ghost" onclick="hideModal()">Cancel</button><button class="btn btn-primary" id="gitCloneStartBtn">Clone</button>`);
  $('#gitCloneStartBtn').onclick=async()=>{
    const url=$('#gitUrl').value.trim(),target=$('#gitTarget').value.trim();
    if(!url||!target){toast('Fill all fields','warning');return;}
    try{await api('/git/clone',{method:'POST',body:JSON.stringify({url,target_path:target,branch:$('#gitBranch').value.trim()||'main'})});hideModal();toast('Cloned','success');loadGitDeploy();}catch(e){toast(e.message,'danger');}
  };
}
window.gitPull=function(id){confirmAction('Pull latest changes?',async()=>{try{await api('/git/pull',{method:'POST',body:JSON.stringify({repo_id:id})});toast('Pulled','success');loadGitDeploy();}catch(e){toast(e.message,'danger');}});};
window.gitLog=function(id){api('/git/log/'+id).then(d=>{const commits=objToArray(d&&d.commits);showModal('Commit Log','<div style="max-height:400px;overflow-y:auto">'+commits.map(c=>`<div style="padding:4px 0;border-bottom:1px solid var(--border)"><code style="color:var(--accent)">${c.hash}</code> ${c.message}</div>`).join('')+'</div>','<button class="btn btn-ghost" onclick="hideModal()">Close</button>');}).catch(e=>toast(e.message,'danger'));};
window.gitWebhook=function(id){showModal('Setup Webhook',`<div class="form-group"><label>Branch</label><input class="form-control" id="whBranch" value="main"></div><div class="form-group"><label>Secret (optional)</label><input class="form-control" id="whSecret" placeholder="Auto-generated"></div>`,`<button class="btn btn-ghost" onclick="hideModal()">Cancel</button><button class="btn btn-primary" id="whSetupBtn">Setup</button>`);$('#whSetupBtn').onclick=async()=>{try{const d=await api('/git/webhook',{method:'POST',body:JSON.stringify({repo_id:id,branch:$('#whBranch').value.trim(),secret:$('#whSecret').value.trim()||null})});hideModal();toast('Webhook: '+d.webhook_url,'success');}catch(e){toast(e.message,'danger');}};};

// ── Staging ───────────────────────────────────────────────────────────
async function loadStaging(){
  const c=$('#content');
  c.innerHTML=`<div class="section-header"><h1 class="section-title">Staging Environments</h1><button class="btn btn-primary" id="stagingCloneBtn">+ Clone to Staging</button></div><div class="card"><div class="table-wrap"><table><thead><tr><th>Staging Domain</th><th>Source</th><th>Status</th><th>Actions</th></tr></thead><tbody id="stagingList"></tbody></table></div></div>`;
  $('#stagingCloneBtn').onclick=()=>showStagingClone();
  try{
    const d=await api('/staging/list');
    const staging=objToArray(d&&d.staging);
    const tb=$('#stagingList');
    if(staging.length){
      tb.innerHTML=staging.map(s=>`<tr><td>${s.staging_domain}</td><td>${s.source_domain}</td><td><span class="badge ${s.status==='active'?'badge-success':'badge-neutral'}">${s.status}</span></td><td><button class="btn btn-sm btn-ghost" onclick="stagingPush('${s.id}')">Push to Prod</button> <button class="btn btn-sm btn-ghost" onclick="stagingPull('${s.id}')">Pull from Prod</button></td></tr>`).join('');
    }else{tb.innerHTML='<tr><td colspan="4"><div class="empty-state"><div class="icon">&#9879;</div><h3>No staging environments</h3><p>Clone a site to a staging environment</p></div></td></tr>';}
  }catch(e){$('#stagingList').innerHTML='<tr><td colspan="4" class="text-muted text-center">Failed to load staging</td></tr>';}
}
function showStagingClone(){
  showModal('Clone to Staging',
    `<div class="form-group"><label>Source Domain</label><input class="form-control" id="stgSource" placeholder="example.com"></div>
     <div class="form-group"><label>Staging Domain</label><input class="form-control" id="stgStaging" placeholder="staging.example.com"></div>`,
    `<button class="btn btn-ghost" onclick="hideModal()">Cancel</button><button class="btn btn-primary" id="stgCloneBtn">Clone</button>`);
  $('#stgCloneBtn').onclick=async()=>{
    const s=$('#stgSource').value.trim(),t=$('#stgStaging').value.trim();
    if(!s||!t){toast('Fill all fields','warning');return;}
    try{await api('/staging/clone',{method:'POST',body:JSON.stringify({source_domain:s,staging_domain:t})});hideModal();toast('Cloned','success');loadStaging();}catch(e){toast(e.message,'danger');}
  };
}
window.stagingPush=function(id){confirmAction('Push staging to production?',async()=>{try{await api('/staging/push',{method:'POST',body:JSON.stringify({staging_id:id})});toast('Pushed','success');}catch(e){toast(e.message,'danger');}});};
window.stagingPull=function(id){confirmAction('Pull production to staging?',async()=>{try{await api('/staging/pull',{method:'POST',body:JSON.stringify({staging_id:id})});toast('Pulled','success');}catch(e){toast(e.message,'danger');}});};

// ── Error Pages ───────────────────────────────────────────────────────
async function loadErrorPages(){
  const c=$('#content');
  c.innerHTML=`<div class="section-header"><h1 class="section-title">Custom Error Pages</h1></div>
    <div class="card mb-24">
      <div class="form-group"><label>Domain</label><input class="form-control" id="epDomain" placeholder="example.com"></div>
      <button class="btn btn-primary" id="epLoadBtn">Load Error Pages</button>
    </div>
    <div id="epContent"></div>`;
  $('#epLoadBtn').onclick=async()=>{
    const domain=$('#epDomain').value.trim();
    if(!domain){toast('Enter a domain','warning');return;}
    try{
      const d=await api('/errorpages/'+domain);
      const pages=d&&d.pages?d.pages:{};
      const el=$('#epContent');
      el.innerHTML=Object.keys(pages).map(code=>`<div class="card mb-16"><div class="card-header"><span class="card-title">${code} Error</span><span class="badge ${pages[code].custom?'badge-success':'badge-neutral'}">${pages[code].custom?'Custom':'Default'}</span></div><div class="form-group"><textarea class="form-control" id="ep${code}" rows="3">${pages[code].content}</textarea></div><button class="btn btn-sm btn-primary" onclick="saveEp('${domain}','${code}')">Save</button> <button class="btn btn-sm btn-ghost" onclick="resetEp('${domain}','${code}')">Reset to Default</button></div>`).join('');
    }catch(e){toast(e.message,'danger');}
  };
}
window.saveEp=function(domain,code){api('/errorpages/'+domain+'/'+code,{method:'PUT',body:JSON.stringify({content:document.getElementById('ep'+code).value})}).then(()=>toast('Saved','success')).catch(e=>toast(e.message,'danger'));};
window.resetEp=function(domain,code){confirmAction('Reset '+code+' to default?',()=>{api('/errorpages/'+domain+'/'+code,{method:'DELETE'}).then(()=>{toast('Reset','success');$('#epLoadBtn').click();}).catch(e=>toast(e.message,'danger'));});};

// ── Disk Quotas ───────────────────────────────────────────────────────
async function loadQuotas(){
  const c=$('#content');
  c.innerHTML=`<div class="section-header"><h1 class="section-title">Disk Quotas</h1><button class="btn btn-primary" id="addQuotaBtn">+ Set Quota</button></div><div class="card"><div class="table-wrap"><table><thead><tr><th>User</th><th>Limit</th><th>Used</th><th>%</th><th>Actions</th></tr></thead><tbody id="quotaList"></tbody></table></div></div>`;
  $('#addQuotaBtn').onclick=()=>showAddQuota();
  try{
    const d=await api('/quotas');
    const quotas=objToArray(d&&d.quotas);
    const tb=$('#quotaList');
    if(quotas.length){
      tb.innerHTML=quotas.map(q=>`<tr><td>${q.username}</td><td>${q.disk_limit_mb} MB</td><td>${q.current_usage?q.current_usage.disk_used_human:'--'}</td><td>${q.percent_used||0}%</td><td><button class="btn btn-sm btn-danger" onclick="deleteQuota('${q.username}')">Remove</button></td></tr>`).join('');
    }else{tb.innerHTML='<tr><td colspan="5"><div class="empty-state"><div class="icon">&#128200;</div><h3>No quotas set</h3><p>Set disk quotas for users</p></div></td></tr>';}
  }catch(e){$('#quotaList').innerHTML='<tr><td colspan="5" class="text-muted text-center">Failed to load quotas</td></tr>';}
}
function showAddQuota(){
  showModal('Set Disk Quota',
    `<div class="form-group"><label>Username</label><input class="form-control" id="quotaUser" placeholder="username"></div>
     <div class="form-group"><label>Disk Limit (MB)</label><input class="form-control" id="quotaDisk" type="number" value="1024"></div>
     <div class="form-group"><label>Inode Limit</label><input class="form-control" id="quotaInode" type="number" value="100000"></div>`,
    `<button class="btn btn-ghost" onclick="hideModal()">Cancel</button><button class="btn btn-primary" id="saveQuotaBtn">Set Quota</button>`);
  $('#saveQuotaBtn').onclick=async()=>{
    const user=$('#quotaUser').value.trim();
    if(!user){toast('Enter username','warning');return;}
    try{await api('/quotas/'+user,{method:'PUT',body:JSON.stringify({disk_limit_mb:parseInt($('#quotaDisk').value)||1024,inode_limit:parseInt($('#quotaInode').value)||100000})});hideModal();toast('Quota set','success');loadQuotas();}catch(e){toast(e.message,'danger');}
  };
}
window.deleteQuota=function(u){confirmAction('Remove quota for '+u+'?',async()=>{try{await api('/quotas/'+u,{method:'DELETE'});toast('Removed','success');loadQuotas();}catch(e){toast(e.message,'danger');}});};

// ── API Tokens ────────────────────────────────────────────────────────
async function loadApiTokens(){
  const c=$('#content');
  c.innerHTML=`<div class="section-header"><h1 class="section-title">API Tokens</h1><button class="btn btn-primary" id="addTokenBtn">+ Create Token</button></div><div class="card"><div class="table-wrap"><table><thead><tr><th>Name</th><th>Preview</th><th>Permissions</th><th>Expires</th><th>Status</th><th>Actions</th></tr></thead><tbody id="tokenList"></tbody></table></div></div>`;
  $('#addTokenBtn').onclick=()=>showAddToken();
  try{
    const d=await api('/tokens');
    const tokens=objToArray(d&&d.tokens);
    const tb=$('#tokenList');
    if(tokens.length){
      tb.innerHTML=tokens.map(t=>`<tr><td>${t.name}</td><td class="font-mono text-sm">${t.token_preview||'--'}</td><td>${(t.permissions||[]).join(', ')}</td><td>${t.expires_at||'Never'}</td><td><span class="badge ${t.expired?'badge-danger':'badge-success'}">${t.expired?'Expired':'Active'}</span></td><td><button class="btn btn-sm btn-danger" onclick="revokeToken('${t.id}')">Revoke</button></td></tr>`).join('');
    }else{tb.innerHTML='<tr><td colspan="6"><div class="empty-state"><div class="icon">&#128273;</div><h3>No API tokens</h3><p>Create tokens for API access</p></div></td></tr>';}
  }catch(e){$('#tokenList').innerHTML='<tr><td colspan="6" class="text-muted text-center">Failed to load tokens</td></tr>';}
}
function showAddToken(){
  showModal('Create API Token',
    `<div class="form-group"><label>Name</label><input class="form-control" id="tokenName" placeholder="My Token"></div>
     <div class="form-group"><label>Permissions</label><select class="form-control" id="tokenPerms" multiple><option value="read" selected>Read</option><option value="write">Write</option><option value="admin">Admin</option></select></div>
     <div class="form-group"><label>Expires (days)</label><input class="form-control" id="tokenExpiry" type="number" value="30"></div>`,
    `<button class="btn btn-ghost" onclick="hideModal()">Cancel</button><button class="btn btn-primary" id="saveTokenBtn">Create</button>`);
  $('#saveTokenBtn').onclick=async()=>{
    const name=$('#tokenName').value.trim();
    if(!name){toast('Enter a name','warning');return;}
    const perms=Array.from($('#tokenPerms').selectedOptions).map(o=>o.value);
    try{
      const d=await api('/tokens',{method:'POST',body:JSON.stringify({name,permissions:perms,expires_days:parseInt($('#tokenExpiry').value)||30})});
      hideModal();
      showModal('Token Created',`<div class="mb-16"><strong>Token:</strong></div><div style="font-family:monospace;word-break:break-all;background:var(--bg-alt);padding:12px;border-radius:8px">${d.token}</div><div class="text-muted text-sm mt-8">Save this token. It will not be shown again.</div>`,'<button class="btn btn-primary" onclick="hideModal()">Done</button>');
      loadApiTokens();
    }catch(e){toast(e.message,'danger');}
  };
}
window.revokeToken=function(id){confirmAction('Revoke this token?',async()=>{try{await api('/tokens/'+id,{method:'DELETE'});toast('Revoked','success');loadApiTokens();}catch(e){toast(e.message,'danger');}});};

// ── S3 Backups ────────────────────────────────────────────────────────
async function loadBackups3(){
  const c=$('#content');
  c.innerHTML=`<div class="section-header"><h1 class="section-title">S3 / Remote Backups</h1></div>
    <div class="grid-2">
      <div class="card"><div class="card-header"><span class="card-title">S3 Configuration</span></div>
        <div class="form-group"><label>Bucket</label><input class="form-control" id="s3Bucket" placeholder="my-backup-bucket"></div>
        <div class="form-group"><label>Access Key</label><input class="form-control" id="s3AccessKey"></div>
        <div class="form-group"><label>Secret Key</label><input type="password" class="form-control" id="s3SecretKey"></div>
        <div class="form-group"><label>Region</label><input class="form-control" id="s3Region" value="us-east-1"></div>
        <div class="form-group"><label>Endpoint (optional)</label><input class="form-control" id="s3Endpoint" placeholder="https://s3.example.com"></div>
        <button class="btn btn-primary" id="s3SaveBtn">Save Config</button>
      </div>
      <div class="card"><div class="card-header"><span class="card-title">Remote Backups</span></div>
        <div id="s3List">Configure S3 first</div>
      </div>
    </div>
    <div class="card mt-24"><div class="card-header"><span class="card-title">Actions</span></div>
      <button class="btn btn-primary mb-16" id="s3PushBtn">Push Backup to S3</button>
      <div id="s3RemoteBackups"></div>
    </div>`;
  try{
    const d=await api('/backups/remote/config');
    if(d&&d.config){
      if(d.config.bucket)$('#s3Bucket').value=d.config.bucket;
      if(d.config.region)$('#s3Region').value=d.config.region;
      if(d.config.endpoint)$('#s3Endpoint').value=d.config.endpoint;
    }
  }catch(e){}
  $('#s3SaveBtn').onclick=async()=>{
    try{await api('/backups/remote/config',{method:'POST',body:JSON.stringify({bucket:$('#s3Bucket').value.trim(),access_key:$('#s3AccessKey').value.trim(),secret_key:$('#s3SecretKey').value.trim(),region:$('#s3Region').value.trim(),endpoint:$('#s3Endpoint').value.trim()||null,prefix:'atulya-backups'})});toast('S3 config saved','success');loadS3Backups();}catch(e){toast(e.message,'danger');}
  };
  $('#s3PushBtn').onclick=async()=>{
    try{await api('/backups/remote/push',{method:'POST'});toast('Pushed to S3','success');}catch(e){toast(e.message,'danger');}
  };
  loadS3Backups();
}
async function loadS3Backups(){
  try{
    const d=await api('/backups/remote/list');
    const backups=objToArray(d&&d.backups);
    const el=$('#s3RemoteBackups');
    if(el&&backups.length){
      el.innerHTML=`<div class="table-wrap"><table style="width:100%"><thead><tr><th>Key</th><th>Size</th><th>Modified</th></tr></thead><tbody>${backups.map(b=>`<tr><td class="font-mono text-sm truncate" style="max-width:200px">${b.key}</td><td>${formatSize(b.size)}</td><td>${b.last_modified}</td></tr>`).join('')}</tbody></table></div>`;
    }
  }catch(e){}
}

// ── Status Page ───────────────────────────────────────────────────────
async function loadStatusPage(){
  const c=$('#content');
  c.innerHTML=`<div class="section-header"><h1 class="section-title">Status Page</h1></div>
    <div class="grid-2">
      <div class="card"><div class="card-header"><span class="card-title">Configuration</span></div>
        <div class="form-group"><label>Title</label><input class="form-control" id="spTitle" value="System Status"></div>
        <div class="form-group"><label>Description</label><textarea class="form-control" id="spDesc" rows="2"></textarea></div>
        <button class="btn btn-primary" id="spSaveBtn">Save Config</button>
      </div>
      <div class="card"><div class="card-header"><span class="card-title">Create Incident</span></div>
        <div class="form-group"><label>Title</label><input class="form-control" id="spIncTitle" placeholder="Degraded Performance"></div>
        <div class="form-group"><label>Description</label><textarea class="form-control" id="spIncDesc" rows="2"></textarea></div>
        <div class="form-group"><label>Status</label><select class="form-control" id="spIncStatus"><option value="investigating">Investigating</option><option value="identified">Identified</option><option value="monitoring">Monitoring</option><option value="resolved">Resolved</option></select></div>
        <button class="btn btn-primary" id="spIncBtn">Create Incident</button>
      </div>
    </div>
    <div class="card mt-24"><div class="card-header"><span class="card-title">Public Status</span></div><div id="spPreview"></div></div>`;
  try{
    const d=await api('/statuspage');
    if(d){
      $('#spTitle').value=d.title||'System Status';
      $('#spDesc').value=d.description||'';
      $('#spPreview').innerHTML=`<div class="mb-16"><strong>${d.title}</strong></div><div class="text-muted mb-16">${d.description||''}</div>${d.incidents&&d.incidents.length?d.incidents.map(i=>`<div style="padding:12px;border-left:3px solid var(--warning);background:var(--bg-alt);border-radius:4px;margin-bottom:8px"><strong>${i.title}</strong> <span class="badge badge-warning">${i.status}</span><div class="text-sm">${i.description||''}</div></div>`).join(''):'<div class="text-muted">No active incidents</div>'}`;
    }
  }catch(e){}
  $('#spSaveBtn').onclick=async()=>{
    try{await api('/statuspage/config',{method:'PUT',body:JSON.stringify({title:$('#spTitle').value.trim(),description:$('#spDesc').value.trim()})});toast('Config saved','success');}catch(e){toast(e.message,'danger');}
  };
  $('#spIncBtn').onclick=async()=>{
    const title=$('#spIncTitle').value.trim();
    if(!title){toast('Enter a title','warning');return;}
    try{await api('/statuspage/incident',{method:'POST',body:JSON.stringify({title,description:$('#spIncDesc').value.trim(),status:$('#spIncStatus').value})});toast('Incident created','success');$('#spIncTitle').value='';$('#spIncDesc').value='';loadStatusPage();}catch(e){toast(e.message,'danger');}
  };
}

// ── FTP Accounts ──────────────────────────────────────────────────────
async function loadFTP(){
  const c=$('#content');
  c.innerHTML=`<div class="section-header"><h1 class="section-title">FTP Accounts</h1><button class="btn btn-primary" id="addFtpBtn">+ Add Account</button></div><div class="card"><div class="table-wrap"><table><thead><tr><th>Username</th><th>Home Dir</th><th>Quota</th><th>Actions</th></tr></thead><tbody id="ftpList"></tbody></table></div></div>`;
  $('#addFtpBtn').onclick=()=>showAddFtp();
  try{
    const d=await api('/ftp/accounts');
    const accounts=objToArray(d&&d.accounts);
    const tb=$('#ftpList');
    if(accounts.length){
      tb.innerHTML=accounts.map(a=>`<tr><td class="font-mono text-sm">${a.username}</td><td class="text-sm">${a.home_dir||'--'}</td><td>${a.quota_mb||1024} MB</td><td><button class="btn btn-sm btn-ghost" onclick="ftpChangePass('${a.username}')">Password</button> <button class="btn btn-sm btn-danger" onclick="ftpDelete('${a.username}')">Delete</button></td></tr>`).join('');
    }else{tb.innerHTML='<tr><td colspan="4"><div class="empty-state"><div class="icon">&#128193;</div><h3>No FTP accounts</h3><p>Create FTP accounts for file access</p></div></td></tr>';}
  }catch(e){$('#ftpList').innerHTML='<tr><td colspan="4" class="text-muted text-center">Failed to load FTP accounts</td></tr>';}
}
function showAddFtp(){
  showModal('Add FTP Account',
    `<div class="form-group"><label>Username</label><input class="form-control" id="ftpUser" placeholder="ftpuser"></div>
     <div class="form-group"><label>Password</label><input type="password" class="form-control" id="ftpPass" placeholder="Strong password"></div>
     <div class="form-group"><label>Home Directory</label><input class="form-control" id="ftpHome" placeholder="/home/ftpuser"></div>
     <div class="form-group"><label>Quota (MB)</label><input class="form-control" id="ftpQuota" type="number" value="1024"></div>`,
    `<button class="btn btn-ghost" onclick="hideModal()">Cancel</button><button class="btn btn-primary" id="createFtpBtn">Create</button>`);
  $('#createFtpBtn').onclick=async()=>{
    const user=$('#ftpUser').value.trim(),pass=$('#ftpPass').value;
    if(!user||!pass){toast('Fill all fields','warning');return;}
    try{await api('/ftp/accounts',{method:'POST',body:JSON.stringify({username:user,password:pass,home_dir:$('#ftpHome').value.trim()||null,quota_mb:parseInt($('#ftpQuota').value)||1024})});hideModal();toast('FTP account created','success');loadFTP();}catch(e){toast(e.message,'danger');}
  };
}
window.ftpChangePass=function(u){
  showModal('Change Password',`<div class="form-group"><label>New Password</label><input type="password" class="form-control" id="ftpNewPass"></div>`,
    `<button class="btn btn-ghost" onclick="hideModal()">Cancel</button><button class="btn btn-primary" id="ftpPassBtn">Update</button>`);
  $('#ftpPassBtn').onclick=async()=>{
    const pass=$('#ftpNewPass').value;if(!pass){toast('Enter password','warning');return;}
    try{await api('/ftp/accounts/'+u+'/password',{method:'PUT',body:JSON.stringify({new_password:pass})});hideModal();toast('Password updated','success');}catch(e){toast(e.message,'danger');}
  };
};
window.ftpDelete=function(u){confirmAction('Delete FTP account '+u+'?',async()=>{try{await api('/ftp/accounts/'+u,{method:'DELETE'});toast('Deleted','success');loadFTP();}catch(e){toast(e.message,'danger');}});};

// ── Webmail ───────────────────────────────────────────────────────────
async function loadWebmail(){
  const c=$('#content');
  c.innerHTML=`<div class="section-header"><h1 class="section-title">Webmail</h1></div>
    <div class="card mb-24"><div class="card-header"><span class="card-title">Status</span></div><div id="wmStatus">Loading...</div></div>
    <div class="card"><div class="card-header"><span class="card-title">Actions</span></div>
      <button class="btn btn-primary" id="wmInstallBtn">Install Roundcube</button>
      <div id="wmConfig" class="mt-16"></div>
    </div>`;
  try{
    const d=await api('/webmail/status');
    const el=$('#wmStatus');
    if(d){
      el.innerHTML=`<div><strong>Installed:</strong> ${d.installed?'Yes':'No'}</div><div><strong>URL:</strong> ${d.url||'--'}</div>`;
      if(!d.installed){$('#wmInstallBtn').style.display='';}else{$('#wmInstallBtn').style.display='none';}
    }
  }catch(e){$('#wmStatus').innerHTML='Failed to load status';}
  $('#wmInstallBtn').onclick=async()=>{
    try{await api('/webmail/install',{method:'POST'});toast('Roundcube installed','success');loadWebmail();}catch(e){toast(e.message,'danger');}
  };
}

// ── Autoresponders ────────────────────────────────────────────────────
async function loadAutoresponders(){
  const c=$('#content');
  c.innerHTML=`<div class="section-header"><h1 class="section-title">Autoresponders</h1><button class="btn btn-primary" id="addAutoBtn">+ Add Autoresponder</button></div><div class="card"><div class="table-wrap"><table><thead><tr><th>Email</th><th>Subject</th><th>Actions</th></tr></thead><tbody id="autoList"></tbody></table></div></div>`;
  $('#addAutoBtn').onclick=()=>showAddAuto();
  try{
    const d=await api('/autoresponders');
    const items=objToArray(d&&d.autoresponders);
    const tb=$('#autoList');
    if(items.length){
      tb.innerHTML=items.map(a=>`<tr><td>${a.email}</td><td class="truncate" style="max-width:250px">${a.subject}</td><td><button class="btn btn-sm btn-danger" onclick="deleteAuto('${a.id||''}')">Delete</button></td></tr>`).join('');
    }else{tb.innerHTML='<tr><td colspan="3"><div class="empty-state"><div class="icon">&#128227;</div><h3>No autoresponders</h3><p>Set up auto-reply for email addresses</p></div></td></tr>';}
  }catch(e){$('#autoList').innerHTML='<tr><td colspan="3" class="text-muted text-center">Failed to load</td></tr>';}
}
function showAddAuto(){
  showModal('Add Autoresponder',
    `<div class="form-group"><label>Email</label><input class="form-control" id="autoEmail" placeholder="user@domain.com"></div>
     <div class="form-group"><label>Subject</label><input class="form-control" id="autoSubject" placeholder="Out of Office"></div>
     <div class="form-group"><label>Body</label><textarea class="form-control" id="autoBody" rows="3" placeholder="I am currently unavailable..."></textarea></div>
     <div class="form-row"><div class="form-group"><label>Start Date</label><input type="date" class="form-control" id="autoStart"></div><div class="form-group"><label>End Date</label><input type="date" class="form-control" id="autoEnd"></div></div>`,
    `<button class="btn btn-ghost" onclick="hideModal()">Cancel</button><button class="btn btn-primary" id="createAutoBtn">Create</button>`);
  $('#createAutoBtn').onclick=async()=>{
    const email=$('#autoEmail').value.trim(),subject=$('#autoSubject').value.trim(),body=$('#autoBody').value.trim();
    if(!email||!subject||!body){toast('Fill required fields','warning');return;}
    try{await api('/autoresponders',{method:'POST',body:JSON.stringify({email,subject,body,start_date:$('#autoStart').value||null,end_date:$('#autoEnd').value||null})});hideModal();toast('Created','success');loadAutoresponders();}catch(e){toast(e.message,'danger');}
  };
}
window.deleteAuto=function(id){confirmAction('Delete autoresponder?',async()=>{try{await api('/autoresponders/'+id,{method:'DELETE'});toast('Deleted','success');loadAutoresponders();}catch(e){toast(e.message,'danger');}});};

// ── Spam Filter ───────────────────────────────────────────────────────
async function loadSpam(){
  const c=$('#content');
  c.innerHTML=`<div class="section-header"><h1 class="section-title">Spam Filter (SpamAssassin)</h1></div>
    <div class="card mb-24"><div class="card-header"><span class="card-title">Status</span></div>
      <div id="spamStatus">Loading...</div>
      <div class="mt-16"><button class="btn btn-success" id="spamEnableBtn">Enable</button> <button class="btn btn-danger" id="spamDisableBtn">Disable</button></div>
    </div>
    <div class="card mb-24"><div class="card-header"><span class="card-title">Add Rule</span></div>
      <div class="form-group"><label>Rule</label><input class="form-control" id="spamRule" placeholder="header MY_RULE X-Spam-Status: Yes"></div>
      <div class="form-group"><label>Action</label><select class="form-control" id="spamAction"><option value="reject">Reject</option><option value="flag">Flag</option><option value="discard">Discard</option></select></div>
      <div class="form-group"><label>Description</label><input class="form-control" id="spamDesc" placeholder="Custom spam rule"></div>
      <button class="btn btn-primary" id="addSpamRuleBtn">Add Rule</button>
    </div>
    <div class="card"><div class="card-header"><span class="card-title">Rules</span></div><div class="table-wrap"><table><thead><tr><th>Rule</th><th>Action</th><th>Description</th><th>Actions</th></tr></thead><tbody id="spamRules"></tbody></table></div></div>`;
  try{
    const d=await api('/spam/status');
    if(d){
      $('#spamStatus').innerHTML=`<div><strong>Enabled:</strong> <span class="badge ${d.enabled?'badge-success':'badge-neutral'}">${d.enabled?'Yes':'No'}</span></div><div><strong>SpamAssassin:</strong> ${d.spamassassin_installed?'Installed':'Not installed'}</div>`;
    }
  }catch(e){$('#spamStatus').innerHTML='Failed to load status';}
  $('#spamEnableBtn').onclick=async()=>{try{await api('/spam/enable',{method:'POST'});toast('Spam filter enabled','success');loadSpam();}catch(e){toast(e.message,'danger');}};
  $('#spamDisableBtn').onclick=async()=>{try{await api('/spam/disable',{method:'POST'});toast('Spam filter disabled','success');loadSpam();}catch(e){toast(e.message,'danger');}};
  $('#addSpamRuleBtn').onclick=async()=>{
    const rule=$('#spamRule').value.trim(),desc=$('#spamDesc').value.trim();
    if(!rule){toast('Enter a rule','warning');return;}
    try{await api('/spam/rules',{method:'POST',body:JSON.stringify({rule,action:$('#spamAction').value,description:desc})});toast('Rule added','success');$('#spamRule').value='';$('#spamDesc').value='';loadSpamRules();}catch(e){toast(e.message,'danger');}
  };
  loadSpamRules();
}
async function loadSpamRules(){
  try{
    const d=await api('/spam/rules');
    const rules=objToArray(d&&d.rules);
    const tb=$('#spamRules');
    if(tb&&rules.length){
      tb.innerHTML=rules.map(r=>`<tr><td class="font-mono text-sm">${r.rule}</td><td><span class="badge badge-warning">${r.action}</span></td><td class="truncate" style="max-width:200px">${r.description||'--'}</td><td><button class="btn btn-sm btn-danger" onclick="deleteSpamRule(${r.id})">Delete</button></td></tr>`).join('');
    }else if(tb){tb.innerHTML='<tr><td colspan="4"><div class="empty-state"><p>No spam rules</p></div></td></tr>';}
  }catch(e){}
}
window.deleteSpamRule=function(id){confirmAction('Delete this rule?',async()=>{try{await api('/spam/rules/'+id,{method:'DELETE'});toast('Deleted','success');loadSpamRules();}catch(e){toast(e.message,'danger');}});};

// ── Docker ────────────────────────────────────────────────────────────
async function loadDocker(){
  const c=$('#content');
  c.innerHTML=`<div class="section-header"><h1 class="section-title">Docker</h1></div>
    <div class="tabs"><button class="tab active" data-dtab="containers">Containers</button><button class="tab" data-dtab="images">Images</button><button class="tab" data-dtab="compose">Compose</button></div>
    <div id="dockerTabContent"></div>`;
  $$('.tab[data-dtab]').forEach(t=>t.onclick=function(){
    $$('.tab[data-dtab]').forEach(x=>x.classList.remove('active'));
    this.classList.add('active');
    renderDockerTab(this.dataset.dtab);
  });
  renderDockerTab('containers');
}
async function renderDockerTab(tab){
  const el=$('#dockerTabContent');
  if(tab==='containers'){
    el.innerHTML=`<div class="card"><div class="table-wrap"><table><thead><tr><th>ID</th><th>Name</th><th>Image</th><th>State</th><th>Actions</th></tr></thead><tbody id="dockerContainers"></tbody></table></div></div>`;
    try{
      const d=await api('/docker/containers');
      const items=objToArray(d&&d.containers);
      const tb=$('#dockerContainers');
      if(items.length){
        tb.innerHTML=items.map(ct=>`<tr><td class="font-mono text-sm">${(ct.id||'').substring(0,12)}</td><td>${ct.name}</td><td class="text-sm">${ct.image}</td><td><span class="badge ${ct.state==='running'?'badge-success':'badge-neutral'}">${ct.state}</span></td><td>
          ${ct.state!=='running'?`<button class="btn btn-sm btn-success" onclick="dockerAction('${ct.id}','start')">Start</button>`:`<button class="btn btn-sm btn-warning" onclick="dockerAction('${ct.id}','stop')">Stop</button> <button class="btn btn-sm btn-ghost" onclick="dockerAction('${ct.id}','restart')">Restart</button>`}
          <button class="btn btn-sm btn-ghost" onclick="dockerLogs('${ct.id}')">Logs</button>
          <button class="btn btn-sm btn-danger" onclick="dockerRemove('${ct.id}')">Remove</button></td></tr>`).join('');
      }else{tb.innerHTML='<tr><td colspan="5"><div class="empty-state"><div class="icon">&#128230;</div><h3>No containers</h3></div></td></tr>';}
    }catch(e){$('#dockerContainers').innerHTML='<tr><td colspan="5" class="text-muted text-center">Failed to load containers</td></tr>';}
  }else if(tab==='images'){
    el.innerHTML=`<div class="card mb-16"><div class="form-row"><div class="form-group"><label>Pull Image</label><input class="form-control" id="dockerPullImg" placeholder="nginx:latest"></div><div class="form-group" style="display:flex;align-items:flex-end"><button class="btn btn-primary" id="dockerPullBtn">Pull</button></div></div></div>
      <div class="card"><div class="table-wrap"><table><thead><tr><th>Repository</th><th>Tag</th><th>Size</th><th>Created</th></tr></thead><tbody id="dockerImages"></tbody></table></div></div>`;
    $('#dockerPullBtn').onclick=async()=>{
      const img=$('#dockerPullImg').value.trim();if(!img){toast('Enter image name','warning');return;}
      try{await api('/docker/pull',{method:'POST',body:JSON.stringify({image:img})});toast('Pulling image...','info');}catch(e){toast(e.message,'danger');}
    };
    try{
      const d=await api('/docker/images');
      const items=objToArray(d&&d.images);
      const tb=$('#dockerImages');
      if(items.length){
        tb.innerHTML=items.map(i=>`<tr><td class="font-mono text-sm">${i.repository}</td><td>${i.tag}</td><td>${i.size}</td><td>${i.created}</td></tr>`).join('');
      }else{tb.innerHTML='<tr><td colspan="4"><div class="empty-state"><p>No images</p></div></td></tr>';}
    }catch(e){$('#dockerImages').innerHTML='<tr><td colspan="4" class="text-muted text-center">Failed to load images</td></tr>';}
  }else if(tab==='compose'){
    el.innerHTML=`<div class="card"><div class="table-wrap"><table><thead><tr><th>Name</th><th>Status</th><th>Config</th><th>Actions</th></tr></thead><tbody id="dockerCompose"></tbody></table></div></div>`;
    try{
      const d=await api('/docker/compose');
      const items=objToArray(d&&d.projects);
      const tb=$('#dockerCompose');
      if(items.length){
        tb.innerHTML=items.map(p=>`<tr><td>${p.Name||p.name||'--'}</td><td><span class="badge badge-success">${p.Status||'--'}</span></td><td class="text-sm">${p.ConfigFiles||'--'}</td><td><button class="btn btn-sm btn-warning" onclick="composeDown('${p.Name||p.name}')">Down</button> <button class="btn btn-sm btn-success" onclick="composeUp('${p.Name||p.name}')">Up</button></td></tr>`).join('');
      }else{tb.innerHTML='<tr><td colspan="4"><div class="empty-state"><p>No compose projects</p></div></td></tr>';}
    }catch(e){$('#dockerCompose').innerHTML='<tr><td colspan="4" class="text-muted text-center">Failed to load</td></tr>';}
  }
}
window.dockerAction=function(id,action){confirmAction(action.charAt(0).toUpperCase()+action.slice(1)+' container?',async()=>{try{await api('/docker/containers/'+id+'/'+action,{method:'POST'});toast('Done','success');renderDockerTab('containers');}catch(e){toast(e.message,'danger');}});};
window.dockerRemove=function(id){confirmAction('Remove container?',async()=>{try{await api('/docker/containers/'+id,{method:'DELETE'});toast('Removed','success');renderDockerTab('containers');}catch(e){toast(e.message,'danger');}});};
window.dockerLogs=async function(id){try{const d=await api('/docker/containers/'+id+'/logs?lines=100');showModal('Container Logs','<div class="log-viewer" style="max-height:400px">'+(d.logs||'').split('\n').map(l=>'<div>'+l+'</div>').join('')+'</div>','<button class="btn btn-ghost" onclick="hideModal()">Close</button>');}catch(e){toast(e.message,'danger');}};
window.composeUp=async function(name){try{await api('/docker/compose/up',{method:'POST',body:JSON.stringify({path:name})});toast('Compose up','success');}catch(e){toast(e.message,'danger');}};
window.composeDown=async function(name){try{await api('/docker/compose/down',{method:'POST',body:JSON.stringify({path:name})});toast('Compose down','success');}catch(e){toast(e.message,'danger');}};

// ── Node.js Apps ──────────────────────────────────────────────────────
async function loadNodeApps(){
  const c=$('#content');
  c.innerHTML=`<div class="section-header"><h1 class="section-title">Node.js Apps</h1><button class="btn btn-primary" id="addNodeBtn">+ Add App</button></div><div class="card"><div class="table-wrap"><table><thead><tr><th>Name</th><th>Path</th><th>Port</th><th>Status</th><th>Actions</th></tr></thead><tbody id="nodeList"></tbody></table></div></div>`;
  $('#addNodeBtn').onclick=()=>showAddNode();
  try{
    const d=await api('/nodeapps');
    const apps=objToArray(d&&d.apps);
    const tb=$('#nodeList');
    if(apps.length){
      tb.innerHTML=apps.map(a=>`<tr><td class="font-mono text-sm">${a.name}</td><td class="text-sm truncate" style="max-width:200px">${a.repo_path}</td><td>${a.port||'--'}</td><td><span class="badge ${a.status==='running'?'badge-success':'badge-neutral'}">${a.status||'stopped'}</span></td><td>
        ${a.status!=='running'?`<button class="btn btn-sm btn-success" onclick="nodeAction('${a.name}','start')">Start</button>`:`<button class="btn btn-sm btn-warning" onclick="nodeAction('${a.name}','stop')">Stop</button>`}
        <button class="btn btn-sm btn-ghost" onclick="nodeLogs('${a.name}')">Logs</button>
        <button class="btn btn-sm btn-danger" onclick="nodeDelete('${a.name}')">Delete</button></td></tr>`).join('');
    }else{tb.innerHTML='<tr><td colspan="5"><div class="empty-state"><div class="icon">&#128187;</div><h3>No Node.js apps</h3><p>Deploy your first Node.js application</p></div></td></tr>';}
  }catch(e){$('#nodeList').innerHTML='<tr><td colspan="5" class="text-muted text-center">Failed to load apps</td></tr>';}
}
function showAddNode(){
  showModal('Add Node.js App',
    `<div class="form-group"><label>App Name</label><input class="form-control" id="nodeName" placeholder="myapp"></div>
     <div class="form-group"><label>Repository Path</label><input class="form-control" id="nodePath" placeholder="/var/www/myapp"></div>
     <div class="form-group"><label>Port</label><input class="form-control" id="nodePort" type="number" placeholder="3000"></div>
     <div class="form-group"><label>Node Version</label><input class="form-control" id="nodeVer" placeholder="18"></div>`,
    `<button class="btn btn-ghost" onclick="hideModal()">Cancel</button><button class="btn btn-primary" id="createNodeBtn">Create</button>`);
  $('#createNodeBtn').onclick=async()=>{
    const name=$('#nodeName').value.trim(),path=$('#nodePath').value.trim();
    if(!name||!path){toast('Fill required fields','warning');return;}
    try{await api('/nodeapps',{method:'POST',body:JSON.stringify({name,repo_path:path,port:parseInt($('#nodePort').value)||null,node_version:$('#nodeVer').value.trim()||null})});hideModal();toast('App created','success');loadNodeApps();}catch(e){toast(e.message,'danger');}
  };
}
window.nodeAction=function(name,action){confirmAction(action.charAt(0).toUpperCase()+action.slice(1)+' app '+name+'?',async()=>{try{await api('/nodeapps/'+name+'/'+action,{method:'POST'});toast('Done','success');loadNodeApps();}catch(e){toast(e.message,'danger');}});};
window.nodeDelete=function(name){confirmAction('Delete app '+name+'?',async()=>{try{await api('/nodeapps/'+name,{method:'DELETE'});toast('Deleted','success');loadNodeApps();}catch(e){toast(e.message,'danger');}});};
window.nodeLogs=async function(name){try{const d=await api('/nodeapps/'+name+'/logs?lines=100');showModal('App Logs: '+name,'<div class="log-viewer" style="max-height:400px">'+(d.logs||'').split('\n').map(l=>'<div>'+l+'</div>').join('')+'</div>','<button class="btn btn-ghost" onclick="hideModal()">Close</button>');}catch(e){toast(e.message,'danger');}};

// ── Python Apps ───────────────────────────────────────────────────────
async function loadPythonApps(){
  const c=$('#content');
  c.innerHTML=`<div class="section-header"><h1 class="section-title">Python Apps</h1><button class="btn btn-primary" id="addPyBtn">+ Add App</button></div><div class="card"><div class="table-wrap"><table><thead><tr><th>Name</th><th>Path</th><th>Port</th><th>Status</th><th>Actions</th></tr></thead><tbody id="pyList"></tbody></table></div></div>`;
  $('#addPyBtn').onclick=()=>showAddPy();
  try{
    const d=await api('/pythonapps');
    const apps=objToArray(d&&d.apps);
    const tb=$('#pyList');
    if(apps.length){
      tb.innerHTML=apps.map(a=>`<tr><td class="font-mono text-sm">${a.name}</td><td class="text-sm truncate" style="max-width:200px">${a.repo_path}</td><td>${a.port||'--'}</td><td><span class="badge ${a.status==='running'?'badge-success':'badge-neutral'}">${a.status||'stopped'}</span></td><td>
        ${a.status!=='running'?`<button class="btn btn-sm btn-success" onclick="pyAction('${a.name}','start')">Start</button>`:`<button class="btn btn-sm btn-warning" onclick="pyAction('${a.name}','stop')">Stop</button>`}
        <button class="btn btn-sm btn-ghost" onclick="pyLogs('${a.name}')">Logs</button>
        <button class="btn btn-sm btn-danger" onclick="pyDelete('${a.name}')">Delete</button></td></tr>`).join('');
    }else{tb.innerHTML='<tr><td colspan="5"><div class="empty-state"><div class="icon">&#128013;</div><h3>No Python apps</h3><p>Deploy your first Python application</p></div></td></tr>';}
  }catch(e){$('#pyList').innerHTML='<tr><td colspan="5" class="text-muted text-center">Failed to load apps</td></tr>';}
}
function showAddPy(){
  showModal('Add Python App',
    `<div class="form-group"><label>App Name</label><input class="form-control" id="pyName" placeholder="myapp"></div>
     <div class="form-group"><label>Repository Path</label><input class="form-control" id="pyPath" placeholder="/var/www/myapp"></div>
     <div class="form-group"><label>Port</label><input class="form-control" id="pyPort" type="number" value="8000"></div>
     <div class="form-group"><label>WSGI App</label><input class="form-control" id="pyWsgi" value="app:app"></div>`,
    `<button class="btn btn-ghost" onclick="hideModal()">Cancel</button><button class="btn btn-primary" id="createPyBtn">Create</button>`);
  $('#createPyBtn').onclick=async()=>{
    const name=$('#pyName').value.trim(),path=$('#pyPath').value.trim();
    if(!name||!path){toast('Fill required fields','warning');return;}
    try{await api('/pythonapps',{method:'POST',body:JSON.stringify({name,repo_path:path,port:parseInt($('#pyPort').value)||8000,wsgi_app:$('#pyWsgi').value.trim()||'app:app'})});hideModal();toast('App created','success');loadPythonApps();}catch(e){toast(e.message,'danger');}
  };
}
window.pyAction=function(name,action){confirmAction(action.charAt(0).toUpperCase()+action.slice(1)+' app '+name+'?',async()=>{try{await api('/pythonapps/'+name+'/'+action,{method:'POST'});toast('Done','success');loadPythonApps();}catch(e){toast(e.message,'danger');}});};
window.pyDelete=function(name){confirmAction('Delete app '+name+'?',async()=>{try{await api('/pythonapps/'+name,{method:'DELETE'});toast('Deleted','success');loadPythonApps();}catch(e){toast(e.message,'danger');}});};
window.pyLogs=async function(name){try{const d=await api('/pythonapps/'+name+'/logs?lines=100');showModal('App Logs: '+name,'<div class="log-viewer" style="max-height:400px">'+(d.logs||'').split('\n').map(l=>'<div>'+l+'</div>').join('')+'</div>','<button class="btn btn-ghost" onclick="hideModal()">Close</button>');}catch(e){toast(e.message,'danger');}};

// ── Audit Log ─────────────────────────────────────────────────────────
async function loadAudit(){
  const c=$('#content');
  c.innerHTML=`<div class="section-header"><h1 class="section-title">Audit Log</h1></div><div class="card"><div class="table-wrap"><table><thead><tr><th>Time</th><th>Action</th><th>User</th><th>Details</th></tr></thead><tbody id="auditList"></tbody></table></div></div>`;
  try{
    const d=await api('/audit/logs?limit=200');
    const logs=objToArray(d&&d.logs);
    const tb=$('#auditList');
    if(logs.length){
      tb.innerHTML=logs.map(l=>`<tr><td class="text-sm">${l.timestamp||'--'}</td><td><span class="badge badge-info">${l.action}</span></td><td>${l.user||'--'}</td><td class="text-sm truncate" style="max-width:300px">${JSON.stringify(l.details||{})}</td></tr>`).join('');
    }else{tb.innerHTML='<tr><td colspan="4"><div class="empty-state"><div class="icon">&#128209;</div><h3>No audit entries</h3></div></td></tr>';}
  }catch(e){$('#auditList').innerHTML='<tr><td colspan="4" class="text-muted text-center">Failed to load audit log</td></tr>';}
}

// ── Sessions ──────────────────────────────────────────────────────────
async function loadSessions(){
  const c=$('#content');
  c.innerHTML=`<div class="section-header"><h1 class="section-title">Active Sessions</h1></div><div class="card"><div class="table-wrap"><table><thead><tr><th>Token</th><th>User</th><th>IP</th><th>Created</th><th>Last Active</th><th>Actions</th></tr></thead><tbody id="sessionList"></tbody></table></div></div>`;
  try{
    const d=await api('/sessions');
    const sessions=objToArray(d&&d.sessions);
    const tb=$('#sessionList');
    if(sessions.length){
      tb.innerHTML=sessions.map(s=>`<tr><td class="font-mono text-sm">${s.token_preview}</td><td>${s.user}</td><td>${s.ip||'--'}</td><td class="text-sm">${s.created_at||'--'}</td><td class="text-sm">${s.last_active||'--'}</td><td><button class="btn btn-sm btn-danger" onclick="revokeSession('${s.token_preview}')">Revoke</button></td></tr>`).join('');
    }else{tb.innerHTML='<tr><td colspan="6"><div class="empty-state"><div class="icon">&#128274;</div><h3>No active sessions</h3></div></td></tr>';}
  }catch(e){$('#sessionList').innerHTML='<tr><td colspan="6" class="text-muted text-center">Failed to load sessions</td></tr>';}
}
window.revokeSession=function(tp){confirmAction('Revoke session '+tp+'?',async()=>{try{await api('/sessions/'+encodeURIComponent(tp),{method:'DELETE'});toast('Revoked','success');loadSessions();}catch(e){toast(e.message,'danger');}});};

// ── Login History ─────────────────────────────────────────────────────
async function loadLoginHistory(){
  const c=$('#content');
  c.innerHTML=`<div class="section-header"><h1 class="section-title">Login History</h1></div><div class="card"><div class="table-wrap"><table><thead><tr><th>Time</th><th>Username</th><th>Result</th><th>IP</th></tr></thead><tbody id="loginHistList"></tbody></table></div></div>`;
  try{
    const d=await api('/loginhistory?limit=100');
    const logs=objToArray(d&&d.history);
    const tb=$('#loginHistList');
    if(logs.length){
      tb.innerHTML=logs.map(l=>`<tr><td class="text-sm">${l.timestamp||'--'}</td><td>${l.username}</td><td><span class="badge ${l.success?'badge-success':'badge-danger'}">${l.success?'Success':'Failed'}</span></td><td>${l.ip||'--'}</td></tr>`).join('');
    }else{tb.innerHTML='<tr><td colspan="4"><div class="empty-state"><div class="icon">&#128209;</div><h3>No login history</h3></div></td></tr>';}
  }catch(e){$('#loginHistList').innerHTML='<tr><td colspan="4" class="text-muted text-center">Failed to load login history</td></tr>';}
}

function updateThemeIcon(theme){
  const btn=$('#themeToggle');
  if(btn)btn.innerHTML=theme==='dark'?'&#9789;':'&#9788;';
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

  // Theme toggle
  const savedTheme=localStorage.getItem('theme')||'dark';
  document.documentElement.setAttribute('data-theme',savedTheme);
  updateThemeIcon(savedTheme);
  $('#themeToggle').onclick=()=>{
    const current=document.documentElement.getAttribute('data-theme');
    const next=current==='dark'?'light':'dark';
    document.documentElement.setAttribute('data-theme',next);
    localStorage.setItem('theme',next);
    updateThemeIcon(next);
  };

  navigate('dashboard');
}

init();
})();

function loadCMSInstaller(){const c=document.getElementById('content');c.innerHTML='<h2>CMS Installer</h2><div id="installer-app"><p>Loading...</p></div>';api('/api/installer/manifest').then(d=>{const apps=d.apps||[];c.innerHTML='<h2>One-Click CMS Installer</h2><div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:16px">'+apps.map(a=>'<div style="border:1px solid var(--border);border-radius:8px;padding:16px;background:var(--bg-card)"><div style="display:flex;align-items:center;gap:12px;margin-bottom:8px"><div style="width:40px;height:40px;border-radius:8px;background:'+a.color+';display:flex;align-items:center;justify-content:center;color:#fff;font-weight:bold">'+a.title[0]+'</div><div><strong>'+a.title+'</strong><br><small style="color:var(--text-muted)">v'+a.version+' | '+a.size_mb+' MB</small></div></div><p style="font-size:13px;color:var(--text-muted);margin:8px 0">'+a.description+'</p><button onclick="installCMS(\''+a.name+'\')" style="padding:6px 16px;background:var(--primary);color:#fff;border:none;border-radius:4px;cursor:pointer">Install</button></div>').join('')+'</div>';api('/api/installer/installed').then(d=>{if(d.installed&&d.installed.length>0){c.innerHTML+='<h3 style="margin-top:24px">Installed Applications</h3><table style="width:100%;border-collapse:collapse"><tr><th style="text-align:left;padding:8px;border-bottom:1px solid var(--border)">CMS</th><th style="text-align:left;padding:8px;border-bottom:1px solid var(--border)">Domain</th><th style="text-align:left;padding:8px;border-bottom:1px solid var(--border)">Admin URL</th><th style="text-align:left;padding:8px;border-bottom:1px solid var(--border)">Installed</th><th style="text-align:left;padding:8px;border-bottom:1px solid var(--border)">Action</th></tr>'+d.installed.map(i=>'<tr><td style="padding:8px">'+i.cms+'</td><td style="padding:8px">'+i.domain+'</td><td style="padding:8px"><a href="'+i.admin_url+'" target="_blank">'+i.admin_url+'</a></td><td style="padding:8px">'+i.installed_at+'</td><td style="padding:8px"><button onclick="uninstallCMS(\''+i.cms+'\',\''+i.domain+'\')" style="color:red;background:none;border:none;cursor:pointer">Uninstall</button></td></tr>').join('')+'</table>'}})})}window.installCMS=function(cms){const domain=prompt('Enter domain (e.g., example.com):');const admin_user=prompt('Admin username:','admin');const admin_email=prompt('Admin email:');const admin_password=prompt('Admin password (leave blank for auto):');const site_title=prompt('Site title:',domain);if(!domain||!admin_email)return;api('/api/installer/install',{method:'POST',body:JSON.stringify({cms:cms,domain:domain,admin_user:admin_user||'admin',admin_email:admin_email,admin_password:admin_password||'',site_title:site_title||domain})}).then(d=>{if(d.admin_url){alert('Installed! Admin: '+d.admin_url+'\nUser: '+(d.admin_user||'admin')+'\nPass: '+(d.admin_password||'see above'));loadCMSInstaller()}else{alert(d.note||'Installed successfully')}}).catch(e=>alert('Error: '+e))};window.uninstallCMS=function(cms,domain){if(!confirm('Uninstall '+cms+' from '+domain+'?'))return;api('/api/installer/uninstall',{method:'POST',body:JSON.stringify({cms:cms,domain:domain})}).then(()=>loadCMSInstaller())};

function loadSecurityAdvisor(){const c=document.getElementById('content');c.innerHTML='<h2>Security Advisor</h2><div id="advisor-score"><p>Loading...</p></div>';api('/api/security-advisor/results').then(d=>{if(!d.score&&d.score!==0){c.innerHTML='<h2>Security Advisor</h2><p>No scan results yet.</p><button onclick="runSecurityScan()" style="padding:8px 16px;background:var(--primary);color:#fff;border:none;border-radius:4px;cursor:pointer">Run Security Scan</button>';return}const grade=d.grade||'N/A';const score=d.score||0;const color=score>=90?'#22c55e':score>=75?'#84cc16':score>=60?'#eab308':score>=40?'#f97316':'#ef4444';c.innerHTML='<h2>Security Advisor</h2><div style="display:flex;gap:24px;margin-bottom:24px"><div style="width:120px;height:120px;border-radius:50%;background:'+color+';display:flex;align-items:center;justify-content:center;font-size:32px;font-weight:bold;color:#fff">'+grade+'</div><div><h3>Score: '+score+'/100</h3><p>Last scan: '+(d.scanned_at||'N/A')+'</p><button onclick="runSecurityScan()" style="padding:6px 16px;background:var(--primary);color:#fff;border:none;border-radius:4px;cursor:pointer">Re-scan</button></div></div><h3>Checks</h3><table style="width:100%;border-collapse:collapse">'+(d.checks||[]).map(ch=>'<tr><td style="padding:8px;border-bottom:1px solid var(--border)"><strong>'+ch.name+'</strong><br><small style="color:var(--text-muted)">'+ch.description+'</small></td><td style="padding:8px;border-bottom:1px solid var(--border)"><span style="color:'+(ch.status==="pass"?'#22c55e':ch.status==="fail"?'#ef4444':ch.status==="warn"?'#eab308':'#6b7280')+';font-weight:bold">'+ch.status.toUpperCase()+'</span></td><td style="padding:8px;border-bottom:1px solid var(--border);font-size:13px">'+ch.details+'</td><td style="padding:8px;border-bottom:1px solid var(--border);font-size:12px;color:var(--text-muted)">'+(ch.fix||'')+'</td></tr>').join('')+'</table>'})}window.runSecurityScan=function(){api('/api/security-advisor/scan',{method:'POST'}).then(()=>loadSecurityAdvisor())};

function loadAntivirus(){const c=document.getElementById('content');c.innerHTML='<h2>Antivirus Scanner</h2><p>Loading...</p>';api('/api/antivirus/status').then(d=>{const s=d;c.innerHTML='<h2>Antivirus (ClamAV)</h2><div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:16px;margin-bottom:24px"><div style="border:1px solid var(--border);border-radius:8px;padding:16px;text-align:center"><div style="font-size:24px;font-weight:bold;color:'+(s.enabled?'#22c55e':'#ef4444')+'">'+(s.enabled?'Active':'Disabled')+'</div><small>Engine: '+s.engine+'</small></div><div style="border:1px solid var(--border);border-radius:8px;padding:16px;text-align:center"><div style="font-size:24px;font-weight:bold">'+(s.stats?.total_scans||0)+'</div><small>Total Scans</small></div><div style="border:1px solid var(--border);border-radius:8px;padding:16px;text-align:center"><div style="font-size:24px;font-weight:bold;color:#ef4444">'+(s.stats?.total_viruses||0)+'</div><small>Viruses Found</small></div></div><div><label><input type="checkbox" '+(s.enabled?'checked':'')+' onchange="toggleAV(this.checked)"> Enable Antivirus Scanning</label></div><h3 style="margin-top:24px">Scan Options</h3><div style="display:flex;gap:8px;flex-wrap:wrap"><button onclick="scanAVPath()" style="padding:6px 12px;background:var(--primary);color:#fff;border:none;border-radius:4px;cursor:pointer">Scan Directory</button><button onclick="updateAVDB()" style="padding:6px 12px;background:var(--secondary);color:#fff;border:none;border-radius:4px;cursor:pointer">Update Virus DB</button></div>'})};window.toggleAV=function(en){api('/api/antivirus/config',{method:'POST',body:JSON.stringify({enabled:en})}).then(()=>loadAntivirus())};window.scanAVPath=function(){const p=prompt('Path to scan:','/var/www');if(p)api('/api/antivirus/scan/directory',{method:'POST',body:JSON.stringify({path:p})}).then(d=>{if(d.clean)alert('No viruses found!');else alert('FOUND '+d.infected_files.length+' infected files!')})};window.updateAVDB=function(){api('/api/antivirus/update-database',{method:'POST'}).then(d=>alert(d.status==='updated'?'Virus DB updated!':'Update failed'))};

function loadReseller(){const c=document.getElementById('content');c.innerHTML='<h2>Reseller Plans</h2><p>Loading...</p>';Promise.all([api('/api/reseller/plans'),api('/api/reseller/users'),api('/api/reseller/summary')]).then(([plans,users,summary])=>{const ps=plans.plans||[];const us=users.users||[];c.innerHTML='<h2>Reseller Management</h2><div style="display:flex;gap:24px;margin-bottom:24px"><div style="border:1px solid var(--border);border-radius:8px;padding:16px;text-align:center"><div style="font-size:24px;font-weight:bold">'+(summary.total_plans||0)+'</div><small>Plans</small></div><div style="border:1px solid var(--border);border-radius:8px;padding:16px;text-align:center"><div style="font-size:24px;font-weight:bold">'+(summary.total_users||0)+'</div><small>Resellers</small></div><div style="border:1px solid var(--border);border-radius:8px;padding:16px;text-align:center"><div style="font-size:24px;font-weight:bold">$'+(summary.monthly_revenue||0).toFixed(2)+'</div><small>Monthly Revenue</small></div></div><h3>Plans</h3><table style="width:100%;border-collapse:collapse;margin-bottom:24px"><tr><th style="text-align:left;padding:8px;border-bottom:2px solid var(--border)">Name</th><th style="text-align:left;padding:8px;border-bottom:2px solid var(--border)">Sites</th><th style="text-align:left;padding:8px;border-bottom:2px solid var(--border)">Email</th><th style="text-align:left;padding:8px;border-bottom:2px solid var(--border)">DBs</th><th style="text-align:left;padding:8px;border-bottom:2px solid var(--border)">Disk</th><th style="text-align:left;padding:8px;border-bottom:2px solid var(--border)">Price</th></tr>'+ps.map(p=>'<tr><td style="padding:8px;border-bottom:1px solid var(--border)">'+p.name+'</td><td style="padding:8px;border-bottom:1px solid var(--border)">'+(p.max_sites===-1?'Unlimited':p.max_sites)+'</td><td style="padding:8px;border-bottom:1px solid var(--border)">'+(p.max_email_accounts===-1?'Unlimited':p.max_email_accounts)+'</td><td style="padding:8px;border-bottom:1px solid var(--border)">'+(p.max_databases===-1?'Unlimited':p.max_databases)+'</td><td style="padding:8px;border-bottom:1px solid var(--border)">'+(p.max_disk_mb===-1?'Unlimited':p.max_disk_mb+'MB')+'</td><td style="padding:8px;border-bottom:1px solid var(--border)">$'+p.price_monthly+'/mo</td></tr>').join('')+'</table><h3>Assigned Users</h3><table style="width:100%;border-collapse:collapse"><tr><th style="text-align:left;padding:8px;border-bottom:2px solid var(--border)">User</th><th style="text-align:left;padding:8px;border-bottom:2px solid var(--border)">Plan</th><th style="text-align:left;padding:8px;border-bottom:2px solid var(--border)">Sites Used</th><th style="text-align:left;padding:8px;border-bottom:2px solid var(--border)">Email Used</th></tr>'+us.map(u=>'<tr><td style="padding:8px;border-bottom:1px solid var(--border)">'+u.username+'</td><td style="padding:8px;border-bottom:1px solid var(--border)">'+u.plan_name+'</td><td style="padding:8px;border-bottom:1px solid var(--border)">'+u.usage.sites+'</td><td style="padding:8px;border-bottom:1px solid var(--border)">'+u.usage.email_accounts+'</td></tr>').join('')+'</table>'})};

function loadAnalytics(){const c=document.getElementById('content');c.innerHTML='<h2>Usage Analytics</h2><p>Loading...</p>';Promise.all([api('/api/analytics/dashboard'),api('/api/analytics/health'),api('/api/analytics/bandwidth')]).then(([dash,health,bandwidth])=>{c.innerHTML='<h2>Usage Analytics</h2><div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:16px;margin-bottom:24px"><div style="border:1px solid var(--border);border-radius:8px;padding:16px;text-align:center"><div style="font-size:24px;font-weight:bold;color:'+(dash.cpu?.percent>80?'#ef4444':'#22c55e')+'">'+dash.cpu?.percent+'%</div><small>CPU Usage</small></div><div style="border:1px solid var(--border);border-radius:8px;padding:16px;text-align:center"><div style="font-size:24px;font-weight:bold;color:'+(dash.memory?.percent>80?'#ef4444':'#22c55e')+'">'+dash.memory?.percent+'%</div><small>Memory ('+dash.memory?.used_mb+'MB / '+dash.memory?.total_mb+'MB)</small></div><div style="border:1px solid var(--border);border-radius:8px;padding:16px;text-align:center"><div style="font-size:24px;font-weight:bold;color:'+(dash.disk?.percent>85?'#ef4444':'#22c55e')+'">'+dash.disk?.percent+'%</div><small>Disk ('+dash.disk?.used_gb+'GB / '+dash.disk?.total_gb+'GB)</small></div><div style="border:1px solid var(--border);border-radius:8px;padding:16px;text-align:center"><div style="font-size:24px;font-weight:bold">'+dash.processes+'</div><small>Processes</small></div></div><h3>System Health</h3><div style="display:flex;align-items:center;gap:16px;margin-bottom:16px"><div style="width:80px;height:80px;border-radius:50%;background:'+(health.score>=90?'#22c55e':health.score>=75?'#84cc16':health.score>=60?'#eab308':'#ef4444')+';display:flex;align-items:center;justify-content:center;font-size:24px;font-weight:bold;color:#fff">'+health.grade+'</div><div><strong>Score: '+health.score+'/100</strong><br><small>'+health.checks?.length+' checks performed</small></div></div><table style="width:100%;border-collapse:collapse">'+(health.checks||[]).map(ch=>'<tr><td style="padding:6px 8px;border-bottom:1px solid var(--border)">'+ch.name+'</td><td style="padding:6px 8px;border-bottom:1px solid var(--border)"><span style="color:'+(ch.status==='healthy'?'#22c55e':ch.status==='warning'?'#eab308':'#ef4444')+'">'+ch.status+'</span></td><td style="padding:6px 8px;border-bottom:1px solid var(--border)">'+ch.message+'</td></tr>').join('')+'</table><h3 style="margin-top:24px">Bandwidth</h3><div style="display:flex;gap:24px"><div style="border:1px solid var(--border);border-radius:8px;padding:16px"><strong>Sent:</strong> '+(bandwidth.total_sent_gb||0)+' GB</div><div style="border:1px solid var(--border);border-radius:8px;padding:16px"><strong>Received:</strong> '+(bandwidth.total_recv_gb||0)+' GB</div></div>'})};
