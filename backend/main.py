import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from functools import partial

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI

# 加载环境变量
load_dotenv()

# 配置日志
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "log")
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

log_path = os.path.join(LOG_DIR, "happy_doudizhu.log")

# 使用 RotatingFileHandler 以支持日志文件轮转与自动清理，防范磁盘满溢
# 初始化全局日志系统 (从基础设施层导入并装配)
from app.infrastructure.logging.setup import setup_logging

setup_logging()

logger = logging.getLogger("happy_doudizhu")

# 引入 DDD 重构层
from app.infrastructure.database.session import init_db, should_auto_init_db
from app.infrastructure.config import settings
from app.infrastructure.storage.local_storage_adapter import LocalStorageAdapter
from app.infrastructure.mq.rabbitmq_adapter import RabbitMQAdapter
from app.application.upload.upload_app_service import UploadAppService
from app.interfaces.websocket.ws_routes import WSConnectionManager

# 引入路由适配器
from app.interfaces.api.message_routes import router as message_router
from app.interfaces.api.upload_routes import router as upload_router
from app.interfaces.api.audit_log_routes import router as audit_log_router
from app.interfaces.web.index_route import router as index_router
from app.interfaces.websocket.ws_routes import router as ws_router
from app.interfaces.websocket.game_routes import router as game_ws_router
from app.interfaces.api.game_routes import router as game_api_router

app = FastAPI(title="Happy Doudizhu Service (DDD)")

# CORS 中间件 (支持 Vue 前端跨域访问)
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件目录
from fastapi.staticfiles import StaticFiles

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# 挂载上传文件目录，以便访问上传的本地头像
uploads_dir = os.path.join(BASE_DIR, "uploads")
if not os.path.exists(uploads_dir):
    os.makedirs(uploads_dir)
app.mount("/api/uploads", StaticFiles(directory=uploads_dir), name="uploads")

# 注册所有模块化路由
app.include_router(index_router)
app.include_router(message_router)
app.include_router(upload_router)
app.include_router(ws_router)
app.include_router(audit_log_router)
app.include_router(game_ws_router)
app.include_router(game_api_router)


async def on_mq_message_received(app_instance: FastAPI, data: dict):
    """当监听到 RabbitMQ 消息时的业务处理逻辑（推送给在线的客户端）"""
    receiver = data.get("receiver")
    if not receiver:
        logger.warning("RabbitMQ message missing 'receiver'")
        return

    push_payload = {
        "type": "site_message",
        "data": {
            "id": data.get("id"),
            "sender": data.get("sender", "system"),
            "receiver": receiver,
            "content": data.get("content", ""),
            "is_read": data.get("is_read", 0),
            "created_at": data.get("created_at", "")
        }
    }

    manager: WSConnectionManager = app_instance.state.websocket_manager
    if receiver in manager.active_connections:
        await manager.send_personal_message(
            json.dumps(push_payload, ensure_ascii=False), receiver
        )
        logger.info(f"MQ consumer: 已推送 site_message id={data.get('id')} → {receiver}")
    else:
        logger.info(f"MQ consumer: {receiver} 离线，跳过推送 (消息已入库)")


async def mq_connection_manager(app_instance: FastAPI):
    """后台协程：管理 RabbitMQ 长连接与自动重连，以及注册消费者"""
    attempt = 0
    mq_adapter: RabbitMQAdapter = app_instance.state.mq_adapter
    callback = partial(on_mq_message_received, app_instance)

    while True:
        try:
            logger.info("正在尝试建立 RabbitMQ 异步长连接...")
            await mq_adapter.connect()

            # 开启异步站内信消费者 (使用广播交换机订阅模式以适应多实例部署)
            await mq_adapter.start_consuming_broadcast(mq_adapter.exchange_name, callback)
            logger.info("RabbitMQ robust 连接建立成功，已开启广播交换机消费监听。")
            attempt = 0  # 重置重连计数

            # 维持在此循环，监测连接状态
            while mq_adapter.is_connected:
                await asyncio.sleep(5)

            logger.warning("监测到 RabbitMQ 连接意外断开，准备重新建立连接...")

        except asyncio.CancelledError:
            logger.info("MQ 重新连接管理器任务已取消。")
            break
        except Exception as e:
            attempt += 1
            delay = min(1.5 ** attempt, 30.0)  # 指数退避，最大延迟 30 秒
            logger.error(f"连接 RabbitMQ 失败 (第 {attempt} 次尝试): {e}. 将在 {delay:.1f} 秒后重试...")

            await mq_adapter.close()
            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                break


