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


def _distributed_action_events(action, player_id, result, room, phase_before):
    """把一次领域动作转换成前端已经支持的游戏事件。"""
    events = []
    if action in ("call_landlord", "skip_call") or (
        action == "trigger_ai" and phase_before == "CALLING"
    ):
        score = int(result.get("score", 0))
        if action == "call_landlord" or score > 0:
            events.append({"event": "call_made", "player": player_id, "score": score or 1})
        else:
            events.append({"event": "call_skipped", "player": player_id})
        if result.get("redeal"):
            events.append({"event": "redeal"})
        elif result.get("landlord"):
            events.append(
                {
                    "event": "landlord_decided",
                    "landlord": result["landlord"],
                    "bottom_cards": result.get("bottom_cards", []),
                    "multiplier": result.get("multiplier", room.multiplier),
                }
            )
    elif action in ("choose_double", "trigger_ai") and phase_before == "DOUBLING":
        choice = result.get("double_choice", result.get("choice", "none"))
        events.append(
            {
                "event": "double_chosen",
                "player": player_id,
                "choice": choice,
                "label": {"double": "加倍", "super": "超级加倍"}.get(choice, "不加倍"),
                "multiplier": result.get("multiplier", room.multiplier),
            }
        )
        if result.get("doubling_finished"):
            event = {
                "event": "doubling_finished",
                "current_turn": result.get("next_turn"),
                "multiplier": result.get("multiplier", room.multiplier),
            }
            if result.get("landlord_confirm_required"):
                event["landlord_confirm_required"] = True
            events.append(event)
    elif action in ("landlord_show", "trigger_ai") and phase_before == "LANDLORD_CONFIRM":
        show_result = result.get("show_result")
        event = {
            "event": "landlord_show_decided",
            "player": player_id,
            "show": bool(result.get("show")),
            "multiplier": result.get("multiplier", room.multiplier),
        }
        if show_result:
            event["cards"] = show_result.get("cards", [])
        events.append(event)
    elif action == "show_cards":
        events.append(
            {
                "event": "cards_shown",
                "player": player_id,
                "cards": result.get("cards", []),
                "show_multiplier": result.get("show_multiplier", 2),
                "total_multiplier": result.get("total_multiplier", room.multiplier),
            }
        )
    elif action == "set_auto_play":
        events.append(
            {
                "event": "auto_play_changed",
                "player": player_id,
                "enabled": bool(result.get("enabled")),
            }
        )
    elif action in ("play_cards", "trigger_ai", "trigger_auto_play") and result.get("game_over"):
        events.append(
            {
                "event": "game_over",
                "winner": result["winner"],
                "winner_side": result["winner_side"],
                "scores": result["scores"],
                "multiplier": result["multiplier"],
                "all_hands": result["all_hands"],
            }
        )
    elif action in ("play_cards", "trigger_ai", "trigger_auto_play") and result.get("cards_played"):
        events.append(
            {
                "event": "cards_played",
                "player": player_id,
                "cards": result["cards_played"],
                "card_type": result.get("card_type"),
                "remaining": result.get("remaining"),
            }
        )
    elif action in ("pass_turn", "trigger_ai", "trigger_auto_play") and result.get("next_turn"):
        event = {"event": "turn_passed", "player": player_id}
        if result.get("new_round"):
            event["new_round"] = True
        events.append(event)
    return events


async def _build_distributed_outbox_events(app_instance, room, event_payloads, trace_id):
    from app.application.game.schemas import GameEventSchema
    import time
    import uuid

    events = []
    presence_service = app_instance.state.presence_service
    next_version = int(getattr(room, "envelope_version", 0)) + 1
    for player in room.players:
        if player.is_ai:
            continue
        presence = await presence_service.get_presence(player.id)
        epoch = int((presence or {}).get("connection_epoch", 0))
        room_view = room.get_player_view(player.id)
        for payload in event_payloads:
            message = {**payload, "room_state": room_view}
            events.append(
                GameEventSchema(
                    event_id=f"evt-{uuid.uuid4().hex}",
                    event=payload["event"],
                    room_id=room.room_id,
                    room_version=next_version,
                    target_player_id=player.id,
                    target_connection_epoch=epoch,
                    payload=message,
                    created_at=time.time(),
                    trace_id=trace_id,
                )
            )
    return events


