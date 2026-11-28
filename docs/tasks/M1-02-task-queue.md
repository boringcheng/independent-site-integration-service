# M1-02 任务队列切片（`shop_task_queue`）

> 目标：把「任务」落成一张表，并跑通入队与查询。
> 预计 3–5 小时。**不要写 claim / lease / renew，那是 M2。**
> 配套：[M1-01 走查](M1-01-walkthrough.md) · [PR 描述模板](M1-01-pr.md)

## 0. 边界

这一片只做四件事：

- `TaskStatus` 枚举（7 个状态）
- `ShopTaskQueue` 模型 + 约束 + 索引
- 迁移 `0002`（可 upgrade / downgrade）
- `enqueue()` / `list_pending()` 仓储 + 测试

**不做**：领取、租约续期、Fencing、状态流转、Worker、Celery。

## 1. 已确定的四个决策

| 决策 | 结论 | 理由 |
| --- | --- | --- |
| 排序 | 自增 `id` | `created_at` 同毫秒会并列、时钟可能回拨 |
| 租约 | 放队列表 | 一次原子 UPDATE 完成「抢任务 + 拿租约」 |
| status | `StrEnum` + DB CHECK | 枚举管开发体验，CHECK 管数据底线 |
| 外键 | `ON DELETE RESTRICT` | MySQL 8.4 不允许 `CASCADE` 与「依赖外键列的生成列」共存（报 1215）；改 RESTRICT，删店铺前必须先清任务 |

## 2. 前置检查

```powershell
cd C:\Users\18767\Desktop\独立站
git branch --show-current          # 应为 feat/m1-task-queue
docker compose -f docker-compose.dev.yml ps   # mysql healthy
.\.venv\Scripts\python.exe scripts\dev.py check
```

## 3. Step 1 · `app/enums.py`

```python
"""任务状态枚举。数据库里仍然是 VARCHAR + CHECK，枚举只活在 Python 侧。"""
from __future__ import annotations

from enum import StrEnum


class TaskStatus(StrEnum):
    PENDING = "PENDING"        # 等待执行
    RUNNING = "RUNNING"        # 已拿到租约，正在执行
    RETRY_WAIT = "RETRY_WAIT"  # 等待重试（退避中）
    BLOCKED = "BLOCKED"        # 等待分片作业完成
    UNCERTAIN = "UNCERTAIN"    # 结果未知，需与平台对账
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


CLAIMABLE_STATUSES = (TaskStatus.PENDING, TaskStatus.RETRY_WAIT)
TERMINAL_STATUSES = (TaskStatus.SUCCESS, TaskStatus.FAILED)
```

验证：

```powershell
.\.venv\Scripts\python.exe -c "from app.enums import TaskStatus; print(list(TaskStatus))"
```

## 4. Step 2 · `app/models/task.py`

```python
"""店铺级任务队列：一行 = 一个待执行任务，id 即店铺内顺序号。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.enums import TaskStatus
from app.models.base import Base
from app.utils import utcnow

STATUS_VALUES = ", ".join(f"'{s.value}'" for s in TaskStatus)


class ShopTaskQueue(Base):
    __tablename__ = "shop_task_queue"
    __table_args__ = (
        # 同一店铺最多一个 RUNNING：生成列 + 唯一索引，交给数据库保证
        UniqueConstraint("active_shop_id", name="uq_running_shop"),
        CheckConstraint(f"status IN ({STATUS_VALUES})", name="ck_task_status"),
        Index("ix_stq_shop_status_id", "shop_id", "status", "id"),
        Index("ix_stq_status_available", "status", "available_at"),
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_0900_ai_ci"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    shop_id: Mapped[int] = mapped_column(
        BigInteger,
        # 不能用 CASCADE：MySQL 8.4 不允许 CASCADE 与依赖该列的生成列共存
        ForeignKey("shops.id", ondelete="RESTRICT"),
        nullable=False,
    )
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default=TaskStatus.PENDING, nullable=False
    )

    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    available_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    lease_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    run_epoch: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    # RUNNING 时暴露 shop_id，其余状态为 NULL；
    # MySQL 唯一索引允许多个 NULL，所以非 RUNNING 不冲突。
    active_shop_id: Mapped[int | None] = mapped_column(
        BigInteger,
        Computed(
            "(CASE WHEN status = 'RUNNING' THEN shop_id ELSE NULL END)",
            persisted=True,
        ),
        nullable=True,
    )
```

几个容易写错的点：

| 写法 | 注意 |
| --- | --- |
| `payload` 默认值 | 用 `default=dict`，不要 `default={}`（可变对象共享） |
| `shop_id` 索引 | 复合索引 `(shop_id, status, id)` 已覆盖外键列，不要再 `index=True`，否则多一个冗余索引 |
| `status` 默认值 | 可以写 `TaskStatus.PENDING`，因为 `StrEnum` 是 `str` 子类 |
| 生成列表达式 | 必须确定性、只引用本行字段；MySQL 才会接受 |

