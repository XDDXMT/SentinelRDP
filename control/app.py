# control/app.py
import os, json, time
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit, send, join_room, leave_room
import bcrypt
from config import load_config
import sessions_store as store

cfg = load_config()

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config['SECRET_KEY'] = os.urandom(24)
socketio = SocketIO(app, cors_allowed_origins="*", ping_timeout=30, ping_interval=10)

# Simple session tokens (in-memory)
tokens = set()

# IP白名单管理
ip_whitelist = {}  # ip -> 过期时间戳


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(force=True)
    username = data.get("username")
    password = data.get("password")
    if username != cfg.get("admin_user"):
        return jsonify({"error": "user"}), 403
    ph = cfg.get("admin_pass_hash")
    if not ph or not bcrypt.checkpw(password.encode(), ph.encode()):
        return jsonify({"error": "pass"}), 403
    import uuid
    t = str(uuid.uuid4())
    tokens.add(t)
    return jsonify({"token": t})


# authenticated decorator (very small)
def require_token(f):
    def wrapper(*a, **kw):
        tok = request.headers.get("X-Auth-Token") or request.args.get("token")
        if not tok or tok not in tokens:
            return jsonify({"error": "unauth"}), 401
        return f(*a, **kw)

    wrapper.__name__ = f.__name__
    return wrapper


@app.route("/api/agents")
@require_token
def api_agents():
    return jsonify(store.agent_list())


@app.route("/api/pending")
@require_token
def api_pending():
    return jsonify(store.pop_pending())


@app.route("/api/sessions")
@require_token
def api_sessions():
    return jsonify(store.get_sessions_all())


@app.route("/api/allow", methods=["POST"])
@require_token
def api_allow():
    data = request.get_json(force=True)
    agent = data.get("agent_id");
    sid = data.get("session_id");
    expire = data.get("expire", 86400)
    client_ip = data.get("client_ip")  # 新增：获取客户端IP

    agents = store.agent_list()
    if agent not in agents:
        return jsonify({"error": "agent offline"}), 404

    # 查找agent的socketio sid
    target_sid = None
    from sessions_store import agents as raw_agents
    if agent in raw_agents:
        target_sid = raw_agents[agent]["sid"]
    if not target_sid:
        return jsonify({"error": "no socket"}), 500

    # 发送授权消息
    socketio.emit("control_message", {"type": "auth_allow", "session_id": sid, "expire": expire}, room=target_sid)
    store.remove_pending(agent, sid)

    # 如果提供了client_ip，添加到白名单
    if client_ip:
        add_to_whitelist(client_ip, expire)

    return jsonify({"ok": True, "whitelisted": bool(client_ip)})


@app.route("/api/auto_allow_ip", methods=["POST"])
@require_token
def api_auto_allow_ip():
    """自动批准特定IP的所有会话"""
    data = request.get_json(force=True)
    client_ip = data.get("client_ip")
    expire = data.get("expire", 86400)  # 默认24小时

    if not client_ip:
        return jsonify({"error": "client_ip required"}), 400

    # 添加到白名单
    add_to_whitelist(client_ip, expire)

    # 自动批准该IP的所有待处理会话
    approved_count = auto_approve_pending_sessions(client_ip)

    return jsonify({
        "ok": True,
        "approved_sessions": approved_count,
        "expire_time": time.time() + expire
    })


@app.route("/api/whitelist", methods=["GET"])
@require_token
def api_get_whitelist():
    """获取当前IP白名单"""
    cleanup_whitelist()  # 先清理过期项
    return jsonify({
        "whitelist": ip_whitelist,
        "count": len(ip_whitelist)
    })


@app.route("/api/whitelist/<ip>", methods=["DELETE"])
@require_token
def api_remove_whitelist(ip):
    """从白名单中移除IP"""
    if ip in ip_whitelist:
        del ip_whitelist[ip]
        return jsonify({"ok": True, "removed": ip})
    return jsonify({"error": "IP not in whitelist"}), 404


@app.route("/api/kick", methods=["POST"])
@require_token
def api_kick():
    data = request.get_json(force=True)
    agent = data.get("agent_id");
    sid = data.get("session_id")
    from sessions_store import agents as raw_agents
    if agent not in raw_agents:
        return jsonify({"error": "agent offline"}), 404
    target_sid = raw_agents[agent]["sid"]
    socketio.emit("control_message", {"type": "terminate_session", "session_id": sid}, room=target_sid)
    # also remove local record
    store.remove_session(agent, sid)
    return jsonify({"ok": True})


def add_to_whitelist(client_ip, expire_seconds):
    """添加IP到白名单"""
    expire_timestamp = time.time() + expire_seconds
    ip_whitelist[client_ip] = expire_timestamp
    print(f"[Whitelist] Added {client_ip}, expires in {expire_seconds}s")


def cleanup_whitelist():
    """清理过期的白名单IP"""
    current_time = time.time()
    expired_ips = [ip for ip, expire in ip_whitelist.items() if expire < current_time]
    for ip in expired_ips:
        del ip_whitelist[ip]
    if expired_ips:
        print(f"[Whitelist] Cleaned up expired IPs: {expired_ips}")


