// frontend/src/composables/useGameWebSocket.ts
import { ref } from 'vue'
import { useGameStore } from '@/stores/gameStore'
import { usePlayerStore } from '@/stores/playerStore'
import {
  clearCardPresentationEffectTimer,
  getDoubleChoiceLabel,
  playCardPresentationEffects,
  playDoubleChoiceSound,
  playQuickChatMessage,
} from './gameWebSocketEffects'
import { notifyVoiceSignal, notifyVoiceState } from './gameVoiceEvents'
import { useSoundEngine } from './useSoundEngine'

const isConnected = ref(false)
let ws: WebSocket | null = null
let reconnectAttempt = 0
let reconnectTimer: number | null = null
let manuallyClosed = false
let socketPlayerId = ''
let gameOverTimer: number | null = null

function debugLog(...args: unknown[]) {
  if (import.meta.env.DEV) {
    console.log(...args)
  }
}

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
        const data = JSON.parse(event.data)
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

  function sendAction(action: Record<string, any>) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(action))
    } else {
      console.warn('WebSocket: Cannot send action, socket is not open')
    }
  }

  function handleEvent(data: any) {
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
          gameStore.players = data.players.map((p: any) => ({
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
        gameStore.gamePhase = 'PLAYING'
        if (data.current_turn !== undefined) gameStore.currentTurn = data.current_turn || ''
        if (data.multiplier !== undefined) gameStore.multiplier = data.multiplier
        setTimeout(() => {
          if (gameStore.gamePhase === 'PLAYING') {
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

        const settlementData = {
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
