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
  shownCards?: number[]
  showMultiplier?: number
}

export interface LastPlay {
  player: string | null
  cards: number[]
  cardType: string | null
}

export type GamePhase = 'IDLE' | 'MATCHING' | 'DEALING' | 'CALLING' | 'LANDLORD_CONFIRM' | 'DOUBLING' | 'PLAYING' | 'SETTLING'

export type DoublingChoice = 'double' | 'super' | 'none'

export type WinnerSide = 'landlord' | 'farmer'

export interface GameSettlement {
  winner: string
  winnerSide: WinnerSide
  scores: Record<string, number>
  multiplier: number
  allHands?: Record<string, number[]>
}

export interface RoomStatePlayerPayload {
  id: string
  nickname: string
  is_ai: boolean
  is_online: boolean
  remaining?: number
  is_landlord?: boolean
  is_self?: boolean
  shown_cards?: number[]
  show_multiplier?: number
}

export interface RoomStateLastPlayPayload {
  player: string | null
  cards?: number[]
  card_type: string | null
}

export interface RoomStatePayload {
  room_id?: string
  phase?: GamePhase
  players?: RoomStatePlayerPayload[]
  hand?: number[]
  current_turn?: string | null
  turn_deadline?: number | null
  multiplier?: number
  call_round?: number
  call_scores?: Record<string, number> | null
  first_bidder?: string | null
  landlord?: string | null
  bottom_cards?: number[]
  last_play?: RoomStateLastPlayPayload | null
  base_score?: number
  all_played_cards?: number[]
  doubling_choices?: Record<string, DoublingChoice> | null
  show_cards_players?: Record<string, number> | null
  auto_play_players?: string[]
  play_mode?: string
}

export const useGameStore = defineStore('game', () => {
  const wsConnected = ref(false)
  const roomId = ref('')
  const gamePhase = ref<GamePhase>('IDLE')
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
  const settlement = ref<GameSettlement | null>(null)
  const errorMsg = ref('')
  const playerActions = ref<Record<string, string>>({})
  const playerPlayedCards = ref<Record<string, number[]>>({})
  const allPlayedCards = ref<number[]>([])
  const baseScore = ref(10)
  const doublingChoices = ref<Record<string, DoublingChoice>>({})
  const showAllHands = ref(false)
  const showGameOverBanner = ref(false)
  const showWinnerBanner = ref(false)
  const gameOverTitle = ref('')
  const showRedealNotice = ref(false)
  const activeEffect = ref<'bomb' | 'plane' | 'shimmer' | ''>('')
  const showCardsPlayers = ref<Record<string, number>>({})
  const showCardsAvailableMultiplier = ref<number | null>(null)
  const awaitingLandlordShow = ref(false)
  const aiHintCandidates = ref<number[][]>([])
  const aiHintSource = ref('')
  const autoPlayPlayers = ref<string[]>([])
  const playMode = ref<'classic' | 'no_shuffle'>('classic')

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

  function setAiHintCandidates(candidates: number[][], source: string) {
    aiHintCandidates.value = candidates.map((cards) => sortCardIds(cards))
    aiHintSource.value = source
  }

  function clearAiHintCandidates() {
    aiHintCandidates.value = []
    aiHintSource.value = ''
  }

  function setAutoPlayPlayer(playerId: string, enabled: boolean) {
    const next = new Set(autoPlayPlayers.value)
    if (enabled) next.add(playerId)
    else next.delete(playerId)
    autoPlayPlayers.value = [...next]
  }

  function updateFromRoomState(state: RoomStatePayload) {
    if (state.room_id) roomId.value = state.room_id
    if (state.phase) gamePhase.value = state.phase
    if (state.players) players.value = state.players.map((p) => ({
      id: p.id, nickname: p.nickname, isAi: p.is_ai, isOnline: p.is_online,
      remaining: p.remaining !== undefined ? p.remaining : (p.is_self ? (state.hand ? state.hand.length : 0) : 0),
      isLandlord: p.is_landlord, isSelf: p.is_self,
      shownCards: p.shown_cards,
      showMultiplier: p.show_multiplier,
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
    if (state.doubling_choices !== undefined) doublingChoices.value = state.doubling_choices || {}
    if (state.show_cards_players !== undefined) showCardsPlayers.value = state.show_cards_players || {}
    if (state.auto_play_players !== undefined) autoPlayPlayers.value = state.auto_play_players
    if (state.play_mode !== undefined) playMode.value = state.play_mode as 'classic' | 'no_shuffle'
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
    doublingChoices.value = {}
    showAllHands.value = false
    showGameOverBanner.value = false
    showWinnerBanner.value = false
    gameOverTitle.value = ''
    showRedealNotice.value = false
    activeEffect.value = ''
    showCardsPlayers.value = {}
    showCardsAvailableMultiplier.value = null
    awaitingLandlordShow.value = false
    aiHintCandidates.value = []
    aiHintSource.value = ''
    autoPlayPlayers.value = []
    playMode.value = 'classic'
  }

  return {
    wsConnected, roomId, gamePhase, players, myHand, selectedCards,
    bottomCards, lastPlay, currentTurn, turnDeadline, turnTimeout, multiplier,
    callRound, callScores, firstBidder, landlord, settlement, errorMsg, isMyTurn, playerActions, playerPlayedCards,
    allPlayedCards, baseScore, doublingChoices, showAllHands, showGameOverBanner, showWinnerBanner, gameOverTitle,
    showRedealNotice, activeEffect, showCardsPlayers, showCardsAvailableMultiplier, awaitingLandlordShow,
    aiHintCandidates, aiHintSource, autoPlayPlayers, playMode,
    toggleCard, clearSelection, selectCards, setAiHintCandidates, clearAiHintCandidates, setAutoPlayPlayer,
    updateFromRoomState, reset,
  }
})
