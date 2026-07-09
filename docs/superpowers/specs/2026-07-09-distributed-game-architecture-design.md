# 斗地主多实例分布式架构设计规约

## 1. 决策摘要

本规约将当前单进程斗地主服务升级为可运行在 2～4 个后端实例上的分布式系统，首期目标容量约为 1,000 条并发 WebSocket 连接。

采用以下核心方案：

- RabbitMQ 承担可靠游戏命令、跨实例事件和结算任务的传递。
- Redis 保存房间快照、版本号、实例与玩家在线位置、分片/房间租约、幂等记录、持久调度任务和待发送事件。
- MySQL 保存账号、玩家档案、战绩和唯一结算事实。
- 每个应用实例仍使用同一套代码，同时装配 WebSocket 网关、分片 Worker 和事件 Relay，不在首期拆成大量微服务。
- 固定 16 个游戏命令分片；同一房间的命令始终进入同一分片。
- RabbitMQ Single Active Consumer、Redis 租约与 fencing token、房间版本号共同保证房间单写。
- RabbitMQ 使用至少一次投递语义，业务通过 `command_id`、`event_id`、连接代次和数据库唯一约束实现幂等效果。

本规约优先保证正确性和故障恢复，不以堆叠组件或展示概念为目标。

## 2. 当前问题与改造依据

当前测试基线健康：

- 后端：166 项 pytest 测试通过。
- 前端：50 项 Vitest 测试通过。
- 前端类型检查与生产构建通过。

需要优化的核心问题不在现有测试红灯，而在多实例和生产故障边界：

1. `GameWSConnectionManager.connections` 与 `active_ai_rooms` 只存在于单个进程。
2. `GameAppService._pending_players` 只存在于单个进程，跨实例匹配会丢失玩家昵称等元数据。
3. 创建房间的实例无法直接向连接在其他实例上的玩家广播。
4. 房间更新采用 Redis 快照的读取、修改、覆盖，缺少版本校验和旧 Worker 写入隔离。
5. AI 延迟、匹配超时和部分后续回合依赖 `asyncio.sleep()`、`asyncio.create_task()`，进程退出后任务丢失。
6. 结算写入 MySQL 失败后仍然清理 Redis 房间，存在不可恢复的战绩和资产丢失。
7. 对局记录缺少 `(room_id, player_id)` 唯一约束，结算重试可能重复写入。
8. 正式玩家可以调用接口直接设置自己的欢乐豆和段位。
9. `GAME_AUTH_SECRET` 存在可预测默认值，生产配置缺失时不能可靠失败。
10. 同一玩家重复连接时，旧连接断开可能误删新连接。

## 3. 目标与验收指标

### 3.1 功能目标

- 三名玩家连接到不同实例时，仍可正常匹配、开局、出牌、聊天、语音信令和结算。
- 任一应用实例宕机后，客户端可连接到其他实例并恢复当前房间。
- 房间 Worker 宕机后，未确认命令可由其他实例接管。
- 同一个玩家动作即使被重复投递，也只改变一次房间状态。
- 同一局游戏即使重复提交结算，也只改变一次玩家资产、胜场和段位。
- 所有广播继续使用玩家个人视角，不向其他玩家泄露手牌。

### 3.2 首期容量与服务指标

- 应用实例：2～4 个。
- 并发 WebSocket：约 1,000 条。
- 普通玩家动作从网关接收到事件发出的 p95：小于 300ms，不包含设计中的 AI 思考延迟。
- Worker 故障后的房间恢复目标：15 秒内。
- 稳态下 RabbitMQ 命令队列和 Redis Outbox 不持续积压。
- Redis、RabbitMQ 或 MySQL 短暂故障期间，不发生房间状态倒退、重复出牌或重复结算。

### 3.3 非目标

首期不做以下工作：

- 不拆成独立账号、匹配、房间、结算等大量微服务。
- 不引入 Kafka。
- 不要求 Kubernetes。
- 不实现完整事件溯源；Redis 房间快照仍是进行中对局的权威状态。
- 不重写 `GameRoom` 领域状态机和斗地主规则。
- 不以跨地域多活为目标。
- 不新增生产管理员体系；现有资产和段位直改接口在生产环境直接禁用。

