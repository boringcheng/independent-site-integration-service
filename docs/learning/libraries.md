# 项目依赖库详解（截至 M0）

> 这份文档回答三个问题：**每个库是干什么的、在我们代码的哪一行、为什么选它。**
> 代码里保持干净，注解集中在这里；读完你应该能对着 `app/config.py`、`app/db.py`、
> `tests/conftest.py` 逐行讲出每一行在做什么。

## 0. 先分清三类东西

| 概念 | 例子 | 说明 |
| --- | --- | --- |
| 库（library） | SQLAlchemy、PyMySQL | 你调用它 |
| 框架（framework） | FastAPI、pytest | 它调用你（控制反转） |
| 工具（tool） | ruff、mypy | 不参与运行时，只在开发/CI 阶段跑 |

依赖又分两种：

- **运行时依赖**（`requirements.txt`）：应用启动、处理请求时必须有；
- **开发依赖**（`requirements-dev.txt`）：测试、检查、格式化用，生产环境不需要。

`requirements.lock` 是**锁文件**：把当前验证过的 69 个包（含间接依赖）版本全部钉死，
保证你、CI、未来部署环境装出来的东西完全一致。直接写的只有 15 个，其余都是被依赖带进来的。

## 1. 总表

| 库 | 版本 | 类别 | 在本项目中的角色 | 现在用到了吗 |
| --- | --- | --- | --- | --- |
| pydantic-settings | 2.16.2 | 运行时 | 读 `.env` / 环境变量，产出类型安全的 `Settings` | ✅ `app/config.py` |
| pydantic | 2.14.3 | 运行时 | 上面的底座，做数据校验 | ✅ 间接 |
| SQLAlchemy | 2.1.8 | 运行时 | ORM + 连接池 + 事务 | ✅ `app/db.py` |
| PyMySQL | 1.2.4 | 运行时 | MySQL 驱动（URL 里的 `+pymysql`） | ✅ 间接 |
| cryptography | 50.0.2 | 运行时 | MySQL 8 默认认证插件需要它 | ✅ 间接 |
| python-dotenv | 1.2.4 | 运行时 | 解析 `.env` 文件 | ✅ 间接 |
| pytest | 9.2.0 | 开发 | 测试框架（fixture、标记） | ✅ `tests/` |
| ruff | 0.17.5 | 开发 | lint + 格式化（一个工具顶三个） | ✅ CI / `dev.py` |
| mypy | 2.4.1 | 开发 | 静态类型检查 | ✅ CI / `dev.py` |
| pytest-cov | 7.1.0 | 开发 | 覆盖率统计 | ⚙️ 已配置未启用 |
| alembic | 1.20.1 | 运行时 | 数据库迁移（M1 接入） | ⏳ 未使用 |
| fastapi | 0.162.5 | 运行时 | Webhook / 管理 API（M3） | ⏳ 未使用 |
| starlette | 1.10.0 | 运行时 | FastAPI 的 ASGI 底座 | ⏳ 间接 |
| uvicorn | 0.54.0 | 运行时 | 跑 ASGI 应用的服务器 | ⏳ 未使用 |
| celery | 5.7.0 | 运行时 | 异步触发层（M4，可选） | ⏳ 未使用 |
| redis | 8.1.0 | 运行时 | Celery 的 broker / 缓存 | ⏳ 未使用 |
| httpx | 0.28.1 | 运行时 | HTTP 客户端；`TestClient` 底层 | ⏳ 未使用 |
| pre-commit | 4.7.0 | 开发 | 提交前自动跑检查 | ⏳ 钩子暂未装 |

## 2. 这些库在架构里的位置

```
              ┌──────────────┐
   HTTP 请求 → │   uvicorn    │  ASGI 服务器（M3）
              │   fastapi    │  路由 / 参数校验
              └──────┬───────┘
                     ↓
              ┌──────────────┐
              │  services    │  业务编排（M2 起）
              └──────┬───────┘
                     ↓
              ┌──────────────┐
              │ repositories │  数据访问（M1 起）
              └──────┬───────┘
                     ↓
              ┌──────────────┐
              │  SQLAlchemy  │  ORM / 连接池 / 事务
              └──────┬───────┘
                     ↓
              ┌──────────────┐
              │   PyMySQL    │  驱动（+ cryptography）
              └──────┬───────┘
                     ↓
                   MySQL 8.4

  旁路：alembic 改表结构；celery + redis 触发任务；pytest/ruff/mypy 把关质量
```

## 3. 已使用的库

### 3.1 pydantic-settings —— 配置

**一句话**：把环境变量变成有类型、有默认值、能自动校验的 Python 对象。

