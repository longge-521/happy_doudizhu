import { CHAT_PRESETS } from '@/constants/chatPresets'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  clearCardPresentationEffectTimer,
  playCardPresentationEffects,
  playDoubleChoiceSound,
  playQuickChatMessage,
} from '../gameWebSocketEffects'

const playSoundMock = vi.fn()
const playQuickChatVoiceMock = vi.fn()

vi.mock('../useSoundEngine', () => ({
  useSoundEngine: () => ({
    playSound: playSoundMock,
    playQuickChatVoice: playQuickChatVoiceMock,
  }),
}))

describe('gameWebSocketEffects', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    playSoundMock.mockClear()
    playQuickChatVoiceMock.mockClear()
    clearCardPresentationEffectTimer()
  })

  afterEach(() => {
    clearCardPresentationEffectTimer()
    vi.useRealTimers()
  })

  it('plays super double choice sound in two steps', () => {
    playDoubleChoiceSound('super', 'p2')

    expect(playSoundMock).toHaveBeenCalledWith('doubling')
    expect(playSoundMock).not.toHaveBeenCalledWith('superDouble', 'p2')

    vi.advanceTimersByTime(120)

    expect(playSoundMock).toHaveBeenCalledWith('superDouble', 'p2')
  })

  it('plays quick chat voice by preset id', () => {
    playQuickChatMessage(0, 'p2')

    expect(playQuickChatVoiceMock).toHaveBeenCalledWith(CHAT_PRESETS[0], 'p2', 0)
  })

  it('plays bomb effect and clears visual effect later', () => {
    const gameStore = { activeEffect: '' as 'bomb' | 'plane' | 'shimmer' | '' }

    playCardPresentationEffects([36, 37, 38, 39], 'p2', gameStore)

    expect(playSoundMock).toHaveBeenCalledWith('bomb_effect')
    expect(gameStore.activeEffect).toBe('bomb')

    vi.advanceTimersByTime(200)
    expect(playSoundMock).toHaveBeenCalledWith('bomb', 'p2')

    vi.advanceTimersByTime(1300)
    expect(gameStore.activeEffect).toBe('')
  })

  it('plays rank voice for a single card', () => {
    const gameStore = { activeEffect: '' as 'bomb' | 'plane' | 'shimmer' | '' }

    playCardPresentationEffects([0], 'p2', gameStore)

    expect(playSoundMock).toHaveBeenCalledWith('playCard')
    vi.advanceTimersByTime(100)
    expect(playSoundMock).toHaveBeenCalledWith('3', 'p2')
    expect(gameStore.activeEffect).toBe('')
  })
})
