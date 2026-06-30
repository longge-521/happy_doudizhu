// @vitest-environment jsdom
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { usePlayerStore } from '@/stores/playerStore'
import { onVoiceSignal, onVoiceState } from '../gameVoiceEvents'
import { useGameWebSocket } from '../useGameWebSocket'

type CloseHandler = ((event: CloseEvent) => void) | null

class MockWebSocket {
  static CONNECTING = 0
  static OPEN = 1

  static instances: MockWebSocket[] = []

  readyState = MockWebSocket.CONNECTING
  onopen: (() => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onclose: CloseHandler = null
  onerror: ((event: Event) => void) | null = null

  constructor(public url: string) {
    MockWebSocket.instances.push(this)
  }

  send() {}

  close() {
    this.onclose?.(new CloseEvent('close', { code: 1000 }))
  }
}

describe('useGameWebSocket', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    MockWebSocket.instances = []
    vi.stubGlobal('WebSocket', MockWebSocket)
    setActivePinia(createPinia())
    localStorage.clear()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('does not reconnect after auth policy close', async () => {
    const playerStore = usePlayerStore()
    playerStore.playerId = 'player1'
    playerStore.authToken = 'stale-token'

    const { connect } = useGameWebSocket()
    connect()

    expect(MockWebSocket.instances).toHaveLength(1)
    const socket = MockWebSocket.instances[0]
    expect(socket).toBeDefined()

    socket!.onclose?.(
      new CloseEvent('close', { code: 1008, reason: 'Unauthorized' }),
    )
    await vi.runOnlyPendingTimersAsync()

    expect(MockWebSocket.instances).toHaveLength(1)
  })

  it('syncs double choice events and plays matching voice', async () => {
    const playerStore = usePlayerStore()
    playerStore.playerId = 'p1'
    playerStore.authToken = 'token'

    const { connect } = useGameWebSocket()
    connect()
    const socket = MockWebSocket.instances[0]!
    socket.readyState = MockWebSocket.OPEN
    socket.onopen?.()

    socket.onmessage?.(new MessageEvent('message', {
      data: JSON.stringify({
        event: 'double_chosen',
        player: 'p2',
        choice: 'super',
        room_state: {
          room_id: 'room_1',
          phase: 'DOUBLING',
          players: [],
          doubling_choices: { p2: 'super' },
          multiplier: 4,
        },
      }),
    }))

    const { useGameStore } = await import('@/stores/gameStore')
    const gameStore = useGameStore()
    expect(gameStore.gamePhase).toBe('DOUBLING')
    expect(gameStore.doublingChoices).toEqual({ p2: 'super' })
    expect(gameStore.playerActions.p2).toBe('超级加倍')
    
    vi.advanceTimersByTime(200)
    expect(playSoundMock).toHaveBeenCalledWith('doubling')
    expect(playSoundMock).toHaveBeenCalledWith('superDouble', 'p2')
  })

  it('dispatches voice signaling events from websocket messages', () => {
    const signalListener = vi.fn()
    const stateListener = vi.fn()
    const unsubscribeSignal = onVoiceSignal(signalListener)
    const unsubscribeState = onVoiceState(stateListener)
    const playerStore = usePlayerStore()
    playerStore.playerId = 'p2'
    playerStore.authToken = 'token'

    const { connect } = useGameWebSocket()
    connect()
    const socket = MockWebSocket.instances[0]!

    socket.onmessage?.(new MessageEvent('message', {
      data: JSON.stringify({
        event: 'voice_signal',
        player: 'p1',
        target_player: 'p2',
        signal_type: 'offer',
        payload: { type: 'offer', sdp: 'v=0' },
      }),
    }))
    socket.onmessage?.(new MessageEvent('message', {
      data: JSON.stringify({
        event: 'voice_state',
        player: 'p1',
        enabled: true,
      }),
    }))

    expect(signalListener).toHaveBeenCalledWith({
      player: 'p1',
      targetPlayer: 'p2',
      signalType: 'offer',
      payload: { type: 'offer', sdp: 'v=0' },
    })
    expect(stateListener).toHaveBeenCalledWith({ player: 'p1', enabled: true })
    unsubscribeSignal()
    unsubscribeState()
  })

  it('uses shared funny quick chat presets for chat bubbles', async () => {
    const playerStore = usePlayerStore()
    playerStore.playerId = 'p1'
    playerStore.authToken = 'token'

    const { connect } = useGameWebSocket()
    connect()
    const socket = MockWebSocket.instances[0]!

    socket.onmessage?.(new MessageEvent('message', {
      data: JSON.stringify({
        event: 'chat_msg',
        player: 'p2',
        msg_id: 0,
      }),
    }))

    const { useGameStore } = await import('@/stores/gameStore')
    const gameStore = useGameStore()
    expect(gameStore.playerActions.p2).toBe('快点吧，牌都快睡着了！')
  })
})

const playSoundMock = vi.fn()
vi.mock('../useSoundEngine', () => ({
  useSoundEngine: () => ({
    playSound: playSoundMock,
    startBgm: vi.fn(),
    stopBgm: vi.fn(),
  }),
}))
