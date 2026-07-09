from pydantic import BaseModel, Field
from typing import Dict, Any

class GameCommandSchema(BaseModel):
    schema_version: str = Field(default="1.0", description="版本号")
    command_id: str = Field(..., description="命令唯一ID，通常是前端生成的 action_id，或调度器生成的 task_id")
    action: str = Field(..., description="动作类型，例如 join_match, play_cards 等")
    room_id: str = Field(..., description="所属房间ID")
    player_id: str = Field(..., description="操作玩家ID")
    connection_epoch: int = Field(..., description="连接代次")
    payload: Dict[str, Any] = Field(default_factory=dict, description="动作具体负载数据")
    created_at: float = Field(..., description="创建时间戳")
    trace_id: str = Field(..., description="请求追踪ID")
    source_instance_id: str = Field(..., description="网关实例ID")

class GameEventSchema(BaseModel):
    schema_version: str = Field(default="1.0", description="版本号")
    event_id: str = Field(..., description="事件唯一ID")
    event: str = Field(..., description="事件类型，例如 cards_played, game_over 等")
    room_id: str = Field(..., description="所属房间ID")
    room_version: int = Field(..., description="房间版本号")
    target_player_id: str = Field(..., description="接收事件的玩家ID")
    target_connection_epoch: int = Field(..., description="目标连接代次")
    payload: Dict[str, Any] = Field(default_factory=dict, description="玩家个人视角的事件具体数据")
    created_at: float = Field(..., description="创建时间戳")
    trace_id: str = Field(..., description="请求追踪ID")

class ScheduledTaskSchema(BaseModel):
    task_id: str = Field(..., description="任务唯一ID")
    due_at: float = Field(..., description="到期时间戳")
    room_id: str = Field(..., description="所属房间ID")
    task_type: str = Field(..., description="任务类型，例如 match_timeout, ai_thinking, turn_timeout 等")
    expected_room_version: int = Field(..., description="预期房间版本，过期将被安全忽略")
    payload: Dict[str, Any] = Field(default_factory=dict, description="任务执行具体负载数据")
    created_at: float = Field(..., description="创建时间戳")