async def _schedule_distributed_follow_up(repo, room):
    """每次提交后最多安排一个后续动作，避免一个命令内多次保存同一房间。"""
    from app.application.game.schemas import ScheduledTaskSchema
    import time

    phase = room.phase.name if hasattr(room.phase, "name") else str(room.phase)
    player = None
    action = None
    delay = 15.0

    if phase == "DOUBLING":
        player = next(
            (p for p in room.players if p.is_ai and p.id not in room.doubling_choices),
            None,
        )
        if player:
            action, delay = "trigger_ai", 1.0
    elif phase in ("CALLING", "LANDLORD_CONFIRM", "PLAYING") and room.current_turn:
        player = next((p for p in room.players if p.id == room.current_turn), None)
        if player and player.is_ai:
            action = "trigger_ai"
            delay = 1.5
        elif (
            player
            and phase == "PLAYING"
            and player.id in room.auto_play_players
        ):
            action = "trigger_auto_play"
            delay = 0.1
        elif player and phase == "CALLING":
            action = "skip_call"
        elif player and phase == "LANDLORD_CONFIRM":
            action = "landlord_show"
        elif player and phase == "PLAYING":
            action = "pass_turn"

    if not player or not action or not hasattr(repo, "schedule_game_task"):
        return
    version = int(getattr(room, "envelope_version", 0))
    deadline_token = int(float(room.turn_deadline or 0) * 1000)
    task = ScheduledTaskSchema(
        task_id=f"{action}_{room.room_id}_{player.id}_{deadline_token}",
        room_id=room.room_id,
        task_type=action,
        due_at=time.time() + delay,
        expected_room_version=version,
        created_at=time.time(),
        payload={
            "player_id": player.id,
            "expected_turn_deadline": room.turn_deadline,
        },
    )
    await repo.schedule_game_task(task)


