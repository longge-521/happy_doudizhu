// frontend/src/stores/gameStore.ts
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { usePlayerStore } from './playerStore'
import { sortCardIds } from '@/utils/cardUtils'

export interface PlayerInfo {
  id: string
  nickname: string
  isAi: boolean
  isOnline: boolean
  remaining?: number
  isLandlord?: boolean
  isSelf?: boolean
}

export interface LastPlay {
  player: string | null
  cards: number[]
  cardType: string | null
}

export const useGameStore = defineStore('game', () => {
  const wsConnected = ref(false)
  const roomId = ref('')
  const gamePhase = ref<string>('IDLE')  // IDLE | MATCHING | DEALING | CALLING | PLAYING | SETTLING
  const players = ref<PlayerInfo[]>([])
  const myHand = ref<number[]>([])
  const selectedCards = ref<number[]>([])
  const bottomCards = ref<number[]>([])
  const lastPlay = ref<LastPlay>({ player: null, cards: [], cardType: null })
  const currentTurn = ref('')
  const turnDeadline = ref(0)
  const turnTimeout = ref(15)
  const multiplier = ref(1)
  const callRound = ref(1)
  const callScores = ref<Record<string, number>>({})
  const firstBidder = ref('')
  const landlord = ref('')
  const settlement = ref<any>(null)
  const errorMsg = ref('')
  const playerActions = ref<Record<string, string>>({})
  const playerPlayedCards = ref<Record<string, number[]>>({})
  const allPlayedCards = ref<number[]>([])
  const baseScore = ref(10)
  const showAllHands = ref(false)
  const showGameOverBanner = ref(false)
  const showWinnerBanner = ref(false)
  const gameOverTitle = ref('')
  const showRedealNotice = ref(false)
  const activeEffect = ref<'bomb' | 'plane' | 'shimmer' | ''>('')

  const isMyTurn = computed(() => {
    const playerStore = usePlayerStore()
    return currentTurn.value === playerStore.playerId
  })

  function toggleCard(cardId: number) {
    const idx = selectedCards.value.indexOf(cardId)
    if (idx >= 0) {
      selectedCards.value.splice(idx, 1)
    } else {
      selectedCards.value.push(cardId)
    }
  }

  function clearSelection() {
    selectedCards.value = []
  }

  function selectCards(cardIds: number[]) {
    selectedCards.value = [...cardIds]
  }

  function updateFromRoomState(state: any) {
    if (state.room_id) roomId.value = state.room_id
    if (state.phase) gamePhase.value = state.phase
    if (state.players) players.value = state.players.map((p: any) => ({
      id: p.id, nickname: p.nickname, isAi: p.is_ai, isOnline: p.is_online,
      remaining: p.remaining, isLandlord: p.is_landlord, isSelf: p.is_self,
    }))
    if (state.hand !== undefined) {
      myHand.value = sortCardIds(state.hand)
    }
    if (state.current_turn !== undefined) currentTurn.value = state.current_turn || ''
    if (state.turn_deadline !== undefined) turnDeadline.value = state.turn_deadline || 0
    if (state.multiplier !== undefined) multiplier.value = state.multiplier
    if (state.call_round !== undefined) callRound.value = state.call_round
    if (state.call_scores !== undefined) callScores.value = state.call_scores || {}
    if (state.first_bidder !== undefined) firstBidder.value = state.first_bidder || ''
    if (state.landlord !== undefined) landlord.value = state.landlord || ''
    if (state.bottom_cards !== undefined) bottomCards.value = state.bottom_cards
    if (state.last_play) lastPlay.value = {
      player: state.last_play.player,
      cards: state.last_play.cards || [],
      cardType: state.last_play.card_type,
    }
    if (state.base_score !== undefined) baseScore.value = state.base_score
    if (state.all_played_cards !== undefined) allPlayedCards.value = state.all_played_cards
  }

  function reset() {
    roomId.value = ''
    gamePhase.value = 'IDLE'
    players.value = []
    myHand.value = []
    selectedCards.value = []
    bottomCards.value = []
    lastPlay.value = { player: null, cards: [], cardType: null }
    currentTurn.value = ''
    turnDeadline.value = 0
    multiplier.value = 1
    callRound.value = 1
    callScores.value = {}
    firstBidder.value = ''
    landlord.value = ''
    settlement.value = null
    errorMsg.value = ''
    playerActions.value = {}
    playerPlayedCards.value = {}
    allPlayedCards.value = []
    baseScore.value = 10
    showAllHands.value = false
    showGameOverBanner.value = false
    showWinnerBanner.value = false
    gameOverTitle.value = ''
    showRedealNotice.value = false
    activeEffect.value = ''
  }

  return {
    wsConnected, roomId, gamePhase, players, myHand, selectedCards,
    bottomCards, lastPlay, currentTurn, turnDeadline, turnTimeout, multiplier,
    callRound, callScores, firstBidder, landlord, settlement, errorMsg, isMyTurn, playerActions, playerPlayedCards,
    allPlayedCards, baseScore, showAllHands, showGameOverBanner, showWinnerBanner, gameOverTitle,
    showRedealNotice, activeEffect,
    toggleCard, clearSelection, selectCards, updateFromRoomState, reset,
  }
})
