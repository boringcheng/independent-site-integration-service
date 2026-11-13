# ADR-0002：测试必须跑真实 MySQL

- 状态：Accepted
- 日期：2026-11-13
- 相关里程碑：M0 / M2 / M3

## 背景

这个项目的核心正确性来自数据库行为：行锁、唯一索引、生成列、隔离级别、
死锁检测（错误码 1213）。用 SQLite 或内存数据库跑测试，语法能过，语义完全不对：

- SQLite 没有行级锁与 `SELECT ... FOR UPDATE`；
- SQLite 的事务模型与 InnoDB 不同，隔离级别不可比；
- 生成列、`SKIP LOCKED`、死锁行为都无法复现。

## 决策

1. 本地与 CI 都使用 **MySQL 8.4**；
2. 本地用 `docker-compose.dev.yml` 起 MySQL，测试库为 `shopify_shopline_test`；
3. CI 使用 GitHub Actions 的 `mysql:8.4` service container；
4. 需要数据库的测试标记 `@pytest.mark.integration`，
   并发相关测试标记 `@pytest.mark.concurrency`；
5. 数据库不可用时：本地跳过（并在输出里说明），CI 设置 `REQUIRE_DB=1` 直接失败。

## 后果

正面：

- 锁、隔离级别、约束都能被真实验证；
- CI 与本地行为一致，减少"本地绿、线上炸"。

代价与缓解：

- 测试比纯单测慢 → 单元测试与集成测试分层，日常只跑单元测试，提交前跑全量；
- 每个测试需要隔离数据 → 用事务回滚或按用例建店铺，禁止依赖执行顺序；
- CI 需要等待 MySQL healthy → service container 配置 healthcheck。

## 禁止

- 禁止为了"跑得快"把集成测试改成 SQLite；
- 禁止用 `time.sleep` 代替并发同步原语，等待条件应轮询状态或使用事件；
- 禁止在测试里放宽断言来掩盖偶发失败，偶发失败优先怀疑并发设计。
