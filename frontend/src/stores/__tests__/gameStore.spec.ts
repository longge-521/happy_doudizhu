import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useGameStore, type RoomStatePayload } from '../gameStore'

describe('gameStore room state mapping', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('maps backend room state payload into frontend store state', () => {
    const store = useGameStore()
    const state: RoomStatePayload = {
      room_id: 'room-1',
      phase: 'DOUBLING',
      players: [
        {
          id: 'p1',
          nickname: 'Player One',
          is_ai: false,
          is_online: true,
          is_self: true,
          is_landlord: true,
        },
        {
          id: 'p2',
          nickname: 'AI Two',
          is_ai: true,
          is_online: false,
          remaining: 7,
          is_self: false,
          is_landlord: false,
        },
      ],
      hand: [52, 3, 17],
      current_turn: 'p2',
      turn_deadline: 12345,
      multiplier: 4,
      call_round: 2,
      call_scores: { p1: 3 },
      first_bidder: 'p1',
      landlord: 'p1',
      bottom_cards: [1, 2, 3],
      last_play: {
        player: 'p2',
        cards: [10, 11],
        card_type: 'PAIR',
      },
      base_score: 80,
      all_played_cards: [10, 11, 12],
      doubling_choices: {
        p1: 'super',
        p2: 'none',
      },
    }

    store.updateFromRoomState(state)

    expect(store.roomId).toBe('room-1')
    expect(store.gamePhase).toBe('DOUBLING')
    expect(store.myHand).toEqual([52, 17, 3])
    expect(store.players).toEqual([
      {
        id: 'p1',
        nickname: 'Player One',
        isAi: false,
        isOnline: true,
        remaining: 3,
        isLandlord: true,
        isSelf: true,
      },
      {
        id: 'p2',
        nickname: 'AI Two',
        isAi: true,
        isOnline: false,
        remaining: 7,
        isLandlord: false,
        isSelf: false,
      },
    ])
    expect(store.currentTurn).toBe('p2')
    expect(store.turnDeadline).toBe(12345)
    expect(store.multiplier).toBe(4)
    expect(store.callRound).toBe(2)
    expect(store.callScores).toEqual({ p1: 3 })
    expect(store.firstBidder).toBe('p1')
    expect(store.landlord).toBe('p1')
    expect(store.bottomCards).toEqual([1, 2, 3])
    expect(store.lastPlay).toEqual({
      player: 'p2',
      cards: [10, 11],
      cardType: 'PAIR',
    })
    expect(store.baseScore).toBe(80)
    expect(store.allPlayedCards).toEqual([10, 11, 12])
    expect(store.doublingChoices).toEqual({ p1: 'super', p2: 'none' })
  })

  it('resets room state fields after a mapped room state', () => {
    const store = useGameStore()
    store.updateFromRoomState({
      room_id: 'room-1',
      phase: 'PLAYING',
      players: [
        {
          id: 'p1',
          nickname: 'Player One',
          is_ai: false,
          is_online: true,
          remaining: 3,
        },
      ],
      hand: [3, 4, 5],
      current_turn: 'p1',
      multiplier: 8,
      doubling_choices: { p1: 'double' },
    })

    store.reset()

    expect(store.roomId).toBe('')
    expect(store.gamePhase).toBe('IDLE')
    expect(store.players).toEqual([])
    expect(store.myHand).toEqual([])
    expect(store.currentTurn).toBe('')
    expect(store.multiplier).toBe(1)
    expect(store.doublingChoices).toEqual({})
  })

  it('resets typed settlement data to null', () => {
    const store = useGameStore()
    store.settlement = {
      winner: 'p1',
      winnerSide: 'landlord',
      scores: { p1: 80, p2: -40, p3: -40 },
      multiplier: 4,
      allHands: { p2: [3, 4] },
    }

    store.reset()

    expect(store.settlement).toBeNull()
  })

  it('stores AI hint candidates and auto-play players', () => {
    const store = useGameStore()

    store.setAiHintCandidates([[0, 1], [2, 3]], 'douzero')
    expect(store.aiHintCandidates).toEqual([[1, 0], [3, 2]])
    expect(store.aiHintSource).toBe('douzero')

    store.setAutoPlayPlayer('p1', true)
    expect(store.autoPlayPlayers).toContain('p1')

    store.setAutoPlayPlayer('p1', false)
    expect(store.autoPlayPlayers).not.toContain('p1')
  })
})
