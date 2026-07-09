# backend/app/application/game/game_app_service.py
"""游戏编排服务：匹配、房间管理、游戏流程控制"""
import asyncio
import uuid
import logging
from typing import Optional, List, Dict
from app.domain.game.room import GameRoom, Player, GamePhase
from app.domain.game.ai_strategy import ai_decide_call, ai_decide_play, ai_rank_play_candidates, build_ai_context
from app.infrastructure.redis_game_repository import RedisGameRepository

logger = logging.getLogger("happy_doudizhu")

AI_NAMES = ["机器人小明", "机器人小红", "机器人小刚", "机器人小芳", "机器人小李"]


class GameAppService:
    """游戏应用层编排服务"""

    MATCH_TIMEOUT_SECONDS = 10

    def __init__(self, repo: RedisGameRepository):
        self._repo = repo

    async def _save_match_player_meta(self, player_id: str, nickname: str, base_score: int):
        if hasattr(self._repo, "save_match_player_meta"):
            await self._repo.save_match_player_meta(player_id, nickname, base_score)

    async def join_match(self, player_id: str, nickname: str, auto_ai: bool = True, base_score: int = 10) -> dict:
        """玩家加入匹配队列"""
        # 检查是否已在房间中
        existing_room = await self._repo.get_player_room(player_id)
        if existing_room:
            return {"error": "你已在游戏房间中", "room_id": existing_room}

        await self._save_match_player_meta(player_id, nickname, base_score)
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
            await self._save_match_player_meta(player_id, nickname, base_score)
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
            await self._save_match_player_meta(ai_id, ai_names[i], base_score)
            
        return await self._create_room(player_ids, base_score=base_score)

    async def _create_room(self, player_ids: List[str], base_score: int = 10) -> dict:
        """创建游戏房间并发牌"""
        room_id = f"room_{uuid.uuid4().hex[:12]}"
        players = []
        for pid in player_ids:
            is_ai = pid.startswith("ai_bot_")
            nickname = pid
            
            if hasattr(self._repo, "get_match_player_meta"):
                meta = await self._repo.get_match_player_meta(pid)
                if meta:
                    nickname = meta.get("nickname", pid)
                    await self._repo.delete_match_player_meta(pid)

            players.append(Player(id=pid, nickname=nickname, is_ai=is_ai, is_online=True))

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
        if hasattr(self._repo, "delete_match_player_meta"):
            await self._repo.delete_match_player_meta(player_id)
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

    async def handle_double_choice(self, player_id: str, choice: str) -> dict:
        """处理玩家加倍确认"""
        room = await self._get_player_room(player_id)
        if not room:
            return {"error": "你不在任何房间中"}
        result = room.choose_double(player_id, choice)
        await self._repo.save_room(room)
        result["room"] = room
        return result

    async def handle_show_cards(self, player_id: str, show_multiplier: int) -> dict:
        """处理玩家发牌阶段明牌"""
        room = await self._get_player_room(player_id)
        if not room:
            return {"error": "你不在任何房间中"}
        result = room.show_cards(player_id, show_multiplier)
        await self._repo.save_room(room)
        result["room"] = room
        return result

    async def handle_landlord_show(self, player_id: str, show: bool) -> dict:
        """处理地主明牌确认"""
        room = await self._get_player_room(player_id)
        if not room:
            return {"error": "你不在任何房间中"}
        show_result = None
        if show:
            show_result = room.landlord_show_cards(player_id)
            if not show_result.get("success"):
                await self._repo.save_room(room)
                return show_result
        confirm_result = room.finish_landlord_confirm()
        await self._repo.save_room(room)
        return {
            "room": room,
            "show": show,
            "show_result": show_result,
            "multiplier": room.multiplier,
        }


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

    async def get_ai_play_hints(self, player_id: str) -> dict:
        """获取当前玩家的 DouZero 出牌候选提示"""
        room = await self._get_player_room(player_id)
        if not room:
            return {"error": "你不在任何房间中"}
        if room.phase != GamePhase.PLAYING:
            return {"error": "当前不在出牌阶段"}
        if room.current_turn != player_id:
            return {"error": "当前还没轮到你出牌"}

        hand = room.hands.get(player_id, [])
        last_cp = room.last_play.card_play
        must_play = room.last_play.player is None
        ctx = build_ai_context(room, player_id)
        candidates = ai_rank_play_candidates(hand, last_cp, must_play, ctx)
        return {"candidates": candidates, "source": "douzero", "room": room}

    async def set_auto_play(self, player_id: str, enabled: bool) -> dict:
        """设置真人玩家托管状态"""
        room = await self._get_player_room(player_id)
        if not room:
            return {"error": "你不在任何房间中"}
        if enabled:
            room.auto_play_players.add(player_id)
        else:
            room.auto_play_players.discard(player_id)
        await self._repo.save_room(room)
        return {"room": room, "player": player_id, "enabled": enabled}

    async def handle_auto_play_turn(self, room: GameRoom) -> dict:
        """处理真人玩家托管出牌回合"""
        player_id = room.current_turn
        if room.phase != GamePhase.PLAYING:
            return {"error": "托管只处理出牌阶段"}
        if player_id not in room.auto_play_players:
            return {"error": "当前玩家未开启托管"}

        hand = room.hands.get(player_id, [])
        last_cp = room.last_play.card_play
        must_play = room.last_play.player is None
        ctx = build_ai_context(room, player_id)
        candidates = ai_rank_play_candidates(hand, last_cp, must_play, ctx, limit=1)
        cards = candidates[0] if candidates else None

        if cards:
            result = room.play_cards(player_id, cards)
        else:
            result = room.pass_turn(player_id)
        await self._repo.save_room(room)
        result["room"] = room
        result["auto_player"] = player_id
        return result

    async def handle_ai_turn(self, room: GameRoom) -> dict:
        """处理 AI 回合"""
        ai_id = room.current_turn
        if room.phase == GamePhase.CALLING:
            await asyncio.sleep(1.5)  # AI 思考延迟 (由 1.0s 增至 1.5s)
            hand = room.hands[ai_id]
            call_level = ai_decide_call(hand)
            if room._first_bidder is None:
                # 尚未有人叫地主 -> 叫地主
                if call_level >= 2:
                    result = room.call_landlord(ai_id, 1)
                    score_res = 1
                else:
                    result = room.skip_call(ai_id)
                    score_res = 0
            else:
                # 抢地主
                if call_level >= 3:
                    result = room.call_landlord(ai_id, 1)
                    score_res = 1
                else:
                    result = room.skip_call(ai_id)
                    score_res = 0

            if result.get("redeal"):
                room.deal()
            await self._repo.save_room(room)
            result["room"] = room
            result["ai_player"] = ai_id
            result["score"] = score_res
            return result

        elif room.phase == GamePhase.LANDLORD_CONFIRM:
            await asyncio.sleep(1.5)
            # AI 地主明牌决策：牌力极强时明牌
            should_show = self._should_ai_show_cards(room, ai_id)
            show_result = None
            if should_show:
                show_result = room.landlord_show_cards(ai_id)
            confirm_result = room.finish_landlord_confirm()
            await self._repo.save_room(room)
            return {
                "room": room,
                "ai_player": ai_id,
                "landlord_show": True,
                "show": should_show,
                "show_result": show_result,
                "multiplier": room.multiplier,
            }

        elif room.phase == GamePhase.DOUBLING:
            await asyncio.sleep(1.0)
            choice = self._decide_ai_double_choice(room, ai_id)
            result = room.choose_double(ai_id, choice)
            await self._repo.save_room(room)
            result["room"] = room
            result["ai_player"] = ai_id
            result["double_choice"] = choice
            return result

        elif room.phase == GamePhase.PLAYING:
            await asyncio.sleep(1.5)  # AI 思考延迟 (由 1.0s 增至 1.5s)
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

    def _decide_ai_double_choice(self, room: GameRoom, ai_id: str) -> str:
        """保守 AI 加倍策略：牌力明显较好时加倍，否则不加倍"""
        hand = room.hands.get(ai_id, [])
        high_cards = sum(1 for card in hand if card >= 48)
        is_landlord = ai_id == room.landlord
        if is_landlord or high_cards >= 3:
            return "double"
        return "none"

    def _should_ai_show_cards(self, room: GameRoom, ai_id: str) -> bool:
        """AI 明牌决策：仅在牌力极强时选择明牌"""
        hand = room.hands.get(ai_id, [])
        has_big_joker = 53 in hand   # 大王
        has_small_joker = 52 in hand  # 小王
        # 统计大牌（2, A, K）
        bomb_count = self._count_bombs(hand)
        # 条件：有王炸 + 至少1个炸弹，或者有3个以上炸弹
        if has_big_joker and has_small_joker and bomb_count >= 1:
            return True
        if bomb_count >= 3:
            return True
        return False

    def _count_bombs(self, hand: List[int]) -> int:
        """统计手牌中的炸弹数量"""
        from collections import Counter
        rank_counts = Counter(c // 4 for c in hand if c < 52)
        return sum(1 for count in rank_counts.values() if count == 4)

    def evaluate_ai_dealing_show(self, room: GameRoom) -> List[dict]:
        """评估 AI 玩家是否在发牌阶段明牌，返回明牌的 AI 列表"""
        results = []
        for p in room.players:
            if p.is_ai and p.id not in room.show_cards_players:
                if self._should_ai_show_cards(room, p.id):
                    result = room.show_cards(p.id, 4)  # AI 发牌阶段明牌用最高倍数
                    if result.get("success"):
                        results.append(result)
        return results

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
