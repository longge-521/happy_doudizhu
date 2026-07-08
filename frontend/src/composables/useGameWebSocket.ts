// frontend/src/composables/useGameWebSocket.ts
import { ref } from 'vue'
import {
  useGameStore,
  type DoublingChoice,
  type GameSettlement,
  type RoomStatePayload,
  type RoomStatePlayerPayload,
  type WinnerSide,
} from '@/stores/gameStore'
import { usePlayerStore } from '@/stores/playerStore'
import { debugLog } from '@/utils/debugLog'
import {
  clearCardPresentationEffectTimer,
  getDoubleChoiceLabel,
  playCardPresentationEffects,
  playDoubleChoiceSound,
  playQuickChatMessage,
} from './gameWebSocketEffects'
import {
  type VoiceSignalType,
  notifyVoiceSignal,
  notifyVoiceState,
} from './gameVoiceEvents'
import { useSoundEngine } from './useSoundEngine'

const isConnected = ref(false)
let ws: WebSocket | null = null
let reconnectAttempt = 0
let reconnectTimer: number | null = null
let manuallyClosed = false
let socketPlayerId = ''
let gameOverTimer: number | null = null

type BaseRoomStateEvent<TEvent extends string> = {
  event: TEvent
  room_state?: RoomStatePayload
}

type GameStartEvent = {
  event: 'game_start'
  room_id?: string
  hand: number[]
  current_turn: string
  turn_deadline?: number
  players?: RoomStatePlayerPayload[]
}

type DoubleChosenEvent = BaseRoomStateEvent<'double_chosen'> & {
  player: string
  choice: DoublingChoice
  label?: string
  multiplier?: number
}

type CardsPlayedEvent = BaseRoomStateEvent<'cards_played'> & {
  player: string
  cards: number[]
}

type GameOverRoomState = RoomStatePayload & {
  phase?: 'PLAYING'
}

type GameOverEvent = {
  event: 'game_over'
  winner: string
  winner_side: WinnerSide
  scores: Record<string, number>
  multiplier: number
  all_hands?: Record<string, number[]>
  room_state?: GameOverRoomState
}

type VoiceSignalEvent = {
  event: 'voice_signal'
  player: string
  target_player: string
  signal_type: VoiceSignalType
  payload: Record<string, unknown>
}

type VoiceStateEvent = {
  event: 'voice_state'
  player: string
  enabled: boolean
}

type AiHintsEvent = {
  event: 'ai_hints'
  candidates: number[][]
  source?: string
}

type AutoPlayChangedEvent = {
  event: 'auto_play_changed'
  player: string
  enabled: boolean
}

export type GameClientAction =
  | { action: 'join_match'; nickname: string; base_score: number }
  | { action: 'cancel_match' }
  | { action: 'sync_room_state' }
  | { action: 'call_landlord'; score: number }
  | { action: 'skip_call' }
  | { action: 'play_cards'; cards: number[] }
  | { action: 'pass_turn' }
  | { action: 'get_ai_hints' }
  | { action: 'set_auto_play'; enabled: boolean }
  | { action: 'chat'; msg_id: number }
  | { action: 'choose_double'; choice: DoublingChoice }
  | { action: 'voice_state'; enabled: boolean }
  | {
      action: 'voice_signal'
      target_player: string
      signal_type: VoiceSignalType
      payload: Record<string, unknown>
    }
  | { action: 'show_cards'; multiplier: number }
  | { action: 'landlord_show'; show: boolean }

type GameServerEvent =
  | { event: 'match_waiting' }
  | { event: 'match_cancelled' }
  | (BaseRoomStateEvent<'match_success'> & { room_id: string })
  | GameStartEvent
  | (BaseRoomStateEvent<'call_made'> & { player: string })
  | (BaseRoomStateEvent<'call_skipped'> & { player: string })
  | (BaseRoomStateEvent<'landlord_decided'> & {
      landlord: string
      bottom_cards?: number[]
      multiplier?: number
    })
  | DoubleChosenEvent
  | (BaseRoomStateEvent<'doubling_finished'> & {
      current_turn?: string | null
      multiplier?: number
      landlord_confirm_required?: boolean
    })
  | BaseRoomStateEvent<'redeal'>
  | CardsPlayedEvent
  | (BaseRoomStateEvent<'turn_passed'> & { player: string })
  | GameOverEvent
  | { event: 'chat_msg'; player: string; msg_id: number }
  | AiHintsEvent
  | AutoPlayChangedEvent
  | VoiceSignalEvent
  | VoiceStateEvent
  | (RoomStatePayload & { event: 'reconnected' })
  | { event: 'error'; msg?: string }
  | (BaseRoomStateEvent<'cards_shown'> & {
      player: string
      cards: number[]
      show_multiplier: number
      total_multiplier: number
    })
  | (BaseRoomStateEvent<'landlord_show_decided'> & {
      player: string
      show: boolean
      cards?: number[]
      multiplier: number
    })

