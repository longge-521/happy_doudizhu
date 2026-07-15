from copy import deepcopy

import torch

from app.domain.game import ai_strategy
from app.domain.game.ai_strategy import build_ai_context, generate_legal_actions_dz
from app.domain.game.fifty_k_search import (
    choose_fifty_k_endgame_action,
    should_search_fifty_k_endgame,
)
from app.domain.game.room import GameRoom, LastPlay
from app.training.fifty_k.environment import FiftyKSelfPlayEnv
from app.training.fifty_k import trainer as trainer_module
from app.training.fifty_k.trainer import _rank_rule_actions


def _small_public_room(seed: int = 510) -> GameRoom:
    room = FiftyKSelfPlayEnv(seed=seed).reset()
    kept_hands = {
        player_id: list(hand[:6])
        for player_id, hand in room.hands.items()
    }
    kept_cards = {card_id for hand in kept_hands.values() for card_id in hand}
    room.hands = kept_hands
    room.all_played_cards = [card_id for card_id in range(54) if card_id not in kept_cards]
    room.current_trick_cards = []
    room.last_play = LastPlay()
    room.pass_count = 0
    room.current_turn = "p1"
    return room


def test_endgame_search_trigger_uses_public_remaining_counts():
    room = FiftyKSelfPlayEnv(seed=1).reset()
    assert not should_search_fifty_k_endgame(room, "p1")

    room = _small_public_room()
    assert should_search_fifty_k_endgame(room, "p1")


def test_endgame_search_is_legal_reproducible_and_does_not_mutate_room():
    room = _small_public_room()
    before = deepcopy(room.to_dict())
    actions = _rank_rule_actions(room, "p1")[:4]

    first = choose_fifty_k_endgame_action(
        room,
        "p1",
        actions,
        _rank_rule_actions,
        determinizations=2,
    )
    second = choose_fifty_k_endgame_action(
        room,
        "p1",
        actions,
        _rank_rule_actions,
        determinizations=2,
    )

    assert first in generate_legal_actions_dz(
        room.hands["p1"], None, True, play_mode="fifty_k"
    )
    assert first == second
    assert room.to_dict() == before


def test_endgame_search_does_not_depend_on_real_opponent_hands():
    room = _small_public_room()
    hidden_swap = GameRoom.from_dict(deepcopy(room.to_dict()))
    hidden_swap.hands["p2"], hidden_swap.hands["p3"] = (
        hidden_swap.hands["p3"],
        hidden_swap.hands["p2"],
    )

    actions = _rank_rule_actions(room, "p1")[:4]
    swapped_actions = _rank_rule_actions(hidden_swap, "p1")[:4]
    first = choose_fifty_k_endgame_action(room, "p1", actions, _rank_rule_actions)
    second = choose_fifty_k_endgame_action(
        hidden_swap, "p1", swapped_actions, _rank_rule_actions
    )

    assert actions == swapped_actions
    assert first == second


def test_ai_candidates_do_not_let_rule_rollout_override_model_or_rule_order(monkeypatch):
    room = _small_public_room()
    hand = room.hands["p1"]
    ctx = build_ai_context(room, "p1")
    legal_actions = generate_legal_actions_dz(hand, None, True, play_mode="fifty_k")
    rule_ranked = ai_strategy._rank_fifty_k_rule_actions(hand, legal_actions, None, ctx)
    monkeypatch.setattr(ai_strategy.fifty_k_manager, "is_available", lambda: False)

    ranked = ai_strategy.ai_rank_play_candidates(
        hand,
        None,
        True,
        ctx,
        limit=4,
        room=room,
    )

    assert ranked == rule_ranked[:4]
    assert set(map(tuple, ranked)) == set(map(tuple, rule_ranked[:4]))


def test_ai_candidates_use_endgame_search_for_available_model(monkeypatch):
    room = _small_public_room()
    hand = room.hands["p1"]
    ctx = build_ai_context(room, "p1")
    legal_actions = generate_legal_actions_dz(hand, None, True, play_mode="fifty_k")
    searched_action = legal_actions[-1]
    calls = []

    monkeypatch.setattr(ai_strategy.fifty_k_manager, "is_available", lambda: True)
    monkeypatch.setattr(
        ai_strategy.fifty_k_manager,
        "rank_actions",
        lambda hand, actions, last_play, ctx: list(reversed(actions)),
    )

    def fake_search(search_room, player_id, actions, rank_actions, **kwargs):
        calls.append((search_room, player_id, list(actions), rank_actions))
        return searched_action

    monkeypatch.setattr(ai_strategy, "choose_fifty_k_endgame_action", fake_search)

    ranked = ai_strategy.ai_rank_play_candidates(
        hand,
        None,
        True,
        ctx,
        limit=4,
        room=room,
    )

    assert ranked[0] == searched_action
    assert calls and calls[0][0] is room


def test_offline_evaluation_can_score_all_legal_actions_without_search_override():
    room = _small_public_room()
    actions = trainer_module.generate_legal_actions_dz(
        room.hands["p1"],
        room.last_play.card_play,
        room.last_play.card_play is None,
        play_mode="fifty_k",
    )

    class PreferLastAction(torch.nn.Module):
        def forward(self, features):
            return torch.arange(len(features), dtype=torch.float32).reshape(-1, 1)

        def score_actions_with_shared_history(self, features):
            return self(features)

    selected = trainer_module._model_action(
        PreferLastAction(),
        room,
        "p1",
        use_endgame_search=False,
    )

    assert selected == actions[-1]


def test_offline_evaluation_uses_public_endgame_search_by_default(monkeypatch):
    room = _small_public_room()
    searched_action = _rank_rule_actions(room, "p1")[0]
    calls = []

    def fake_search(search_room, player_id, actions, rank_actions, **kwargs):
        calls.append((search_room, player_id, list(actions), rank_actions))
        return searched_action

    monkeypatch.setattr(trainer_module, "choose_fifty_k_endgame_action", fake_search)

    selected = trainer_module._model_action(
        trainer_module.FiftyKActionValueModel(),
        room,
        "p1",
    )

    assert selected == searched_action
    assert calls and calls[0][0] is room
