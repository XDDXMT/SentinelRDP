// control/static/ws.js
let socket = io(); // connects to /socket.io
let token = null;
let approvedIPs = new Map(); // 存储已批准的IP和过期时间

function login(){
  let u = document.getElementById("username").value;
  let p = document.getElementById("password").value;
  fetch("/api/login", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({username:u,password:p})})
    .then(r=>r.json()).then(j=>{
      if (j.token){
        token = j.token;
        document.getElementById("login_box").style.display = "none";
        document.getElementById("main").style.display = "block";
        // register web client
        socket.emit("web_register", {});
        // 加载已批准的IP列表
        loadApprovedIPs();
      } else {
        document.getElementById("login_msg").innerText = JSON.stringify(j);
      }
    });
}

// 加载已批准的IP列表
function loadApprovedIPs() {
  // 这里可以添加API调用获取已批准IP列表
  // 暂时从localStorage加载
  const saved = localStorage.getItem('approved_ips');
  if (saved) {
    approvedIPs = new Map(JSON.parse(saved));
    updateApprovedIPsDisplay();
  }
}

// 保存已批准的IP列表
function saveApprovedIPs() {
  localStorage.setItem('approved_ips', JSON.stringify(Array.from(approvedIPs.entries())));
}

// 更新已批准IP显示
function updateApprovedIPsDisplay() {
  const el = document.getElementById("approved_ips");
  if (!el) return;

  el.innerHTML = '';
  approvedIPs.forEach((expireTime, ip) => {
    const remaining = Math.max(0, expireTime - Date.now());
    const hours = Math.floor(remaining / (1000 * 60 * 60));

    const ipEl = document.createElement("div");
    ipEl.className = "ip-item";
    ipEl.innerHTML = `
      <span class="ip-address">${ip}</span>
      <span class="ip-expire">剩余: ${hours}小时</span>
      <button onclick="removeApprovedIP('${ip}')" class="danger small">移除</button>
    `;
    el.appendChild(ipEl);
  });
}

// 移除已批准的IP
function removeApprovedIP(ip) {
  approvedIPs.delete(ip);
  saveApprovedIPs();
  updateApprovedIPsDisplay();
}

socket.on("system", (msg) => {
  if (!msg || !msg.type) return;
  if (msg.type === "agents") renderAgents(msg.list);
  if (msg.type === "pending") renderPending(msg.list);
  if (msg.type === "sessions") renderSessions(msg.list);
});

// render helpers
function renderAgents(list){
  let el = document.getElementById("agents");
  el.innerHTML = "";
  for (const aid in list){
    const item = list[aid];
    let d = document.createElement("div"); d.className="table-row";
    d.innerHTML = `<div><strong>${aid}</strong><br><small>${JSON.stringify(item.info)}</small></div><div>在线</div>`;
    el.appendChild(d);
  }
}

function renderPending(list){
  let el = document.getElementById("pending");
  el.innerHTML = "";
  list.forEach(req=>{
    const isApproved = approvedIPs.has(req.client_ip) && approvedIPs.get(req.client_ip) > Date.now();

    let d = document.createElement("div");
    d.className = `table-row ${isApproved ? 'approved' : ''}`;

    d.innerHTML = `
      <div>
        <strong>${req.agent_id}</strong> →
        <span class="client-ip ${isApproved ? 'approved-ip' : ''}">${req.client_ip}</span>
        <br>
        <small>${new Date(req.ts*1000).toLocaleString()}</small>
        ${isApproved ? '<br><span class="auto-approve-badge">自动批准</span>' : ''}
      </div>
      <div>
        <button onclick='allow("${req.agent_id}","${req.session_id}","${req.client_ip}")'>通过</button>
        <button onclick='allowAndAuto("${req.agent_id}","${req.session_id}","${req.client_ip}")' class="auto-approve">自动批准IP</button>
        <button class="danger" onclick='deny("${req.agent_id}","${req.session_id}")'>拒绝</button>
      </div>
    `;
    el.appendChild(d);
  });
}

function allow(agent, session_id, client_ip){
  fetch("/api/allow", {
    method:"POST",
    headers: {"Content-Type":"application/json", "X-Auth-Token": token},
    body: JSON.stringify({agent_id: agent, session_id: session_id, expire: 86400})
  }).then(response => response.json()).then(data => {
    if (data.ok) {
      showReconnectGuide(client_ip, false);
    }
  });
}

// 自动批准该IP的所有连接（24小时）
function allowAndAuto(agent, session_id, client_ip){
  const expireHours = 24;
  const expireTime = Date.now() + (expireHours * 60 * 60 * 1000);

  // 添加到自动批准列表
  approvedIPs.set(client_ip, expireTime);
  saveApprovedIPs();
  updateApprovedIPsDisplay();

  // 批准当前会话
  fetch("/api/allow", {
    method:"POST",
    headers: {"Content-Type":"application/json", "X-Auth-Token": token},
    body: JSON.stringify({agent_id: agent, session_id: session_id, expire: 86400})
  }).then(response => response.json()).then(data => {
    if (data.ok) {
      showReconnectGuide(client_ip, true);

      // 自动批准该IP的其他待处理会话
      autoApproveOtherSessions(client_ip);
    }
  });
}

