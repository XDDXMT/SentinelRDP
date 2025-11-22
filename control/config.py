# control/config.py
import os, json, getpass
import bcrypt

CFG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

DEFAULT = {
    "admin_user": "admin",
    "admin_pass_hash": None
}

def load_config():
    if not os.path.exists(CFG_PATH):
        print("首次运行：请设置管理员密码（bcrypt 哈希）")
        pwd = getpass.getpass("管理员密码: ").strip()
        if not pwd:
            raise SystemExit("密码不能为空")
        ph = bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode()
        DEFAULT["admin_pass_hash"] = ph
        save_config(DEFAULT)
        print(f"配置已写入 {CFG_PATH}")
        return DEFAULT
    with open(CFG_PATH, "r", encoding="utf8") as f:
        return json.load(f)

def save_config(cfg):
    with open(CFG_PATH, "w", encoding="utf8") as f:
        json.dump(cfg, f, indent=2)

if __name__ == "__main__":
    load_config()