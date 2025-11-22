import socket, threading, time, json, argparse, uuid
import socketio  # python-socketio client
import sys

# 控制端地址（http/ws）
# 例如 ws URL: http://CONTROL_HOST:5000
parser = argparse.ArgumentParser()
parser.add_argument("--control", required=False, default="http://127.0.0.1:1409", help="Control server http/ws URL")
parser.add_argument("--id", required=False, default="mypc", help="Agent ID")
parser.add_argument("--target-port", type=int, default=3389, help="TermService real RDP port")
parser.add_argument("--proxy-port", type=int, default=3390, help="Proxy listen port (external)")
args = parser.parse_args()

CONTROL = args.control
AGENT_ID = args.id
TARGET = ("127.0.0.1", args.target_port)
PROXY_PORT = args.proxy_port

sio = socketio.Client(reconnection=True, logger=False, engineio_logger=False)

# session storage: session_id -> {client_ip, start_time, client_socket, backend_socket}
sessions = {}
authorized = {}  # session_id -> expire_ts
lock = threading.Lock()

def send_agent_register():
    sio.emit("agent_register", {"agent_id": AGENT_ID, "info": {"host": socket.gethostname(), "ip": None}})

@sio.event
def connect():
    print("[Agent] connected to control")
    send_agent_register()

@sio.event
def disconnect():
    print("[Agent] disconnected from control")

@sio.on("control_message")
def on_control_message(msg):
    t = msg.get("type")
    if t == "auth_allow":
        sid = msg.get("session_id")
        expire = int(msg.get("expire", 86400))
        authorized[sid] = time.time() + expire
        print("[Agent] auth allowed", sid)
    elif t == "terminate_session":
        sid = msg.get("session_id")
        print("[Agent] terminate request", sid)
        with lock:
            s = sessions.get(sid)
            if s:
                try:
                    s["client_socket"].close()
                except:
                    pass
                try:
                    s["backend_socket"].close()
                except:
                    pass
                sessions.pop(sid, None)
    else:
        print("[Agent] unknown control message:", msg)

def start_socketio():
    try:
        sio.connect(CONTROL, namespaces=['/'])
    except Exception as e:
        print("socketio connect error:", e)
        time.sleep(3)
        start_socketio()

def handle_client(client_sock, addr):
    client_ip = addr[0]
    session_id = f"{client_ip}-{int(time.time())}-{uuid.uuid4().hex[:6]}"
    # notify control for auth
    sio.emit("agent_auth_request", {
        "agent_id": AGENT_ID,
        "session_id": session_id,
        "client_ip": client_ip,
        "ts": int(time.time())
    })

    # wait for authorization
    wait_start = time.time()
    while True:
        # if authorized for this session
        if session_id in authorized and authorized[session_id] > time.time():
            break
        # if same IP has other authorization (optional)
        for sid, exp in list(authorized.items()):
            # optional policy: if same client_ip has an allowed session, allow new session too
            pass
        # timeout or deny: let's wait up to 60 seconds before drop
        if time.time() - wait_start > 60:
            try:
                client_sock.close()
            except:
                pass
            return
        time.sleep(0.5)

    # connect to real RDP service
    backend = socket.socket()
    try:
        backend.connect(TARGET)
    except Exception as e:
        print("connect to real RDP failed:", e)
        try: client_sock.close()
        except: pass
        return

    with lock:
        sessions[session_id] = {"client_ip": client_ip, "start_time": int(time.time()), "client_socket": client_sock, "backend_socket": backend}
    sio.emit("agent_session_update", {"agent_id": AGENT_ID, "sessions": {session_id: {"client_ip": client_ip, "start_time": int(time.time())}}})

    # forward data
    def pipe(src, dst, sid):
        try:
            while True:
                data = src.recv(4096)
                if not data:
                    break
                dst.sendall(data)
        except Exception:
            pass
        finally:
            try: src.close()
            except: pass
            try: dst.close()
            except: pass
            with lock:
                sessions.pop(sid, None)
            sio.emit("agent_session_update", {"agent_id": AGENT_ID, "sessions": {}})

    threading.Thread(target=pipe, args=(client_sock, backend, session_id), daemon=True).start()
    threading.Thread(target=pipe, args=(backend, client_sock, session_id), daemon=True).start()

def start_proxy():
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", PROXY_PORT))
    srv.listen(100)
    print(f"[Agent] Proxy listening on {PROXY_PORT}, forwarding to {TARGET}")
    while True:
        client, addr = srv.accept()
        threading.Thread(target=handle_client, args=(client, addr), daemon=True).start()

if __name__ == "__main__":
    # start socketio client
    threading.Thread(target=start_socketio, daemon=True).start()
    # start proxy
    start_proxy()
