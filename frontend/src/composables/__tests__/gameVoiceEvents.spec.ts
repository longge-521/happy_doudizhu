import { describe, expect, it, vi } from 'vitest'
import {
  notifyVoiceSignal,
  notifyVoiceState,
  onVoiceSignal,
  onVoiceState,
} from '../gameVoiceEvents'

describe('gameVoiceEvents', () => {
  it('notifies and unsubscribes voice signal listeners', () => {
    const listener = vi.fn()
    const unsubscribe = onVoiceSignal(listener)

    notifyVoiceSignal({
      player: 'p1',
      targetPlayer: 'p2',
      signalType: 'offer',
      payload: { type: 'offer', sdp: 'v=0' },
    })
    unsubscribe()
    notifyVoiceSignal({
      player: 'p1',
      targetPlayer: 'p2',
      signalType: 'answer',
      payload: { type: 'answer', sdp: 'v=0' },
    })

    expect(listener).toHaveBeenCalledTimes(1)
    expect(listener).toHaveBeenCalledWith({
      player: 'p1',
      targetPlayer: 'p2',
      signalType: 'offer',
      payload: { type: 'offer', sdp: 'v=0' },
    })
  })

  it('notifies and unsubscribes voice state listeners', () => {
    const listener = vi.fn()
    const unsubscribe = onVoiceState(listener)

    notifyVoiceState({ player: 'p1', enabled: true })
    unsubscribe()
    notifyVoiceState({ player: 'p1', enabled: false })

    expect(listener).toHaveBeenCalledTimes(1)
    expect(listener).toHaveBeenCalledWith({ player: 'p1', enabled: true })
  })
})
