# M1-01 编码走查（照着敲）

> 配套文档：[任务书](M1-01-shop-slice.md) · [PR 描述](M1-01-pr.md)
> 原则：**一个检查点一验证，不通过不进下一步。**
> 标了「自己写」的部分先别抄答案，写完再对照文末。

---

## 检查点 0 · 开分支

```powershell
cd C:\Users\18767\Desktop\独立站
git status
```

如果还有未提交的文档改动，先提交掉：

```powershell
git add README.md pyproject.toml docs/
git commit -m "docs: 补充依赖库详解与 M1 任务书"
```

然后开分支：

```powershell
git switch -c feat/m1-shop-slice
git branch --show-current      # 应输出 feat/m1-shop-slice
```

---

## 检查点 1 · `app/utils.py`（时间来源）

新建 `app/utils.py`：

```python
"""与业务无关的小工具。"""
from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """统一的"当前时间"：naive UTC。

    MySQL 的 DATETIME 不保存时区，全项目统一用 naive UTC，
    避免本地时区与 UTC 混用导致租约判断错乱。
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
```

**为什么不是 `datetime.utcnow()`**：Python 3.12 起它已弃用，而且返回的仍是 naive 对象，容易让人误以为是本地时间。

**验证**：

```powershell
.\.venv\Scripts\python.exe -c "from app.utils import utcnow; print(utcnow(), utcnow().tzinfo)"
```

预期：打印一个时间，`tzinfo` 为 `None`。

---

## 检查点 2 · `app/models/base.py`

```python
"""所有 ORM 模型的基类。"""
from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
```

**为什么单独一个文件**：`alembic/env.py` 要 import `Base.metadata`，
如果 Base 定义在 `__init__.py` 里，导入时会连带导入所有模型，容易循环依赖。

---

## 检查点 3 · `app/models/shop.py`

```python
"""店铺：领域根实体，任务/作业/事件都挂在 shop_id 上。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.utils import utcnow


class Shop(Base):
    __tablename__ = "shops"
    __table_args__ = (
        UniqueConstraint("domain", name="uq_shops_domain"),
        CheckConstraint(
            "platform IN ('shopify', 'shopline')",
            name="ck_shops_platform",
        ),
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_0900_ai_ci"},
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="ACTIVE"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow
    )
```

逐段说明：

| 写法 | 作用 |
| --- | --- |
| `Mapped[int]` + `mapped_column` | SQLAlchemy 2.0 写法，类型标注同时给 mypy 用 |
| `BigInteger` | 自增 ID 用 BIGINT，避免以后不够用 |
| `default=utcnow` | **Python 侧**默认值，插入时由 SQLAlchemy 填 |
| `__table_args__` 的 dict 放最后 | SQLAlchemy 的约定，放前面会报错 |
| `mysql_charset` | 保证中文不乱码；Alembic 不一定生成，迁移里要确认 |

**为什么 `created_at` 不用 `server_default`**：`server_default=func.now()` 用数据库时区，
和项目统一的 naive UTC 可能不一致；Python 侧默认值还能在测试里方便地伪造时间。代价是绕过 ORM 的手写 INSERT 必须自己填这一列。

**验证**：

```powershell
.\.venv\Scripts\python.exe -c "from app.models import Shop; print([c.name for c in Shop.__table__.columns]); print([c.name for c in Shop.__table__.constraints])"
```

预期能看到 `shops` 的列和 `uq_shops_domain`、`ck_shops_platform`。

---

## 检查点 4 · `app/models/__init__.py`

```python
"""模型统一出口，Alembic 和业务代码都从这里导入。"""
from app.models.base import Base
from app.models.shop import Shop

__all__ = ["Base", "Shop"]
```

---

## 检查点 5 · 初始化 Alembic

```powershell
.\.venv\Scripts\python.exe -m alembic init alembic
```

生成：

```
alembic.ini
alembic/
  env.py
  script.py.mako
  versions/
```

### 改 `alembic.ini`

找到这一行，注释掉（不要让连接串写死在配置文件里）：

```ini
# sqlalchemy.url = driver://user:pass@localhost/dbname
```

### 改 `alembic/env.py`

两处。

**第一处**：在文件顶部 import 区域加入

```python
from app.config import get_settings
from app.models import Base
```

**第二处**：找到 `target_metadata = None`，改成

