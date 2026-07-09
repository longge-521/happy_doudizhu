import contextvars

# 用于在 Worker 链路中收集产生的 Outbox 事件 (List[GameEventSchema])
current_outbox_events = contextvars.ContextVar("current_outbox_events", default=None)

# 用于存储当前正在处理的游戏命令 ID，以便 Repository 自动做幂等去重
current_command_id = contextvars.ContextVar("current_command_id", default=None)
