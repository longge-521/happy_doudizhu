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

const rtcConfig: RTCConfiguration = {
  iceServers: [{ urls: 'stun:stun.l.google.com:19302' }],
}

export function useRoomVoiceChat(options: UseRoomVoiceChatOptions) {
  const isVoiceEnabled = ref(false)
  const isConnecting = ref(false)
  const voiceError = ref('')
  const remoteVoicePlayers = ref<Record<string, boolean>>({})
  const peers = new Map<string, RTCPeerConnection>()
  let localStream: MediaStream | null = null

  function sendSignal(
    targetPlayer: string,
    signalType: VoiceSignalType,
    payload: Record<string, unknown>,
  ) {
    options.sendAction({
      action: 'voice_signal',
      target_player: targetPlayer,
      signal_type: signalType,
      payload,
    })
  }

  function getRemotePlayerIds() {
    return options.roomPlayerIds().filter((playerId) => playerId && playerId !== options.selfPlayerId)
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
        removeRemoteAudio(playerId)
      }
    }

    return peer
  }

  async function createOfferFor(playerId: string) {
    const peer = createPeer(playerId)
    const offer = await peer.createOffer()
    await peer.setLocalDescription(offer)
    sendSignal(playerId, 'offer', offer as unknown as Record<string, unknown>)
  }

  async function handleVoiceSignal(event: VoiceSignalEvent) {
    if (event.targetPlayer !== options.selfPlayerId || !isVoiceEnabled.value) {
      return
    }

    const peer = createPeer(event.player)

    if (event.signalType === 'offer') {
      await peer.setRemoteDescription(new RTCSessionDescription(event.payload as RTCSessionDescriptionInit))
      const answer = await peer.createAnswer()
      await peer.setLocalDescription(answer)
      sendSignal(event.player, 'answer', answer as unknown as Record<string, unknown>)
      return
    }

    if (event.signalType === 'answer') {
      await peer.setRemoteDescription(new RTCSessionDescription(event.payload as RTCSessionDescriptionInit))
      return
    }

    if (event.signalType === 'ice_candidate') {
      await peer.addIceCandidate(new RTCIceCandidate(event.payload as RTCIceCandidateInit))
    }
  }

  function stopLocalTracks() {
    localStream?.getTracks().forEach((track) => track.stop())
    localStream = null
  }

  const unsubscribeSignal = onVoiceSignal((event) => {
    void handleVoiceSignal(event).catch(() => {
      voiceError.value = '语音连接失败，可重新开启'
    })
  })

  const unsubscribeState = onVoiceState((event) => {
    if (event.player === options.selfPlayerId) {
      return
    }

    remoteVoicePlayers.value = {
      ...remoteVoicePlayers.value,
      [event.player]: event.enabled,
    }

    if (!event.enabled) {
      const peer = peers.get(event.player)
      peer?.close()
      peers.delete(event.player)
      removeRemoteAudio(event.player)
    }
  })

  async function startVoice() {
    if (isVoiceEnabled.value || isConnecting.value) {
      return
    }

    voiceError.value = ''

    if (!navigator.mediaDevices?.getUserMedia || typeof RTCPeerConnection === 'undefined') {
      voiceError.value = '当前浏览器不支持语音'
      return
    }

    isConnecting.value = true

    try {
      localStream = await navigator.mediaDevices.getUserMedia({ audio: true })
      isVoiceEnabled.value = true
      options.sendAction({ action: 'voice_state', enabled: true })
      await Promise.all(getRemotePlayerIds().map((playerId) => createOfferFor(playerId)))
    } catch {
      voiceError.value = '麦克风权限未开启'
      stopLocalTracks()
      isVoiceEnabled.value = false
    } finally {
      isConnecting.value = false
    }
  }

  function stopVoice() {
    const wasEnabled = isVoiceEnabled.value

    stopLocalTracks()
    peers.forEach((peer, playerId) => {
      peer.close()
      removeRemoteAudio(playerId)
    })
    peers.clear()
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
