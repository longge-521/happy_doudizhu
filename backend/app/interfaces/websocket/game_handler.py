# backend/app/interfaces/websocket/game_handler.py
"""斗地主游戏 WebSocket Handler：事件接收、分发与广播"""
import json
import asyncio
import logging
from fastapi import WebSocket, WebSocketDisconnect
from app.interfaces.websocket.game_routes import GameWSConnectionManager
from app.application.game.game_app_service import GameAppService
from app.domain.game.room import GamePhase

logger = logging.getLogger("hmp_ws_service")


BASE_SCORE_MIN_BEANS = {
    20: 1000,     # 新手场底分 20，最低 1,000 豆
    80: 3000,     # 初级场底分 80，最低 3,000 豆
    300: 8000,    # 普通场底分 300，最低 8,000 豆
    900: 25000,   # 中级场底分 900，最低 25,000 豆
    2700: 80000,  # 高级场底分 2700，最低 80,000 豆
    6000: 300000, # 顶级场底分 6000，最低 300,000 豆
}


class GameWebSocketHandler:
    """处理单个游戏 WebSocket 连接的所有事件"""

    def __init__(
        self,
        websocket: WebSocket,
        player_id: str,
        manager: GameWSConnectionManager,
        game_service: GameAppService,
    ):
        self.ws = websocket
        self.player_id = player_id
        self.manager = manager
        self.service = game_service

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
        """向房间内所有在线真人玩家广播事件"""
        for p in room.players:
            if not p.is_ai and p.id in self.manager.connections:
                # 每个玩家收到自己的视角
                player_view = room.get_player_view(p.id)
                msg = {**event_data, "room_state": player_view}
                await self.manager.send_to_player(p.id, msg)

    async def _handle_message(self, text: str):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            await self._send({"event": "error", "msg": "无效的 JSON 格式"})
            return

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
                    event = {"event": "call_made", "player": self.player_id, "score": score}
                    if result.get("landlord"):
                        event["event"] = "landlord_decided"
                        event["landlord"] = result["landlord"]
                        event["bottom_cards"] = result["bottom_cards"]
                        event["multiplier"] = result["multiplier"]
                    await self._broadcast_room_event(room, event)
                    # 如果下一个是 AI，自动处理
                    await self._process_ai_turns(room)

        elif action == "skip_call":
            result = await self.service.handle_skip_call(self.player_id)
            if result.get("error"):
                await self._send({"event": "error", "msg": result["error"]})
            else:
                room = result.get("room")
                if room:
                    event = {"event": "call_skipped", "player": self.player_id}
                    if result.get("redeal"):
                        event["event"] = "redeal"
                    elif result.get("landlord"):
                        event["event"] = "landlord_decided"
                        event["landlord"] = result["landlord"]
                        event["bottom_cards"] = result["bottom_cards"]
                        event["multiplier"] = result["multiplier"]
                    await self._broadcast_room_event(room, event)
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

        elif action == "chat":
            msg_id = data.get("msg_id", 0)
            room = await self.service._get_player_room(self.player_id)
            if room:
                event = {"event": "chat_msg", "player": self.player_id, "msg_id": msg_id}
                await self._broadcast_room_event(room, event)

        elif action == "sync_room_state":
            room_state = await self.service.get_room_state(self.player_id)
            if room_state:
                await self._send({"event": "reconnected", **room_state})

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
            # 如果首位叫牌者是 AI
            await self._process_ai_turns(room)

    async def _process_ai_turns(self, room):
        """循环处理 AI 回合，直到轮到真人玩家"""
        while room.phase in (GamePhase.CALLING, GamePhase.PLAYING):
            current = room.current_turn
            current_player = next((p for p in room.players if p.id == current), None)
            if not current_player or not current_player.is_ai:
                break
            # AI 延迟 1~2 秒模拟思考（或者直接在此睡眠）
            await asyncio.sleep(0.5)
            result = await self.service.handle_ai_turn(room)
            if result.get("error"):
                break
            room = result.get("room", room)
            # 广播 AI 的操作
            ai_id = result.get("ai_player")
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
            elif result.get("redeal"):
                await self._broadcast_room_event(room, {"event": "redeal"})
                # 重发后继续处理可能的 AI 叫地主
                continue
            elif result.get("landlord"):
                event = {
                    "event": "landlord_decided",
                    "landlord": result["landlord"],
                    "bottom_cards": result.get("bottom_cards", []),
                    "multiplier": result.get("multiplier", 1),
                }
                await self._broadcast_room_event(room, event)
            elif result.get("cards_played"):
                event = {
                    "event": "cards_played",
                    "player": ai_id,
                    "cards": result["cards_played"],
                    "card_type": result.get("card_type"),
                    "remaining": result.get("remaining"),
                }
                await self._broadcast_room_event(room, event)
            elif "next_caller" in result:
                score = result.get("score", 0)
                if score > 0:
                    event = {"event": "call_made", "player": ai_id, "score": score}
                else:
                    event = {"event": "call_skipped", "player": ai_id}
                await self._broadcast_room_event(room, event)
            elif result.get("next_turn"):
                event = {"event": "turn_passed" if not result.get("cards_played") else "call_skipped", "player": ai_id}
                await self._broadcast_room_event(room, event)

    async def _on_game_over(self, room, result: dict):
        """游戏结束后的清理与结算入库"""
        try:
            from app.infrastructure.database.session import transactional_session
            from app.infrastructure.database.game_repository import SQLGameRepository
            from app.domain.game.entities import GameRecord

            scores = result.get("scores", {})
            with transactional_session() as db:
                repo = SQLGameRepository(db)
                for p in room.players:
                    if p.is_ai:
                        continue
                    is_landlord = (p.id == room.landlord)
                    score_change = scores.get(p.id, 0)
                    is_win = score_change > 0
                    repo.get_or_create_profile(p.id, p.nickname)
                    repo.update_profile_stats(p.id, score_change, is_win)
                    repo.update_rank_stats(p.id, is_win, room.multiplier)
                    repo.save_game_record(GameRecord(
                        room_id=room.room_id,
                        player_id=p.id,
                        role="landlord" if is_landlord else "farmer",
                        result="win" if is_win else "lose",
                        score_change=score_change,
                        multiplier=room.multiplier,
                    ))
        except Exception as e:
            logger.error(f"游戏结算入库失败: {e}")

        # 清理 Redis 房间
        player_ids = [p.id for p in room.players]
        await self.service.cleanup_room(room.room_id, player_ids)

    async def _handle_delayed_ai_match(self, player_id: str, nickname: str, base_score: int):
        """延迟 3 秒尝试匹配机器人"""
        await asyncio.sleep(3)
        result = await self.service.match_ai_for_player(player_id, nickname, base_score=base_score)
        if result and result.get("status") == "room_created":
            await self._on_room_created(result)
