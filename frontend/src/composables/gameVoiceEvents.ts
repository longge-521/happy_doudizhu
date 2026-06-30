export type VoiceSignalType = 'offer' | 'answer' | 'ice_candidate'

export interface VoiceSignalEvent {
  player: string
  targetPlayer: string
  signalType: VoiceSignalType
  payload: Record<string, unknown>
}

export interface VoiceStateEvent {
  player: string
  enabled: boolean
}

type Listener<T> = (event: T) => void

const voiceSignalListeners = new Set<Listener<VoiceSignalEvent>>()
const voiceStateListeners = new Set<Listener<VoiceStateEvent>>()

export function onVoiceSignal(listener: Listener<VoiceSignalEvent>) {
  voiceSignalListeners.add(listener)
  return () => {
    voiceSignalListeners.delete(listener)
  }
}

export function notifyVoiceSignal(event: VoiceSignalEvent) {
  voiceSignalListeners.forEach((listener) => listener(event))
}

export function onVoiceState(listener: Listener<VoiceStateEvent>) {
  voiceStateListeners.add(listener)
  return () => {
    voiceStateListeners.delete(listener)
  }
}

export function notifyVoiceState(event: VoiceStateEvent) {
  voiceStateListeners.forEach((listener) => listener(event))
}
