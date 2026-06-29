// frontend/src/composables/useGameWebSocket.ts
import { ref } from 'vue'
import { useGameStore } from '@/stores/gameStore'
import { usePlayerStore } from '@/stores/playerStore'
import { detectCardPlay } from '@/utils/cardUtils'

const isConnected = ref(false)
let ws: WebSocket | null = null
let reconnectAttempt = 0
let reconnectTimer: number | null = null
let manuallyClosed = false
let socketPlayerId = ''
let gameOverTimer: number | null = null
let effectTimer: number | null = null

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
      console.log('WebSocket: Connected successfully')
    }

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        handleEvent(data)
      } catch (e) {
        console.error('WebSocket: Failed to parse event data:', e)
      }
    }

    socket.onclose = () => {
      if (ws !== socket) return

      isConnected.value = false
      const gameStore = useGameStore()
      gameStore.wsConnected = false
      ws = null
      console.log('WebSocket: Connection closed')
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
      case 'match_success':
        gameStore.roomId = data.room_id
        if (data.room_state) gameStore.updateFromRoomState(data.room_state)
        break
      case 'match_cancelled':
        gameStore.gamePhase = 'IDLE'
        break
      case 'game_start':
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
            isLandlord: false, isSelf: p.is_self,
          }))
        }
        break
      case 'call_made': {
        const hadBid = Object.values(gameStore.callScores).some((score) => score > 0)
        if (data.room_state) gameStore.updateFromRoomState(data.room_state)
        gameStore.playerActions = { ...gameStore.playerActions, [data.player]: hadBid ? '抢地主' : '叫地主' }
        break
      }
      case 'call_skipped': {
        const hasBid = Object.values(gameStore.callScores).some((score) => score > 0)
        if (data.room_state) gameStore.updateFromRoomState(data.room_state)
        gameStore.playerActions = { ...gameStore.playerActions, [data.player]: hasBid ? '不抢' : '不叫' }
        break
      }
      case 'landlord_decided':
        if (data.room_state) gameStore.updateFromRoomState(data.room_state)
        gameStore.gamePhase = 'PLAYING'
        gameStore.landlord = data.landlord
        gameStore.bottomCards = data.bottom_cards || []
        gameStore.multiplier = data.multiplier || 1
        gameStore.playerActions = {} // 清空叫分提示
        break
      case 'redeal':
        if (data.room_state) gameStore.updateFromRoomState(data.room_state)
        gameStore.playerActions = {}
        gameStore.playerPlayedCards = {}
        gameStore.showRedealNotice = true
        setTimeout(() => {
          gameStore.showRedealNotice = false
        }, 1800)
        break
      case 'cards_played':
        if (data.room_state) gameStore.updateFromRoomState(data.room_state)
        gameStore.playerActions = { ...gameStore.playerActions, [data.player]: '' }
        gameStore.playerPlayedCards = { ...gameStore.playerPlayedCards, [data.player]: data.cards }
        const play = detectCardPlay(data.cards)
        if (play) {
          if (effectTimer) {
            clearTimeout(effectTimer)
            effectTimer = null
          }
          if (play.kind === 'bomb' || play.kind === 'rocket') {
            gameStore.activeEffect = 'bomb'
            effectTimer = window.setTimeout(() => {
              gameStore.activeEffect = ''
              effectTimer = null
            }, 1500)
          } else if (play.kind === 'airplane' || play.kind === 'airplane_single' || play.kind === 'airplane_pair') {
            gameStore.activeEffect = 'plane'
            effectTimer = window.setTimeout(() => {
              gameStore.activeEffect = ''
              effectTimer = null
            }, 1500)
          } else if (play.kind === 'straight' || play.kind === 'double_straight') {
            gameStore.activeEffect = 'shimmer'
            effectTimer = window.setTimeout(() => {
              gameStore.activeEffect = ''
              effectTimer = null
            }, 1500)
          }
        }
        break
      case 'turn_passed':
        if (data.room_state) gameStore.updateFromRoomState(data.room_state)
        gameStore.playerActions = { ...gameStore.playerActions, [data.player]: '不出' }
        gameStore.playerPlayedCards = { ...gameStore.playerPlayedCards, [data.player]: [] }
        break
      case 'game_over':
        if (gameOverTimer) {
          clearTimeout(gameOverTimer)
          gameOverTimer = null
        }
        if (data.room_state) {
          data.room_state.phase = 'PLAYING'
          gameStore.updateFromRoomState(data.room_state)
          // 将最后的绝杀出牌写入 playerPlayedCards，以便在桌面上与结算单中正确展示绝杀牌
          if (data.room_state.last_play && data.room_state.last_play.player) {
            const lastPlayer = data.room_state.last_play.player
            const lastCards = data.room_state.last_play.cards || []
            gameStore.playerPlayedCards = {
              ...gameStore.playerPlayedCards,
              [lastPlayer]: lastCards
            }
            gameStore.playerActions = {
              ...gameStore.playerActions,
              [lastPlayer]: ''
            }
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

        gameStore.showAllHands = true
        gameStore.showGameOverBanner = true
        gameStore.showWinnerBanner = false
        gameStore.gameOverTitle = data.winner_side === 'landlord' ? '地主胜利' : '农民胜利'
        
        // 3秒后弹出谁胜利了的大字
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
      case 'chat_msg':
        {
          const presets = [
            "快点吧，等得我花都谢了！",
            "合作愉快，合作愉快！",
            "大牌在后头，千万别放他！",
            "不要走，决战到天亮！",
            "你是地主派来的卧底吧？"
          ]
          const msg = presets[data.msg_id] || '...'
          gameStore.playerActions[data.player] = msg
          setTimeout(() => {
            if (gameStore.playerActions[data.player] === msg) {
              gameStore.playerActions[data.player] = ''
            }
          }, 3000)
        }
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
