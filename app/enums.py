"""任务状态枚举。

数据库里仍然是 VARCHAR + CHECK，枚举只活在 Python 侧：
枚举负责开发体验（补全、拼写检查、重构），CHECK 负责数据底线。
"""

from __future__ import annotations

from enum import StrEnum


class TaskStatus(StrEnum):
    PENDING = "PENDING"  # 等待执行
    RUNNING = "RUNNING"  # 已拿到租约，正在执行
    RETRY_WAIT = "RETRY_WAIT"  # 等待重试（退避中）
    BLOCKED = "BLOCKED"  # 等待分片作业完成
    UNCERTAIN = "UNCERTAIN"  # 结果未知，需与平台对账
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


# 可以被 worker 领取的状态
CLAIMABLE_STATUSES: tuple[TaskStatus, ...] = (
    TaskStatus.PENDING,
    TaskStatus.RETRY_WAIT,
)

# 终态：不会再变化
TERMINAL_STATUSES: tuple[TaskStatus, ...] = (
    TaskStatus.SUCCESS,
    TaskStatus.FAILED,
)