## 4. 部署拓扑与基础设施前提

### 4.1 应用实例

每个实例生成或配置唯一 `instance_id`，并包含：

- WebSocket Gateway：维护本机连接，接收玩家动作，发送玩家事件。
- Command Publisher：将动作封装为命令并可靠发布。
- Shard Worker：消费当前实例持有的命令分片。
- Match Worker：处理匹配队列和房间创建。
- Outbox Relay：转发 Redis 中尚未确认的玩家事件。
- Durable Scheduler：将到期的匹配、AI 和回合超时任务发布为普通命令。
- Settlement Worker：执行幂等数据库结算。

负载均衡器不依赖粘性会话。客户端断线后可连接任意健康实例。

### 4.2 基础设施高可用边界

多应用实例不能自动消除共享基础设施的单点故障。正式高可用部署建议：

- RabbitMQ 使用 3 节点集群和 quorum 命令/结算队列。
- Redis 使用 Sentinel、托管高可用实例或等价主从切换方案。
- MySQL 至少具备自动备份和恢复演练；更高要求下使用托管高可用或主从切换。

本仓库首期实现负责正确处理依赖短暂不可用，不负责自动搭建上述集群。

## 5. RabbitMQ 拓扑

### 5.1 游戏命令

新增 durable direct exchange：

```text
ddz.game.commands
```

固定声明 16 个 durable 命令队列：

```text
ddz.game.commands.shard.0
...
ddz.game.commands.shard.15
```

房间命令的分片公式固定为：

```text
crc32(room_id) % GAME_COMMAND_SHARDS
```

实现必须使用 UTF-8 编码后的 `room_id` 和无符号 CRC32，禁止使用各进程随机化的语言内置 `hash()`。`GAME_COMMAND_SHARDS` 首期默认为 16。上线后不得直接修改；扩分片需要单独的排空和迁移方案。

每个队列启用 Single Active Consumer。Redis 分片租约协调各实例只主动消费自己持有的分片；Single Active Consumer 作为重叠消费时的第二层保护。

### 5.2 匹配命令

加入、取消和超时补 AI 进入独立 durable 队列：

```text
ddz.match.commands
```

该队列使用 Single Active Consumer。首期只有六个主要底分档位，单个匹配逻辑写者足以支撑目标容量，并能显著降低重复组房风险。

玩家匹配元数据全部写入 Redis，不再使用 `_pending_players`：

```text
game:match_player:{player_id}
```

元数据至少包含昵称、底分、加入时间、`connection_epoch` 和匹配状态。

匹配 Worker 使用 Lua 将选中的玩家从 `waiting` 原子切换为 `forming`，并生成稳定 `match_id`。房间 ID 由 `match_id` 确定。Worker 在弹出玩家后宕机时，重投的同一匹配命令必须继续完成原 `match_id`，不能再次选择三名玩家或生成第二个房间。长时间停留在 `forming` 且没有房间结果的记录由恢复任务重新发布，不直接放回队列。

### 5.3 玩家事件

新增 direct exchange：

```text
ddz.game.events
```

每个在线应用实例声明自己的事件队列，路由键包含 `instance_id`。事件队列只服务该实例当前连接；实例消失后允许队列自动清理。

玩家事件不是对局事实的唯一存储。网关宕机导致事件未送达时，客户端通过断线重连和 `sync_room_state` 从 Redis 权威快照恢复。

### 5.4 重试与死信

- Publisher 必须启用 confirm。
- Consumer 必须手动 Ack。
- Redis 或临时依赖故障不使用无间隔 `nack/requeue`，避免热循环。
- 使用带 TTL 的重试队列实现 1 秒、5 秒、30 秒等分级退避。
- 超过上限的命令或结算任务进入死信队列，并产生告警和人工重放入口。

## 6. 分片所有权、租约和单写

### 6.1 实例成员

实例定期刷新：

```text
game:instance:{instance_id}
```

记录启动时间、版本、心跳时间和可消费能力，TTL 建议为 30 秒，刷新间隔建议为 10 秒。

### 6.2 分片分配

所有实例根据当前健康实例集合和分片编号计算确定性的优先所有者。实例只尝试领取分配给自己的分片，从而得到近似均衡分布。

