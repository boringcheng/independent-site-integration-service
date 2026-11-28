"""店铺级任务队列：一行 = 一个待执行任务，id 即店铺内的顺序号。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.enums import TaskStatus
from app.models.base import Base
from app.utils import utcnow

STATUS_VALUES = ", ".join(f"'{status.value}'" for status in TaskStatus)


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
        # 注意：不能用 ON DELETE CASCADE。
        # MySQL 8.4 不允许「外键带 CASCADE」与「依赖该外键列的生成列」共存，
        # 建表会报 1215。这里用 RESTRICT：删店铺前必须先清任务，避免误删队列历史。
        ForeignKey("shops.id", ondelete="RESTRICT"),
        nullable=False,
    )
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=TaskStatus.PENDING, nullable=False)

    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    available_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    # --- 租约与栅栏（M2 使用） ---
    lease_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    run_epoch: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    # RUNNING 时暴露 shop_id，其余状态为 NULL；
    # MySQL 唯一索引允许多个 NULL，所以非 RUNNING 的任务不会互相冲突。
    active_shop_id: Mapped[int | None] = mapped_column(
        BigInteger,
        Computed(
            "(CASE WHEN status = 'RUNNING' THEN shop_id ELSE NULL END)",
            persisted=True,
        ),
        nullable=True,
    )