```python
config.set_main_option("sqlalchemy.url", get_settings().database_url)
target_metadata = Base.metadata
```

> 注意：`set_main_option` 会对 `%` 做插值，密码里如果有 `%` 要写成 `%%`。
> 我们的 `app_pass` 没有，先不用管。

**验证配置能跑通**（不生成迁移）：

```powershell
.\.venv\Scripts\python.exe -m alembic current
```

预期：输出一行 `INFO  [alembic.runtime.migration] ...`，没有报错（此时还没有版本，`current` 为空是正常的）。

---

## 检查点 6 · 生成并审查迁移

```powershell
.\.venv\Scripts\python.exe -m alembic revision --autogenerate -m "create shops"
```

预期日志里有：

```
INFO  [alembic.autogenerate.compare] Detected added table 'shops'
```

打开 `alembic/versions/xxxx_create_shops.py`，逐行检查：

- [ ] `op.create_table("shops", ...)` 里的列类型、`nullable` 对不对；
- [ ] 唯一约束 `uq_shops_domain` 在不在；
- [ ] **CHECK 约束大概率没有**（Alembic 不检测），手动补；
- [ ] `mysql_charset` 有没有，没有就加；
- [ ] `downgrade()` 里有 `op.drop_table("shops")`。

手动补 CHECK，放在 `create_table` 之后：

```python
op.create_check_constraint(
    "ck_shops_platform",
    "shops",
    "platform IN ('shopify', 'shopline')",
)
```

补字符集（如果 `create_table` 里没有）：

```python
op.create_table(
    "shops",
    ...,
    mysql_charset="utf8mb4",
    mysql_collate="utf8mb4_0900_ai_ci",
)
```

---

## 检查点 7 · 迁移三连

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic downgrade base
.\.venv\Scripts\python.exe -m alembic upgrade head
```

每一次都要成功，中间不能报错。

然后直接看数据库真实结构：

```powershell
docker exec ss-mysql mysql -uapp -papp_pass shopify_shopline -e "SHOW CREATE TABLE shops\G"
```

确认三件事：

1. `UNIQUE KEY uq_shops_domain`；
2. `CONSTRAINT ck_shops_platform CHECK (...)`；
3. `DEFAULT CHARSET=utf8mb4`。

再手工试一次非法值：

```powershell
docker exec ss-mysql mysql -uapp -papp_pass shopify_shopline -e "INSERT INTO shops (platform, domain, status, created_at) VALUES ('amazon','x.com','ACTIVE',NOW());"
```

预期报错：

```
ERROR 3819 (HY000): Check constraint 'ck_shops_platform' is violated.
```

看到这个报错，说明约束真的生效了——这一步比看代码可靠。

---

## 检查点 8 · 仓储（自己写）

新建 `app/repositories/__init__.py`（空文件即可）和 `app/repositories/shops.py`。

规格：

```python
class ShopAlreadyExists(Exception):
    """domain 已存在。"""

def get_by_domain(session: Session, domain: str) -> Shop | None: ...

def create_shop(session: Session, platform: str, domain: str) -> Shop:
    """新建；domain 冲突时抛 ShopAlreadyExists。不 commit。"""

def ensure_shop(session: Session, platform: str, domain: str) -> tuple[Shop, bool]:
    """幂等：返回 (shop, 是否新建)。不 commit。"""
```

必须用到的写法（这段是难点，先理解再写）：

```python
from sqlalchemy.exc import IntegrityError

try:
    with session.begin_nested():   # 保存点
        session.add(shop)
        session.flush()            # 立刻 INSERT，才能在这一刻捕获冲突
except IntegrityError as exc:
    raise ShopAlreadyExists(domain) from exc
```

要点：

- 没有 `flush()` 就不会发 INSERT，异常永远不会在这里出现；
- 没有 `begin_nested()`，一次冲突会把外层事务整体标记为失败；
- `ensure_shop` 捕获后要重新查一次（刚刚失败的插入已经回滚，表里没有这一行）；
- 三个函数都**不 commit**，留给调用方。

**验证**：

```powershell
.\.venv\Scripts\python.exe -c "from app.repositories.shops import ensure_shop"
```

导入不报错只是第一步，真正的行为验证放到检查点 10 的测试里。

---

## 检查点 9 · 命令行（自己写）

新建 `scripts/create_shop.py`。

结构：

```python
import argparse