验证：

```powershell
.\.venv\Scripts\python.exe -c "from app.models import ShopTaskQueue; print([c.name for c in ShopTaskQueue.__table__.columns]); print([c.name for c in ShopTaskQueue.__table__.constraints])"
```

预期能看到 `active_shop_id` 列和 `uq_running_shop`、`ck_task_status`。

## 5. Step 3 · 导出模型

`app/models/__init__.py` 加上：

```python
from app.models.task import ShopTaskQueue

__all__ = ["Base", "Shop", "ShopTaskQueue"]
```

## 6. Step 4 · 生成并审查迁移

```powershell
.\.venv\Scripts\python.exe -m alembic revision --autogenerate -m "create shop_task_queue"
```

**不要直接相信生成结果。** 逐项检查：

- [ ] `create_table` 里有全部 14 个字段，类型、`nullable` 正确；
- [ ] 生成列 `active_shop_id` 是否存在（Alembic 有时会漏）；
- [ ] 唯一约束 `uq_running_shop` 是否存在；
- [ ] CHECK `ck_task_status` 是否存在（**通常没有**）；
- [ ] 两个索引是否存在、名字对不对；
- [ ] `downgrade()` 里有 `op.drop_table("shop_task_queue")`。

缺什么就手动补。示例：

```python
def upgrade() -> None:
    op.create_table(
        "shop_task_queue",
        ...
        sa.Column(
            "active_shop_id",
            sa.BigInteger(),
            sa.Computed("(CASE WHEN status = 'RUNNING' THEN shop_id ELSE NULL END)", persisted=True),
            nullable=True,
        ),
        ...
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_unique_constraint("uq_running_shop", "shop_task_queue", ["active_shop_id"])
    op.create_check_constraint(
        "ck_task_status",
        "shop_task_queue",
        "status IN ('PENDING','RUNNING','RETRY_WAIT','BLOCKED','UNCERTAIN','SUCCESS','FAILED')",
    )
    op.create_index("ix_stq_shop_status_id", "shop_task_queue", ["shop_id", "status", "id"])
    op.create_index("ix_stq_status_available", "shop_task_queue", ["status", "available_at"])
```

> 如果自动生成的 `create_table` 里已经带了约束/索引，就别重复创建，否则迁移会报 `Duplicate key name`。

### 迁移三连

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic downgrade -1
.\.venv\Scripts\python.exe -m alembic upgrade head
```

三次都要 exit 0。

### 看真实表结构

```powershell
docker exec ss-mysql mysql -uapp -papp_pass shopify_shopline -e "SHOW CREATE TABLE shop_task_queue\G"
```

必须看到：

- `GENERATED ALWAYS AS (...) STORED`；
- `UNIQUE KEY uq_running_shop (active_shop_id)`；
- `CONSTRAINT ck_task_status CHECK (...)`；
- 两个索引；
- `DEFAULT CHARSET=utf8mb4`。

### 手工验证唯一约束

先确认有一个店铺（M1-01 建的 `m1-demo`，或自己再跑一次 `create_shop.py`），然后：

```powershell
docker exec ss-mysql mysql -uapp -papp_pass shopify_shopline -e "INSERT INTO shop_task_queue (shop_id, task_type, payload, status, attempts, max_attempts, available_at, run_epoch, created_at, updated_at) VALUES (1, 'sync_inventory', '{}', 'RUNNING', 0, 3, NOW(), 1, NOW(), NOW());"
```

再执行一次同样的 SQL，预期：

```
ERROR 1062 (23000): Duplicate entry '1' for key 'shop_task_queue.uq_running_shop'
```

再试非法状态：

```powershell
docker exec ss-mysql mysql -uapp -papp_pass shopify_shopline -e "INSERT INTO shop_task_queue (shop_id, task_type, payload, status, run_epoch, created_at, updated_at) VALUES (1, 'x', '{}', 'RUNNIG', 0, NOW(), NOW());"
```

预期 `ERROR 3819 ... Check constraint 'ck_task_status' is violated.`

记得把测试数据删掉：

```sql
DELETE FROM shop_task_queue WHERE shop_id = 1;
```

## 7. Step 5 · 仓储 `app/repositories/tasks.py`

接口（先写签名，再写实现）：

```python
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import CLAIMABLE_STATUSES, TaskStatus
from app.models.task import ShopTaskQueue
from app.utils import utcnow


def enqueue(
    session: Session,
    shop_id: int,
    task_type: str,
    payload: dict | None = None,
    *,
    max_attempts: int = 3,
    delay_seconds: float = 0.0,
) -> ShopTaskQueue:
    """入队一个 PENDING 任务；不 commit。"""


def list_pending(session: Session, shop_id: int) -> list[ShopTaskQueue]:
    """按 id 升序返回该店铺可执行（PENDING / RETRY_WAIT）的任务。"""
