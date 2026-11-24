"""模型统一出口，Alembic 和业务代码都从这里导入。"""

from app.models.base import Base
from app.models.shop import Shop

__all__ = ["Base", "Shop"]
