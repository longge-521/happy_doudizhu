import { describe, it, expect } from 'vitest'
import { findAllPlayableHints, detectCardPlay, canBeatCardPlay } from '../cardUtils'

describe('cardUtils - 510K rules', () => {
  it('isolates 510K detection from classic mode', () => {
    expect(detectCardPlay([8, 28, 40], 'classic')).toBeNull()
    expect(detectCardPlay([8, 28, 40], 'fifty_k')?.kind).toBe('fifty_k_true')
    expect(detectCardPlay([9, 30, 43], 'fifty_k')?.kind).toBe('fifty_k_false')
  })

  it('uses rocket > true 510K > bomb > false 510K > normal', () => {
    const rocket = detectCardPlay([52, 53], 'fifty_k')!
    const true510K = detectCardPlay([8, 28, 40], 'fifty_k')!
    const bomb = detectCardPlay([0, 1, 2, 3], 'fifty_k')!
    const false510K = detectCardPlay([9, 30, 43], 'fifty_k')!
    const single = detectCardPlay([4], 'fifty_k')!

    expect(canBeatCardPlay(rocket, true510K, 'fifty_k')).toBe(true)
    expect(canBeatCardPlay(true510K, bomb, 'fifty_k')).toBe(true)
    expect(canBeatCardPlay(bomb, false510K, 'fifty_k')).toBe(true)
    expect(canBeatCardPlay(false510K, single, 'fifty_k')).toBe(true)
  })
})

describe('cardUtils - findAllPlayableHints', () => {
  // 卡牌ID辅助
  const c3 = 0
  const c4 = 4
  const c5 = 8
  const c6 = 12
  const c7 = 16
  const c8 = 20
  const c9 = 24
  const c10 = 28
  const cJ = 32
  const cQ = 36
  const cK = 40
  const cA = 44
  const c2 = 48
  const sJoker = 52
  const bJoker = 53

  it('自由出牌 - 应该提示各种单一牌型和组合牌型', () => {
    // 手牌：3, 3, 4, 5, 6, 7, 8 (可以出单张、对子、顺子)
    const hand = [c3, c3 + 1, c4, c5, c6, c7, c8]
    const hints = findAllPlayableHints(hand)

    // 应该包含单张 3, 4, 5, 6, 7, 8
    const single3 = hints.find(h => h.length === 1 && h[0] === c3)
    const single4 = hints.find(h => h.length === 1 && h[0] === c4)
    expect(single3).toBeDefined()
    expect(single4).toBeDefined()

    // 应该包含对子 3
    const pair3 = hints.find(h => h.length === 2 && h.includes(c3) && h.includes(c3 + 1))
    expect(pair3).toBeDefined()

    // 应该包含顺子 3-4-5-6-7 和 4-5-6-7-8
    const straight1 = hints.find(h => h.length === 5 && h.includes(c3) && h.includes(c7))
    const straight2 = hints.find(h => h.length === 5 && h.includes(c4) && h.includes(c8))
    expect(straight1).toBeDefined()
    expect(straight2).toBeDefined()
  })

  it('自由出牌 - 应该提供三带一和三带二提示且避免拆炸弹', () => {
    // 手牌：3, 3, 3, 4, 4, 4, 4, 5 (3个3，4个4是炸弹，1个5)
    // 带牌时，不能拆 4（炸弹），因此三带一只能带5
    const hand = [c3, c3 + 1, c3 + 2, c4, c4 + 1, c4 + 2, c4 + 3, c5]
    const hints = findAllPlayableHints(hand)

    // 应该有三张 3
    const triple3 = hints.find(h => h.length === 3 && h.includes(c3))
    expect(triple3).toBeDefined()

    // 应该有三带一 3带5，但绝不能是3带4
    const tripleOne = hints.filter(h => h.length === 4 && h.includes(c3))
    expect(tripleOne.length).toBeGreaterThan(0)
    // 每一个 3带一 都不应包含 4 的牌
    for (const hint of tripleOne) {
      const containsC4 = hint.some(c => c >= c4 && c < c4 + 4)
      expect(containsC4).toBe(false)
    }
  })

  it('跟牌模式 - 压过单牌', () => {
    const hand = [c3, c5, c8, c2]
    const lastPlay = [c4] // 上家出单张 4
    const hints = findAllPlayableHints(hand, lastPlay)

    // 应该提示 5, 8, 2
    expect(hints.length).toBe(3)
    expect(hints.some(h => h.length === 1 && h[0] === c5)).toBe(true)
    expect(hints.some(h => h.length === 1 && h[0] === c8)).toBe(true)
    expect(hints.some(h => h.length === 1 && h[0] === c2)).toBe(true)
  })

  it('跟牌模式 - 压过对子且带炸弹/火箭兜底', () => {
    // 手牌：对5，对10，炸弹Q，王炸
    const hand = [c5, c5 + 1, c10, c10 + 1, cQ, cQ + 1, cQ + 2, cQ + 3, sJoker, bJoker]
    const lastPlay = [c8, c8 + 1] // 上家出对 8
    const hints = findAllPlayableHints(hand, lastPlay)

    // 1. 同牌型压制：对10应该可以压
    expect(hints.some(h => h.length === 2 && h.includes(c10))).toBe(true)
    // 对5不能压对8，所以不应该有对5
    expect(hints.some(h => h.length === 2 && h.includes(c5))).toBe(false)

    // 2. 炸弹兜底：炸弹Q应该能压对8
    expect(hints.some(h => h.length === 4 && h.includes(cQ))).toBe(true)

    // 3. 火箭兜底：王炸能压对8
    expect(hints.some(h => h.length === 2 && h.includes(sJoker) && h.includes(bJoker))).toBe(true)
  })

  it('跟牌模式 - 压过顺子', () => {
    // 手牌：4, 5, 6, 7, 8, 9 (可以出顺子 4-5-6-7-8 或 5-6-7-8-9)
    const hand = [c4, c5, c6, c7, c8, c9]
    const lastPlay = [c3, c4, c5, c6, c7] // 上家出顺子 3-4-5-6-7
    const hints = findAllPlayableHints(hand, lastPlay)

    // 只能提示 4-5-6-7-8 和 5-6-7-8-9
    expect(hints.length).toBe(2)
    expect(hints.some(h => h.includes(c4) && h.includes(c8))).toBe(true)
    expect(hints.some(h => h.includes(c5) && h.includes(c9))).toBe(true)
  })
})
