from abc import ABC, abstractmethod
from typing import Callable, Awaitable, Optional, List, Dict, Any
from app.application.game.schemas import GameCommandSchema, GameEventSchema, ScheduledTaskSchema

class IGameMessageBus(ABC):
    """游戏消息总线接口：处理跨实例的分布式命令和事件路由。"""

    @abstractmethod
    async def publish_command(self, shard_id: int, command: GameCommandSchema) -> None:
        """发布游戏命令到特定分片的队列。"""
        pass

    @abstractmethod
    async def subscribe_commands(
        self, 
        shard_id: int, 
        callback: Callable[[GameCommandSchema], Awaitable[None]]
    ) -> None:
        """订阅特定分片的命令队列，收到后执行 callback 异步处理。"""
        pass

    @abstractmethod
    async def unsubscribe_commands(self, shard_id: int) -> None:
        """取消订阅特定分片的命令队列，释放消费者资源。"""
        pass

    @abstractmethod
    async def publish_event(self, instance_id: str, event: GameEventSchema) -> None:
        """向特定应用网关实例（instance_id）上的特定玩家分发个人视角事件。"""
        pass

class IPresenceService(ABC):
    """玩家连接位置与代次（Presence）服务接口：确保重复登录 kickout 及消息的精准路由。"""

    @abstractmethod
    async def get_presence(self, player_id: str) -> Optional[Dict[str, Any]]:
        """获取玩家当前 Presence 位置元数据（如 instance_id, connection_epoch, connected_at, last_seen_at）。"""
        pass

    @abstractmethod
    async def set_presence(self, player_id: str, instance_id: str, epoch: int) -> None:
        """更新/设置玩家当前在线位置并保持心跳。"""
        pass

    @abstractmethod
    async def refresh_presence(self, player_id: str, instance_id: str, epoch: int) -> bool:
        """仅当实例和连接代次匹配时续期 Presence。"""
        pass

    @abstractmethod
    async def increment_epoch(self, player_id: str) -> int:
        """原子递增玩家的连接代次（epoch），返回新的代次。"""
        pass

    @abstractmethod
    async def remove_presence(self, player_id: str, expected_epoch: int) -> bool:
        """在期望代次匹配的情况下，安全移除玩家的 Presence 在线记录。"""
        pass

class ILeaseManager(ABC):
    """租约管理器接口：在多实例冲突下，保证分片的所有权独占以及房间的单写隔离。"""

    @abstractmethod
    async def acquire_shard_lease(self, shard_id: int, instance_id: str) -> Optional[int]:
        """尝试为特定实例抢占特定分片的优先所有权租约。若成功返回 fencing token，失败返回 None。"""
        pass

    @abstractmethod
    async def renew_shard_lease(self, shard_id: int, instance_id: str, token: int) -> bool:
        """续约分片租约，如果续约失败或被抢占，返回 False。"""
        pass

    @abstractmethod
    async def acquire_room_lease(self, room_id: str, shard_id: int, token: int) -> bool:
        """在当前分片拥有者（fencing token）的合法前提下，原子锁定/获取房间租约。"""
        pass

class IOutboxService(ABC):
    """事件信箱（Outbox）服务接口：可靠存储玩家事件，确保至少一次投递语义。"""

    @abstractmethod
    async def save_event(self, room_id: str, event: GameEventSchema) -> None:
        """在一个原子事务中保存新房间状态并将个人事件写入 Outbox。"""
        pass

    @abstractmethod
    async def save_events(self, room_id: str, events: List[GameEventSchema]) -> None:
        """原子批量保存房间状态并将多条事件写入 Outbox。"""
        pass

    @abstractmethod
    async def get_pending_events(self, room_id: str) -> List[GameEventSchema]:
        """获取当前房间未确认发送的事件列表。"""
        pass

    @abstractmethod
    async def acknowledge_event(self, room_id: str, event_id: str) -> None:
        """确认特定事件已成功投递（Relay 已经发送并收到 MQ 确认），将其从 Outbox 移除。"""
        pass

class ISchedulerService(ABC):
    """调度服务接口：处理超时托管、AI延迟和匹配超时的异步调度任务。"""

    @abstractmethod
    async def schedule_task(self, task: ScheduledTaskSchema) -> None:
        """调度一个未来指定时间执行的任务。"""
        pass

    @abstractmethod
    async def cancel_task(self, task_id: str) -> None:
        """根据 task_id 撤销一个尚未执行的到期任务。"""
        pass
