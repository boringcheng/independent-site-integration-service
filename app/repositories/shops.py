from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.shop import Shop


class ShopAlreadyExists(Exception):
    """domain 已存在。"""


def get_by_domain(session: Session, domain: str) -> Shop | None:
    stmt = select(Shop).where(Shop.domain == domain)
    return session.execute(stmt).scalar_one_or_none()


def create_shop(session: Session, platform: str, domain: str) -> Shop:
    """新建；domain 冲突时抛 ShopAlreadyExists。不 commit。"""
    # 1. 先查询，避免不必要的 insert
    existing_shop = get_by_domain(session, domain)
    if existing_shop is not None:
        raise ShopAlreadyExists(f"店铺域名已存在: {domain}")

    # 2. 创建 ORM 对象
    shop = Shop(platform=platform, domain=domain)

    # 3. 使用嵌套事务隔离 INSERT 失败
    try:
        with session.begin_nested():
            session.add(shop)
            # 将 INSERT 提前发送到数据库，让唯一约束等错误在这里暴露
            session.flush()
    except IntegrityError as exc:
        existing_shop = get_by_domain(session, domain)

        if existing_shop is not None:
            raise ShopAlreadyExists(f"店铺域名已存在: {domain}") from exc

        # 其他完整性错误不应该伪装成域名重复
        raise
    return shop


def ensure_shop(session: Session, platform: str, domain: str) -> tuple[Shop, bool]:
    """幂等：返回 (shop, 是否新建)。不 commit。"""
    # 1. 先查询
    shop = get_by_domain(session, domain)
    if shop is not None:
        return shop, False

    # 2. 不存在时则尝试创建
    try:
        shop = create_shop(session=session, platform=platform, domain=domain)
        return shop, True
    except ShopAlreadyExists:
        # 3. 可能是并发请求先创建成功了
        shop = get_by_domain(session, domain)
        if shop is None:
            # 查不到说明不是可恢复的域名重复情况
            raise
        return shop, False
