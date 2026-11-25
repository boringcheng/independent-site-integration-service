#!/usr/bin/env python
"""注册一个店铺（本地开发 / seed 用，幂等）。

用法：
    python scripts/create_shop.py --platform shopline --domain demo.myshopline.com
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

# 直接执行 `python scripts/create_shop.py` 时，sys.path[0] 是 scripts/ 而不是仓库根，
# 这里补上仓库根目录，保证能 import app。
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="注册一个店铺（幂等）")
    parser.add_argument(
        "--platform",
        required=True,
        choices=["shopify", "shopline"],
        help="平台类型",
    )
    parser.add_argument("--domain", required=True, help="店铺域名")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    # 延迟导入：确保上面的 sys.path 已经生效
    from app.db import build_engine
    from app.repositories.shops import ensure_shop
    from sqlalchemy.orm import Session

    args = parse_args(argv)

    engine = build_engine()
    try:
        with Session(engine) as session:
            shop, created = ensure_shop(session, args.platform, args.domain)
            session.commit()
            print(
                f"shop_id={shop.id}  platform={shop.platform}  domain={shop.domain}  "
                f"status={shop.status}  ({'created' if created else 'exists'})"
            )
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