// 自动批准同一IP的其他会话
function autoApproveOtherSessions(client_ip) {
  const pendingSection = document.getElementById("pending");
  const pendingItems = pendingSection.getElementsByClassName("table-row");

  Array.from(pendingItems).forEach(item => {
    const ipElement = item.querySelector('.client-ip');
    if (ipElement && ipElement.textContent === client_ip) {
      const buttons = item.querySelectorAll('button');
      const approveButton = Array.from(buttons).find(btn => btn.textContent === '通过');

      if (approveButton) {
        // 模拟点击批准按钮
        approveButton.click();
      }
    }
  });
}

function deny(agent, session_id){
  fetch("/api/kick", {
    method:"POST",
    headers: {"Content-Type":"application/json", "X-Auth-Token": token},
    body: JSON.stringify({agent_id: agent, session_id: session_id})
  });
}

function renderSessions(list){
  let el = document.getElementById("sessions");
  el.innerHTML = "";
  for (const agent in list){
    const group = list[agent];
    let head = document.createElement("div"); head.className="card";
    head.innerHTML = `<h4>${agent}</h4>`;
    for (const sid in group){
      const s = group[sid];
      let r = document.createElement("div"); r.className="table-row";
      r.innerHTML = `<div><b>${s.client_ip}</b><br><small>${new Date(s.start_time*1000).toLocaleString()}</small></div>
        <div><button onclick='kick("${agent}","${sid}")' class="danger">踢下线</button></div>`;
      head.appendChild(r);
    }
    el.appendChild(head);
  }
}

function kick(agent, session_id){
  fetch("/api/kick", {
    method:"POST",
    headers: {"Content-Type":"application/json", "X-Auth-Token": token},
    body: JSON.stringify({agent_id: agent, session_id: session_id})
  });
}

// 显示重连指导
function showReconnectGuide(client_ip, isAutoApprove) {
  const guideHtml = `
    <div class="reconnect-guide">
      <h3>连接已批准</h3>
      <p>IP地址: <strong>${client_ip}</strong></p>
      ${isAutoApprove ? '<p class="auto-note">✅ 该IP已加入自动批准列表（24小时有效）</p>' : ''}
      <div class="steps">
        <p><strong>请按以下步骤操作：</strong></p>
        <ol>
          <li>让用户断开当前的RDP连接</li>
          <li>等待5-10秒</li>
          <li>让用户重新进行RDP连接</li>
          <li>本次连接将自动成功</li>
        </ol>
      </div>
      <button onclick="closeReconnectGuide()" class="primary">确定</button>
    </div>
  `;

  let guideEl = document.getElementById('reconnectGuide');
  if (!guideEl) {
    guideEl = document.createElement('div');
    guideEl.id = 'reconnectGuide';
    guideEl.className = 'modal-overlay';
    document.body.appendChild(guideEl);
  }

  guideEl.innerHTML = guideHtml;
  guideEl.style.display = 'flex';
}

function closeReconnectGuide() {
  const guideEl = document.getElementById('reconnectGuide');
  if (guideEl) {
    guideEl.style.display = 'none';
  }
}

// 添加键盘事件监听
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') {
    closeReconnectGuide();
  }
});

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
  // 添加样式
  const style = document.createElement('style');
  style.textContent = `
    .approved { background-color: #f0fff0; }
    .approved-ip { color: #28a745; font-weight: bold; }
    .auto-approve-badge {
      background: #28a745;
      color: white;
      padding: 2px 6px;
      border-radius: 3px;
      font-size: 12px;
    }
    .auto-approve { background-color: #28a745; color: white; }
    .modal-overlay {
      position: fixed;
      top: 0; left: 0;
      width: 100%; height: 100%;
      background: rgba(0,0,0,0.5);
      display: none;
      justify-content: center;
      align-items: center;
      z-index: 1000;
    }
    .reconnect-guide {
      background: white;
      padding: 20px;
      border-radius: 8px;
      max-width: 500px;
      margin: 20px;
    }
    .steps {
      background: #f8f9fa;
      padding: 15px;
      border-radius: 5px;
      margin: 15px 0;
    }
    .steps ol { margin: 10px 0; padding-left: 20px; }
    .steps li { margin: 5px 0; }
    .auto-note { color: #28a745; font-weight: bold; }
    .ip-item {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 8px;
      border-bottom: 1px solid #eee;
    }
    .ip-address { font-family: monospace; }
    .ip-expire { color: #666; font-size: 12px; }
    .small { padding: 2px 6px; font-size: 12px; }
  `;
  document.head.appendChild(style);

  // 创建已批准IP显示区域
  const mainEl = document.getElementById('main');
  if (mainEl) {
    const ipSection = document.createElement('div');
    ipSection.className = 'card';
    ipSection.innerHTML = `
      <h3>✅ 已批准的IP地址（24小时有效）</h3>
      <div id="approved_ips"></div>
    `;
    mainEl.insertBefore(ipSection, mainEl.firstChild);
  }
});