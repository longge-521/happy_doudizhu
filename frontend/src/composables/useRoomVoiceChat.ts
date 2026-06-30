import { ref } from 'vue'
import {
  type VoiceSignalEvent,
  type VoiceSignalType,
  onVoiceSignal,
  onVoiceState,
} from './gameVoiceEvents'

interface UseRoomVoiceChatOptions {
  selfPlayerId: string
  roomPlayerIds: () => string[]
  sendAction: (payload: Record<string, unknown>) => void
}

type VoiceSignalPayload = Record<string, unknown> | RTCSessionDescriptionInit | RTCIceCandidateInit

const rtcConfig: RTCConfiguration = {
  iceServers: [{ urls: 'stun:stun.l.google.com:19302' }],
}

export function useRoomVoiceChat(options: UseRoomVoiceChatOptions) {
  const isVoiceEnabled = ref(false)
  const isConnecting = ref(false)
  const voiceError = ref('')
  const remoteVoicePlayers = ref<Record<string, boolean>>({})
  const peers = new Map<string, RTCPeerConnection>()
  const makingOffer = new Map<string, boolean>()
  const offerGenerations = new Map<string, number>()
  const pendingIceCandidates = new Map<string, RTCIceCandidateInit[]>()
  let localStream: MediaStream | null = null
  let sessionGeneration = 0
  let isDisposed = false

  function sendSignal(
    targetPlayer: string,
    signalType: VoiceSignalType,
    payload: VoiceSignalPayload,
  ) {
    options.sendAction({
      action: 'voice_signal',
      target_player: targetPlayer,
      signal_type: signalType,
      payload: payload as Record<string, unknown>,
    })
  }

  function getRemotePlayerIds() {
    return options.roomPlayerIds().filter((playerId) => playerId && playerId !== options.selfPlayerId)
  }

  function isPolitePeer(playerId: string) {
    return options.selfPlayerId.localeCompare(playerId) > 0
  }

  function attachRemoteAudio(playerId: string, stream: MediaStream) {
    const audioId = `voice-audio-${playerId}`
    let audio = document.getElementById(audioId) as HTMLAudioElement | null

    if (!audio) {
      audio = document.createElement('audio')
      audio.id = audioId
      audio.autoplay = true
      document.body.appendChild(audio)
    }

    audio.srcObject = stream
    if (typeof audio.play === 'function') {
      void audio.play().catch(() => {
        voiceError.value = '语音播放受阻，请点击页面后重试'
      })
    }
  }

  function removeRemoteAudio(playerId: string) {
    document.getElementById(`voice-audio-${playerId}`)?.remove()
  }

  function stopTracks(stream: MediaStream | null) {
    stream?.getTracks().forEach((track) => track.stop())
  }

  function stopLocalTracks() {
    stopTracks(localStream)
    localStream = null
  }

  function resetPeerState(playerId: string) {
    makingOffer.delete(playerId)
    offerGenerations.delete(playerId)
    pendingIceCandidates.delete(playerId)
  }

  function beginOfferAttempt(playerId: string) {
    const nextGeneration = (offerGenerations.get(playerId) ?? 0) + 1
    offerGenerations.set(playerId, nextGeneration)
    return nextGeneration
  }

  function invalidateOfferAttempt(playerId: string) {
    beginOfferAttempt(playerId)
  }

  function isActiveOfferAttempt(playerId: string, offerGeneration: number) {
    return offerGenerations.get(playerId) === offerGeneration
  }

  function closePeer(playerId: string) {
    const peer = peers.get(playerId)
    if (!peer) {
      resetPeerState(playerId)
      removeRemoteAudio(playerId)
      return
    }

    peer.close()
    peers.delete(playerId)
    resetPeerState(playerId)
    removeRemoteAudio(playerId)
  }

  function queueIceCandidate(playerId: string, candidate: RTCIceCandidateInit) {
    const pending = pendingIceCandidates.get(playerId) ?? []
    pending.push(candidate)
    pendingIceCandidates.set(playerId, pending)
  }

  async function flushPendingIceCandidates(playerId: string, peer: RTCPeerConnection) {
    const pending = pendingIceCandidates.get(playerId)
    if (!pending?.length) {
      return
    }

    pendingIceCandidates.delete(playerId)
    for (const candidate of pending) {
      await peer.addIceCandidate(new RTCIceCandidate(candidate))
    }
  }

  function createPeer(playerId: string) {
    const existingPeer = peers.get(playerId)
    if (existingPeer) {
      return existingPeer
    }

    const peer = new RTCPeerConnection(rtcConfig)
    peers.set(playerId, peer)

    localStream?.getTracks().forEach((track) => {
      peer.addTrack(track, localStream as MediaStream)
    })

    peer.onicecandidate = (event) => {
      const candidate = event.candidate
      if (candidate) {
        const payload =
          typeof candidate.toJSON === 'function'
            ? candidate.toJSON()
            : (candidate as unknown as Record<string, unknown>)
        sendSignal(playerId, 'ice_candidate', payload)
      }
    }

    peer.ontrack = (event) => {
      const [stream] = event.streams
      if (!stream) {
        return
      }

      remoteVoicePlayers.value = {
        ...remoteVoicePlayers.value,
        [playerId]: true,
      }
      attachRemoteAudio(playerId, stream)
    }

    peer.onconnectionstatechange = () => {
      if (['failed', 'closed', 'disconnected'].includes(peer.connectionState)) {
        remoteVoicePlayers.value = {
          ...remoteVoicePlayers.value,
          [playerId]: false,
        }
        peers.delete(playerId)
        resetPeerState(playerId)
        removeRemoteAudio(playerId)
      }
    }

    return peer
  }

  async function createOfferFor(playerId: string, generation: number) {
    const peer = createPeer(playerId)
    const offerGeneration = beginOfferAttempt(playerId)
    makingOffer.set(playerId, true)

    try {
      const offer = await peer.createOffer()
      if (
        generation !== sessionGeneration
        || !isVoiceEnabled.value
        || isDisposed
        || !isActiveOfferAttempt(playerId, offerGeneration)
      ) {
        return
      }

      await peer.setLocalDescription(offer)
      if (
        generation !== sessionGeneration
        || !isVoiceEnabled.value
        || isDisposed
        || !isActiveOfferAttempt(playerId, offerGeneration)
      ) {
        return
      }

      sendSignal(playerId, 'offer', offer as unknown as Record<string, unknown>)
    } finally {
      makingOffer.set(playerId, false)
    }
  }

  async function handleVoiceSignal(event: VoiceSignalEvent) {
    if (event.targetPlayer !== options.selfPlayerId || !isVoiceEnabled.value || isDisposed) {
      return
    }

    const peer = createPeer(event.player)

    if (event.signalType === 'offer') {
      const description = event.payload as unknown as RTCSessionDescriptionInit
      const offerCollision =
        makingOffer.get(event.player) === true || peer.signalingState !== 'stable'

      if (offerCollision && !isPolitePeer(event.player)) {
        return
      }

      invalidateOfferAttempt(event.player)
      if (offerCollision && peer.signalingState !== 'stable') {
        await peer.setLocalDescription({ type: 'rollback' })
      }

      await peer.setRemoteDescription(new RTCSessionDescription(description))
      await flushPendingIceCandidates(event.player, peer)

      const answer = await peer.createAnswer()
      await peer.setLocalDescription(answer)
      sendSignal(event.player, 'answer', answer as unknown as Record<string, unknown>)
      return
    }

    if (event.signalType === 'answer') {
      await peer.setRemoteDescription(new RTCSessionDescription(event.payload as unknown as RTCSessionDescriptionInit))
      await flushPendingIceCandidates(event.player, peer)
      return
    }

    if (event.signalType === 'ice_candidate') {
      const candidate = event.payload as unknown as RTCIceCandidateInit
      if (!peer.remoteDescription) {
        queueIceCandidate(event.player, candidate)
        return
      }

      await peer.addIceCandidate(new RTCIceCandidate(candidate))
    }
  }

  const unsubscribeSignal = onVoiceSignal((event) => {
    void handleVoiceSignal(event).catch(() => {
      voiceError.value = '语音连接失败，可重新开启'
    })
  })

  const unsubscribeState = onVoiceState((event) => {
    if (event.player === options.selfPlayerId || isDisposed) {
      return
    }

    remoteVoicePlayers.value = {
      ...remoteVoicePlayers.value,
      [event.player]: event.enabled,
    }

    if (!event.enabled) {
      closePeer(event.player)
    }
  })

  async function startVoice() {
    if (isDisposed || isVoiceEnabled.value || isConnecting.value) {
      return
    }

    voiceError.value = ''

    if (!navigator.mediaDevices?.getUserMedia || typeof RTCPeerConnection === 'undefined') {
      voiceError.value = '当前浏览器不支持语音'
      return
    }

    const generation = ++sessionGeneration
    isConnecting.value = true

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      if (generation !== sessionGeneration || isDisposed) {
        stopTracks(stream)
        return
      }

      localStream = stream
      isVoiceEnabled.value = true
      options.sendAction({ action: 'voice_state', enabled: true })
      await Promise.all(getRemotePlayerIds().map((playerId) => createOfferFor(playerId, generation)))
    } catch {
      if (generation !== sessionGeneration || isDisposed) {
        return
      }

      voiceError.value = '麦克风权限未开启'
      stopLocalTracks()
      isVoiceEnabled.value = false
    } finally {
      if (generation === sessionGeneration) {
        isConnecting.value = false
      }
    }
  }

  function stopVoice() {
    const wasEnabled = isVoiceEnabled.value

    sessionGeneration += 1
    stopLocalTracks()
    peers.forEach((_, playerId) => {
      closePeer(playerId)
    })
    remoteVoicePlayers.value = {}
    isVoiceEnabled.value = false
    isConnecting.value = false

    if (wasEnabled) {
      options.sendAction({ action: 'voice_state', enabled: false })
    }
  }

  async function toggleVoice() {
    if (isVoiceEnabled.value) {
      stopVoice()
      return
    }

    await startVoice()
  }

  function dispose() {
    if (isDisposed) {
      return
    }

    isDisposed = true
    stopVoice()
    unsubscribeSignal()
    unsubscribeState()
  }

  return {
    isVoiceEnabled,
    isConnecting,
    voiceError,
    remoteVoicePlayers,
    toggleVoice,
    startVoice,
    stopVoice,
    dispose,
  }
}
