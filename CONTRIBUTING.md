# 贡献指南

本项目按里程碑推进，每个里程碑都必须满足本文的完成标准。

## 分支与提交

- `main` 受保护，只接受 PR；
- 分支命名：`feat/m2-lease-fencing`、`fix/m3-publish-twice`、`docs/m5-interview`；
- 提交信息使用 Conventional Commits：

```
feat(scheduler): 实现店铺租约接管与 fencing
fix(queue): 修正领取时的状态过滤条件
test(concurrency): 增加同店并行回归用例
docs(adr): 记录 READ COMMITTED 的取舍
chore(ci): 缓存 pip 依赖
```

一个提交只做一件事；格式化与逻辑改动分开提交。

## 完成标准（Definition of Done）

一个 PR 合并前必须满足：

1. `python scripts/dev.py check` 全绿；
2. 新增/修改的逻辑有对应测试，且测试能在真实 MySQL 上跑；
3. 类型标注完整（`mypy app` 通过）；
4. 涉及架构取舍的，有 ADR 或更新了已有 ADR；
5. 没有提交密钥、`.env`、日志、大文件；
6. README / 文档与行为一致。

## 代码规范

- 公共函数必须有类型标注与 docstring；docstring 说明**为什么**，不是复述代码；
- 配置只从 `app.config.get_settings()` 读取，禁止散落 `os.getenv`；
- 数据库会话不跨外部调用：**不要在持有事务/行锁时发起 HTTP 请求或 sleep**；
- 日志使用结构化字段（`task_id`、`shop_id`、`epoch`），不要拼字符串；
- 异常要区分"可重试"与"结果未知"：未知走 `UNCERTAIN`，不要盲目重试。

## 测试规范

| 类型 | 标记 | 要求 |
| --- | --- | --- |
| 单元测试 | 无 | 不依赖数据库，毫秒级 |
| 集成测试 | `@pytest.mark.integration` | 连真实 MySQL |
| 并发测试 | `@pytest.mark.concurrency` | 多线程/多连接，重复运行 |

- **禁止用 SQLite 替代 MySQL 验证锁语义**，两者行为不同，会给你虚假的安全感；
- 每个并发不变量至少一个测试：同店串行、跨店并行、租约接管、旧执行者提交被拒、
  分片只发布一次、重复 Webhook 只入队一次；
- 测试之间必须隔离：每个用例自己准备数据，不依赖执行顺序。

## 数据库变更

- 所有 schema 变更通过 Alembic：`alembic revision --autogenerate -m "..."`；
- 迁移必须可回滚（`downgrade` 可用）；
- 大表变更在 PR 描述里说明锁影响与上线步骤；
- 生成列、唯一索引这类"不变量约束"要在 ADR 里解释原因。

## 评审清单

- [ ] 这个改动解决的是哪一个问题？有没有更小的做法？
- [ ] 并发窗口在哪里？靠什么保证正确性（行锁 / 唯一索引 / 条件更新）？
- [ ] 失败路径是什么？重试会不会产生重复副作用？
- [ ] 有没有在事务里做网络调用？
- [ ] 测试是否能在 CI 的 MySQL 上稳定通过？