Redis Lua 脚本原子领取：

```text
game:shard_owner:{shard_id}
```

租约包含 `instance_id`、过期时间和单调递增的 fencing token。实例续约失败后必须停止获取新命令并关闭对应 Consumer。

分片和房间租约首期采用 10 秒有效期、每 3 秒续约。实现需加入少量随机抖动，避免所有实例同时续约。恢复目标以租约到期而不是实例心跳 TTL 为准。

### 6.3 房间租约

分片 Worker 第一次处理某个房间时领取：

```text
game:room_owner:{room_id}
```

房间租约关联当前分片所有者和 fencing token。Redis 房间写入脚本同时校验：

- 房间 owner 是否仍为当前实例。
- fencing token 是否仍有效。
- `room_version` 是否等于 Worker 读取时的版本。
- `command_id` 是否已经处理。

旧 Worker 即使在网络分区后恢复，也无法用旧 fencing token 覆盖新状态。

## 7. 连接位置与重复登录

### 7.1 Presence

玩家连接成功时，Redis Lua 原子递增连接代次：

```text
game:connection_epoch:{player_id}
```

并写入：

```text
game:presence:{player_id}
```

Presence 包含：

- `player_id`
- `instance_id`
- `connection_epoch`
- `connected_at`
- `last_seen_at`

Presence TTL 建议为 60 秒，在线连接每 20 秒刷新一次。

### 7.2 新连接接管

同一玩家建立新连接时：

1. 原子生成更大的 `connection_epoch`。
2. 新 Presence 覆盖旧实例位置。
3. 向旧实例发布 kick 事件。
4. 新实例立即同步最新房间快照。
5. 旧 epoch 的命令和事件全部拒绝。

本地连接表的键必须包含玩家和 epoch。旧连接断开时，只能在 Redis Presence 的 epoch 仍匹配时删除记录，不能误删新连接。

## 8. 命令与事件契约

### 8.1 玩家动作 ID

前端为每次需要可靠执行的动作生成稳定 `action_id`。网络超时后重试必须复用同一 ID。

服务端将其作为 `command_id` 的主要组成部分。旧客户端未提供时可以由网关临时生成，但不保证网关宕机后的端到端重试幂等；正式启用分布式模式前必须完成前端协议升级。

### 8.2 命令信封

命令使用 Pydantic 明确定义，至少包含：

```text
schema_version
command_id
action
room_id
player_id
connection_epoch
payload
created_at
trace_id
source_instance_id
```

客户端不能决定 owner、fencing token 或房间版本。Worker 必须再次验证身份、连接代次、房间成员关系和领域状态机。

### 8.3 事件信封

事件至少包含：

```text
schema_version
event_id
event
room_id
room_version
target_player_id
target_connection_epoch
payload
created_at
trace_id
```

每个 Outbox 项只包含一个目标玩家的个人视角数据。禁止将完整房间手牌放进通用广播，再交给网关过滤。

Outbox 中先保存逻辑目标 `target_player_id`。Relay 在实际发布前查询最新 Presence，并填入当时的 `target_connection_epoch` 和实例路由；这样玩家跨实例重连后不会继续把事件发往旧实例。

网关按 `event_id` 短期去重，并校验目标 epoch 后再发送 WebSocket。

## 9. 房间状态原子提交与 Redis Outbox

房间 Redis 值升级为带元数据的信封：

```text
room_id
room_version
owner_instance_id
fencing_token
phase
state
updated_at
```

Worker 完成领域操作后，使用 Lua 脚本在一个原子步骤中：

1. 校验 owner、fencing token 和旧 `room_version`。
2. 检查 `command_id` 是否已处理。
3. 保存新房间快照并递增版本。
4. 记录已处理的 `command_id`。
5. 将逐玩家事件写入该房间 Redis Outbox。

Outbox Relay 查询玩家最新 Presence 后，将事件路由到当前实例。RabbitMQ publisher confirm 成功后才标记事件已转发。

Relay 或应用实例中途退出时，未确认 Outbox 项由新 owner 或其他 Relay 继续转发。事件可能重复，但不能丢失到没有恢复手段；网关使用 `event_id` 去重，掉线玩家通过重连同步快照。

