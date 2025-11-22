# control/sessions_store.py
# 进程内存存储：agent 列表、待授权队列、会话总表
import time
from threading import Lock

lock = Lock()

agents = {}       # agent_id -> {"sid": socketio_sid, "info": {...}}
pending_auth = [] # list of auth requests dicts: {agent_id, session_id, client_ip, ts}
# sessions_by_agent: agent_id -> session_id -> session_info
sessions_by_agent = {}

def register_agent(agent_id, sid, info=None):
    with lock:
        agents[agent_id] = {"sid": sid, "info": info or {}, "last_seen": time.time()}
        sessions_by_agent.setdefault(agent_id, {})

def unregister_agent_by_sid(sid):
    with lock:
        remove = None
        for aid, v in list(agents.items()):
            if v.get("sid") == sid:
                remove = aid
                break
        if remove:
            agents.pop(remove, None)
            sessions_by_agent.pop(remove, None)

def agent_list():
    with lock:
        return {k: {"info": v["info"], "last_seen": v["last_seen"]} for k,v in agents.items()}

def push_pending(req):
    with lock:
        pending_auth.append(req)

def pop_pending():
    with lock:
        return list(pending_auth)

def remove_pending(agent_id, session_id):
    with lock:
        global pending_auth
        pending_auth = [p for p in pending_auth if not (p["agent_id"]==agent_id and p["session_id"]==session_id)]

def add_session(agent_id, session_id, info):
    with lock:
        sessions_by_agent.setdefault(agent_id, {})
        sessions_by_agent[agent_id][session_id] = info

def get_sessions_all():
    with lock:
        return {aid: dict(s) for aid, s in sessions_by_agent.items()}

def remove_session(agent_id, session_id):
    with lock:
        if agent_id in sessions_by_agent and session_id in sessions_by_agent[agent_id]:
            sessions_by_agent[agent_id].pop(session_id, None)