async def stale_upload_reaper(app_instance: FastAPI):
    """后台任务：周期性清理超时的临时上传目录。"""
    REAPER_INTERVAL_SECONDS = 1800  # 30 分钟
    while True:
        try:
            await asyncio.sleep(REAPER_INTERVAL_SECONDS)
            upload_service: UploadAppService = app_instance.state.upload_service
            cleaned = upload_service.cleanup_stale_uploads(timeout_hours=2.0)
            if cleaned > 0:
                logger.info(f"Stale upload cleanup completed: {cleaned} directories removed")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error running stale upload reaper: {e}")


# 声明并注入分布式或单机契约组件及其后台任务
async def instance_heartbeat_sender(app_instance: FastAPI):
    """后台任务：定时刷新实例在 Redis 中的心跳和状态"""
    from app.infrastructure.redis_client import redis_client
    import time
    
    instance_id = settings.INSTANCE_ID
    key = f"game:instance:{instance_id}"
    logger.info(f"[Lifespan] Starting instance heartbeat sender for {instance_id}")
    
    try:
        while True:
            info = {
                "instance_id": instance_id,
                "heartbeat_at": time.time(),
                "status": "healthy"
            }
            await redis_client.set(key, json.dumps(info), ex=30)
            await asyncio.sleep(10)
    except asyncio.CancelledError:
        logger.info(f"[Lifespan] Stopping instance heartbeat sender for {instance_id}")
        try:
            await redis_client.delete(key)
        except Exception:
            pass
    except Exception as e:
        logger.error(f"[Lifespan] Error in instance heartbeat sender: {e}")