已处理命令和事件去重记录至少保留到房间 tombstone 到期。数据结构必须有数量或 TTL 上限，避免长局无限增长。

同一房间的快照、命令去重和 Outbox Redis key 使用相同 `{room_id}` hash tag，保证未来使用 Redis Cluster 时仍能在同一槽内执行原子脚本；首期部署仍以 Sentinel 或托管高可用 Redis 为主。

## 10. 持久调度器

以下逻辑不能继续只依赖 `asyncio.sleep()` 或后台 `create_task()`：

- 匹配超时后补 AI。
- AI 思考延迟。
- 真人回合超时。
- 掉线后进入托管。
- 结算重试。

使用 Redis ZSET 保存到期任务：

```text
game:schedule
```

调度任务至少包含 `task_id`、`due_at`、`room_id`、任务类型、预期房间版本和 payload。

单个 Scheduler leader 通过 Redis 租约工作，原子领取到期任务并发布为普通 RabbitMQ 命令。命令 ID 由 `task_id` 确定，因此调度重复发布不会重复生效。

“领取”不能直接删除 ZSET 项。Lua 应将任务从 `due` 原子移动到带 claim deadline 的 `processing` 集合；RabbitMQ publisher confirm 成功后才标记完成。Scheduler 在发布前宕机时，其他实例会回收超过 claim deadline 的任务并用同一 `task_id` 再次发布。

任务执行时必须校验当前房间版本和阶段。已经过期的旧 AI/超时任务应安全忽略。

## 11. 可靠结算

### 11.1 状态变化

游戏结束后，房间进入：

```text
SETTLING_PENDING
```

领域结果、全部分数、倍数和结果摘要先可靠保存在 Redis 房间快照和 Outbox 中，再发布结算任务。

玩家可以先看到 `game_over`，其中带 `settlement_status=pending`。MySQL 事务提交后再发送 `settlement_confirmed`。

### 11.2 数据库模型

新增 `ddz_game_settlement`：

- `room_id`：唯一。
- `result_hash`：结果摘要，防止同一房间出现两个不同结果。
- `status`：`pending/completed/failed`。
- `attempts`
- `last_error`
- `created_at`
- `completed_at`

为 `ddz_game_record` 增加 `(room_id, player_id)` 唯一约束。

### 11.3 幂等事务

Settlement Worker 在一个 MySQL 事务中：

1. 先用短事务确保唯一结算主记录存在。
2. 在业务事务中锁定结算主记录。
3. 如果状态已为 `completed`，直接返回成功。
4. 校验 `result_hash` 一致。
5. 更新所有真人玩家欢乐豆、总局数和胜场。
6. 更新所有真人玩家段位。
7. 写入每位玩家的唯一战绩记录。
8. 将结算主记录设为 `completed`。
9. 提交业务事务。

任一步骤失败必须整体回滚。RabbitMQ 重投不会重复改变资产。

业务事务失败后，Worker 使用独立短事务更新 `attempts` 和脱敏后的 `last_error`；该诊断更新不改变任何玩家资产。若进程在记录错误前退出，RabbitMQ 重投次数仍是恢复和告警的补充依据。

只有数据库提交并发布 `settlement_confirmed` 后，才移除玩家房间映射。房间保留短期 tombstone，用于重复命令去重和断线客户端获取最终状态，之后再由受控清理任务删除。

MySQL 不可用时持续退避重试；超过阈值进入死信队列并告警，绝不提前删除 Redis 结果。

## 12. 安全设计

### 12.1 生产配置

- `GAME_AUTH_SECRET` 在生产环境必须显式配置为随机高强度值。
- 代码不得提供可用于生产签名的默认密钥。
- 缺少必要密钥、Redis、RabbitMQ 或数据库配置时，生产启动应失败。
- `PORT`、CORS、RabbitMQ 变量名等统一由 Settings 提供，禁止入口文件继续硬编码。

### 12.2 玩家资产与调试能力

- `/profile/{player_id}/beans` 与 `/profile/{player_id}/rank` 在生产环境禁用。
- 大厅中的手动修改入口只在 development 显示。
- 调试控制台和普通 HMP 管理 API 在生产环境要求独立管理凭证或直接关闭。
- 正式玩家资产和段位只能通过幂等结算事务改变。

