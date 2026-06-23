// frontend/src/composables/useGameWebSocket.ts
import { ref } from 'vue'
import { useGameStore } from '@/stores/gameStore'
import { usePlayerStore } from '@/stores/playerStore'

export function useGameWebSocket() {
  const isConnected = ref(false)
  let ws: WebSocket | null = null
  let reconnectAttempt = 0
  let reconnectTimer: number | null = null

  function connect() {
    const playerStore = usePlayerStore()
    if (!playerStore.playerId) {
      console.warn('WebSocket: Cannot connect without playerId')
      return
    }

    const host = window.location.host
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const token = localStorage.getItem('hmp_token') || new URLSearchParams(window.location.search).get('token') || ''
    const tokenQuery = token ? `?token=${token}` : ''
    const url = `${protocol}//${host}/ws/game/${playerStore.playerId}${tokenQuery}`
    
    ws = new WebSocket(url)

    ws.onopen = () => {
      isConnected.value = true
      reconnectAttempt = 0
      const gameStore = useGameStore()
      gameStore.wsConnected = true
      console.log('WebSocket: Connected successfully')
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        handleEvent(data)
      } catch (e) {
        console.error('WebSocket: Failed to parse event data:', e)
      }
    }

    ws.onclose = () => {
      isConnected.value = false
      const gameStore = useGameStore()
      gameStore.wsConnected = false
      console.log('WebSocket: Connection closed')
      scheduleReconnect()
    }

    ws.onerror = (err) => {
      console.error('WebSocket error:', err)
    }
  }

  function disconnect() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    if (ws) {
      ws.close()
      ws = null
    }
    isConnected.value = false
  }

  function scheduleReconnect() {
    reconnectAttempt++
    const delay = Math.min(1000 * Math.pow(2, reconnectAttempt), 30000)
    reconnectTimer = window.setTimeout(() => connect(), delay)
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
        break
      case 'match_cancelled':
        gameStore.gamePhase = 'IDLE'
        break
      case 'game_start':
        gameStore.gamePhase = 'CALLING'
        gameStore.myHand = data.hand
        gameStore.currentTurn = data.current_turn
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
      case 'call_made':
        if (data.room_state) gameStore.updateFromRoomState(data.room_state)
        gameStore.playerActions[data.player] = `${data.score}分`
        break
      case 'call_skipped':
        if (data.room_state) gameStore.updateFromRoomState(data.room_state)
        gameStore.playerActions[data.player] = '不叫'
        break
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
        break
      case 'cards_played':
        if (data.room_state) gameStore.updateFromRoomState(data.room_state)
        gameStore.playerActions[data.player] = ''
        gameStore.playerPlayedCards[data.player] = data.cards
        break
      case 'turn_passed':
        if (data.room_state) gameStore.updateFromRoomState(data.room_state)
        gameStore.playerActions[data.player] = '不出'
        gameStore.playerPlayedCards[data.player] = []
        break
      case 'game_over':
        if (data.room_state) gameStore.updateFromRoomState(data.room_state)
        gameStore.gamePhase = 'SETTLING'
        gameStore.settlement = {
          winner: data.winner,
          winnerSide: data.winner_side,
          scores: data.scores,
          multiplier: data.multiplier,
        }
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
