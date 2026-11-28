"""shop_task_queue 的模型与仓储测试。

覆盖：默认值、延迟、排序、过滤、同店唯一 RUNNING、跨店并行、
状态 CHECK、外键 RESTRICT。
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
from app.enums import TaskStatus
from app.models import Base, Shop
from app.models.task import ShopTaskQueue
from app.repositories.tasks import enqueue, list_pending
from app.utils import utcnow
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session


@pytest.fixture(scope="module")
def schema(engine: Engine) -> Iterator[None]:
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


def _make_shop(engine: Engine) -> int:
    with Session(engine) as session:
        shop = Shop(platform="shopline", domain=f"q-{uuid4().hex[:10]}.com")
        session.add(shop)
        session.commit()
        return shop.id


def test_enqueue_defaults(engine: Engine, schema: None) -> None:
    shop_id = _make_shop(engine)
    with Session(engine) as session:
        task = enqueue(session, shop_id, "sync_inventory", {"limit": 100})
        session.commit()

        assert task.id is not None
        assert task.status == TaskStatus.PENDING
        assert task.attempts == 0
        assert task.run_epoch == 0
        assert task.payload == {"limit": 100}
        assert task.lease_token is None
        assert task.available_at is not None


def test_enqueue_delay(engine: Engine, schema: None) -> None:
    shop_id = _make_shop(engine)
    before = utcnow()

    with Session(engine) as session:
        task = enqueue(session, shop_id, "sync_inventory", delay_seconds=60)
        session.commit()

        assert (task.available_at - before).total_seconds() >= 59


def test_list_pending_orders_by_id(engine: Engine, schema: None) -> None:
    shop_id = _make_shop(engine)
    with Session(engine) as session:
        created = [enqueue(session, shop_id, f"task_{i}") for i in range(3)]
        session.commit()
        created_ids = [task.id for task in created]

        pending = list_pending(session, shop_id)

        assert [task.id for task in pending] == sorted(created_ids)


def test_list_pending_excludes_terminal(engine: Engine, schema: None) -> None:
    shop_id = _make_shop(engine)
    with Session(engine) as session:
        task = enqueue(session, shop_id, "sync_inventory")
        task.status = TaskStatus.SUCCESS
        session.commit()

        assert list_pending(session, shop_id) == []


def test_same_shop_two_running_rejected(engine: Engine, schema: None) -> None:
    shop_id = _make_shop(engine)
    with Session(engine) as session:
        session.add(ShopTaskQueue(shop_id=shop_id, task_type="a", status=TaskStatus.RUNNING))
        session.flush()

        session.add(ShopTaskQueue(shop_id=shop_id, task_type="b", status=TaskStatus.RUNNING))
        with pytest.raises(IntegrityError):
            session.flush()


def test_different_shops_can_both_run(engine: Engine, schema: None) -> None:
    shop_a = _make_shop(engine)
    shop_b = _make_shop(engine)

    with Session(engine) as session:
        session.add(ShopTaskQueue(shop_id=shop_a, task_type="a", status=TaskStatus.RUNNING))
        session.add(ShopTaskQueue(shop_id=shop_b, task_type="b", status=TaskStatus.RUNNING))
        session.commit()

        running = session.query(ShopTaskQueue).filter(
            ShopTaskQueue.status == TaskStatus.RUNNING,
            ShopTaskQueue.shop_id.in_([shop_a, shop_b]),
        )
        assert running.count() == 2


def test_invalid_status_rejected_by_check(engine: Engine, schema: None) -> None:
    shop_id = _make_shop(engine)
    with Session(engine) as session, pytest.raises(DBAPIError) as excinfo:
        session.add(ShopTaskQueue(shop_id=shop_id, task_type="x", status="RUNNIG"))
        session.flush()

    assert "ck_task_status" in str(excinfo.value)


def test_delete_shop_with_tasks_rejected(engine: Engine, schema: None) -> None:
    shop_id = _make_shop(engine)
    with Session(engine) as session:
        enqueue(session, shop_id, "sync_inventory")
        session.commit()

    with Session(engine) as session, pytest.raises(IntegrityError):
        shop = session.get(Shop, shop_id)
        session.delete(shop)
        session.flush()