**用在哪**：`app/config.py`

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    database_url: str = "mysql+pymysql://..."
    lease_seconds: int = 20
```

`.env` 里写的是 `DATABASE_URL=...`，字段名是 `database_url`——**能对上，是因为它默认大小写不敏感**。
`lease_seconds: int` 会自动把字符串 `"20"` 转成整数，转不了就启动时报错。

**为什么不用 `os.getenv`**：

- 没有类型，`int(os.getenv(...))` 到处散落；
- 没有统一默认值；
- 拼错变量名不会报错，只会拿到 `None`，运行时才炸。

**常见坑**：

- `extra="ignore"` 让 `.env` 里那些不认识的变量（如 `MYSQL_ROOT_PASSWORD`）不报错；
- 改了 `.env` 要重启进程，`@lru_cache` 不会自己刷新；
- 生产环境不要依赖 `.env` 文件，应该用真实环境变量（容器注入）。

**学习优先级**：现在就要懂。

### 3.2 SQLAlchemy —— 数据库访问

**一句话**：Python 里操作数据库的标准工具，管三件事：连接池、事务、对象映射。

**用在哪**：`app/db.py`

```python
create_engine(
    url,
    pool_pre_ping=True,      # 取连接前先探活
    pool_size=10,            # 常驻连接数
    max_overflow=20,         # 高峰期最多再借 20 个
    isolation_level="READ COMMITTED",
)
```

三个关键概念：

1. **Engine**：连接池 + 方言（MySQL 8 怎么说话）。整个进程一个就够，不要每次请求都建；
2. **Session**：一次工作单元，负责事务边界。M1 起每个请求/任务一个；
3. **Dialect**：URL 里的 `mysql+pymysql` 就是在选方言和驱动。

`pool_pre_ping=True` 解决什么：MySQL 有 `wait_timeout`，连接空闲太久会被服务端掐断，
再拿出来用就报 "MySQL server has gone away"。预 ping 会在借出前换掉死连接。

`isolation_level="READ COMMITTED"` 是我们**主动覆盖 MySQL 默认值**的地方，
原因见 `app/db.py` 顶部注释和 ADR-0001，改动必须先改 ADR。

**常见坑**：

- `Session` 不是线程安全的，多线程要各自建；
- 不要在持有事务时做 HTTP 调用或 `sleep`（会把行锁拖到超时）；
- `create_engine` 是惰性的，写错密码要到第一次连接才发现。

**学习优先级**：现在懂 Engine；M1 懂 Session 与事务。

### 3.3 PyMySQL —— MySQL 驱动

**一句话**：真正把 SQL 发给 MySQL 的底层库。

**用在哪**：只出现在连接串 `mysql+pymysql://` 里，代码不直接 import。

SQLAlchemy 负责"怎么组织 SQL"，PyMySQL 负责"怎么在 TCP 上把它发出去、怎么读结果"。
换驱动（比如 `mysqlclient`）只需改 URL 前缀，业务代码不动——这就是方言抽象的价值。

**常见坑**：PyMySQL 是纯 Python 实现，性能略低于 C 驱动，但安装零依赖、跨平台省心。

### 3.4 cryptography —— 为什么装它

MySQL 8 默认认证插件是 `caching_sha2_password`，PyMySQL 实现这个握手需要 `cryptography`。
不装会报：`cryptography package is required for sha256_password or caching_sha2_password auth methods`。

它不是"我们主动用的库"，而是**运行时必需的手脚**。这类依赖最容易被漏掉，
所以锁文件要完整。

### 3.5 pytest —— 测试框架

**一句话**：写测试、组织测试、跑测试。

**用在哪**：`tests/conftest.py`、`tests/test_*.py`

```python
@pytest.fixture(scope="session")
def engine(test_database_url: str) -> Iterator[Engine]:
    ...
    yield eng          # yield 之前 = 准备，之后 = 清理
    eng.dispose()
```

- **fixture**：测试的"准备工作"，可以按函数/类/模块/会话复用；
- **scope="session"**：整个测试会话只建一次连接池，快；
- **yield**：把资源交给测试，测试跑完回来执行清理；
- **marker**：`@pytest.mark.integration` 给测试打标签，CI 可以只跑某类。

`conftest.py` 里的 `pytest.skip` 与 `pytest.fail` 是本项目的一个设计：
本地没数据库就跳过，CI 设 `REQUIRE_DB=1` 就失败——**不允许"假装跑了"**。

**常见坑**：fixture 里 `return` 而不是 `yield`，清理逻辑就不会执行；测试之间共享可变状态会互相污染。

### 3.6 ruff —— lint + 格式化

