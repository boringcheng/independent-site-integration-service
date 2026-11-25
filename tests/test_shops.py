"""店铺注册的仓储层测试。

覆盖：正常注册、重复报错、幂等、非法平台、并发只创建一次。
"""

from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from app.models import Base
from app.repositories.shops import ShopAlreadyExists, create_shop, ensure_shop
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session


@pytest.fixture(scope="module")
def schema(engine: Engine) -> Iterator[None]:
    """仓储测试只需要表存在；迁移本身的正确性由 alembic 三连验证。"""
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


def _domain() -> str:
    return f"test-{uuid4().hex[:10]}.myshopline.com"


def test_create_shop(engine: Engine, schema: None) -> None:
    domain = _domain()
    with Session(engine) as session:
        shop = create_shop(session, "shopline", domain)
        session.commit()

        assert shop.id is not None
        assert shop.platform == "shopline"
        assert shop.domain == domain
        assert shop.status == "ACTIVE"


def test_duplicate_raises(engine: Engine, schema: None) -> None:
    domain = _domain()
    with Session(engine) as session:
        create_shop(session, "shopline", domain)
        session.commit()

    with Session(engine) as session, pytest.raises(ShopAlreadyExists):
        create_shop(session, "shopline", domain)


def test_ensure_shop_is_idempotent(engine: Engine, schema: None) -> None:
    domain = _domain()
    with Session(engine) as session:
        first, created_first = ensure_shop(session, "shopline", domain)
        session.commit()
        first_id = first.id

    with Session(engine) as session:
        second, created_second = ensure_shop(session, "shopline", domain)
        session.commit()
        second_id = second.id

    assert created_first is True
    assert created_second is False
    assert first_id == second_id


def test_invalid_platform_rejected(engine: Engine, schema: None) -> None:
    # MySQL 把 CHECK 违反报成 3819，PyMySQL 抛的是 OperationalError 而不是 IntegrityError，
    # 所以这里用 DBAPIError（两者的基类）兜住，并确认是哪条约束被触发。
    with Session(engine) as session, pytest.raises(DBAPIError) as excinfo:
        create_shop(session, "amazon", _domain())

    assert "ck_shops_platform" in str(excinfo.value)


@pytest.mark.concurrency
def test_concurrent_ensure_shop_creates_once(engine: Engine, schema: None) -> None:
    domain = _domain()

    def worker(_: int) -> tuple[int, bool]:
        with Session(engine) as session:
            shop, created = ensure_shop(session, "shopline", domain)
            session.commit()
            return shop.id, created

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(worker, range(2)))

    ids = {shop_id for shop_id, _created in results}
    created_flags = sorted(created for _shop_id, created in results)

    assert len(ids) == 1, f"并发注册产生了多个店铺: {results}"
    assert created_flags == [False, True], f"created 标志不对: {results}"