def is_ip_whitelisted(client_ip):
    """检查IP是否在白名单中"""
    cleanup_whitelist()  # 先清理过期项
    return client_ip in ip_whitelist


def auto_approve_pending_sessions(client_ip):
    """自动批准特定IP的所有待处理会话"""
    approved_count = 0
    pending_list = store.get_pending_list()

    for session in pending_list[:]:  # 使用副本遍历，避免修改原列表
        if session.get("client_ip") == client_ip:
            agent_id = session.get("agent_id")
            session_id = session.get("session_id")

            # 查找agent的socketio sid
            target_sid = None
            from sessions_store import agents as raw_agents
            if agent_id in raw_agents:
                target_sid = raw_agents[agent_id]["sid"]

            if target_sid:
                # 自动批准会话
                socketio.emit("control_message", {
                    "type": "auth_allow",
                    "session_id": session_id,
                    "expire": 86400
                }, room=target_sid)

                store.remove_pending(agent_id, session_id)
                approved_count += 1
                print(f"[AutoApprove] Approved session {session_id} for IP {client_ip}")

    return approved_count


# ---------------- SocketIO events ----------------
@socketio.on("agent_register")
def on_agent_register(msg):
    # msg: {"agent_id": "node1", "info": {"host": "..."}}
    agent_id = msg.get("agent_id")
    sid = request.sid
    info = msg.get("info", {})
    # store socket id inside agents for direct room targeting
    store.register_agent(agent_id, sid, info)
    # Keep a mirror in store.agents with socket id saved
    # Also emit agents list to admin web clients
    socketio.emit("system", {"type": "agents", "list": store.agent_list()})
    print(f"[Control] Agent registered: {agent_id} sid={sid}")


@socketio.on("agent_session_update")
def on_agent_session_update(msg):
    # msg: {"agent_id": "...", "sessions": {...}}
    agent_id = msg.get("agent_id")
    sessions = msg.get("sessions", {})
    # update store sessions
    # we expect sessions is session_id -> info dict
    for sid_key, info in sessions.items():
        store.add_session(agent_id, sid_key, info)
    # remove any not present (ensure reflect)
    # For simplicity, overwrite map:
    # (safe approach: remove then add)
    # We'll just rebuild:
    store.sessions_by_agent = getattr(store, "sessions_by_agent", {})
    # broadcast to web clients
    socketio.emit("system", {"type": "sessions", "list": store.get_sessions_all()})


@socketio.on("agent_auth_request")
def on_agent_auth_request(msg):
    # msg: {"agent_id":..., "session_id":..., "client_ip":..., "ts":...}
    client_ip = msg.get("client_ip")

    # 检查IP是否在白名单中
    if client_ip and is_ip_whitelisted(client_ip):
        # 自动批准
        agent_id = msg.get("agent_id")
        session_id = msg.get("session_id")

        print(f"[AutoApprove] Auto-approving session for whitelisted IP: {client_ip}")

        # 查找agent的socketio sid
        target_sid = None
        from sessions_store import agents as raw_agents
        if agent_id in raw_agents:
            target_sid = raw_agents[agent_id]["sid"]

        if target_sid:
            # 自动发送批准消息
            socketio.emit("control_message", {
                "type": "auth_allow",
                "session_id": session_id,
                "expire": 86400
            }, room=target_sid)

            # 记录自动批准日志
            auto_approve_log = {
                "agent_id": agent_id,
                "session_id": session_id,
                "client_ip": client_ip,
                "auto_approved": True,
                "timestamp": time.time()
            }

            # 发送自动批准通知到前端
            socketio.emit("system", {
                "type": "auto_approve",
                "log": auto_approve_log
            })

            print(f"[AutoApprove] Auto-approved session {session_id} for IP {client_ip}")
        else:
            # 如果找不到agent，还是加入待处理列表
            store.push_pending(msg)
    else:
        # 正常流程：加入待处理列表
        store.push_pending(msg)

    # 通知web客户端更新待处理列表
    socketio.emit("system", {"type": "pending", "list": store.pop_pending()})
    print("[Control] Auth request:", msg)


@socketio.on("disconnect")
def on_disconnect():
    sid = request.sid
    store.unregister_agent_by_sid(sid)
    socketio.emit("system", {"type": "agents", "list": store.agent_list()})
    print("[Control] disconnected sid:", sid)


# socketio endpoint for web client (admin UI)
@socketio.on("web_register")
def on_web_register(msg):
    # 发送当前状态
    emit("system", {"type": "agents", "list": store.agent_list()})
    emit("system", {"type": "pending", "list": store.pop_pending()})
    emit("system", {"type": "sessions", "list": store.get_sessions_all()})

    # 发送白名单状态
    cleanup_whitelist()
    emit("system", {
        "type": "whitelist",
        "list": ip_whitelist,
        "count": len(ip_whitelist)
    })


if __name__ == "__main__":
    # run with eventlet for concurrency
    import eventlet
    import eventlet.wsgi

    print("Starting SentinelRDP Control (Flask + SocketIO) with IP Whitelist...")
    print("Features:")
    print("- IP自动批准白名单")
    print("- 自动重连指导")
    print("- 实时会话管理")
    socketio.run(app, host="0.0.0.0", port=1409)