export { playDoubleChoiceSound }

export function useGameWebSocket() {
  function connect() {
    const playerStore = usePlayerStore()
    if (!playerStore.playerId) {
      console.warn('WebSocket: Cannot connect without playerId')
      return
    }

    if (
      ws &&
      socketPlayerId === playerStore.playerId &&
      (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)
    ) {
      return
    }

    if (ws && socketPlayerId !== playerStore.playerId) {
      disconnect()
    }

    manuallyClosed = false
    socketPlayerId = playerStore.playerId
    const host = window.location.host
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const token = playerStore.authToken || localStorage.getItem('hmp_game_auth_token') || ''
    const tokenQuery = token ? `?auth_token=${encodeURIComponent(token)}` : ''
    const url = `${protocol}//${host}/ws/game/${playerStore.playerId}${tokenQuery}`

    const socket = new WebSocket(url)
    ws = socket

    socket.onopen = () => {
      isConnected.value = true
      reconnectAttempt = 0
      const gameStore = useGameStore()
      gameStore.wsConnected = true
      debugLog('WebSocket: Connected successfully')
    }

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as GameServerEvent
        handleEvent(data)
      } catch (e) {
        console.error('WebSocket: Failed to parse event data:', e)
      }
    }

    socket.onclose = (event) => {
      if (ws !== socket) return

      isConnected.value = false
      const gameStore = useGameStore()
      gameStore.wsConnected = false
      ws = null
      debugLog('WebSocket: Connection closed', event.code, event.reason)
      if (event.code === 1008) {
        manuallyClosed = true
        gameStore.errorMsg = event.reason || '登录状态已失效，请重新登录'
        console.warn('WebSocket: Auth rejected, stop reconnecting')
        return
      }
      if (!manuallyClosed) {
        scheduleReconnect()
      }
    }

    socket.onerror = (err) => {
      console.error('WebSocket error:', err)
    }
  }

  function disconnect() {
    manuallyClosed = true
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    if (gameOverTimer) {
      clearTimeout(gameOverTimer)
      gameOverTimer = null
    }
    clearCardPresentationEffectTimer()
    if (ws) {
      ws.close()
      ws = null
    }
    isConnected.value = false
    const gameStore = useGameStore()
    gameStore.wsConnected = false
  }

  function scheduleReconnect() {
    if (reconnectTimer) return
    reconnectAttempt++
    const delay = Math.min(1000 * Math.pow(2, reconnectAttempt), 30000)
    reconnectTimer = window.setTimeout(() => {
      reconnectTimer = null
      connect()
    }, delay)
  }

  function sendAction(action: GameClientAction) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(action))
    } else {
      console.warn('WebSocket: Cannot send action, socket is not open')
    }
  }

  function handleEvent(data: GameServerEvent) {
    const gameStore = useGameStore()
    const event = data.event

    switch (event) {
      case 'match_waiting':
        gameStore.gamePhase = 'MATCHING'
        break
      case 'match_success': {
        const { playSound } = useSoundEngine()
        playSound('matchSuccess')
        gameStore.roomId = data.room_id
        if (data.room_state) gameStore.updateFromRoomState(data.room_state)
        break
      }
      case 'match_cancelled':
        gameStore.gamePhase = 'IDLE'
        break
      case 'game_start': {
        const { startBgm } = useSoundEngine()
        startBgm('game')
        if (gameOverTimer) {
          clearTimeout(gameOverTimer)
          gameOverTimer = null
        }
        gameStore.gamePhase = 'CALLING'
        if (data.room_id) gameStore.roomId = data.room_id
        gameStore.myHand = data.hand
        gameStore.currentTurn = data.current_turn
        if (data.turn_deadline) gameStore.turnDeadline = data.turn_deadline
        gameStore.playerActions = {}
        gameStore.playerPlayedCards = {}
        if (data.players) {
          gameStore.players = data.players.map((p) => ({
            id: p.id, nickname: p.nickname, isAi: p.is_ai,
            isOnline: p.is_online, remaining: p.remaining,
            isSelf: p.is_self,
          }))
        }
        break
      }
      case 'call_made': {
        const { playSound: playSoundCall } = useSoundEngine()
        const hadBid = Object.values(gameStore.callScores).some((score) => score > 0)
        playSoundCall(hadBid ? 'robLandlord' : 'callLandlord', data.player)
        if (data.room_state) gameStore.updateFromRoomState(data.room_state)
        gameStore.playerActions = { ...gameStore.playerActions, [data.player]: hadBid ? '抢地主' : '叫地主' }
        break
      }
      case 'call_skipped': {
        const { playSound: playSoundSkip } = useSoundEngine()
        const hasBid = Object.values(gameStore.callScores).some((score) => score > 0)
        playSoundSkip(hasBid ? 'skipRob' : 'skipCall', data.player)
        if (data.room_state) gameStore.updateFromRoomState(data.room_state)
        gameStore.playerActions = { ...gameStore.playerActions, [data.player]: hasBid ? '不抢' : '不叫' }
        break
      }
      case 'landlord_decided': {
        const { playSound: playSoundLD } = useSoundEngine()
        playSoundLD('landlordDecided')
        if (data.room_state) gameStore.updateFromRoomState(data.room_state)
        gameStore.landlord = data.landlord
        gameStore.bottomCards = data.bottom_cards || []
        gameStore.multiplier = data.multiplier || 1
        gameStore.playerActions = {}
        break
      }
      case 'cards_shown': {
        const { playSound: playSoundShow } = useSoundEngine()
        playSoundShow('showCards')
        setTimeout(() => playSoundShow('mingpai', data.player), 120)
        if (data.room_state) gameStore.updateFromRoomState(data.room_state)
        gameStore.showCardsPlayers = { ...gameStore.showCardsPlayers, [data.player]: data.show_multiplier }
        // 找到该玩家并更新 shownCards
        const playerIdx = gameStore.players.findIndex(p => p.id === data.player)
        if (playerIdx >= 0) {
          const player = gameStore.players[playerIdx]
          if (player) {
            player.shownCards = data.cards
            player.showMultiplier = data.show_multiplier
          }
        }
        if (data.total_multiplier !== undefined) gameStore.multiplier = data.total_multiplier
        gameStore.playerActions = { ...gameStore.playerActions, [data.player]: `明牌 ×${data.show_multiplier}` }
        break
      }
      case 'landlord_show_decided': {
        const { playSound: playSoundLS } = useSoundEngine()
        if (data.show) {
          playSoundLS('showCards')
          setTimeout(() => playSoundLS('mingpai', data.player), 120)
          gameStore.showCardsPlayers = { ...gameStore.showCardsPlayers, [data.player]: 2 }
          const pIdx = gameStore.players.findIndex(p => p.id === data.player)
          if (pIdx >= 0 && data.cards) {
            const player = gameStore.players[pIdx]
            if (player) {
              player.shownCards = data.cards
              player.showMultiplier = 2
            }
          }
          gameStore.playerActions = { ...gameStore.playerActions, [data.player]: '明牌 ×2' }
        }
        if (data.room_state) gameStore.updateFromRoomState(data.room_state)
        if (data.multiplier !== undefined) gameStore.multiplier = data.multiplier
        gameStore.awaitingLandlordShow = false
        break
      }
      case 'double_chosen': {
        if (data.room_state) gameStore.updateFromRoomState(data.room_state)
        const label = data.label || getDoubleChoiceLabel(data.choice)
        gameStore.playerActions = { ...gameStore.playerActions, [data.player]: label }
        if (data.multiplier !== undefined) gameStore.multiplier = data.multiplier
        const playerStore = usePlayerStore()
        if (data.player !== playerStore.playerId) {
          playDoubleChoiceSound(data.choice, data.player)
        }
        break
      }
      case 'doubling_finished': {
        if (data.room_state) gameStore.updateFromRoomState(data.room_state)
        if (data.landlord_confirm_required) {
          gameStore.gamePhase = 'LANDLORD_CONFIRM'
          gameStore.awaitingLandlordShow = true
        } else {
          gameStore.gamePhase = 'PLAYING'
        }
        if (data.current_turn !== undefined) gameStore.currentTurn = data.current_turn || ''
        if (data.multiplier !== undefined) gameStore.multiplier = data.multiplier
        setTimeout(() => {
          if (gameStore.gamePhase === 'PLAYING' || gameStore.gamePhase === 'LANDLORD_CONFIRM') {
            gameStore.playerActions = {}
          }
        }, 2500)
        break
      }
      case 'redeal': {
        const { playSound: playSoundRD } = useSoundEngine()
        playSoundRD('redeal')
        if (data.room_state) gameStore.updateFromRoomState(data.room_state)
        gameStore.playerActions = {}
        gameStore.playerPlayedCards = {}
        gameStore.showRedealNotice = true
        setTimeout(() => {
          gameStore.showRedealNotice = false
        }, 1800)
        break
      }
      case 'cards_played': {
        const { playSound: playSoundCP } = useSoundEngine()
        if (data.room_state) gameStore.updateFromRoomState(data.room_state)
        gameStore.playerActions = { ...gameStore.playerActions, [data.player]: '' }
        gameStore.playerPlayedCards = { ...gameStore.playerPlayedCards, [data.player]: data.cards }

        const activePlayer = gameStore.players.find(p => p.id === data.player)
        if (activePlayer) {
          if (activePlayer.remaining === 2) {
            void playSoundCP('baojing2', data.player)
          } else if (activePlayer.remaining === 1) {
            void playSoundCP('baojing1', data.player)
          }
        }

        playCardPresentationEffects(data.cards, data.player, gameStore)
        break
      }
      case 'turn_passed': {
        const { playSound: playSoundTP } = useSoundEngine()
        playSoundTP('pass', data.player)
        if (data.room_state) gameStore.updateFromRoomState(data.room_state)
        gameStore.playerActions = { ...gameStore.playerActions, [data.player]: '不出' }
        gameStore.playerPlayedCards = { ...gameStore.playerPlayedCards, [data.player]: [] }
        break
      }
      case 'game_over': {
        const { playSound: playSoundGO, stopBgm: stopBgmGO } = useSoundEngine()
        const playerStoreGO = usePlayerStore()
        stopBgmGO()
        if (gameOverTimer) {
          clearTimeout(gameOverTimer)
          gameOverTimer = null
        }
        if (data.room_state) {
          data.room_state.phase = 'PLAYING'
          gameStore.updateFromRoomState(data.room_state)
          if (data.room_state.last_play && data.room_state.last_play.player) {
            const lastPlayer = data.room_state.last_play.player
            const lastCards = data.room_state.last_play.cards || []
            gameStore.playerPlayedCards = {
              ...gameStore.playerPlayedCards,
              [lastPlayer]: lastCards,
            }
            gameStore.playerActions = {
              ...gameStore.playerActions,
              [lastPlayer]: '',
            }
            playCardPresentationEffects(lastCards, lastPlayer, gameStore)
          }
        }

        const settlementData: GameSettlement = {
          winner: data.winner,
          winnerSide: data.winner_side,
          scores: data.scores,
          multiplier: data.multiplier,
          allHands: data.all_hands || {},
        }
        gameStore.settlement = settlementData

        const myId = playerStoreGO.playerId
        const isLandlord = gameStore.landlord === myId
        const myWon = (data.winner_side === 'landlord' && isLandlord) ||
                       (data.winner_side === 'farmer' && !isLandlord)
        setTimeout(() => {
          playSoundGO(myWon ? 'gameWin' : 'gameLose')
        }, 1500)

        gameStore.showAllHands = true
        gameStore.showGameOverBanner = true
        gameStore.showWinnerBanner = false
        gameStore.gameOverTitle = data.winner_side === 'landlord' ? '地主胜利' : '农民胜利'

        setTimeout(() => {
          gameStore.showWinnerBanner = true
        }, 3000)

        gameOverTimer = window.setTimeout(() => {
          gameStore.showGameOverBanner = false
          gameStore.showWinnerBanner = false
          gameStore.showAllHands = false
          gameStore.gamePhase = 'SETTLING'
          gameOverTimer = null
        }, 5000)
        break
      }
      case 'chat_msg':
        playQuickChatMessage(data.msg_id, data.player)
        break
      case 'ai_hints':
        gameStore.setAiHintCandidates(data.candidates, data.source || 'douzero')
        break
      case 'auto_play_changed':
        gameStore.setAutoPlayPlayer(data.player, data.enabled)
        break
      case 'voice_signal':
        notifyVoiceSignal({
          player: data.player,
          targetPlayer: data.target_player,
          signalType: data.signal_type,
          payload: data.payload,
        })
        break
      case 'voice_state':
        notifyVoiceState({
          player: data.player,
          enabled: Boolean(data.enabled),
        })
        break
      case 'reconnected':
        gameStore.updateFromRoomState(data)
        break
      case 'error':
        gameStore.errorMsg = data.msg || '未知错误'
        break
    }
  }

  return { isConnected, connect, disconnect, sendAction }
}
