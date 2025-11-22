# SentinelRDP

SentinelRDP 是一个多节点 **透明 RDP 代理与授权管理系统**，实现对 RDP 连接的实时授权、监控和管理。


## 功能特点

- 🌐 **多节点支持**：可在多台分服上运行 Agent，与主控服务器集中管理
- 🔐 **首次授权机制**：首次访问需管理员通过，授权 IP 一天有效
- 📊 **Web 任务管理器**：实时监控所有 RDP 会话，支持踢人操作
- 🗂 **安全登录**：管理员登录系统，密码经过哈希存储（非明文）
- ⚡ **实时网页通知**：显示新的授权请求、在线会话状态
- 🎨 **美化 Web Dashboard**：清晰可操作的前端界面

## 安装与运行

### 依赖

#### 控制端
```bash
pip install flask flask-sock bcrypt
````
#### 节点端
```bash
pip install python-socketio
````

### 自动配置
使用 `control/config.py` 自动生成管理员密码哈希（或直接运行app.py）
```bash
cd control
python config.py
```

### 启动主控服务器
首次运行可能会让你输入密码并以哈希加密保存到config.json（如果您执行了config.py则不会要求输入密码）
```bash
cd control
python app.py
```

默认监听 **1409 端口**，网页访问：[http://your-server-ip:1409](http://your-server-ip:1409)

### 启动节点

```bash
cd agent
python rdp_proxy.py
```

每台节点会自动连接主控服务器进行授权管理。

## 使用说明

默认用户名为：admin

1. 访问 Web Dashboard 登录后台
2. 首次 RDP 连接请求会显示在 Dashboard
3. 管理员可选择通过或拒绝授权
4. 授权后，该 IP 当天可直接访问 RDP
5. 可在任务管理器中查看所有正在连接会话，并可踢下线

## 节点使用说明

1. 运行 `rdp_proxy.py`
2. 配置 `--control` 参数指向主控服务器（默认为 `http://127.0.0.1:1409`）
3. 配置 `--id` 参数为节点 ID（默认为 `mypc`）
4. 配置 `--target-port` 为 RDP 端口（默认为 3389）
5. 配置 `--proxy-port` 为代理端口（默认为 3390）
6. 代理端口为远程登录的端口，可通过此端口通过2FA后访问 RDP

## 注意事项

* 首次登录时，管理员需手动输入密码
* 在防火墙中开放主控服务器和节点代理端口
* 建议本地关闭原RDP端口，使用代理端口进行连接，否则无法通过授权进行登录

## 安全说明

* 管理员密码经过哈希处理，Web 登录安全
* 授权信息基于客户端 IP

## 许可证

MIT License
