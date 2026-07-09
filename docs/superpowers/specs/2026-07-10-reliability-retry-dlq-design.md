# 2026-07-10 可靠结算队列重试与死信机制设计规格书

本规格书定义了分布式欢乐斗地主系统中，针对游戏结束结算任务的 RabbitMQ 重试、死信队列（DLQ）与人工重放工具的设计实现。

## 1. 业务痛点
- 当前结算任务在异常时如果 requeue，由于无时间间隔和次数限制，在永久性故障（如序列化出错）时会导致无限高速死循环，刷爆服务器 CPU 和日志。
- 需要提供短暂临时性故障（如 MySQL 瞬断）的 3 次带退避自动重试，并在超过重试次数时安全移动至死信队列，提供管理员手动重放修复的接口。

## 2. 拓扑与队列设计

### 2.1 队列声明
- **主结算队列**：`ddz.game.settlement`（durable=True）
  - 绑定死信交换机（DLX）参数：
    - `x-dead-letter-exchange`: `ddz.game.settlement.dlx`
    - `x-dead-letter-routing-key`: `settle_dlq`
- **死信队列**：`ddz.game.settlement.dlq`（durable=True）
  - 绑定死信交换机：`ddz.game.settlement.dlx`，路由键：`settle_dlq`

### 2.2 消息重试与死信降级规则
- 在主结算消息中，首发时默认不含 `x-retry-count` header（或为 0）。
- 消费者在 `try...except` 块中捕获逻辑失败：
  - 从 `message.headers` 提取 `x-retry-count`。
  - **若 `x-retry-count < 3`**：
    - 递增 `x-retry-count`；
    - 等待 `3.0` 秒（退避）；
    - 发布一个包含更新后 headers 且内容一致的新消息至主交换机 `ddz.game.settlement.exchange`（路由键 `settle`）；
    - 调用 `await message.ack()` 确认删除当前老消息。
  - **若 `x-retry-count >= 3`**：
    - 打印 Error 日志，宣告重试耗尽；
    - 直接调用 `await message.nack(requeue=False)` 拒绝老消息。此时 RabbitMQ 会自动将消息转移至 `ddz.game.settlement.dlx` 并安全归档入 `ddz.game.settlement.dlq`（死信队列）。

---

## 3. 重放接口设计 (Replay Tool)
在接口层新增 HTTP 端点：
- **路径**：`POST /api/game/dev/settlement/replay`
- **校验**：非 production 或 API_TOKEN 校验。
- **业务动作**：
  1. 连接并逐个获取 `ddz.game.settlement.dlq` 中的死信消息。
  2. 将获取到的消息 Headers 中的 `x-retry-count` 重置为 0，重新发布至主结算队列。
  3. 对死信队列中的该消息执行 `ack` 以清空死信。
  4. 返回重放的结算任务数 `{"replayed_count": N}`。
