// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'

class MockMediaStreamTrack {
  stopped = false
  stop = vi.fn(() => {
    this.stopped = true
  })
}

class MockMediaStream {
  tracks = [new MockMediaStreamTrack()]
  getTracks = vi.fn(() => this.tracks)
}

class MockPeerConnection {
  static instances: MockPeerConnection[] = []
  static createOfferImplementation = async () =>
    ({ type: 'offer', sdp: 'offer-sdp' }) as RTCSessionDescriptionInit
  static createAnswerImplementation = async () =>
    ({ type: 'answer', sdp: 'answer-sdp' }) as RTCSessionDescriptionInit

  localDescription: RTCSessionDescriptionInit | null = null
  remoteDescription: RTCSessionDescriptionInit | null = null
  signalingState: RTCSignalingState = 'stable'
  connectionState: RTCPeerConnectionState = 'new'
  onicecandidate: ((event: RTCPeerConnectionIceEvent) => void) | null = null
  ontrack: ((event: RTCTrackEvent) => void) | null = null
  onconnectionstatechange: (() => void) | null = null
  closed = false
  candidates: RTCIceCandidateInit[] = []

  constructor() {
    MockPeerConnection.instances.push(this)
  }

  addTrack = vi.fn()
  createOffer = vi.fn(() => MockPeerConnection.createOfferImplementation())
  createAnswer = vi.fn(() => MockPeerConnection.createAnswerImplementation())
  setLocalDescription = vi.fn(async (description?: RTCSessionDescriptionInit) => {
    if (description?.type === 'rollback') {
      this.localDescription = null
      this.signalingState = 'stable'
      return
    }

    this.localDescription = description ?? null
    if (description?.type === 'offer') {
      this.signalingState = 'have-local-offer'
      return
    }

    this.signalingState = 'stable'
  })
  setRemoteDescription = vi.fn(async (description: RTCSessionDescriptionInit) => {
    this.remoteDescription = description
    if (description.type === 'offer') {
      this.signalingState = 'have-remote-offer'
      return
    }

    this.signalingState = 'stable'
  })
  addIceCandidate = vi.fn(async (candidate: RTCIceCandidateInit) => {
    this.candidates.push(candidate)
  })
  close = vi.fn(() => {
    this.closed = true
    this.connectionState = 'closed'
    this.signalingState = 'closed'
  })
}

type SendAction = (payload: Record<string, unknown>) => void

function createDeferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((innerResolve, innerReject) => {
    resolve = innerResolve
    reject = innerReject
  })

  return { promise, resolve, reject }
}

async function flushPromises(times = 8) {
  for (let index = 0; index < times; index += 1) {
    await Promise.resolve()
  }
}

async function loadVoiceModules() {
  const gameVoiceEvents = await import('../gameVoiceEvents')
  const roomVoiceChat = await import('../useRoomVoiceChat')

  return {
    ...gameVoiceEvents,
    ...roomVoiceChat,
  }
}

