# backend/app/interfaces/websocket/game_handler.py
"""斗地主游戏 WebSocket Handler：事件接收、分发与广播"""
import json
import asyncio
import logging
from typing import TYPE_CHECKING
from fastapi import WebSocket, WebSocketDisconnect
from app.interfaces.websocket.game_routes import GameWSConnectionManager
from app.domain.game.room import GamePhase

if TYPE_CHECKING:
    from app.application.game.game_app_service import GameAppService

logger = logging.getLogger("happy_doudizhu")


BASE_SCORE_MIN_BEANS = {
    20: 1000,     # 新手场底分 20，最低 1,000 豆
    80: 3000,     # 初级场底分 80，最低 3,000 豆
    300: 8000,    # 普通场底分 300，最低 8,000 豆
    900: 25000,   # 中级场底分 900，最低 25,000 豆
    2700: 80000,  # 高级场底分 2700，最低 80,000 豆
    6000: 300000, # 顶级场底分 6000，最低 300,000 豆
}
VOICE_SIGNAL_TYPES = {"offer", "answer", "ice_candidate"}
VOICE_SIGNAL_MAX_PAYLOAD_BYTES = 16 * 1024


class GameWebSocketHandler:
    """处理单个游戏 WebSocket 连接的所有事件"""

    def __init__(
        self,
        websocket: WebSocket,
        player_id: str,
        manager: GameWSConnectionManager,
        game_service: "GameAppService",
        settlement_service=None,
        connection_epoch: int = 0,
    ):
        from app.application.game.settlement_service import GameSettlementService

        self.ws = websocket
        self.player_id = player_id
        self.manager = manager
        self.service = game_service
        self.settlement_service = settlement_service or GameSettlementService()
        self.connection_epoch = connection_epoch

    async def run(self):
        await self.manager.connect(self.ws, self.player_id)

        # 检查是否有断线重连的房间
        room_state = await self.service.get_room_state(self.player_id)
        if room_state:
            await self._send({"event": "reconnected", **room_state})

        try:
            while True:
                text = await self.ws.receive_text()
                await self._handle_message(text)
        except WebSocketDisconnect:
            self.manager.disconnect(self.player_id)
            logger.info(f"游戏WS: 玩家 '{self.player_id}' 断开连接")
            # 在实际业务中可能启动托管/掉线倒计时
        except Exception as e:
            logger.error(f"游戏WS: 玩家 '{self.player_id}' 错误: {e}")
            self.manager.disconnect(self.player_id)

    async def _send(self, data: dict):
        await self.manager.send_to_player(self.player_id, data)

    async def _broadcast_room_event(self, room, event_data: dict):
        """向房间内所有在线真人玩家广播事件，支持跨实例路由"""
        from app.infrastructure.config import settings
        from app.application.game.schemas import GameEventSchema
        import uuid
        import time

        presence_service = self.ws.app.state.presence_service
        message_bus = self.ws.app.state.game_message_bus

        for p in room.players:
            if p.is_ai:
                continue

            player_view = room.get_player_view(p.id)
            msg = {**event_data, "room_state": player_view}

            # 如果玩家连接在当前实例上
            if p.id in self.manager.connections:
                await self.manager.send_to_player(p.id, msg)
            elif settings.DISTRIBUTED_MODE:
                # 跨实例中转路由
                presence = await presence_service.get_presence(p.id)
                if presence:
                    target_instance = presence.get("instance_id")
                    target_epoch = presence.get("connection_epoch")
                    if target_instance:
                        event = GameEventSchema(
                            event_id=f"evt-{uuid.uuid4().hex[:8]}",
                            event=event_data.get("event", "room_event"),
                            room_id=room.room_id,
                            room_version=room.version if hasattr(room, "version") else 0,
                            target_player_id=p.id,
                            target_connection_epoch=target_epoch,
                            payload=msg,
                            created_at=time.time(),
                            trace_id=event_data.get("trace_id", f"relay-trace-{p.id}")
                        )
                        try:
                            await message_bus.publish_event(target_instance, event)
                        except Exception as e:
                            logger.error("跨实例事件路由广播失败: player_id=%s, error=%s", p.id, e)

    async def _handle_voice_state(self, data: dict):
        room = await self.service._get_player_room(self.player_id)
        if not room:
            await self._send({"event": "error", "msg": "当前不在房间内，无法使用语音"})
            return

        await self._broadcast_room_event(
            room,
            {
                "event": "voice_state",
                "player": self.player_id,
                "enabled": bool(data.get("enabled", False)),
            },
        )

    async def _handle_voice_signal(self, data: dict):
        from app.infrastructure.config import settings
        
        room = await self.service._get_player_room(self.player_id)
        if not room:
            await self._send({"event": "error", "msg": "当前不在房间内，无法发送语音信号"})
            return

        target_player = data.get("target_player")
        room_player_ids = {p.id for p in room.players if not p.is_ai}
        if target_player not in room_player_ids:
            await self._send({"event": "error", "msg": "语音信令目标不在当前房间"})
            return

        signal_type = data.get("signal_type")
        if signal_type not in VOICE_SIGNAL_TYPES:
            await self._send({"event": "error", "msg": "不支持的语音信令类型"})
            return

        payload = data.get("payload")
        if not isinstance(payload, dict):
            await self._send({"event": "error", "msg": "语音信令内容格式不正确"})
            return

        payload_size = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        if payload_size > VOICE_SIGNAL_MAX_PAYLOAD_BYTES:
            await self._send({"event": "error", "msg": "语音信令内容过大"})
            return

        msg = {
            "event": "voice_signal",
            "player": self.player_id,
            "target_player": target_player,
            "signal_type": signal_type,
            "payload": payload,
        }

        if target_player in self.manager.connections:
            await self.manager.send_to_player(target_player, msg)
        elif settings.DISTRIBUTED_MODE:
            from app.application.game.schemas import GameEventSchema
            import uuid
            import time

            presence_service = self.ws.app.state.presence_service
            message_bus = self.ws.app.state.game_message_bus

            presence = await presence_service.get_presence(target_player)
            if presence:
                target_instance = presence.get("instance_id")
                target_epoch = presence.get("connection_epoch")
                if target_instance:
                    event = GameEventSchema(
                        event_id=f"v-sig-{uuid.uuid4().hex[:8]}",
                        event="voice_signal",
                        room_id=room.room_id,
                        room_version=0,
                        target_player_id=target_player,
                        target_connection_epoch=target_epoch,
                        payload=msg,
                        created_at=time.time(),
                        trace_id=f"v-trace-{target_player}"
                    )
                    try:
                        await message_bus.publish_event(target_instance, event)
                    except Exception as e:
                        logger.error("跨实例语音信令路由发送失败: player_id=%s, error=%s", target_player, e)

    async def _handle_message(self, text: str):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            await self._send({"event": "error", "msg": "无效的 JSON 格式"})
            return

        if isinstance(data, dict) and "action_id" not in data:
            import uuid
            data["action_id"] = f"gen-{uuid.uuid4()}"

        action = data.get("action")

        if action == "join_match":
            nickname = data.get("nickname", self.player_id)
            base_score = data.get("base_score", 10)
            
            # 加入金币准入条件核查
            from app.infrastructure.database.session import transactional_session
            from app.infrastructure.database.game_repository import SQLGameRepository
            
            with transactional_session() as db:
                repo = SQLGameRepository(db)
                profile = repo.get_or_create_profile(self.player_id, nickname)
                min_beans = BASE_SCORE_MIN_BEANS.get(base_score, 0)
                if profile.beans < min_beans:
                    await self._send({
                        "event": "error",
                        "msg": f"您的欢乐豆不足，该赛事最低需要 {min_beans} 欢乐豆"
                    })
                    return

            result = await self.service.join_match(self.player_id, nickname, auto_ai=False, base_score=base_score)
            if result.get("error"):
                await self._send({"event": "error", "msg": result["error"]})
            elif result.get("status") == "waiting":
                await self._send({"event": "match_waiting", "count": result["queue_length"]})
                asyncio.create_task(self._handle_delayed_ai_match(self.player_id, nickname, base_score))
            elif result.get("status") == "room_created":
                await self._on_room_created(result)

        elif action == "cancel_match":
            await self.service.cancel_match(self.player_id)
            await self._send({"event": "match_cancelled"})

        elif action == "call_landlord":
            score = data.get("score", 1)
            result = await self.service.handle_call(self.player_id, score)
            if result.get("error"):
                await self._send({"event": "error", "msg": result["error"]})
            else:
                room = result.get("room")
                if room:
                    # 总是先广播此次叫地主/抢地主动作
                    action_event = {"event": "call_made", "player": self.player_id, "score": score}
                    await self._broadcast_room_event(room, action_event)
                    
                    # 若此举确定了地主，延迟后广播 decided
                    if result.get("landlord"):
                        await asyncio.sleep(1.0)
                        decided_event = {
                            "event": "landlord_decided",
                            "landlord": result["landlord"],
                            "bottom_cards": result["bottom_cards"],
                            "multiplier": result["multiplier"]
                        }
                        await self._broadcast_room_event(room, decided_event)
                    # 随后继续处理 AI 回合
                    await self._process_ai_turns(room)

        elif action == "skip_call":
            result = await self.service.handle_skip_call(self.player_id)
            if result.get("error"):
                await self._send({"event": "error", "msg": result["error"]})
            else:
                room = result.get("room")
                if room:
                    # 总是先广播不叫/不抢动作
                    action_event = {"event": "call_skipped", "player": self.player_id}
                    await self._broadcast_room_event(room, action_event)
                    
                    # 若此举触发洗牌或地主确立，延迟后广播对应事件
                    if result.get("redeal"):
                        await asyncio.sleep(1.0)
                        await self._broadcast_room_event(room, {"event": "redeal"})
                    elif result.get("landlord"):
                        await asyncio.sleep(1.0)
                        decided_event = {
                            "event": "landlord_decided",
                            "landlord": result["landlord"],
                            "bottom_cards": result["bottom_cards"],
                            "multiplier": result["multiplier"]
                        }
                        await self._broadcast_room_event(room, decided_event)
                    # 随后继续处理 AI 回合
                    await self._process_ai_turns(room)

        elif action == "show_cards":
            show_multiplier = data.get("multiplier", 2)
            result = await self.service.handle_show_cards(self.player_id, show_multiplier)
            if result.get("error") or result.get("success") is False:
                await self._send({"event": "error", "msg": result.get("error", "明牌失败")})
            else:
                room = result.get("room")
                if room:
                    event = {
                        "event": "cards_shown",
                        "player": self.player_id,
                        "cards": result.get("cards", []),
                        "show_multiplier": result.get("show_multiplier", 2),
                        "total_multiplier": result.get("total_multiplier", room.multiplier),
                    }
                    await self._broadcast_room_event(room, event)

        elif action == "landlord_show":
            show = data.get("show", False)
            result = await self.service.handle_landlord_show(self.player_id, show)
            if result.get("error") or result.get("success") is False:
                await self._send({"event": "error", "msg": result.get("error", "地主明牌操作失败")})
            else:
                room = result.get("room")
                if room:
                    show_result = result.get("show_result")
                    event = {
                        "event": "landlord_show_decided",
                        "player": self.player_id,
                        "show": show,
                        "multiplier": result.get("multiplier", room.multiplier),
                    }
                    if show and show_result:
                        event["cards"] = show_result.get("cards", [])
                    await self._broadcast_room_event(room, event)
                    await self._process_ai_turns(room)

        elif action == "choose_double":
            choice = data.get("choice", "none")
            result = await self.service.handle_double_choice(self.player_id, choice)
            if result.get("error") or result.get("success") is False:
                await self._send({"event": "error", "msg": result.get("error", "加倍失败")})
            else:
                room = result.get("room")
                if room:
                    event = {
                        "event": "double_chosen",
                        "player": self.player_id,
                        "choice": choice,
                        "label": self._double_choice_label(choice),
                        "multiplier": result.get("multiplier", room.multiplier),
                    }
                    await self._broadcast_room_event(room, event)
                    if result.get("doubling_finished"):
                        event_data = {
                            "event": "doubling_finished",
                            "current_turn": result.get("next_turn"),
                            "multiplier": result.get("multiplier", room.multiplier),
                        }
                        if result.get("landlord_confirm_required"):
                            event_data["landlord_confirm_required"] = True
                        await self._broadcast_room_event(room, event_data)
                    await self._process_ai_turns(room)

        elif action == "play_cards":
            cards = data.get("cards", [])
            result = await self.service.handle_play(self.player_id, cards)
            if result.get("error"):
                await self._send({"event": "error", "msg": result["error"]})
            else:
                room = result.get("room")
                if room:
                    if result.get("game_over"):
                        event = {
                            "event": "game_over",
                            "winner": result["winner"],
                            "winner_side": result["winner_side"],
                            "scores": result["scores"],
                            "multiplier": result["multiplier"],
                            "all_hands": result["all_hands"],
                        }
                        await self._broadcast_room_event(room, event)
                        await self._on_game_over(room, result)
                    else:
                        event = {
                            "event": "cards_played",
                            "player": self.player_id,
                            "cards": result["cards_played"],
                            "card_type": result["card_type"],
                            "remaining": result["remaining"],
                        }
                        await self._broadcast_room_event(room, event)
                        await self._process_ai_turns(room)

        elif action == "pass_turn":
            result = await self.service.handle_pass(self.player_id)
            if result.get("error"):
                await self._send({"event": "error", "msg": result["error"]})
            else:
                room = result.get("room")
                if room:
                    event = {"event": "turn_passed", "player": self.player_id}
                    if result.get("new_round"):
                        event["new_round"] = True
                    await self._broadcast_room_event(room, event)
                    await self._process_ai_turns(room)

        elif action == "get_ai_hints":
            result = await self.service.get_ai_play_hints(self.player_id)
            if result.get("error"):
                await self._send({"event": "error", "msg": result["error"]})
            else:
                await self._send({
                    "event": "ai_hints",
                    "candidates": result.get("candidates", []),
                    "source": result.get("source", "douzero"),
                })

        elif action == "set_auto_play":
            enabled = bool(data.get("enabled", False))
            result = await self.service.set_auto_play(self.player_id, enabled)
            if result.get("error"):
                await self._send({"event": "error", "msg": result["error"]})
            else:
                room = result.get("room")
                event = {
                    "event": "auto_play_changed",
                    "player": self.player_id,
                    "enabled": enabled,
                }
                if room:
                    await self._broadcast_room_event(room, event)
                    if enabled:
                        asyncio.create_task(self._process_ai_turns(room))
                else:
                    await self._send(event)

        elif action == "chat":
            msg_id = data.get("msg_id", 0)
            room = await self.service._get_player_room(self.player_id)
            if room:
                event = {"event": "chat_msg", "player": self.player_id, "msg_id": msg_id}
                await self._broadcast_room_event(room, event)

        elif action == "voice_state":
            await self._handle_voice_state(data)

        elif action == "voice_signal":
            await self._handle_voice_signal(data)

        elif action == "sync_room_state":
            room_state = await self.service.get_room_state(self.player_id)
            if room_state:
                await self._send({"event": "reconnected", **room_state})
                # 重新拉起 AI 处理协程，防止重连后 AI 协程挂起不动作
                room_id = await self.service._repo.get_player_room(self.player_id)
                if room_id:
                    room = await self.service._repo.get_room(room_id)
                    if room:
                        asyncio.create_task(self._process_ai_turns(room))

        else:
            await self._send({"event": "error", "msg": f"未知动作: {action}"})

    async def _on_room_created(self, result: dict):
        """房间创建后的广播逻辑"""
        room_id = result["room_id"]
        from app.infrastructure.redis_client import redis_client
        from app.infrastructure.redis_game_repository import RedisGameRepository
        repo = RedisGameRepository(redis_client)
        room = await repo.get_room(room_id)
        if room:
            event = {
                "event": "match_success",
                "room_id": room_id,
                "players": result["players"],
            }
            await self._broadcast_room_event(room, event)
            # 发送 game_start（包含各自手牌）
            for p in room.players:
                if not p.is_ai and p.id in self.manager.connections:
                    view = room.get_player_view(p.id)
                    await self.manager.send_to_player(p.id, {
                        "event": "game_start",
                        "hand": view["hand"],
                        "players": view["players"],
                        "current_turn": room.current_turn,
                    })

            # 评估 AI 发牌阶段明牌
            ai_show_results = self.service.evaluate_ai_dealing_show(room)
            if ai_show_results:
                await self.service._repo.save_room(room)
                for show_result in ai_show_results:
                    await asyncio.sleep(1.0)
                    show_event = {
                        "event": "cards_shown",
                        "player": show_result["player_id"],
                        "cards": show_result["cards"],
                        "show_multiplier": show_result["show_multiplier"],
                        "total_multiplier": show_result["total_multiplier"],
                    }
                    await self._broadcast_room_event(room, show_event)

            # 如果首位叫牌者是 AI，等待前端发牌动画播放结束（2.5秒）后再执行 AI 回合
            current = room.current_turn
            current_player = next((p for p in room.players if p.id == current), None)
            if current_player and current_player.is_ai:
                await asyncio.sleep(2.5)
            await self._process_ai_turns(room)

    async def _process_ai_turns(self, room):
        """AI回合包装器：防并发锁校验"""
        room_id = room.room_id
        if room_id in self.manager.active_ai_rooms:
            logger.info(f"游戏WS [room={room_id}]: 已经有一个 AI 回合处理器在运行中，跳过并发请求")
            return
        self.manager.active_ai_rooms.add(room_id)
        try:
            await self._do_process_ai_turns(room)
        finally:
            self.manager.active_ai_rooms.discard(room_id)

    async def _do_process_ai_turns(self, room):
        """循环处理 AI 回合，直到轮到真人玩家"""
        logger.info(f"游戏WS [room={room.room_id}]: 开始 _do_process_ai_turns. 阶段={room.phase.value}, 当前回合={room.current_turn}")
        
        # 0. 优先处理并行的加倍阶段 (DOUBLING)
        if room.phase == GamePhase.DOUBLING:
            # 找到所有尚未做出加倍选择的 AI 玩家并依次处理
            for p in room.players:
                if p.is_ai and p.id not in room.doubling_choices:
                    await asyncio.sleep(0.5)
                    # 临时修改 current_turn 为 AI 以免被 service 的回合校验拦截
                    room.current_turn = p.id
                    logger.info(f"游戏WS [room={room.room_id}]: 触发 AI 玩家 {p.id} 加倍选择...")
                    try:
                        result = await self.service.handle_ai_turn(room)
                    except Exception as e:
                        import traceback
                        logger.error(f"游戏WS: AI 加倍自动处理异常 [room={room.room_id}, player={p.id}]: {e}\n{traceback.format_exc()}")
                        if room.phase == GamePhase.DOUBLING:
                            room.current_turn = None
                        continue
                    if room.phase == GamePhase.DOUBLING:
                        room.current_turn = None  # 恢复
                    
                    if result.get("error"):
                        logger.error(f"游戏WS: AI 加倍自动处理出错 [room={room.room_id}, player={p.id}]: {result['error']}")
                        continue
                    
                    room = result.get("room", room)
                    ai_id = result.get("ai_player")
                    choice = result.get("double_choice")
                    logger.info(f"游戏WS [room={room.room_id}]: AI 玩家 {ai_id} 加倍选择为: {choice}")
                    if choice:
                        event = {
                            "event": "double_chosen",
                            "player": ai_id,
                            "choice": choice,
                            "label": self._double_choice_label(choice),
                            "multiplier": result.get("multiplier", room.multiplier),
                        }
                        await self._broadcast_room_event(room, event)
                        if result.get("doubling_finished"):
                            logger.info(f"游戏WS [room={room.room_id}]: 加倍确认完毕")
                            event_data = {
                                "event": "doubling_finished",
                                "current_turn": result.get("next_turn"),
                                "multiplier": result.get("multiplier", room.multiplier),
                            }
                            if result.get("landlord_confirm_required"):
                                event_data["landlord_confirm_required"] = True
                            await self._broadcast_room_event(room, event_data)
                            # 继续处理后续阶段（LANDLORD_CONFIRM 或 PLAYING）
                            await self._do_process_ai_turns(room)
            return

        # 1. 处理地主明牌确认阶段 (LANDLORD_CONFIRM)
        if room.phase == GamePhase.LANDLORD_CONFIRM:
            current = room.current_turn
            current_player = next((p for p in room.players if p.id == current), None)
            if current_player and current_player.is_ai:
                await asyncio.sleep(1.5)
                try:
                    result = await self.service.handle_ai_turn(room)
                except Exception as e:
                    import traceback
                    logger.error(f"游戏WS: AI 地主明牌自动处理异常 [room={room.room_id}]: {e}\n{traceback.format_exc()}")
                    # 出错时直接跳过明牌确认进入出牌
                    room.finish_landlord_confirm()
                    await self.service._repo.save_room(room)
                    result = {"room": room, "show": False}
                
                room = result.get("room", room)
                show = result.get("show", False)
                show_result = result.get("show_result")
                
                # 如果 AI 选择了明牌，先广播明牌事件
                if show and show_result:
                    show_event = {
                        "event": "cards_shown",
                        "player": current,
                        "cards": show_result.get("cards", []),
                        "show_multiplier": show_result.get("show_multiplier", 2),
                        "total_multiplier": show_result.get("total_multiplier", room.multiplier),
                    }
                    await self._broadcast_room_event(room, show_event)
                    await asyncio.sleep(0.5)
                
                # 广播地主明牌确认结束
                event = {
                    "event": "landlord_show_decided",
                    "player": current,
                    "show": show,
                    "multiplier": room.multiplier,
                }
                if show and show_result:
                    event["cards"] = show_result.get("cards", [])
                await self._broadcast_room_event(room, event)
                
                # 继续处理后续阶段（PLAYING）
                await self._do_process_ai_turns(room)
            return

        # 2. 轮流处理叫地主 and 出牌阶段
        while room.phase in (GamePhase.CALLING, GamePhase.PLAYING):
            current = room.current_turn
            current_player = next((p for p in room.players if p.id == current), None)
            is_auto_player = bool(current_player and current in getattr(room, "auto_play_players", set()))
            if not current_player or (not current_player.is_ai and not is_auto_player):
                logger.info(f"游戏WS [room={room.room_id}]: 轮到真人玩家 {current}，跳出 AI 自动处理器")
                break
            # AI 延迟 1~2 秒模拟思考（或者直接在此睡眠）
            await asyncio.sleep(0.5)
            logger.info(f"游戏WS [room={room.room_id}]: 触发自动玩家 {current} 在阶段 {room.phase.value} 做自动决策...")
            try:
                if current_player.is_ai:
                    result = await self.service.handle_ai_turn(room)
                else:
                    result = await self.service.handle_auto_play_turn(room)
            except Exception as e:
                import traceback
                logger.error(f"游戏WS: 自动处理回合异常 [room_id={room.room_id}, player={current}]: {e}\n{traceback.format_exc()}")
                break
            if result.get("error"):
                logger.error(f"游戏WS: 自动处理 AI 回合发生错误 [room_id={room.room_id}, player={current}]: {result['error']}")
                break
            room = result.get("room", room)
            # 广播 AI 的操作
            ai_id = result.get("ai_player") or result.get("auto_player")
            logger.info(f"游戏WS [room={room.room_id}]: 自动玩家 {ai_id} 回合决策返回: {result.keys()}")
            if room.phase == GamePhase.SETTLING or result.get("game_over"):
                event = {
                    "event": "game_over",
                    "winner": result.get("winner"),
                    "winner_side": result.get("winner_side"),
                    "scores": result.get("scores", {}),
                    "multiplier": result.get("multiplier", 1),
                    "all_hands": result.get("all_hands", {}),
                }
                await self._broadcast_room_event(room, event)
                await self._on_game_over(room, result)
                break
            elif "score" in result:
                score = result["score"]
                if score > 0:
                    action_event = {"event": "call_made", "player": ai_id, "score": score}
                else:
                    action_event = {"event": "call_skipped", "player": ai_id}
                await self._broadcast_room_event(room, action_event)

                if result.get("redeal"):
                    await asyncio.sleep(1.0)
                    await self._broadcast_room_event(room, {"event": "redeal"})
                    continue
                elif result.get("landlord"):
                    await asyncio.sleep(1.0)
                    decided_event = {
                        "event": "landlord_decided",
                        "landlord": result["landlord"],
                        "bottom_cards": result.get("bottom_cards", []),
                        "multiplier": result.get("multiplier", 1),
                    }
                    await self._broadcast_room_event(room, decided_event)
                    # AI 获得地主身份，需在当前 AI 回合内递归调用处理后续的地主明牌/加倍等流程，防止退出循环导致流程卡死
                    await self._do_process_ai_turns(room)
                    break
            elif result.get("cards_played"):
                event = {
                    "event": "cards_played",
                    "player": ai_id,
                    "cards": result["cards_played"],
                    "card_type": result.get("card_type"),
                    "remaining": result.get("remaining"),
                }
                await self._broadcast_room_event(room, event)
            elif result.get("next_turn"):
                event = {"event": "turn_passed", "player": ai_id}
                await self._broadcast_room_event(room, event)

    async def _on_game_over(self, room, result: dict) -> bool:
        """游戏结束后的清理与结算入库"""
        try:
            self.settlement_service.settle(room, result)
        except Exception:
            logger.exception(
                "游戏结算入库失败，保留房间等待后续恢复: room_id=%s",
                room.room_id,
            )
            await self.service._repo.save_room(room)
            return False

        player_ids = [p.id for p in room.players]
        await self.service.cleanup_room(room.room_id, player_ids)
        return True

    async def _handle_delayed_ai_match(self, player_id: str, nickname: str, base_score: int):
        """延迟 3 秒尝试匹配机器人"""
        await asyncio.sleep(3)
        result = await self.service.match_ai_for_player(player_id, nickname, base_score=base_score)
        if result and result.get("status") == "room_created":
            await self._on_room_created(result)

    def _double_choice_label(self, choice: str) -> str:
        return {
            "double": "加倍",
            "super": "超级加倍",
            "none": "不加倍",
        }.get(choice, "不加倍")