**一句话**：一个工具同时干 flake8（查错）、isort（排 import）、black（格式化）、pyupgrade（升级语法）的活。

**用在哪**：`pyproject.toml` 的 `[tool.ruff]`，CI 的 Lint / Format check 两步，`scripts/dev.py`。

```toml
select = ["E", "F", "I", "UP", "B", "SIM", "RUF"]
```

| 代号 | 管什么 |
| --- | --- |
| E | 语法/风格错误（未定义变量等） |
| F | Pyflakes：未使用 import、未定义名字 |
| I | import 排序 |
| UP | 用新语法替换旧写法 |
| B | 常见 bug 模式（可变默认参数、`except` 裸抓） |
| SIM | 可以简化的代码 |
| RUF | ruff 自己的规则 |

我们关了 `RUF001/002/003`（全角标点告警），因为项目以中文注释为主。

**为什么重要**：风格争论交给工具，review 只讨论设计。

### 3.7 mypy —— 静态类型检查

**一句话**：不运行代码，靠类型标注找出"这里可能传错东西"。

**用在哪**：`pyproject.toml` 的 `[tool.mypy]`，CI 的 Type check。

```toml
strict = true
files = ["app"]
plugins = ["pydantic.mypy"]
```

- `strict`：函数必须有类型标注、禁止隐式 `Any`；
- `files = ["app"]`：只严格检查应用代码，测试代码先放过（fixture 的类型很绕，收益低）；
- `pydantic.mypy`：让 mypy 理解 Pydantic 模型，否则 `Settings()` 会被误报。

**常见坑**：`# type: ignore` 是止痛药不是解药，能改类型就别忽略；第三方库没类型时要装 `types-*` 包或用 `ignore_missing_imports`。

### 3.8 pytest-cov —— 覆盖率

**一句话**：统计测试跑到了哪些行、哪些分支。

**用在哪**：`pyproject.toml` 的 `[tool.coverage.*]`，目前配置了就绪，还没在 `dev.py` 里默认开启。

```powershell
python -m pytest --cov=app --cov-report=term-missing
```

**提醒**：覆盖率是"没被测到的代码"的指示器，不是 KPI。100% 覆盖率也可能全是无效断言。

### 3.9 python-dotenv —— `.env` 解析

**一句话**：把 `.env` 文件的 `KEY=VALUE` 读进环境变量。

我们没直接 import 它，是 **pydantic-settings 在 `env_file=".env"` 时用它**。
所以它出现在锁文件里，但代码里看不到。

## 4. 已安装、按里程碑才会用的库

### 4.1 alembic（M1）

数据库迁移工具，和 SQLAlchemy 同源。核心概念：

- `alembic revision --autogenerate`：对比模型和数据库，生成迁移脚本；
- `alembic upgrade head` / `downgrade base`：前进/回退；
- `alembic_version` 表：记录当前数据库版本。

**autogenerate 不是全自动**：索引命名、字符集、CHECK 约束经常要手改。
M1 会实际用它建 `shops` 表。

### 4.2 fastapi + starlette + uvicorn（M3）

- **FastAPI**：写 HTTP 接口的框架，靠类型标注自动做参数校验和文档；
- **Starlette**：它底下的 ASGI 工具箱（路由、请求响应）；
- **uvicorn**：真正监听端口的服务器，`uvicorn app.api:app --reload`。

三者关系：uvicorn 跑 starlette，starlette 承载 fastapi 的路由。
M3 用它们接 Webhook。

### 4.3 celery + redis（M4，可选）

- **Celery**：分布式任务队列，负责"把任务丢给别的进程去跑"；
- **Redis**：内存存储，这里当 Celery 的 broker（消息中转）。

**注意本项目的立场**：任务的顺序与状态**不由 Celery 保证**，权威源是 MySQL 队列。
Celery 只做"触发器"，这样即使 Celery 丢消息，数据库里的任务仍在，Beat 扫描能补。
这个取舍写在 ADR-0001。

### 4.4 httpx（M3）

同步/异步 HTTP 客户端。两个用途：

1. FastAPI 的 `TestClient` 底层就是 httpx，测试接口时用；
2. 未来写真实平台客户端时，可以用它发请求（替代 `requests`，支持 async）。

## 5. 代码里用到的标准库（不是第三方）

