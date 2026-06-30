// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { notifyVoiceSignal } from '../gameVoiceEvents'

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
  localDescription: RTCSessionDescriptionInit | null = null
  remoteDescription: RTCSessionDescriptionInit | null = null
  onicecandidate: ((event: RTCPeerConnectionIceEvent) => void) | null = null
  ontrack: ((event: RTCTrackEvent) => void) | null = null
  closed = false
  candidates: RTCIceCandidateInit[] = []

  constructor() {
    MockPeerConnection.instances.push(this)
  }

  addTrack = vi.fn()
  createOffer = vi.fn(async () => ({ type: 'offer', sdp: 'offer-sdp' }) as RTCSessionDescriptionInit)
  createAnswer = vi.fn(async () => ({ type: 'answer', sdp: 'answer-sdp' }) as RTCSessionDescriptionInit)
  setLocalDescription = vi.fn(async (description: RTCSessionDescriptionInit) => {
    this.localDescription = description
  })
  setRemoteDescription = vi.fn(async (description: RTCSessionDescriptionInit) => {
    this.remoteDescription = description
  })
  addIceCandidate = vi.fn(async (candidate: RTCIceCandidateInit) => {
    this.candidates.push(candidate)
  })
  close = vi.fn(() => {
    this.closed = true
  })
}

describe('useRoomVoiceChat', () => {
  let stream: MockMediaStream
  let sendAction: ReturnType<typeof vi.fn>

  beforeEach(() => {
    vi.unstubAllGlobals()
    stream = new MockMediaStream()
    sendAction = vi.fn()
    MockPeerConnection.instances = []
    vi.stubGlobal('RTCPeerConnection', MockPeerConnection)
    vi.stubGlobal('RTCSessionDescription', function (description: RTCSessionDescriptionInit) {
      return description
    })
    vi.stubGlobal('RTCIceCandidate', function (candidate: RTCIceCandidateInit) {
      return candidate
    })
    Object.defineProperty(globalThis.navigator, 'mediaDevices', {
      value: { getUserMedia: vi.fn(async () => stream) },
      configurable: true,
    })
  })

  it('starts voice, opens peers for room players, and sends voice_state', async () => {
    const { useRoomVoiceChat } = await import('../useRoomVoiceChat')
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
  })

  it('stops tracks and closes peer connections when stopped', async () => {
    const { useRoomVoiceChat } = await import('../useRoomVoiceChat')
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

  it('answers incoming offers and applies ice candidates', async () => {
    const { useRoomVoiceChat } = await import('../useRoomVoiceChat')
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
    await Promise.resolve()
    await Promise.resolve()
    notifyVoiceSignal({
      player: 'p1',
      targetPlayer: 'p2',
      signalType: 'ice_candidate',
      payload: { candidate: 'candidate-1' },
    })
    await Promise.resolve()

    const peer = MockPeerConnection.instances.find((item) => item.remoteDescription?.sdp === 'remote-offer')
    expect(peer).toBeDefined()
    expect(sendAction).toHaveBeenCalledWith({
      action: 'voice_signal',
      target_player: 'p1',
      signal_type: 'answer',
      payload: { type: 'answer', sdp: 'answer-sdp' },
    })
    expect(peer!.candidates).toEqual([{ candidate: 'candidate-1' }])
  })

  it('sets an error when microphone permission fails', async () => {
    vi.mocked(navigator.mediaDevices.getUserMedia).mockRejectedValueOnce(new Error('denied'))
    const { useRoomVoiceChat } = await import('../useRoomVoiceChat')
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