### 12.3 登录与令牌

- 登录和注册使用 Redis 令牌桶限制 IP 与账号维度频率。
- 登录失败使用统一提示，避免区分账号不存在与密码错误。
- 提高新密码最低长度。
- 旧明文密码只允许兼容验证；验证成功后立即升级为当前哈希格式。
- 长期令牌不再直接放入 WebSocket URL。
- 客户端先通过已认证 REST 接口获取 30 秒有效、单次使用的 WebSocket ticket，再用 ticket 建立连接。
- WebSocket 校验 Origin、ticket、player_id 和单次消费状态。

### 12.4 协议滥用防护

- 对 WebSocket 文本大小、JSON 深度、数组长度和动作频率设置上限。
- `play_cards` 牌数量、聊天 ID、语音信令类型和信令大小继续做服务端校验。
- RabbitMQ 使用独立 vhost、最小权限账号和 TLS（生产环境）。

## 13. 故障处理

### 13.1 Worker 宕机

1. 未 Ack 命令留在 RabbitMQ。
2. 分片租约过期，备用实例领取分片。
3. Single Active Consumer 切换到新 Consumer。
4. 新 Worker 获取更大的 fencing token。
5. 重投命令按 `command_id` 去重或继续执行。
6. Redis Outbox 中未确认事件继续转发。

目标恢复时间为 15 秒内。

### 13.2 网关宕机

- 客户端重连任意实例。
- 新实例生成更大的连接 epoch。
- 使用 Redis 房间快照恢复。
- 旧实例事件因 epoch 不匹配而失效。

### 13.3 RabbitMQ 不可用

- Gateway 未得到 publisher confirm 时，不向客户端声称动作已接受。
- 前端使用同一 `action_id` 重试。
- 不在进程内建立无限待发送队列。
- Readiness 失败，负载均衡器停止分配新连接。

### 13.4 Redis 不可用

- Worker 停止推进房间，不降级到进程内存。
- 命令进入延迟重试队列。
- 已连接客户端显示服务暂时繁忙，并保持重连/同步能力。

### 13.5 MySQL 不可用

- 已进行的对局可以依赖 Redis 和 RabbitMQ 继续。
- 登录、资料等数据库接口返回明确服务不可用。
- 已结束房间保持 `SETTLING_PENDING`，结算任务持续重试。

## 14. 可观测性

### 14.1 结构化日志

跨实例日志统一包含：

- `instance_id`
- `trace_id`
- `command_id`
- `event_id`
- `room_id`
- `player_id`
- `shard_id`
- `room_version`
- `fencing_token`

不得记录密码、访问令牌、WebSocket ticket 或完整其他玩家手牌。

### 14.2 指标

至少暴露：

- 每实例 WebSocket 连接数和重连率。
- 命令发布失败、消费延迟、执行 p50/p95/p99。
- 每个分片的队列深度和活跃 Consumer。
- 租约领取、续约失败和接管次数。
- 房间 CAS 冲突数、重复命令数。
- Redis Outbox 未发送数量和最大延迟。
- Scheduler 到期任务积压。
- 待结算房间、结算重试和死信数量。
- Redis、RabbitMQ、MySQL 连接状态。
- 鉴权失败和限流次数。

### 14.3 健康检查

- `/health/live`：只反映进程事件循环是否存活。
- `/health/ready`：检查 Redis、RabbitMQ 以及实例必要的数据库访问。

依赖故障不应导致 liveness 失败并触发无意义重启，但应导致 readiness 失败并停止接收新流量。

## 15. 测试策略

### 15.1 单元测试

- Pydantic 命令和事件 schema。
- 分片计算稳定性。
- Redis Lua 的领取、续约、fencing、CAS 和去重。
- Presence epoch 的新连接接管。
- 调度任务的过期忽略与重复发布。
- 结算事务的重复调用。
- 生产环境安全配置和调试接口禁用。

### 15.2 真实中间件集成测试

不能只依赖 Mock。测试环境使用真实 Redis、RabbitMQ 和 MySQL 验证：

- publisher confirm 和手动 Ack。
- Consumer 断开后的未确认消息重投。
- Redis 租约过期和旧 fencing token 写入失败。
- MySQL 事务回滚与唯一约束。
- Outbox Relay 重启后的事件重放。

