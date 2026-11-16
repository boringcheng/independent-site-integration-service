# M1-01 店铺垂直切片（自学任务）

> 目标：用最小的一条闭环，把「模型 → 迁移 → 仓储 → 命令 → 测试」串起来。
> 预计 2–4 小时。**不要写队列、不要写 API、不要接真实 SHOPLINE。**

## 为什么从店铺开始

`shops` 是领域根实体：任务、作业、分片、Webhook 事件最终都挂在 `shop_id` 上。
先把"注册一家店铺"跑通，你就有了一条能运行、能验证的最小路径。

## 前置检查

```powershell
cd C:\Users\18767\Desktop\独立站
.\.venv\Scripts\Activate.ps1
docker compose -f docker-compose.dev.yml ps      # ss-mysql / ss-redis 都是 healthy
python scripts/dev.py check                      # 当前应为全绿
```

## 任务分解

### Step 1 · 读现有代码（20 分钟）

按顺序读，边读边回答"它为什么存在"：

- `app/config.py`：配置为什么集中在这里？
- `app/db.py`：为什么隔离级别固定 READ COMMITTED？
- `tests/conftest.py`：测试库从哪来？`REQUIRE_DB` 干什么用？
- `docs/adr/0001-architecture.md`、`0002-testing.md`

产出：无代码，只有一个结论——新增代码应该放在哪一层。

### Step 2 · 回答三个设计问题（30 分钟，写在 PR 描述里）

1. 一条 shop 记录最少需要哪些字段？`status` 为什么需要，能不能不要？
2. 同一店铺重复注册，应该报错还是返回已有记录？为什么？
3. `platform` 用字符串还是枚举？数据库要不要加 CHECK 约束？

**先写出答案，再写代码。** 这三个问题决定了表结构和仓储行为。

### Step 3 · 建模型与迁移

建议结构：

```
app/models/__init__.py     # 导出 Base、Shop
app/models/base.py         # DeclarativeBase
app/models/shop.py         # Shop
alembic/                   # alembic init 生成
alembic/versions/xxxx_create_shops.py
```

要求：

- SQLAlchemy 2.0 写法（`Mapped` / `mapped_column`），不要用旧版 `declarative_base()`；
- `domain` 唯一索引；`platform` 长度够用；`created_at` 语义明确；
- `env.py` 从 `get_settings().database_url` 读连接串，`target_metadata` 指向你的 `Base.metadata`；
- 自动生成后**逐行审查**迁移：唯一索引名、可空、默认值、字符集；
- 在空库上验证：

```powershell
alembic upgrade head
alembic downgrade base
alembic upgrade head
```

自检：`downgrade` 真的能把表删干净吗？

### Step 4 · 仓储层

```
app/repositories/shops.py
```

建议接口（签名可以自己调整）：

```python
def register_shop(session: Session, platform: str, domain: str) -> Shop: ...
def get_by_domain(session: Session, domain: str) -> Shop | None: ...
```

要求：

- **仓储不 commit**，事务由调用方（命令/服务）控制；
- 先查再插，插入时捕获 `IntegrityError`（并发下唯一索引会兜底）；
- 捕获异常要用 `session.begin_nested()`，否则外层事务会被标记为失败；
- 不要在这里写"平台是否合法"之外的业务判断。

### Step 5 · 命令行入口

```
scripts/create_shop.py
```

要求：参数 `--platform`、`--domain`；成功打印 `shop_id / platform / domain / status`；重复执行不报错。

自检：连续执行两次，第二次输出是否和第一次一致？

### Step 6 · 测试

```
tests/test_shops.py
```

至少四个用例：

1. 正常注册，字段落库正确；
2. 重复注册返回同一 `shop_id`，且表里只有一条；
3. 非法 platform 被拒绝（异常类型要明确）；
4. （加分）两个线程同时注册同一 domain：只有一个插入成功，两边最终拿到同一个 id。

注意：测试之间要隔离——用带随机后缀的 domain，别依赖清表顺序。

## 验收标准

```powershell
alembic upgrade head           # 空库可执行
alembic downgrade base         # 可回滚
alembic upgrade head           # 可重复

python scripts/create_shop.py --platform shopline --domain demo.myshopline.com
python scripts/create_shop.py --platform shopline --domain demo.myshopline.com   # 不报错

python scripts/dev.py check    # ruff + mypy + pytest 全绿
```

另外：

- 迁移文件里没有多余/遗漏的索引；
- 仓储函数没有 `commit()`；
- 测试覆盖上面四类场景。

## 提示与坑（不给答案）

- Alembic autogenerate **不等于**正确：它可能漏掉 CHECK、表字符集、索引命名，必须人工看 SQL；
- `IntegrityError` 在 MySQL 里不会让整个事务失效，但 SQLAlchemy 的 Session 需要 `begin_nested()` 才能安全继续；
- `created_at` 用 Python 默认还是 `server_default`，要能说出理由（时钟、批量插入、迁移可读性）；
- 测试并发时，两个线程要用**各自的 Session**，共用一个 Session 测不出竞争；
- 如果 `mypy` 报 `Session` 类型问题，先看 `sqlalchemy.orm.Session` 的泛型用法，别急着 `# type: ignore`。

## 提交要求

```powershell
git switch -c feat/m1-shop-slice
git add ...
git commit -m "feat(shop): 支持 SHOPLINE 店铺幂等注册"
```

一个提交只做这一件事；不要顺手改 README 或 CI。

## 交给我 review 的材料

1. 三个设计问题的答案；
2. `git diff main...HEAD`（或直接说改了哪些文件）；
3. 四条验收命令的输出；
4. 卡住过的地方（怎么想通的，或者还没想通）。

我会按这份清单逐项看：表结构 → 迁移可回滚 → 事务边界 → 并发处理 → 测试质量 → 提交规范。

## 参考资料

- SQLAlchemy 2.0 ORM Quickstart：https://docs.sqlalchemy.org/en/20/orm/quickstart.html
- Alembic Tutorial：https://alembic.sqlalchemy.org/en/latest/tutorial.html
- MySQL 8.4 唯一索引与 NULL：https://dev.mysql.com/doc/refman/8.4/en/create-index.html
