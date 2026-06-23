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
  const turnTimeout = ref(20)
  const multiplier = ref(1)
  const landlord = ref('')
  const settlement = ref<any>(null)
  const errorMsg = ref('')
  const playerActions = ref<Record<string, string>>({})
  const playerPlayedCards = ref<Record<string, number[]>>({})

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

  function updateFromRoomState(state: any) {
    if (state.room_id) roomId.value = state.room_id
    if (state.phase) gamePhase.value = state.phase
    if (state.players) players.value = state.players.map((p: any) => ({
      id: p.id, nickname: p.nickname, isAi: p.is_ai, isOnline: p.is_online,
      remaining: p.remaining, isLandlord: p.is_landlord, isSelf: p.is_self,
    }))
    if (state.hand) {
      myHand.value = sortCardIds(state.hand)
    }
    if (state.current_turn) currentTurn.value = state.current_turn
    if (state.multiplier) multiplier.value = state.multiplier
    if (state.landlord) landlord.value = state.landlord
    if (state.bottom_cards) bottomCards.value = state.bottom_cards
    if (state.last_play) lastPlay.value = {
      player: state.last_play.player,
      cards: state.last_play.cards || [],
      cardType: state.last_play.card_type,
    }
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
    multiplier.value = 1
    landlord.value = ''
    settlement.value = null
    errorMsg.value = ''
    playerActions.value = {}
    playerPlayedCards.value = {}
  }

  return {
    wsConnected, roomId, gamePhase, players, myHand, selectedCards,
    bottomCards, lastPlay, currentTurn, turnTimeout, multiplier,
    landlord, settlement, errorMsg, isMyTurn, playerActions, playerPlayedCards,
    toggleCard, clearSelection, updateFromRoomState, reset,
  }
})