describe('useRoomVoiceChat', () => {
  let stream: MockMediaStream
  let sendAction: SendAction
  let sendActionMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    vi.resetModules()
    vi.unstubAllGlobals()
    document.body.innerHTML = ''
    stream = new MockMediaStream()
    sendActionMock = vi.fn()
    sendAction = sendActionMock as SendAction
    MockPeerConnection.instances = []
    MockPeerConnection.createOfferImplementation = async () =>
      ({ type: 'offer', sdp: 'offer-sdp' }) as RTCSessionDescriptionInit
    MockPeerConnection.createAnswerImplementation = async () =>
      ({ type: 'answer', sdp: 'answer-sdp' }) as RTCSessionDescriptionInit
    vi.stubGlobal('RTCPeerConnection', MockPeerConnection)
    vi.stubGlobal('RTCSessionDescription', function (description: RTCSessionDescriptionInit) {
      return description
    })
    vi.stubGlobal('RTCIceCandidate', function (candidate: RTCIceCandidateInit) {
      return candidate
    })
    vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined)
    Object.defineProperty(globalThis.navigator, 'mediaDevices', {
      value: { getUserMedia: vi.fn(async () => stream as unknown as MediaStream) },
      configurable: true,
    })
  })

  it('starts voice, opens peers for room players, and sends voice_state', async () => {
    const { useRoomVoiceChat } = await loadVoiceModules()
    const voice = useRoomVoiceChat({
      selfPlayerId: 'p1',
      roomPlayerIds: () => ['p1', 'p2', 'p3'],
      sendAction,
    })

    await voice.startVoice()

    expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledWith({ audio: true })
    expect(sendAction).toHaveBeenCalledWith({ action: 'voice_state', enabled: true })
    expect(sendAction).toHaveBeenCalledWith({
      action: 'voice_signal',
      target_player: 'p2',
      signal_type: 'offer',
      payload: { type: 'offer', sdp: 'offer-sdp' },
    })
    expect(sendAction).toHaveBeenCalledWith({
      action: 'voice_signal',
      target_player: 'p3',
      signal_type: 'offer',
      payload: { type: 'offer', sdp: 'offer-sdp' },
    })
    expect(voice.isVoiceEnabled.value).toBe(true)
    expect(MockPeerConnection.instances).toHaveLength(2)
  })

  it('stops tracks and closes peer connections when stopped', async () => {
    const { useRoomVoiceChat } = await loadVoiceModules()
    const voice = useRoomVoiceChat({
      selfPlayerId: 'p1',
      roomPlayerIds: () => ['p1', 'p2'],
      sendAction,
    })

    await voice.startVoice()
    voice.stopVoice()

    expect(stream.tracks[0]!.stop).toHaveBeenCalled()
    expect(MockPeerConnection.instances[0]!.close).toHaveBeenCalled()
    expect(sendAction).toHaveBeenLastCalledWith({ action: 'voice_state', enabled: false })
    expect(voice.isVoiceEnabled.value).toBe(false)
  })

  it('applies remote answers for locally created offers', async () => {
    const { notifyVoiceSignal, useRoomVoiceChat } = await loadVoiceModules()
    const voice = useRoomVoiceChat({
      selfPlayerId: 'p1',
      roomPlayerIds: () => ['p1', 'p2'],
      sendAction,
    })

    await voice.startVoice()
    notifyVoiceSignal({
      player: 'p2',
      targetPlayer: 'p1',
      signalType: 'answer',
      payload: { type: 'answer', sdp: 'remote-answer' },
    })
    await flushPromises()

    expect(MockPeerConnection.instances[0]!.remoteDescription).toEqual({
      type: 'answer',
      sdp: 'remote-answer',
    })
  })

  it('queues ice candidates until a remote offer is applied', async () => {
    const { notifyVoiceSignal, useRoomVoiceChat } = await loadVoiceModules()
    const voice = useRoomVoiceChat({
      selfPlayerId: 'p2',
      roomPlayerIds: () => ['p1', 'p2'],
      sendAction,
    })

    await voice.startVoice()
    notifyVoiceSignal({
      player: 'p1',
      targetPlayer: 'p2',
      signalType: 'ice_candidate',
      payload: { candidate: 'candidate-before-offer' },
    })
    await flushPromises()

    expect(MockPeerConnection.instances[0]!.candidates).toEqual([])

    notifyVoiceSignal({
      player: 'p1',
      targetPlayer: 'p2',
      signalType: 'offer',
      payload: { type: 'offer', sdp: 'remote-offer' },
    })
    await flushPromises()

    expect(MockPeerConnection.instances[0]!.remoteDescription).toEqual({
      type: 'offer',
      sdp: 'remote-offer',
    })
    expect(MockPeerConnection.instances[0]!.candidates).toEqual([
      { candidate: 'candidate-before-offer' },
    ])
    expect(sendAction).toHaveBeenCalledWith({
      action: 'voice_signal',
      target_player: 'p1',
      signal_type: 'answer',
      payload: { type: 'answer', sdp: 'answer-sdp' },
    })
  })

  it('queues ice candidates until a remote answer is applied', async () => {
    const { notifyVoiceSignal, useRoomVoiceChat } = await loadVoiceModules()
    const voice = useRoomVoiceChat({
      selfPlayerId: 'p1',
      roomPlayerIds: () => ['p1', 'p2'],
      sendAction,
    })

    await voice.startVoice()
    notifyVoiceSignal({
      player: 'p2',
      targetPlayer: 'p1',
      signalType: 'ice_candidate',
      payload: { candidate: 'candidate-before-answer' },
    })
    await flushPromises()

    expect(MockPeerConnection.instances[0]!.candidates).toEqual([])

    notifyVoiceSignal({
      player: 'p2',
      targetPlayer: 'p1',
      signalType: 'answer',
      payload: { type: 'answer', sdp: 'remote-answer' },
    })
    await flushPromises()

    expect(MockPeerConnection.instances[0]!.candidates).toEqual([
      { candidate: 'candidate-before-answer' },
    ])
  })

  it('handles remote voice_state off by closing the peer and removing audio', async () => {
    const { notifyVoiceState, useRoomVoiceChat } = await loadVoiceModules()
    const voice = useRoomVoiceChat({
      selfPlayerId: 'p1',
      roomPlayerIds: () => ['p1', 'p2'],
      sendAction,
    })

    await voice.startVoice()
    const remoteStream = new MockMediaStream() as unknown as MediaStream
    MockPeerConnection.instances[0]!.ontrack?.({ streams: [remoteStream] } as unknown as RTCTrackEvent)

    expect(document.getElementById('voice-audio-p2')).not.toBeNull()
    expect(voice.remoteVoicePlayers.value.p2).toBe(true)

    notifyVoiceState({ player: 'p2', enabled: false })

    expect(MockPeerConnection.instances[0]!.close).toHaveBeenCalled()
    expect(document.getElementById('voice-audio-p2')).toBeNull()
    expect(voice.remoteVoicePlayers.value.p2).toBe(false)
  })

  it('ignores late getUserMedia completion after stop', async () => {
    const deferredStream = createDeferred<MediaStream>()
    vi.mocked(navigator.mediaDevices.getUserMedia).mockImplementationOnce(() => deferredStream.promise)
    const { useRoomVoiceChat } = await loadVoiceModules()
    const voice = useRoomVoiceChat({
      selfPlayerId: 'p1',
      roomPlayerIds: () => ['p1', 'p2'],
      sendAction,
    })

    const startPromise = voice.startVoice()
    voice.stopVoice()
    deferredStream.resolve(stream as unknown as MediaStream)
    await startPromise

    expect(voice.isVoiceEnabled.value).toBe(false)
    expect(voice.isConnecting.value).toBe(false)
    expect(stream.tracks[0]!.stop).toHaveBeenCalled()
    expect(sendAction).not.toHaveBeenCalledWith({ action: 'voice_state', enabled: true })
    expect(sendAction).not.toHaveBeenCalledWith(
      expect.objectContaining({
        action: 'voice_signal',
        signal_type: 'offer',
      }),
    )
  })

  it('rolls back and answers on offer collision for polite peers', async () => {
    const { notifyVoiceSignal, useRoomVoiceChat } = await loadVoiceModules()
    const voice = useRoomVoiceChat({
      selfPlayerId: 'p2',
      roomPlayerIds: () => ['p1', 'p2'],
      sendAction,
    })

    await voice.startVoice()
    notifyVoiceSignal({
      player: 'p1',
      targetPlayer: 'p2',
      signalType: 'offer',
      payload: { type: 'offer', sdp: 'remote-offer' },
    })
    await flushPromises()

    expect(MockPeerConnection.instances[0]!.setLocalDescription).toHaveBeenCalledWith({ type: 'rollback' })
    expect(MockPeerConnection.instances[0]!.remoteDescription).toEqual({
      type: 'offer',
      sdp: 'remote-offer',
    })
    expect(sendAction).toHaveBeenCalledWith({
      action: 'voice_signal',
      target_player: 'p1',
      signal_type: 'answer',
      payload: { type: 'answer', sdp: 'answer-sdp' },
    })
  })

  it('does not send a stale local offer after accepting a remote offer during createOffer', async () => {
    const deferredOffer = createDeferred<RTCSessionDescriptionInit>()
    const localOffer = { type: 'offer', sdp: 'late-offer' } satisfies RTCSessionDescriptionInit
    MockPeerConnection.createOfferImplementation = () => deferredOffer.promise

    const { notifyVoiceSignal, useRoomVoiceChat } = await loadVoiceModules()
    const voice = useRoomVoiceChat({
      selfPlayerId: 'p2',
      roomPlayerIds: () => ['p1', 'p2'],
      sendAction,
    })

    const startPromise = voice.startVoice()
    await flushPromises()

    notifyVoiceSignal({
      player: 'p1',
      targetPlayer: 'p2',
      signalType: 'offer',
      payload: { type: 'offer', sdp: 'remote-offer-during-create' },
    })
    await flushPromises()

    expect(sendAction).toHaveBeenCalledWith({
      action: 'voice_signal',
      target_player: 'p1',
      signal_type: 'answer',
      payload: { type: 'answer', sdp: 'answer-sdp' },
    })

    deferredOffer.resolve(localOffer)
    await startPromise
    await flushPromises()

    expect(
      MockPeerConnection.instances[0]!.setLocalDescription.mock.calls.some(
        ([description]) => description?.type === 'offer' && description.sdp === 'late-offer',
      ),
    ).toBe(false)
    expect(
      sendActionMock.mock.calls.some(
        ([payload]) =>
          payload.action === 'voice_signal'
          && payload.target_player === 'p1'
          && payload.signal_type === 'offer'
          && (payload.payload as RTCSessionDescriptionInit | undefined)?.sdp === 'late-offer',
      ),
    ).toBe(false)
  })

  it('ignores colliding offers for impolite peers', async () => {
    const { notifyVoiceSignal, useRoomVoiceChat } = await loadVoiceModules()
    const voice = useRoomVoiceChat({
      selfPlayerId: 'p1',
      roomPlayerIds: () => ['p1', 'p2'],
      sendAction,
    })

    await voice.startVoice()
    notifyVoiceSignal({
      player: 'p2',
      targetPlayer: 'p1',
      signalType: 'offer',
      payload: { type: 'offer', sdp: 'remote-offer' },
    })
    await flushPromises()

    expect(MockPeerConnection.instances[0]!.setLocalDescription).not.toHaveBeenCalledWith({ type: 'rollback' })
    expect(MockPeerConnection.instances[0]!.remoteDescription).not.toEqual({
      type: 'offer',
      sdp: 'remote-offer',
    })
    expect(sendAction).not.toHaveBeenCalledWith({
      action: 'voice_signal',
      target_player: 'p2',
      signal_type: 'answer',
      payload: { type: 'answer', sdp: 'answer-sdp' },
    })
  })

  it('disposes subscriptions and resources cleanly', async () => {
    const { notifyVoiceSignal, notifyVoiceState, useRoomVoiceChat } = await loadVoiceModules()
    const voice = useRoomVoiceChat({
      selfPlayerId: 'p1',
      roomPlayerIds: () => ['p1', 'p2'],
      sendAction,
    })

    await voice.startVoice()
    const actionsBeforeDispose = sendActionMock.mock.calls.length

    voice.dispose()
    notifyVoiceState({ player: 'p2', enabled: true })
    notifyVoiceSignal({
      player: 'p2',
      targetPlayer: 'p1',
      signalType: 'offer',
      payload: { type: 'offer', sdp: 'remote-offer' },
    })
    await flushPromises()

    expect(stream.tracks[0]!.stop).toHaveBeenCalled()
    expect(MockPeerConnection.instances[0]!.close).toHaveBeenCalled()
    expect(sendAction).toHaveBeenLastCalledWith({ action: 'voice_state', enabled: false })
    expect(sendActionMock.mock.calls).toHaveLength(actionsBeforeDispose + 1)
    expect(voice.remoteVoicePlayers.value).toEqual({})
  })

  it('sets an error when microphone permission fails', async () => {
    vi.mocked(navigator.mediaDevices.getUserMedia).mockRejectedValueOnce(new Error('denied'))
    const { useRoomVoiceChat } = await loadVoiceModules()
    const voice = useRoomVoiceChat({
      selfPlayerId: 'p1',
      roomPlayerIds: () => ['p1', 'p2'],
      sendAction,
    })

    await voice.startVoice()

    expect(voice.voiceError.value).toBe('麦克风权限未开启')
    expect(voice.isVoiceEnabled.value).toBe(false)
    expect(sendAction).not.toHaveBeenCalledWith({ action: 'voice_state', enabled: true })
  })
})
