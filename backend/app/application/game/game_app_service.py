# backend/app/application/game/game_app_service.py
"""游戏编排服务：匹配、房间管理、游戏流程控制"""
import asyncio
import uuid
import logging
from typing import Optional, List, Dict
from app.domain.game.room import GameRoom, Player, GamePhase
from app.domain.game.ai_strategy import ai_decide_call, ai_decide_play, build_ai_context
from app.infrastructure.redis_game_repository import RedisGameRepository

logger = logging.getLogger("hmp_ws_service")

AI_NAMES = ["机器人小明", "机器人小红", "机器人小刚", "机器人小芳", "机器人小李"]


class GameAppService:
    """游戏应用层编排服务"""

    MATCH_TIMEOUT_SECONDS = 10

    def __init__(self, repo: RedisGameRepository):
        self._repo = repo
        # 维护一份等待中的玩家信息 (player_id -> nickname)
        self._pending_players: Dict[str, str] = {}

    async def join_match(self, player_id: str, nickname: str, auto_ai: bool = True, base_score: int = 10) -> dict:
        """玩家加入匹配队列"""
        # 检查是否已在房间中
        existing_room = await self._repo.get_player_room(player_id)
        if existing_room:
            return {"error": "你已在游戏房间中", "room_id": existing_room}

        self._pending_players[player_id] = nickname
        await self._repo.add_to_match_queue(player_id, base_score=base_score)
        queue_len = await self._repo.get_match_queue_length(base_score=base_score)

        if queue_len >= 3:
            # 凑够3人，创建房间
            player_ids = await self._repo.pop_match_players(3, base_score=base_score)
            if len(player_ids) >= 3:
                return await self._create_room(player_ids, base_score=base_score)
        elif auto_ai:
            # 不够3人，但启用了自动机器人，则将当前在队列中的人全部弹出，用 AI 补齐并开局
            player_ids = await self._repo.pop_match_players(queue_len, base_score=base_score)
            if player_ids:
                return await self.fill_with_ai(player_ids, base_score=base_score)

        return {"status": "waiting", "queue_length": queue_len}

    async def match_ai_for_player(self, player_id: str, nickname: str, base_score: int) -> Optional[dict]:
        """强制为某个玩家匹配 AI 并开局（如果在队列中），若队列里有其他真人玩家也一并拉入"""
        existing_room = await self._repo.get_player_room(player_id)
        if existing_room:
            return None

        removed = await self._repo.remove_from_match_queue(player_id, base_score=base_score)
        if removed and removed > 0:
            self._pending_players[player_id] = nickname
            player_ids = [player_id]
            # 尝试拉入队列中其他正在等待的真人玩家（最多2人）
            others = await self._repo.pop_match_players(2, base_score=base_score)
            if others:
                player_ids.extend(others)
            return await self.fill_with_ai(player_ids, base_score=base_score)
        return None

    async def fill_with_ai(self, player_ids: List[str], base_score: int = 10) -> dict:
        """用 AI 填充不足的玩家位并创建房间"""
        import random
        ai_count = 3 - len(player_ids)
        ai_names = random.sample(AI_NAMES, ai_count)
        for i in range(ai_count):
            ai_id = f"ai_bot_{uuid.uuid4().hex[:8]}"
            player_ids.append(ai_id)
            self._pending_players[ai_id] = ai_names[i]
        return await self._create_room(player_ids, base_score=base_score)

    async def _create_room(self, player_ids: List[str], base_score: int = 10) -> dict:
        """创建游戏房间并发牌"""
        room_id = f"room_{uuid.uuid4().hex[:12]}"
        players = []
        for pid in player_ids:
            is_ai = pid.startswith("ai_bot_")
            nickname = self._pending_players.get(pid, pid)
            players.append(Player(id=pid, nickname=nickname, is_ai=is_ai, is_online=True))
            # 清理临时数据
            self._pending_players.pop(pid, None)

        room = GameRoom.create(room_id, players, base_score=base_score)
        room.deal()

        # 保存到 Redis
        await self._repo.save_room(room)
        for pid in player_ids:
            await self._repo.set_player_room(pid, room_id)

        logger.info(f"游戏房间 {room_id} 已创建: {[p.nickname for p in players]}")
        return {
            "status": "room_created",
            "room_id": room_id,
            "players": [{"id": p.id, "nickname": p.nickname, "is_ai": p.is_ai} for p in players],
        }

    async def cancel_match(self, player_id: str) -> dict:
        """取消匹配"""
        for bs in [10, 20, 80, 300, 900, 2700, 6000]:
            await self._repo.remove_from_match_queue(player_id, base_score=bs)
        self._pending_players.pop(player_id, None)
        return {"status": "cancelled"}

    async def _get_player_room(self, player_id: str) -> Optional[GameRoom]:
        """获取玩家所在的房间"""
        room_id = await self._repo.get_player_room(player_id)
        if not room_id:
            return None
        return await self._repo.get_room(room_id)

    async def handle_call(self, player_id: str, score: int) -> dict:
        """处理叫地主"""
        room = await self._get_player_room(player_id)
        if not room:
            return {"error": "你不在任何房间中"}
        result = room.call_landlord(player_id, score)
        if result.get("redeal"):
            room.deal()
        await self._repo.save_room(room)
        result["room"] = room
        return result

    async def handle_skip_call(self, player_id: str) -> dict:
        """处理不叫"""
        room = await self._get_player_room(player_id)
        if not room:
            return {"error": "你不在任何房间中"}
        result = room.skip_call(player_id)
        if result.get("redeal"):
            room.deal()
        await self._repo.save_room(room)
        result["room"] = room
        return result

    async def handle_play(self, player_id: str, card_ids: List[int]) -> dict:
        """处理出牌"""
        room = await self._get_player_room(player_id)
        if not room:
            return {"error": "你不在任何房间中"}
        result = room.play_cards(player_id, card_ids)
        await self._repo.save_room(room)
        result["room"] = room
        return result

    async def handle_pass(self, player_id: str) -> dict:
        """处理不出"""
        room = await self._get_player_room(player_id)
        if not room:
            return {"error": "你不在任何房间中"}
        result = room.pass_turn(player_id)
        await self._repo.save_room(room)
        result["room"] = room
        return result

    async def handle_ai_turn(self, room: GameRoom) -> dict:
        """处理 AI 回合"""
        ai_id = room.current_turn
        if room.phase == GamePhase.CALLING:
            await asyncio.sleep(1)  # AI 思考延迟
            hand = room.hands[ai_id]
            score = ai_decide_call(hand)
            if score > 0:
                # 确保叫分高于当前最高分
                current_max = max(room._call_scores.values()) if room._call_scores else 0
                if room._call_round == 1:
                    # 第一轮：叫分增量限制为+1，避免直接叫3分导致流程提早结束
                    proposed = current_max + 1
                    if proposed <= score:
                        score = proposed
                    else:
                        score = 0
                else:
                    if score <= current_max:
                        score = 0
            if score > 0:
                result = room.call_landlord(ai_id, score)
            else:
                result = room.skip_call(ai_id)
            if result.get("redeal"):
                room.deal()
            await self._repo.save_room(room)
            result["room"] = room
            result["ai_player"] = ai_id
            result["score"] = score
            return result

        elif room.phase == GamePhase.PLAYING:
            await asyncio.sleep(1)  # AI 思考延迟
            hand = room.hands[ai_id]
            last_cp = room.last_play.card_play
            must_play = (room.last_play.player is None)
            ctx = build_ai_context(room, ai_id)
            # 使用 AI 策略决策出牌 (包含 DouZero 神经网络与规则引擎降级逻辑)
            cards = ai_decide_play(hand, last_cp, must_play, ctx)
            if cards:
                result = room.play_cards(ai_id, cards)
            else:
                result = room.pass_turn(ai_id)
            await self._repo.save_room(room)
            result["room"] = room
            result["ai_player"] = ai_id
            return result

        return {"error": "AI 当前无法操作"}

    async def get_room_state(self, player_id: str) -> Optional[dict]:
        """获取玩家可见的房间状态 (用于断线重连)"""
        room = await self._get_player_room(player_id)
        if not room:
            return None
        return room.get_player_view(player_id)

    async def cleanup_room(self, room_id: str, player_ids: List[str]) -> None:
        """清理已结束的游戏房间"""
        await self._repo.delete_room(room_id)
        for pid in player_ids:
            if not pid.startswith("ai_bot_"):
                await self._repo.remove_player_room(pid)
