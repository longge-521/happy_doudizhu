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
  sentMessages: string[] = []

  constructor(public url: string) {
    MockWebSocket.instances.push(this)
  }

  send(message: string) {
    this.sentMessages.push(message)
  }

  close() {
    this.onclose?.(new CloseEvent('close', { code: 1000 }))
  }
}

describe('useGameWebSocket', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    playSoundMock.mockClear()
    playQuickChatVoiceMock.mockClear()
    MockWebSocket.instances = []
    vi.stubGlobal('WebSocket', MockWebSocket)
    setActivePinia(createPinia())
    localStorage.clear()
  })

  afterEach(() => {
    useGameWebSocket().disconnect()
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

  it('requests room state when no websocket event arrives for five seconds', async () => {
    const playerStore = usePlayerStore()
    playerStore.playerId = 'player1'
    playerStore.authToken = 'token'
    const { useGameStore } = await import('@/stores/gameStore')
    const gameStore = useGameStore()
    gameStore.roomId = 'room-1'

    const { connect } = useGameWebSocket()
    connect()
    const socket = MockWebSocket.instances[0]!
    socket.readyState = MockWebSocket.OPEN
    socket.onopen?.()

    await vi.advanceTimersByTimeAsync(5_100)

    const actions = socket.sentMessages.map((message) => JSON.parse(message))
    expect(actions.some((action) => action.action === 'sync_room_state')).toBe(true)
  })

  it('starts fifty-k directly in playing phase and applies server balances', async () => {
    const playerStore = usePlayerStore()
    playerStore.playerId = 'p1'
    playerStore.authToken = 'token'
    const { connect } = useGameWebSocket()
    connect()
    const socket = MockWebSocket.instances[0]!

    socket.onmessage?.(new MessageEvent('message', {
      data: JSON.stringify({
        event: 'game_start',
        room_id: 'room-510k-state',
        hand: [8, 28, 40],
        current_turn: 'p1',
        turn_deadline: 123,
        phase: 'PLAYING',
        play_mode: 'fifty_k',
        scores: { p1: 0, p2: 0, p3: 0 },
        bean_balances: { p1: 10000, p2: 9000, p3: 8000 },
        players: [],
      }),
    }))

    const { useGameStore } = await import('@/stores/gameStore')
    const gameStore = useGameStore()
    expect(gameStore.gamePhase).toBe('PLAYING')
    expect(gameStore.playMode).toBe('fifty_k')
    expect(gameStore.beanBalances).toEqual({ p1: 10000, p2: 9000, p3: 8000 })
  })

  it('announces the club-three starter when a fifty-k game begins', async () => {
    const playerStore = usePlayerStore()
    playerStore.playerId = 'p1'
    playerStore.authToken = 'token'
    const { connect } = useGameWebSocket()
    connect()
    const socket = MockWebSocket.instances[0]!

    socket.onmessage?.(new MessageEvent('message', {
      data: JSON.stringify({
        event: 'game_start',
        room_id: 'room-510k-announce',
        hand: [2, 8, 28],
        current_turn: 'p1',
        phase: 'PLAYING',
        play_mode: 'fifty_k',
        players: [],
      }),
    }))

    vi.advanceTimersByTime(2200)

    expect(playSoundMock).toHaveBeenCalledWith('club_three_first', 'p1')
    expect(playQuickChatVoiceMock).not.toHaveBeenCalled()
  })

  it('announces the club-three starter only once for duplicate game_start events in the same room', () => {
    const playerStore = usePlayerStore()
    playerStore.playerId = 'p1'
    playerStore.authToken = 'token'
    const { connect } = useGameWebSocket()
    connect()
    const socket = MockWebSocket.instances[0]!
    const event = new MessageEvent('message', {
      data: JSON.stringify({
        event: 'game_start',
        room_id: 'room-510k-duplicate',
        hand: [2, 8, 28],
        current_turn: 'p1',
        phase: 'PLAYING',
        play_mode: 'fifty_k',
        players: [],
      }),
    })

    socket.onmessage?.(event)
    socket.onmessage?.(event)

    vi.advanceTimersByTime(2200)

    expect(playSoundMock).toHaveBeenCalledTimes(1)
    expect(playSoundMock).toHaveBeenCalledWith('club_three_first', 'p1')
  })

  it('does not announce the club-three starter when a classic game begins', () => {
    const playerStore = usePlayerStore()
    playerStore.playerId = 'p1'
    playerStore.authToken = 'token'
    const { connect } = useGameWebSocket()
    connect()
    const socket = MockWebSocket.instances[0]!

    socket.onmessage?.(new MessageEvent('message', {
      data: JSON.stringify({
        event: 'game_start',
        room_id: 'room-classic',
        hand: [2, 8, 28],
        current_turn: 'p1',
        phase: 'CALLING',
        play_mode: 'classic',
        players: [],
      }),
    }))

    expect(playSoundMock).not.toHaveBeenCalledWith('club_three_first', expect.anything())
    expect(playQuickChatVoiceMock).not.toHaveBeenCalled()
  })

  it('does not announce the same fifty-k room again after an explicit disconnect', () => {
    const playerStore = usePlayerStore()
    playerStore.playerId = 'p1'
    playerStore.authToken = 'token'
    const { connect, disconnect } = useGameWebSocket()
    const event = new MessageEvent('message', {
      data: JSON.stringify({
        event: 'game_start',
        room_id: 'room-510k-disconnect',
        hand: [2, 8, 28],
        current_turn: 'p1',
        phase: 'PLAYING',
        play_mode: 'fifty_k',
        players: [],
      }),
    })

    connect()
    MockWebSocket.instances[0]!.onmessage?.(event)
    vi.advanceTimersByTime(2200)
    disconnect()
    connect()
    MockWebSocket.instances[1]!.onmessage?.(event)
    vi.advanceTimersByTime(2200)

    expect(playSoundMock).toHaveBeenCalledTimes(1)
    expect(playSoundMock).toHaveBeenCalledWith('club_three_first', 'p1')
  })

  it('does not announce the club-three starter from a reconnected state snapshot', () => {
    const playerStore = usePlayerStore()
    playerStore.playerId = 'p1'
    playerStore.authToken = 'token'
    const { connect } = useGameWebSocket()
    connect()

    MockWebSocket.instances[0]!.onmessage?.(new MessageEvent('message', {
      data: JSON.stringify({
        event: 'reconnected',
        room_id: 'room-510k-reconnected',
        hand: [2, 8, 28],
        current_turn: 'p1',
        phase: 'PLAYING',
        play_mode: 'fifty_k',
        players: [],
      }),
    }))

    expect(playSoundMock).not.toHaveBeenCalledWith('club_three_first', expect.anything())
  })

  it('does not announce the club-three starter when a no-shuffle game begins', () => {
    const playerStore = usePlayerStore()
    playerStore.playerId = 'p1'
    playerStore.authToken = 'token'
    const { connect } = useGameWebSocket()
    connect()

    MockWebSocket.instances[0]!.onmessage?.(new MessageEvent('message', {
      data: JSON.stringify({
        event: 'game_start',
        room_id: 'room-no-shuffle',
        hand: [2, 8, 28],
        current_turn: 'p1',
        phase: 'CALLING',
        play_mode: 'no_shuffle',
        players: [],
      }),
    }))

    expect(playSoundMock).not.toHaveBeenCalledWith('club_three_first', expect.anything())
    expect(playQuickChatVoiceMock).not.toHaveBeenCalled()
  })

  it('applies authoritative balances from trick settlement', async () => {
    const playerStore = usePlayerStore()
    playerStore.playerId = 'p1'
    playerStore.authToken = 'token'
    const { connect } = useGameWebSocket()
    connect()
    const socket = MockWebSocket.instances[0]!

    socket.onmessage?.(new MessageEvent('message', {
      data: JSON.stringify({
        event: 'trick_settled',
        trick_no: 1,
        winner_id: 'p1',
        trick_cards: [8, 28, 40],
        score_gained: 35,
        bean_changes: { p1: 350, p2: -175, p3: -175 },
        bean_balances: { p1: 10350, p2: 9825, p3: 9825 },
        current_scores: { p1: 35, p2: 0, p3: 0 },
      }),
    }))

    const { useGameStore } = await import('@/stores/gameStore')
    const gameStore = useGameStore()
    expect(gameStore.scores).toEqual({ p1: 35, p2: 0, p3: 0 })
    expect(gameStore.beanBalances).toEqual({ p1: 10350, p2: 9825, p3: 9825 })
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

  it('serializes typed client actions before sending them', () => {
    const playerStore = usePlayerStore()
    playerStore.playerId = 'p1'
    playerStore.authToken = 'token'

    const { connect, disconnect, sendAction } = useGameWebSocket()
    connect()
    const socket = MockWebSocket.instances[0]!
    socket.readyState = MockWebSocket.OPEN

    sendAction({ action: 'play_cards', cards: [3, 4, 5] })

    expect(socket.sentMessages).toHaveLength(1)
    const sentMsg = JSON.parse(socket.sentMessages[0]!)
    expect(sentMsg.action).toBe('play_cards')
    expect(sentMsg.cards).toEqual([3, 4, 5])
    expect(sentMsg.action_id).toBeDefined()
    expect(typeof sentMsg.action_id).toBe('string')
    disconnect()
  })

  it('stores AI hints and auto-play state from websocket messages', async () => {
    const playerStore = usePlayerStore()
    playerStore.playerId = 'p1'
    playerStore.authToken = 'token'

    const { connect, disconnect } = useGameWebSocket()
    connect()
    const socket = MockWebSocket.instances[0]!

    socket.onmessage?.(new MessageEvent('message', {
      data: JSON.stringify({
        event: 'ai_hints',
        candidates: [[0, 1]],
        source: 'douzero',
      }),
    }))
    socket.onmessage?.(new MessageEvent('message', {
      data: JSON.stringify({
        event: 'auto_play_changed',
        player: 'p1',
        enabled: true,
      }),
    }))

    const { useGameStore } = await import('@/stores/gameStore')
    const gameStore = useGameStore()
    expect(gameStore.aiHintCandidates).toEqual([[1, 0]])
    expect(gameStore.aiHintSource).toBe('douzero')
    expect(gameStore.autoPlayPlayers).toContain('p1')
    disconnect()
  })

  it('plays quick chat voice without showing chat text on the table', async () => {
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
    expect(playQuickChatVoiceMock).toHaveBeenCalledWith('大家好，很高兴见到各位。', 'p2', 0)
    expect(playSoundMock).not.toHaveBeenCalledWith('chatMsg')
    expect(gameStore.playerActions.p2).toBeUndefined()
  })

  it('triggers alarm sound and balloon text when remaining card count is 1 or 2 after cards_played', async () => {
    vi.useFakeTimers()
    const { usePlayerStore } = await import('@/stores/playerStore')
    const playerStore = usePlayerStore()
    playerStore.playerId = 'p2'
    playerStore.authToken = 'token'

    const { useGameStore } = await import('@/stores/gameStore')
    const gameStore = useGameStore()
    
    gameStore.players = [
      { id: 'p2', nickname: 'Test2', isAi: false, isOnline: true, remaining: 17, isLandlord: false, isSelf: false }
    ]

    const { connect } = useGameWebSocket()
    connect()
    const socket = MockWebSocket.instances[0]!

    socket.onmessage?.(new MessageEvent('message', {
      data: JSON.stringify({
        event: 'cards_played',
        player: 'p2',
        cards: [1, 2],
        room_state: {
          players: [
            { id: 'p2', nickname: 'Test2', is_ai: false, is_online: true, remaining: 2, is_landlord: false, is_self: false }
          ]
        }
      }),
    }))

    expect(playSoundMock).toHaveBeenCalledWith('baojing2', 'p2')
    expect(gameStore.playerActions.p2).toBe('')

    vi.useRealTimers()
  })
})

const playSoundMock = vi.fn()
const playQuickChatVoiceMock = vi.fn()
vi.mock('../useSoundEngine', () => ({
  useSoundEngine: () => ({
    playSound: playSoundMock,
    playQuickChatVoice: playQuickChatVoiceMock,
    startBgm: vi.fn(),
    stopBgm: vi.fn(),
  }),
}))