### 15.3 多实例端到端测试

至少启动三个应用实例，让三名玩家分别连接不同实例，覆盖：

- 真人跨实例匹配和创建房间。
- 叫地主、加倍、明牌、出牌、过牌和结算。
- 聊天与语音信令定向转发。
- 重复登录踢出旧连接。
- 对局中杀死当前分片 Worker。
- RabbitMQ 重复投递同一命令。
- 断线后连接到另一实例并同步状态。
- 确认所有事件仍按玩家视角隐藏他人手牌。

### 15.4 故障与容量测试

- 短暂停止 Redis，确认没有本机内存写入和状态倒退。
- 短暂停止 RabbitMQ，确认客户端使用相同 action ID 重试。
- 在结算期间停止 MySQL，恢复后确认资产只变化一次。
- 使用 1,000 个模拟 WebSocket 客户端持续进行匹配和动作。
- 验证普通动作 p95 小于 300ms，命令队列和 Outbox 无持续积压。

## 16. 分阶段迁移

### 阶段 0：生产安全与结算止损

- 生产环境强制安全密钥。
- 禁用生产环境资产和段位直改。
- 迁移前只读检查现有战绩是否存在重复 `(room_id, player_id)`；发现重复时停止迁移并生成清单，由用户确认数据处理方式，不自动批量删除。
- 新增唯一结算主记录及战绩唯一约束。
- 结算失败时不再删除 Redis 房间。
- 增加对应失败测试和 Alembic 迁移。

### 阶段 1：协议与适配边界

- 定义命令、事件和调度任务 schema。
- 前端为动作增加 `action_id`。
- 为 RabbitMQ、租约、Outbox、Presence 建立小型明确接口。
- 保留单实例适配器，使用 feature flag 控制分布式链路。

### 阶段 2：跨实例连接与事件

- 上线 `instance_id`、实例心跳和 Presence epoch。
- 上线重复连接接管。
- 上线按实例路由的玩家事件。
- 先验证跨实例聊天、语音和状态同步，不立即切换房间写入。

### 阶段 3：命令分片与房间单写

- 上线 16 个命令分片、分片租约和 Single Active Consumer。
- 上线房间 owner、fencing token、版本 CAS、命令去重和 Redis Outbox。
- 迁移匹配元数据，删除对 `_pending_players` 的运行时依赖。
- 开启双实例灰度，确认旧本地写路径已完全关闭，禁止双写。

### 阶段 4：持久任务与可靠结算

- 迁移匹配超时、AI 延迟、回合超时和掉线托管到 Redis ZSET Scheduler。
- 上线 Settlement Worker、重试队列、死信队列和重放工具。
- 清除关键流程对裸 `create_task()` 的依赖。

### 阶段 5：故障演练与扩容

- 运行真实中间件集成测试、多实例 E2E 和 1,000 连接容量测试。
- 先运行 2 个实例，再扩到 4 个实例。
- 演练 Worker、Redis、RabbitMQ 和 MySQL 短暂故障。
- 指标、告警和运维手册齐备后，才将分布式 feature flag 设为默认。

## 17. 回退策略

- 阶段 0～2 可回退到单实例模式，但保留新的结算唯一约束和安全限制。
- 阶段 3 启用后，旧本地房间写路径必须保持关闭；回退方式是将所有 16 个分片集中分配给一个健康实例，而不是重新启用双写。
- 新旧代码读取同一版本化房间信封时必须保持向后兼容；任何破坏性 schema 变更需要先完成双读，再切写入。
- RabbitMQ 或 Redis schema 变更通过新 routing key/key 前缀灰度，不原地改变正在处理的队列语义。

## 18. 实施约束

- 每个阶段单独形成实施计划，不把全部改造塞入一次提交。
- 修复现有缺陷时先补复现测试。
- 跨层协议修改同步检查后端 Handler、前端 WebSocket composable、Pinia store、测试和文档。
- 所有 Redis Lua 必须有真实 Redis 集成测试。
- 所有数据库模型变更必须提供 Alembic 迁移。
- 不进行与本设计无关的前端页面拆分或样式重构。
- 用户人工确认完整无误前不执行 `git commit`。
