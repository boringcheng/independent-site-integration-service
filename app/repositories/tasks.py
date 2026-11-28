"""店铺任务队列的入队与查询。

M1 阶段只做「写进去、读出来」，领取/租约/状态流转在 M2。
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import CLAIMABLE_STATUSES, TaskStatus
from app.models.task import ShopTaskQueue
from app.utils import utcnow


def enqueue(
    session: Session,
    shop_id: int,
    task_type: str,
    payload: dict[str, Any] | None = None,
    *,
    max_attempts: int = 3,
    delay_seconds: float = 0.0,
) -> ShopTaskQueue:
    """入队一个 PENDING 任务；不 commit。

    delay_seconds > 0 时任务会在一段时间后才「到期」，
    领取方需要按 available_at 过滤（M2 的 claim）。
    """
    task = ShopTaskQueue(
        shop_id=shop_id,
        task_type=task_type,
        payload=payload or {},
        status=TaskStatus.PENDING,
        max_attempts=max_attempts,
        available_at=utcnow() + timedelta(seconds=delay_seconds),
    )
    session.add(task)
    session.flush()  # 立刻 INSERT，拿到自增 id
    return task


def list_pending(session: Session, shop_id: int) -> list[ShopTaskQueue]:
    """按 id 升序返回该店铺可执行（PENDING / RETRY_WAIT）的任务。"""
    stmt = (
        select(ShopTaskQueue)
        .where(
            ShopTaskQueue.shop_id == shop_id,
            ShopTaskQueue.status.in_(CLAIMABLE_STATUSES),
        )
        .order_by(ShopTaskQueue.id.asc())
    )
    return list(session.scalars(stmt).all())
