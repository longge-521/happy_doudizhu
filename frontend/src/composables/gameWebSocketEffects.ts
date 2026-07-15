import { CHAT_PRESETS } from '@/constants/chatPresets'
import { detectCardPlay, type PlayMode } from '@/utils/cardUtils'
import { useSoundEngine } from './useSoundEngine'

export type PresentationEffect = 'bomb' | 'plane' | 'shimmer' | ''

export interface GameEffectStore {
  activeEffect: PresentationEffect
}

let effectTimer: number | null = null

export function clearCardPresentationEffectTimer() {
  if (effectTimer) {
    clearTimeout(effectTimer)
    effectTimer = null
  }
}

function setTimedEffect(gameStore: GameEffectStore, effect: PresentationEffect) {
  clearCardPresentationEffectTimer()
  gameStore.activeEffect = effect
  effectTimer = window.setTimeout(() => {
    gameStore.activeEffect = ''
    effectTimer = null
  }, 1500)
}

function getVoiceRank(mainRank: number | undefined): number {
  if (mainRank === 13) return 16
  if (mainRank === 14) return 17
  if (mainRank !== undefined) return mainRank + 3
  return 3
}

export function playCardPresentationEffects(
  cards: number[],
  playerId: string,
  gameStore: GameEffectStore,
  playMode: PlayMode = 'classic',
) {
  const { playSound } = useSoundEngine()
  const play = detectCardPlay(cards, playMode)
  if (!play) {
    playSound('playCard', playerId)
    return
  }

  const cardVal = getVoiceRank(play.mainRank)

  if (play.kind === 'bomb') {
    playSound('bomb_effect')
    setTimeout(() => playSound('bomb', playerId), 200)
    setTimedEffect(gameStore, 'bomb')
  } else if (play.kind === 'fifty_k_true' || play.kind === 'fifty_k_false') {
    const voiceName = play.kind === 'fifty_k_true' ? 'fifty_k_true' : 'fifty_k_false'
    playSound('playCard')
    setTimeout(() => playSound(voiceName, playerId), 200)
  } else if (play.kind === 'rocket') {
    playSound('bomb_effect')
    setTimeout(() => playSound('rocket', playerId), 200)
    setTimedEffect(gameStore, 'bomb')
  } else if (play.kind === 'airplane' || play.kind === 'airplane_single' || play.kind === 'airplane_pair') {
    playSound('plane_effect')
    setTimeout(() => playSound('airplane', playerId), 200)
    setTimedEffect(gameStore, 'plane')
  } else if (play.kind === 'straight') {
    playSound('shunzi_effect')
    setTimeout(() => playSound('straight', playerId), 200)
    setTimedEffect(gameStore, 'shimmer')
  } else if (play.kind === 'double_straight') {
    playSound('shunzi_effect')
    setTimeout(() => playSound('double_straight', playerId), 200)
    setTimedEffect(gameStore, 'shimmer')
  } else if (play.kind === 'single') {
    playSound('playCard')
    setTimeout(() => playSound(String(cardVal) as `${number}`, playerId), 100)
  } else if (play.kind === 'pair') {
    playSound('playCard')
    setTimeout(() => playSound(`pair${cardVal}`, playerId), 100)
  } else if (play.kind === 'triple') {
    playSound('playCard')
    setTimeout(() => playSound(`three_one${cardVal}`, playerId), 100)
  } else if (play.kind === 'triple_one') {
    playSound('playCard')
    setTimeout(() => playSound('three_one', playerId), 100)
  } else if (play.kind === 'triple_two') {
    playSound('playCard')
    setTimeout(() => playSound('three_two', playerId), 100)
  } else if (play.kind === 'four_two_single') {
    playSound('playCard')
    setTimeout(() => playSound('four_two_single', playerId), 100)
  } else if (play.kind === 'four_two_pair') {
    playSound('playCard')
    setTimeout(() => playSound('four_two_pair', playerId), 100)
  } else {
    playSound('playCard', playerId)
  }
}

export function getDoubleChoiceLabel(choice: string) {
  if (choice === 'double') return '加倍'
  if (choice === 'super') return '超级加倍'
  return '不加倍'
}

export function playDoubleChoiceSound(choice: string, playerId: string) {
  const { playSound } = useSoundEngine()
  if (choice === 'double') {
    playSound('doubling')
    setTimeout(() => playSound('jiabei', playerId), 120)
  } else if (choice === 'super') {
    playSound('doubling')
    setTimeout(() => playSound('superDouble', playerId), 120)
  } else {
    playSound('bujiabei', playerId)
  }
}

export function playQuickChatMessage(msgId: number, playerId: string) {
  const { playQuickChatVoice } = useSoundEngine()
  const msg = CHAT_PRESETS[msgId] || '...'
  void playQuickChatVoice(msg, playerId, msgId)
}