from sqlalchemy.orm import Session

from app.db import build_engine
from app.repositories.shops import ensure_shop


def main() -> None:
    parser = argparse.ArgumentParser(description="注册一个店铺")
    parser.add_argument("--platform", required=True, choices=["shopify", "shopline"])
    parser.add_argument("--domain", required=True)
    args = parser.parse_args()

    engine = build_engine()
    with Session(engine) as session:
        shop, created = ensure_shop(session, args.platform, args.domain)
        session.commit()
        print(
            f"shop_id={shop.id}  platform={shop.platform}  domain={shop.domain}  "
            f"status={shop.status}  ({'created' if created else 'exists'})"
        )


if __name__ == "__main__":
    main()
```

**验证**：

```powershell
.\.venv\Scripts\python.exe scripts\create_shop.py --platform shopline --domain demo.myshopline.com
.\.venv\Scripts\python.exe scripts\create_shop.py --platform shopline --domain demo.myshopline.com
```

两次输出同一个 `shop_id`，第二次是 `exists`。

---

## 检查点 10 · 测试（自己写）

新建 `tests/test_shops.py`。

测试库需要先有表。在测试文件里加一个 fixture（session 级）：

```python
import pytest
from sqlalchemy.orm import Session

from app.models import Base
from app.repositories.shops import ShopAlreadyExists, create_shop, ensure_shop


@pytest.fixture(scope="module")
def schema(engine):
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)
```

> 说明：仓储测试用 `create_all` 建表就够了；迁移本身的正确性由检查点 7 的
> `upgrade/downgrade` 验证。两者用的都是同一份模型定义，不会漂移。

四个用例，前两个给出，后两个自己写：

```python
def test_create_shop(engine, schema):
    domain = f"t-{uuid4().hex[:8]}.myshopline.com"
    with Session(engine) as session:
        shop = create_shop(session, "shopline", domain)
        session.commit()
        assert shop.id is not None
        assert shop.status == "ACTIVE"


def test_duplicate_raises(engine, schema):
    domain = f"t-{uuid4().hex[:8]}.myshopline.com"
    with Session(engine) as session:
        create_shop(session, "shopline", domain)
        session.commit()
    with Session(engine) as session:
        with pytest.raises(ShopAlreadyExists):
            create_shop(session, "shopline", domain)
```

**自己写：**

1. `test_ensure_shop_is_idempotent`：连调两次，第一次 `created=True`，
   第二次 `created=False`，两次 `shop.id` 相同；
2. `test_invalid_platform_rejected`：`platform="amazon"` 应被拒绝
   （注意：Python 层没校验时，要等 `flush()` 才会抛 `IntegrityError`）。

**加分（可选）**：两个线程用各自的 `Session` 同时 `ensure_shop` 同一个 domain，
最终表里只有一行，两边拿到同一个 id。

---

## 检查点 11 · 收尾

```powershell
.\.venv\Scripts\python.exe scripts\dev.py check
```

必须全绿，特别注意 mypy：`app/` 下的新代码全在 strict 检查范围里。

```powershell
git add app/ alembic/ alembic.ini scripts/create_shop.py tests/test_shops.py
git status --short          # 确认没有 .env、日志、__pycache__
git commit -m "feat(shop): 支持 SHOPLINE 店铺幂等注册"
git push -u origin feat/m1-shop-slice
```

然后开 PR，标题和正文用 [PR 描述](M1-01-pr.md)。

---

## 卡住时的求助格式

别只说"报错了"。按这个格式发我：

```
目标：ensure_shop 第二次调用应该返回 created=False
实际：抛了 ShopAlreadyExists
报错：（完整 traceback）
相关代码：（函数本体，不要整个文件）
已尝试：（改过什么）
```

---

## 参考实现（先自己写，写完再对照）

<details>
<summary>点开看 ensure_shop 的参考写法</summary>

```python
def ensure_shop(session: Session, platform: str, domain: str) -> tuple[Shop, bool]:
    existing = get_by_domain(session, domain)
    if existing is not None:
        return existing, False
    try:
        return create_shop(session, platform, domain), True
    except ShopAlreadyExists:
        existing = get_by_domain(session, domain)
        if existing is None:  # 理论上不会发生
            raise
        return existing, False
```

</details>