async def dispatch_game_command(app_instance: FastAPI, command):
    """消费一个房间命令，并且只执行一次房间 CAS 提交。"""
    from app.infrastructure.game.context import current_outbox_events, current_command_id
    from app.infrastructure.config import settings
    import binascii

    game_service = app_instance.state.game_service
    repo = game_service._repo
    room_id = command.room_id
    action = command.action
    payload = command.payload

    room = await repo.get_room(room_id)
    if not room:
        logger.warning("[dispatch_game_command] Room %s not found.", room_id)
        return

    expected_version = payload.get("expected_room_version")
    if expected_version is not None and int(expected_version) != int(room.envelope_version):
        phase = room.phase.name if hasattr(room.phase, "name") else str(room.phase)
        target_player_id = payload.get("player_id", command.player_id)
        target_player = next(
            (player for player in room.players if player.id == target_player_id),
            None,
        )
        expected_turn_deadline = payload.get("expected_turn_deadline")
        deadline_matches = (
            expected_turn_deadline is not None
            and float(expected_turn_deadline) == float(room.turn_deadline)
        )
        still_applicable = False
        if action == "trigger_ai" and target_player and target_player.is_ai:
            if phase == "DOUBLING":
                still_applicable = target_player_id not in room.doubling_choices
            else:
                still_applicable = room.current_turn == target_player_id
        elif action == "trigger_auto_play":
            still_applicable = (
                phase == "PLAYING"
                and room.current_turn == target_player_id
                and target_player_id in room.auto_play_players
            )
        elif action == "skip_call":
            still_applicable = (
                phase == "CALLING" and room.current_turn == target_player_id
            )
        elif action == "pass_turn":
            still_applicable = (
                phase == "PLAYING" and room.current_turn == target_player_id
            )
        elif action == "landlord_show":
            still_applicable = (
                phase == "LANDLORD_CONFIRM"
                and room.current_turn == target_player_id
            )

        if not still_applicable or not deadline_matches:
            logger.info(
                "[dispatch_game_command] Ignore stale command %s: expected=%s, actual=%s",
                command.command_id,
                expected_version,
                room.envelope_version,
            )
            return
        logger.info(
            "[dispatch_game_command] Continue stale-but-applicable command %s: "
            "expected=%s, actual=%s, player=%s",
            command.command_id,
            expected_version,
            room.envelope_version,
            target_player_id,
        )

    shard_id = binascii.crc32(room_id.encode("utf-8")) % 16
    token = 0
    for _ in range(15):
        token = getattr(app_instance.state, "my_held_shards", {}).get(shard_id, 0)
        if token or not settings.DISTRIBUTED_MODE:
            break
        await asyncio.sleep(0.1)
    if settings.DISTRIBUTED_MODE and not token:
        logger.error(
            "[dispatch_game_command] Drop command %s because shard %s lease is absent.",
            command.command_id,
            shard_id,
        )
        return

    room.envelope_fencing_token = token
    room.envelope_owner = settings.INSTANCE_ID
    player_id = command.player_id
    phase_before = room.phase.name if hasattr(room.phase, "name") else str(room.phase)
    token_outbox = current_outbox_events.set([])
    token_cmd = current_command_id.set(command.command_id)

    try:
        if action == "trigger_ai":
            if phase_before == "DOUBLING":
                ai_player = next(
                    (
                        p
                        for p in room.players
                        if p.is_ai and p.id not in room.doubling_choices
                    ),
                    None,
                )
                if not ai_player:
                    return
                room.current_turn = ai_player.id
                player_id = ai_player.id
            else:
                ai_player = next(
                    (p for p in room.players if p.id == room.current_turn), None
                )
                if not ai_player or not ai_player.is_ai:
                    return
                player_id = ai_player.id
            result = await game_service.handle_ai_turn(
                room, persist=False, thinking_delay=False
            )
        elif action == "trigger_auto_play":
            if (
                room.phase.name != "PLAYING"
                or room.current_turn != player_id
                or player_id not in room.auto_play_players
            ):
                return
            result = await game_service.handle_auto_play_turn(room, persist=False)
        else:
            if player_id not in {p.id for p in room.players}:
                logger.warning(
                    "[dispatch_game_command] Player %s is not in room %s.",
                    player_id,
                    room_id,
                )
                return
            if action == "call_landlord":
                result = room.call_landlord(player_id, int(payload.get("score", 1)))
            elif action == "skip_call":
                result = room.skip_call(player_id)
            elif action == "play_cards":
                result = room.play_cards(player_id, payload.get("cards", []))
            elif action == "pass_turn":
                result = room.pass_turn(player_id)
            elif action == "choose_double":
                result = room.choose_double(player_id, payload.get("choice", "none"))
            elif action == "show_cards":
                result = room.show_cards(
                    player_id, int(payload.get("show_multiplier", 2))
                )
            elif action == "landlord_show":
                show = bool(payload.get("show", False))
                show_result = room.landlord_show_cards(player_id) if show else None
                result = room.finish_landlord_confirm() if not show else show_result
                result = {
                    **result,
                    "show": show,
                    "show_result": show_result,
                    "multiplier": room.multiplier,
                }
            elif action == "set_auto_play":
                enabled = bool(payload.get("enabled", False))
                if enabled:
                    room.auto_play_players.add(player_id)
                else:
                    room.auto_play_players.discard(player_id)
                result = {
                    "success": True,
                    "player": player_id,
                    "enabled": enabled,
                }
            else:
                logger.warning(
                    "[dispatch_game_command] Unknown action %s for room %s",
                    action,
                    room_id,
                )
                return
            if result.get("redeal"):
                room.deal()

        if result.get("success") is False or result.get("error"):
            logger.warning(
                "[dispatch_game_command] Reject command %s: %s",
                command.command_id,
                result.get("error"),
            )
            return

        event_payloads = _distributed_action_events(
            action, player_id, result, room, phase_before
        )
        events = await _build_distributed_outbox_events(
            app_instance, room, event_payloads, command.trace_id
        )
        current_outbox_events.set(events)
        await repo.save_room(room)
        if result.get("game_over"):
            settlement_service = getattr(
                app_instance.state,
                "game_settlement_service",
                None,
            )
            if settlement_service is None:
                from app.application.game.settlement_service import GameSettlementService

                settlement_service = GameSettlementService()
            try:
                await asyncio.to_thread(settlement_service.settle, room, result)
            except Exception:
                logger.exception(
                    "[dispatch_game_command] Settlement failed; keep room for recovery: %s",
                    room.room_id,
                )
                return
            await game_service.cleanup_room(
                room.room_id,
                [player.id for player in room.players],
            )
            return
        await _schedule_distributed_follow_up(repo, room)
    except Exception as exc:
        logger.error(
            "[dispatch_game_command] Executing %s failed: %s",
            action,
            exc,
            exc_info=True,
        )
    finally:
        current_outbox_events.reset(token_outbox)
        current_command_id.reset(token_cmd)


