# 本地开发环境配置记录（Windows）

> 最后更新：2026-11-09
> 目标栈：Python 3.12 + PyCharm + Docker Desktop + Git + Node.js LTS
> 开发模式：Windows 本地开发 → ECS 远程部署 → Docker 统一运行环境
> 当前状态：**全部就绪，MySQL / Redis 已在运行**

---

## 1. 机器与系统

| 项目 | 情况 |
| --- | --- |
| 系统 | Windows 11 家庭版 23H2（Build 22631） |
| CPU | Intel Core i5-1135G7，VT-x 已开启 |
| 磁盘 | C: 剩余 283 GB / 374.8 GB；D: 剩余 18.3 GB / 100 GB |
| 当前账户 | `chen\18767`，在 Administrators 组，但日常进程不提权 |
| 系统代理 | `127.0.0.1:10808`（下载 GitHub / 镜像必须走它） |

---

## 2. 工具状态

| 工具 | 版本 | 位置 / 说明 |
| --- | --- | --- |
| Python | **3.12.10** | `%LOCALAPPDATA%\Programs\Python\Python312`，`python` 默认指向它 |
| Python（遗留） | 3.14.5 | 官方安装版，保留但不用 |
| PyCharm | 2026.2.1 | 已预装 |
| Git | **2.56.0** | `C:\Program Files\Git`，已在系统 PATH |
| Node.js | **24.20.0 LTS** | winget 解压版，已进用户 PATH；npm 11.19.0 |
| WSL | **3.0.3**（内核 6.18.54.1） | `C:\Program Files\WSL` |
| Docker Desktop | **4.98.0**（引擎 29.9.2） | 引擎运行中，驱动 overlayfs |
| Docker Compose | v5.6.1 | 随 Docker Desktop 安装 |

---

## 3. 本次实际执行的改动

1. **Python 3.12.10**（用户级）：写入用户 PATH 且排在 WindowsApps 之前，`python` 直接指向 3.12。
2. **Node.js 24.20.0 LTS**（winget）：解压到 WinGet Packages 目录，已加入用户 PATH。
3. **Git 2.56.0**：系统级安装，`C:\Program Files\Git\cmd` 已在系统 PATH。
4. **`PY_PYTHON=3.12`**：`py` 命令默认用 3.12，避免误用 3.14。
5. **PowerShell 执行策略** `CurrentUser=RemoteSigned`：否则 `npm.ps1`、venv 激活脚本会被拦截。
6. **Docker Desktop 4.98.0**：管理员安装，当前用户已加入 `docker-users` 组。
7. **WSL 3.0.3**：管理员安装 MSI（见第 4 节，本次最花时间的一步）。

---

## 4. 踩过的坑：WSL2 内核缺失

重启后 `wsl --status` 报：

```
用于 Linux 的 Windows 子系统内核尚未更新 …… 未找到 WSL 2 内核文件。
```

同时 `Docker Desktop is unable to start`，引擎起不来。
原因：Windows 只启用了 WSL **功能**，而 23H2 自带的是老版 WSL，没有内核文件。

三条路都试过：

| 方案 | 结果 |
| --- | --- |
| `wsl --update` | 卡死（走 Microsoft Store，国内网络不通） |
| `winget install 9P9TQF7MRM4R`（Store 版 WSL） | 卡 10 分钟无流量 |
| **GitHub 下载 WSL 3.0.3 MSI + msiexec 安装** | ✅ 成功 |

关键点：GitHub 直连被墙（`curl: (28)`），**必须加 `--proxy http://127.0.0.1:10808`**，速度约 3 MB/s。
下载地址：`https://github.com/microsoft/WSL/releases/download/3.0.3/wsl.3.0.3.0.x64.msi`（350 MB，注意选 **x64**，不是 arm64）。

安装后 `wsl --version` 正常，重启 Docker Desktop 即恢复。

---

## 5. 已运行的服务

```powershell
docker compose -f docker-compose.dev.yml ps
```

| 容器 | 镜像 | 状态 | 端口 |
| --- | --- | --- | --- |
| ss-mysql | mysql:8.4（8.4.13） | healthy | 3306 |
| ss-redis | redis:7.4-alpine | healthy | 6379 |

已验证：MySQL 字符集 `utf8mb4`，库 `shopify_shopline` 已创建；Redis `PING → PONG`。

连接串：

```
mysql+pymysql://app:app_pass@127.0.0.1:3306/shopify_shopline?charset=utf8mb4
redis://:redis_pass@127.0.0.1:6379/0
```

常用命令：

```powershell
docker compose -f docker-compose.dev.yml up -d      # 启动
docker compose -f docker-compose.dev.yml logs -f    # 看日志
docker compose -f docker-compose.dev.yml down       # 停止（数据保留在 volume）
```

---

## 6. 项目级约定（每个新项目照做）

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r requirements.txt
```

- **PyCharm 解释器**：Settings → Project → Python Interpreter → Add → Existing →
  选 `.venv\Scripts\python.exe`，不要用系统解释器。
- **前端**：`npm install` / `npm run dev`；若团队统一用 pnpm，先 `corepack enable`。
- npm 官方源较慢（实测单次查询 10s），需要时切镜像：
  `npm config set registry https://registry.npmmirror.com`

---

## 7. 还没做的两件小事

1. **Git 身份未配置**：

   ```powershell
   git config --global user.name  "你的名字"
   git config --global user.email "你的邮箱"
   ```

2. **项目 `.venv` 未创建**：等确定项目骨架后再建（现在建了也没依赖可装）。

---

## 8. 一键自检

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\verify-env.ps1
```

当前输出：**0 项不合格**，其余为提示项（未提权、D 盘空间、.venv、git 身份）。
退出码 0 表示环境可用。

---

## 9. 脚本清单

| 脚本 | 用途 |
| --- | --- |
| `scripts\verify-env.ps1` | 只读自检，随时可跑 |
| `scripts\setup-docker-admin.ps1` | 管理员：启用 WSL 功能 + 装 Docker Desktop（已完成，留作迁移服务器参考） |
| `scripts\after-reboot.ps1` | 重启后：起 Docker → 拉镜像 → 起 MySQL/Redis → 报健康状态（已完成） |