async def instance_event_consumer(app_instance: FastAPI, bus):
    """后台任务：消费 RabbitMQ 中发往当前实例的跨实例玩家事件"""
    from app.application.game.schemas import GameEventSchema
    
    instance_id = settings.INSTANCE_ID
    queue_name = f"ddz.game.events.{instance_id}"
    routing_key = f"instance.{instance_id}"
    
    logger.info(f"[Lifespan] Starting instance event consumer for {instance_id}")
    
    try:
        channel = bus.channel
        queue = await channel.declare_queue(
            queue_name, 
            durable=True, 
            exclusive=False, 
            auto_delete=True
        )
        exchange = await channel.get_exchange(bus.event_exchange_name)
        await queue.bind(exchange, routing_key=routing_key)
        
        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process():
                    try:
                        data_str = message.body.decode("utf-8")
                        event = GameEventSchema.model_validate_json(data_str)
                        
                        game_ws_manager = app_instance.state.game_ws_manager
                        ws = game_ws_manager.connections.get(event.target_player_id)
                        
                        if ws:
                            if event.event == "kick":
                                logger.info(f"[EventConsumer] Kicking player {event.target_player_id} due to duplicate login")
                                try:
                                    await ws.close(code=1008, reason="DuplicateLogin")
                                except Exception:
                                    pass
                            else:
                                try:
                                    await ws.send_text(json.dumps(event.payload, ensure_ascii=False))
                                except Exception as e:
                                    logger.error(f"[EventConsumer] Failed to send WS message to {event.target_player_id}: {e}")
                    except Exception as e:
                        logger.error(f"[EventConsumer] Error processing cross-instance event: {e}")
    except asyncio.CancelledError:
        logger.info(f"[EventConsumer] Stopping instance event consumer for {instance_id}")
    except Exception as e:
        logger.error(f"[EventConsumer] Error in instance event consumer: {e}")


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    settings.validate_production_settings()
    
    # 0. 根据模式初始化消息总线和在线位置服务
    from app.infrastructure.game.memory_adapters import MemoryMessageBus, MemoryPresenceService
    from app.infrastructure.game.rabbitmq_bus import RabbitMQMessageBus
    from app.infrastructure.game.redis_presence import RedisPresenceService
    
    dist_heartbeat_task = None
    dist_consumer_task = None
    bus = None

    if settings.DISTRIBUTED_MODE:
        bus = RabbitMQMessageBus()
        await bus.connect()
        presence = RedisPresenceService()
        
        app_instance.state.game_message_bus = bus
        app_instance.state.presence_service = presence
        
        # 启动心跳协程和事件消费协程
        dist_heartbeat_task = asyncio.create_task(instance_heartbeat_sender(app_instance))
        dist_consumer_task = asyncio.create_task(instance_event_consumer(app_instance, bus))
    else:
        bus = MemoryMessageBus()
        presence = MemoryPresenceService()
        app_instance.state.game_message_bus = bus
        app_instance.state.presence_service = presence

    # 1. 自动创建/确认 MySQL 表结构
    if should_auto_init_db():
        try:
            init_db()
            logger.info("MySQL tables verified/created successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize MySQL tables: {e}")
    else:
        logger.info("Skipping automatic MySQL table initialization.")

    # 2. 依赖注入装配 (IoC)
    websocket_manager = WSConnectionManager()
    storage_adapter = LocalStorageAdapter()
    upload_service = UploadAppService(storage_adapter)
    mq_adapter = RabbitMQAdapter()

    from app.interfaces.websocket.game_routes import GameWSConnectionManager
    from app.application.game.game_app_service import GameAppService
    from app.infrastructure.redis_game_repository import RedisGameRepository
    from app.infrastructure.redis_client import redis_client

    game_ws_manager = GameWSConnectionManager()
    game_repo = RedisGameRepository(redis_client)
    game_service = GameAppService(game_repo)

    # 状态保留于 FastAPI app.state
    app_instance.state.websocket_manager = websocket_manager
    app_instance.state.storage_adapter = storage_adapter
    app_instance.state.upload_service = upload_service
    app_instance.state.mq_adapter = mq_adapter
    app_instance.state.game_ws_manager = game_ws_manager
    app_instance.state.game_service = game_service

    # 启动时清理超时的孤儿临时上传目录
    upload_service.cleanup_stale_uploads(timeout_hours=2.0)

    # 3. 启动后台协程任务
    reaper_task = asyncio.create_task(stale_upload_reaper(app_instance))
    mq_manager_task = asyncio.create_task(mq_connection_manager(app_instance))

    yield

    # 4. 关闭清理后台任务
    reaper_task.cancel()
    try:
        await reaper_task
    except asyncio.CancelledError:
        pass

    # 5. 取消并断开 RabbitMQ 资源
    mq_manager_task.cancel()
    try:
        await mq_manager_task
    except asyncio.CancelledError:
        pass

    await mq_adapter.close()
    logger.info("Lifespan shutdown: MQ resources cleaned up successfully.")

    # 6. 关闭分布式组件资源
    if settings.DISTRIBUTED_MODE:
        if dist_heartbeat_task:
            dist_heartbeat_task.cancel()
        if dist_consumer_task:
            dist_consumer_task.cancel()
        await asyncio.gather(
            dist_heartbeat_task, 
            dist_consumer_task, 
            return_exceptions=True
        )
        if bus:
            await bus.close()
            logger.info("Lifespan shutdown: Distributed MessageBus closed.")


# 注册 FastAPI 生命周期挂载点
app.router.lifespan_context = lifespan

if __name__ == "__main__":
    logger.info("Starting HMP WS Service on http://127.0.0.1:18088")
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=True,
        reload_dirs=["app", "templates"],
        ws_per_message_deflate=False,
    )
