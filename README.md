# Independent Site Integration Service

面向 Shopify / SHOPLINE 等独立站平台的多店铺数据集成服务。核心不是"调通 API"，
而是把多店铺同步做成一个**有顺序、有租约、能恢复、能扩展**的后端任务系统。

> 状态：**M0 工程基线**。当前只有配置、数据库连通性与工程规范，
> 领域模型与调度逻辑按里程碑逐步加入（见 [Roadmap](#roadmap)）。

## 技术栈

| 层 | 选型 | 说明 |
| --- | --- | --- |
| Web | FastAPI | Webhook 接收、管理端点 |
| 调度 | MySQL 队列表 + 租约 | **任务顺序与状态的权威源** |
| 异步执行 | Celery + Redis（可选触发层） | 只负责触发，不承担顺序保证 |
| 存储 | MySQL 8.4 / SQLAlchemy 2.0 / Alembic | 迁移即代码 |
| 质量 | pytest + ruff + mypy + pre-commit + GitHub Actions | 本地与 CI 同一套命令 |

## 快速开始

前置：Docker Desktop 已启动，Python 3.12。

```powershell
# 1. 依赖服务（MySQL 8.4 + Redis 7.4）
docker compose -f docker-compose.dev.yml up -d

# 2. 测试库（只需执行一次）
docker exec ss-mysql mysql -uroot -proot_pass -e "CREATE DATABASE IF NOT EXISTS shopify_shopline_test CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci; GRANT ALL ON shopify_shopline_test.* TO 'app'@'%'; FLUSH PRIVILEGES;"

# 3. 虚拟环境
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt

# 4. 一键检查（lint + format + mypy + pytest）
python scripts/dev.py check
```

## 常用命令

| 命令 | 作用 |
| --- | --- |
| `python scripts/dev.py check` | lint + format 检查 + 类型检查 + 测试 |
| `python scripts/dev.py test` | 只跑测试 |
| `python scripts/dev.py lint` / `format` | ruff 检查 / 格式化 |
| `python scripts/dev.py typecheck` | mypy |
| `python scripts/dev.py up` / `down` | 起停 MySQL/Redis |
| `pre-commit install` | 安装提交前钩子 |

## 目录结构

```
app/                 应用代码（M1 起加入 models / repositories / services / api）
tests/               测试（integration / concurrency 标记）
docs/
  adr/               架构决策记录（改架构先改 ADR）
  local-env.md       本地环境搭建记录
scripts/
  dev.py             跨平台任务入口
  verify-env.ps1     环境自检
.github/workflows/   CI
```

## Roadmap

| 里程碑 | 内容 | 状态 |
| --- | --- | --- |
| M0 | 工程基线：git / 规范 / lint / 类型 / 测试 / CI / ADR | ✅ 已完成 |
| M1 | 领域模型 + Alembic 迁移 + 仓储层单测 | ⏳ 待开始 |
| M2 | 店铺级队列、租约、Fencing、状态机（并发测试） | ⏳ |
| M3 | 分片作业（Barrier/Publish）、Webhook 幂等、FastAPI 端点 | ⏳ |
| M4 | Worker 运行时、可观测性、demo 与 chaos 演示 | ⏳ |
| M5 | 文档定稿、面试问答材料 | ⏳ |

## 设计文档

- [ADR-0001 架构与调度权威源](docs/adr/0001-architecture.md)
- [ADR-0002 测试策略](docs/adr/0002-testing.md)
- [贡献指南](CONTRIBUTING.md)
- [本地环境](docs/local-env.md)

## 约定

- 数据库变更只走 Alembic，不允许手改表；
- 需要真实 MySQL 语义的测试必须打 `integration` 标记；
- 涉及取舍的改动先写 ADR，再写代码；
- 提交信息遵循 Conventional Commits。