async def shard_lease_coordinator(app_instance: FastAPI):
    """
    分片租约管理器协程：
    每 3 秒做一次分片拥有权盘点，并动态管理 RabbitMQ 分片 Consumer。
    """
    from app.infrastructure.redis_client import redis_client
    import time
    
    logger.info("[Lifespan] Starting shard lease coordinator...")
    instance_id = settings.INSTANCE_ID
    my_held_shards = app_instance.state.my_held_shards
    
    lease_manager = app_instance.state.lease_manager
    bus = app_instance.state.game_message_bus
    
    async def shard_command_callback(command):
        try:
            await dispatch_game_command(app_instance, command)
        except Exception as e:
            logger.error(f"[Coordinator] Failed to dispatch command {command.command_id}: {e}")

    try:
        while True:
            # 1. 扫描所有健康实例键
            keys = await redis_client.keys("game:instance:*")
            healthy_instances = []
            for k in keys:
                parts = k.split(":")
                if len(parts) >= 3:
                    healthy_instances.append(parts[2])
            
            healthy_instances.sort()
            
            if not healthy_instances:
                healthy_instances = [instance_id]
                
            if instance_id not in healthy_instances:
                healthy_instances.append(instance_id)
                healthy_instances.sort()
                
            my_index = healthy_instances.index(instance_id)
            num_instances = len(healthy_instances)
            
            # 2. 遍历 16 个分片
            for shard_id in range(16):
                should_own = (shard_id % num_instances == my_index)
                
                if should_own:
                    token = my_held_shards.get(shard_id)
                    success = False
                    
                    if token:
                        success = await lease_manager.renew_shard_lease(shard_id, instance_id, token)
                        if not success:
                            logger.warning(f"[Coordinator] Lost lease for shard {shard_id} (renew failed).")
                            my_held_shards.pop(shard_id, None)
                            await bus.unsubscribe_commands(shard_id)
                    
                    if not success:
                        new_token = await lease_manager.acquire_shard_lease(shard_id, instance_id)
                        if new_token:
                            logger.info(f"[Coordinator] Successfully acquired lease for shard {shard_id} (token={new_token}).")
                            my_held_shards[shard_id] = new_token
                            await bus.subscribe_commands(shard_id, shard_command_callback)
                else:
                    if shard_id in my_held_shards:
                        logger.info(f"[Coordinator] Releasing shard {shard_id} (assigned to other instance).")
                        my_held_shards.pop(shard_id, None)
                        await bus.unsubscribe_commands(shard_id)
            
            await asyncio.sleep(3)
    except asyncio.CancelledError:
        logger.info("[Lifespan] Stopping shard lease coordinator...")
        for shard_id in list(my_held_shards.keys()):
            try:
                await bus.unsubscribe_commands(shard_id)
            except Exception:
                pass
    except Exception as e:
        logger.error(f"[Coordinator] Error in lease loop: {e}")


def _scheduled_task_to_command(task):
    """恢复调度任务的真实目标玩家和预期房间版本。"""
    from app.application.game.schemas import GameCommandSchema
    import time

    payload = dict(task.payload)
    player_id = payload.get("player_id")
    if not player_id:
        raise ValueError(f"调度任务缺少 player_id: {task.task_id}")
    payload["expected_room_version"] = task.expected_room_version
    return GameCommandSchema(
        command_id=f"sched-{task.task_id}",
        action=task.task_type,
        room_id=task.room_id,
        player_id=player_id,
        connection_epoch=0,
        payload=payload,
        created_at=time.time(),
        trace_id=f"sched-trace-{task.task_id}",
        source_instance_id="scheduler-poller",
    )