| 模块 | 用在哪 | 作用 |
| --- | --- | --- |
| `functools.lru_cache` | `app/config.py` | 缓存 `Settings()`，全进程只构造一次 |
| `os` | `tests/conftest.py` | 读 `TEST_DATABASE_URL`、`REQUIRE_DB` |
| `collections.abc.Iterator` | `tests/conftest.py` | 给 fixture 的 `yield` 标注类型 |
| `argparse` | `scripts/dev.py` | 解析命令行子命令 |
| `subprocess` | `scripts/dev.py` | 调 ruff / mypy / pytest |
| `shutil` | `scripts/dev.py` | 找 `docker` 可执行文件 |
| `pathlib` | `scripts/dev.py` | 定位项目根目录 |
| `sys` | `scripts/dev.py` | 当前 Python、`sys.exit` |

## 6. 逐行读 `app/config.py`

```python
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
```

- `BaseSettings`：pydantic 的"会读环境变量"的模型基类；
- `SettingsConfigDict`：配置项的类型化写法（比传 dict 更容易被 mypy 检查）。

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",            # 本地开发从 .env 读
        env_file_encoding="utf-8",  # 中文注释/值不出乱码
        extra="ignore",             # .env 里无关变量不报错
    )
```

```python
    database_url: str = "mysql+pymysql://..."
```

字段名 = 环境变量名（大小写不敏感），默认值让"没配也能跑本地"。

```python
@lru_cache
def get_settings() -> Settings:
    return Settings()
```

第一次调用构造并缓存；后续调用直接返回同一个对象。好处是配置只解析一次，
坏处是改了环境变量不会生效（测试里要清缓存）。

**这里没有 import 的库**：`os`。因为读环境变量这件事被 pydantic-settings 接管了。

## 7. 逐行读 `app/db.py`

```python
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
```

- `create_engine`：建连接池 + 选方言；
- `text`：把原生 SQL 包成可执行对象（`SELECT 1` 用）；
- `Engine`：只是类型标注，方便 mypy。

```python
def build_engine(url: str | None = None, *, pool_size: int = 10) -> Engine:
    return create_engine(
        url or get_settings().database_url,
```

`url or ...`：测试可以传自己的库，生产用配置里的。

```python
        pool_pre_ping=True,
        pool_size=pool_size,
        max_overflow=pool_size * 2,
```

连接池三件套：探活、常驻、溢出。

```python
        isolation_level="READ COMMITTED",
        future=True,
```

`future=True` 是 SQLAlchemy 1.4 时代的过渡开关，2.x 已默认，保留无害。

```python
def ping(engine: Engine) -> bool:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
```

`with` 结束会自动把连接还给池子（不是关闭 TCP），这就是连接池的意义。

## 8. 逐行读 `tests/conftest.py`

- `DEFAULT_TEST_URL`：本地测试库，和开发库分开，避免测试写脏开发数据；
- `@pytest.fixture(scope="session")`：整个测试会话共享一个 Engine；
- `pytest.fail` vs `pytest.skip`：CI 要失败，本地可跳过；
- `yield eng` 后的 `eng.dispose()`：测试结束释放连接池。

**为什么测试库要单独一个**：测试会建表、插数据、甚至故意制造冲突，
和开发库混用迟早出事。

## 9. 依赖关系（谁把谁带进来）

```
fastapi ──→ starlette ──→ anyio
pydantic-settings ──→ pydantic ──→ pydantic-core（Rust 实现，快）
pydantic-settings ──→ python-dotenv
sqlalchemy ──→ (可选 greenlet)
pymysql ──→ cryptography（MySQL 8 认证）
celery ──→ kombu ──→ amqp / redis
pytest ──→ pluggy / iniconfig
mypy ──→ mypy_extensions / typing_extensions
```

理解这张图的好处：出问题时能判断"这是我们的代码，还是依赖的锅"。

## 10. 建议的学习顺序

1. **现在**：`pydantic-settings`（配置）→ `SQLAlchemy Engine`（连接）→ `pytest fixture`（测试）；
2. **M1**：`SQLAlchemy Session/事务` → `alembic`（迁移）；
3. **M2**：`SELECT ... FOR UPDATE`、隔离级别、死锁（这些是 MySQL 知识，不是库知识）；
4. **M3**：`FastAPI` 路由与依赖注入、`httpx` 测试；
5. **M4**：`Celery` 基本模型（broker/worker/beat），但记住它只是触发器。

## 11. 自测题

1. `.env` 里写 `DATABASE_URL`，为什么字段叫 `database_url` 也能读到？
2. `pool_pre_ping=True` 解决的是哪一类报错？
3. 为什么 `mypy` 只检查 `app/`，不检查 `tests/`？
4. `pytest` fixture 里 `yield` 前后分别发生什么？
5. MySQL 8 为什么需要 `cryptography` 这个看起来无关的包？
6. 我们为什么不让 Celery 负责任务顺序？

能答出 4 个以上，说明 M0 的代码你已经读懂了。