```

要求：

- 不 `commit`，事务交给调用方；
- `enqueue` 里 `session.add()` + `session.flush()`，保证返回对象有 `id`；
- `available_at = utcnow() + timedelta(seconds=delay_seconds)`；
- 查询按 `id.asc()` 排序，只取 `CLAIMABLE_STATUSES`；
- 不要在这里写重试、租约、状态流转。

自测：

```powershell
.\.venv\Scripts\python.exe -c "from app.repositories.tasks import enqueue, list_pending; print('ok')"
```

## 8. Step 6 · 测试 `tests/test_task_queue.py`

沿用 M1-01 的 `schema` fixture（`Base.metadata.create_all/drop_all`）。

至少六个用例：

| # | 用例 | 断言 |
| --- | --- | --- |
| 1 | `enqueue` 默认值 | `status=PENDING`、`attempts=0`、`run_epoch=0`、`payload={}` |
| 2 | `list_pending` 排序 | 依次入队 3 条，返回 id 升序 |
| 3 | 过滤终态 | 把一条改成 `SUCCESS`，它不出现在结果里 |
| 4 | 同店双 RUNNING | 第二条 `IntegrityError`（1062） |
| 5 | 不同店同时 RUNNING | 两条都成功（最终清理掉） |
| 6 | 外键 RESTRICT | 删除有任务的 shop 被拒绝（1451） |

给两个示例：

```python
def test_enqueue_defaults(engine: Engine, schema: None) -> None:
    with Session(engine) as session:
        task = enqueue(session, 1, "sync_inventory", {"limit": 100})
        session.commit()

        assert task.id is not None
        assert task.status == "PENDING"
        assert task.attempts == 0
        assert task.run_epoch == 0
        assert task.payload == {"limit": 100}


def test_same_shop_two_running_rejected(engine: Engine, schema: None) -> None:
    with Session(engine) as session:
        session.add(ShopTaskQueue(shop_id=1, task_type="a", status=TaskStatus.RUNNING))
        session.flush()

        session.add(ShopTaskQueue(shop_id=1, task_type="b", status=TaskStatus.RUNNING))
        with pytest.raises(IntegrityError):
            session.flush()
```

剩下四个自己写。注意：

- 测试里用的 `shop_id` 必须真实存在（外键），先建店铺；
- 每个用例用独立的店铺或清理数据，别依赖执行顺序；
- 并发相关（如果写）打 `@pytest.mark.concurrency`。

## 9. 验收

```powershell
.\.venv\Scripts\python.exe scripts\dev.py check
```

必须全绿，且测试数从 11 增加到 17+。

```powershell
alembic upgrade head
alembic downgrade -1
alembic upgrade head
```

三连通过，`SHOW CREATE TABLE` 里约束和索引齐全。

## 10. 常见坑

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 迁移报 Duplicate key name | 自动生成已带索引/约束，又手写了一遍 | 只保留一份 |
| `1062` 出现在不该出现的测试里 | 上一个用例的 RUNNING 没清理 | 每个用例独立店铺 |
| 插入报 1452 外键失败 | `shop_id` 不存在 | 先建店铺 |
| 删除店铺很慢 | 任务太多，级联删除持锁 | 测试里少造数据；业务用软删除 |
| 建表报 `1215 Cannot add foreign key constraint` | `ON DELETE CASCADE` 与依赖 `shop_id` 的生成列冲突 | 改成 `RESTRICT` |
| downgrade 报 `1553 Cannot drop index needed in a foreign key` | 先删了外键依赖的索引 | `downgrade` 只写 `drop_table`，索引随表删除 |
| JSON 字段读出 `None` | 插入时 `payload=None` | `default=dict` 只对未赋值生效，显式 `None` 不会替换 |

## 11. 提交

```powershell
git add app/enums.py app/models/ alembic/ app/repositories/tasks.py tests/test_task_queue.py
git status --short          # 确认没有 .env / __pycache__
git commit -m "feat(task): 新增店铺任务队列模型与入队仓储"
git push -u origin HEAD
```

然后开 PR，标题：

```
feat(task): 新增 shop_task_queue 模型与入队仓储
```

PR 描述至少写清：四个决策、迁移验证命令、测试覆盖的六类场景。

## 12. 交给我 review 的材料

1. `alembic/versions/xxxx_create_shop_task_queue.py` 全文；
2. `SHOW CREATE TABLE shop_task_queue\G` 的输出；
3. `pytest -v` 的输出；
4. 迁移三连的退出码。

## 13. 自测题

1. 为什么唯一索引建在生成列上，而不是 `(shop_id, status)` 联合唯一？
2. `status` 为什么用 `VARCHAR + CHECK`，而不是 MySQL 的 `ENUM`？
3. 为什么 `(shop_id, status, id)` 的列顺序不能换成 `(status, shop_id, id)`？
4. `payload` 用 `JSON` 而不是 `TEXT`，好处和代价各是什么？
5. 级联删除在任务量大时会有什么问题？业务上怎么规避？

答得出 4 个，这张表就算吃透了。