async def scheduler_poller(app_instance: FastAPI):
    """
    后台任务：以 1 秒为周期从 Redis 延时队列中原子拉取到期的超时任务，
    并计算分片路由投递至 RabbitMQ 队列进行 Worker 执行。
    """
    from app.infrastructure.redis_client import redis_client
    from app.application.game.schemas import GameCommandSchema, ScheduledTaskSchema
    import time
    import binascii
    
    zset_key = "game:scheduler:tasks"
    hash_key = "game:scheduler:task_details"
    
    lua_script = """
    local zset_key = KEYS[1]
    local hash_key = KEYS[2]
    local now = tonumber(ARGV[1])
    
    local tids = redis.call('zrangebyscore', zset_key, 0, now)
    local results = {}
    if #tids > 0 then
        for _, tid in ipairs(tids) do
            local detail = redis.call('hget', hash_key, tid)
            if detail then
                table.insert(results, detail)
                redis.call('hdel', hash_key, tid)
            end
        end
        redis.call('zremrangebyscore', zset_key, 0, now)
    end
    return results
    """
    
    bus = app_instance.state.game_message_bus
    logger.info("[SchedulerPoller] Starting scheduler poller...")
    
    try:
        while True:
            now = time.time()
            try:
                raw_tasks = await redis_client.eval(lua_script, 2, zset_key, hash_key, now)
                if raw_tasks:
                    for raw in raw_tasks:
                        if isinstance(raw, bytes):
                            raw = raw.decode("utf-8")
                        
                        task = ScheduledTaskSchema.model_validate_json(raw)
                        
                        command = _scheduled_task_to_command(task)
                        
                        shard_id = binascii.crc32(task.room_id.encode('utf-8')) % 16
                        await bus.publish_command(shard_id, command)
                        logger.debug(f"[SchedulerPoller] Routed expired task {task.task_id} to shard {shard_id}")
            except Exception as poll_err:
                logger.error(f"[SchedulerPoller] Error scanning delay queue: {poll_err}")
                
            await asyncio.sleep(1.0)
    except asyncio.CancelledError:
        logger.info("[SchedulerPoller] Stopping scheduler poller...")


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    settings.validate_production_settings()
    
    # 0. 根据模式初始化消息总线和在线位置服务
    from app.infrastructure.game.memory_adapters import (
        MemoryMessageBus,
        MemoryPresenceService,
        MemoryLeaseManager,
        MemoryOutboxService,
        MemorySchedulerService
    )
    from app.infrastructure.game.rabbitmq_bus import RabbitMQMessageBus
    from app.infrastructure.game.redis_presence import RedisPresenceService
    from app.infrastructure.game.redis_lease import RedisLeaseManager
    from app.infrastructure.game.redis_outbox import RedisOutboxService
    from app.infrastructure.game.redis_scheduler import RedisSchedulerService
    
    dist_heartbeat_task = None
    dist_consumer_task = None
    dist_coord_task = None
    dist_scheduler_task = None
    bus = None

    if settings.DISTRIBUTED_MODE:
        bus = RabbitMQMessageBus()
        await bus.connect()
        presence = RedisPresenceService()
        lease_manager = RedisLeaseManager()
        outbox_service = RedisOutboxService()
        scheduler_service = RedisSchedulerService()
        
        app_instance.state.game_message_bus = bus
        app_instance.state.presence_service = presence
        app_instance.state.lease_manager = lease_manager
        app_instance.state.outbox_service = outbox_service
        app_instance.state.scheduler_service = scheduler_service
        app_instance.state.my_held_shards = {}
        
        dist_heartbeat_task = asyncio.create_task(instance_heartbeat_sender(app_instance))
        dist_consumer_task = asyncio.create_task(instance_event_consumer(app_instance, bus))
        dist_coord_task = asyncio.create_task(shard_lease_coordinator(app_instance))
        dist_scheduler_task = asyncio.create_task(scheduler_poller(app_instance))
    else:
        bus = MemoryMessageBus()
        presence = MemoryPresenceService()
        lease_manager = MemoryLeaseManager()
        outbox_service = MemoryOutboxService()
        scheduler_service = MemorySchedulerService(bus)
        
        app_instance.state.game_message_bus = bus
        app_instance.state.presence_service = presence
        app_instance.state.lease_manager = lease_manager
        app_instance.state.outbox_service = outbox_service
        app_instance.state.scheduler_service = scheduler_service
        app_instance.state.my_held_shards = {s: 1 for s in range(16)}

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
    game_repo = RedisGameRepository(
        redis_client,
        presence_service=app_instance.state.presence_service,
        message_bus=app_instance.state.game_message_bus,
        outbox_service=app_instance.state.outbox_service
    )
    game_service = GameAppService(game_repo)
    from app.application.game.settlement_service import GameSettlementService
    game_settlement_service = GameSettlementService()

    # 状态保留于 FastAPI app.state
    app_instance.state.websocket_manager = websocket_manager
    app_instance.state.storage_adapter = storage_adapter
    app_instance.state.upload_service = upload_service
    app_instance.state.mq_adapter = mq_adapter
    app_instance.state.game_ws_manager = game_ws_manager
    app_instance.state.game_service = game_service
    app_instance.state.game_settlement_service = game_settlement_service
    app_instance.state.scheduler_service = scheduler_service

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
        if dist_coord_task:
            dist_coord_task.cancel()
        if dist_scheduler_task:
            dist_scheduler_task.cancel()
        await asyncio.gather(
            dist_heartbeat_task, 
            dist_consumer_task, 
            dist_coord_task,
            dist_scheduler_task,
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
