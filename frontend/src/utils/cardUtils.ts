// frontend/src/utils/cardUtils.ts
const RANK_NAMES = ['3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A', '2']
const SUIT_SYMBOLS = ['♠', '♥', '♣', '♦']
const SUIT_NAMES = ['spade', 'heart', 'club', 'diamond']

export interface CardDisplay {
  id: number
  rank: string
  suit: string
  suitSymbol: string
  color: 'red' | 'black'
  power: number
}

export function getCardDisplay(cardId: number): CardDisplay {
  if (cardId === 52) return { id: 52, rank: '小', suit: 'joker', suitSymbol: '🃏', color: 'black', power: 13 }
  if (cardId === 53) return { id: 53, rank: '大', suit: 'joker', suitSymbol: '🃏', color: 'red', power: 14 }
  const rank = Math.floor(cardId / 4)
  const suit = cardId % 4
  return {
    id: cardId,
    rank: RANK_NAMES[rank] as string,
    suit: SUIT_NAMES[suit] as string,
    suitSymbol: SUIT_SYMBOLS[suit] as string,
    color: (suit === 1 || suit === 3) ? 'red' : 'black',
    power: rank,
  }
}

export function sortCardIds(cardIds: number[], descending: boolean = true): number[] {
  return [...cardIds].sort((a, b) => {
    const pa = getCardDisplay(a).power
    const pb = getCardDisplay(b).power
    if (pa === pb) {
      return descending ? b - a : a - b
    }
    return descending ? pb - pa : pa - pb
  })
}

export type CardPlayKind =
  | 'single'
  | 'pair'
  | 'triple'
  | 'triple_one'
  | 'triple_two'
  | 'straight'
  | 'double_straight'
  | 'airplane'
  | 'airplane_single'
  | 'airplane_pair'
  | 'bomb'
  | 'rocket'
  | 'four_two_single'
  | 'four_two_pair'

export interface CardPlayAnalysis {
  kind: CardPlayKind
  mainRank: number
  length: number
  cards: number[]
}

const PLAY_KIND_LABELS: Record<CardPlayKind, string> = {
  single: '单张',
  pair: '对子',
  triple: '三张',
  triple_one: '三带一',
  triple_two: '三带二',
  straight: '顺子',
  double_straight: '连对',
  airplane: '飞机',
  airplane_single: '飞机带单',
  airplane_pair: '飞机带对',
  bomb: '炸弹',
  rocket: '王炸',
  four_two_single: '四带二',
  four_two_pair: '四带两对',
}

function getCardRank(cardId: number): number {
  if (cardId === 52) return 13
  if (cardId === 53) return 14
  return Math.floor(cardId / 4)
}

function groupCardsByRank(cardIds: number[]): Map<number, number[]> {
  const groups = new Map<number, number[]>()
  for (const cardId of cardIds) {
    const rank = getCardRank(cardId)
    const cards = groups.get(rank) || []
    cards.push(cardId)
    groups.set(rank, cards)
  }
  for (const cards of groups.values()) {
    cards.sort((a, b) => a - b)
  }
  return groups
}

function getRankCounts(cardIds: number[]): Map<number, number> {
  const counts = new Map<number, number>()
  for (const cardId of cardIds) {
    const rank = getCardRank(cardId)
    counts.set(rank, (counts.get(rank) || 0) + 1)
  }
  return counts
}

function getRanksWithAtLeast(groups: Map<number, number[]>, count: number): number[] {
  return [...groups.entries()]
    .filter(([rank, cards]) => rank < 12 && cards.length >= count)
    .map(([rank]) => rank)
    .sort((a, b) => a - b)
}

function isConsecutive(ranks: number[]): boolean {
  if (ranks.length === 0 || ranks.some((rank) => rank >= 12)) return false
  for (let i = 1; i < ranks.length; i++) {
    if (ranks[i] !== ranks[i - 1]! + 1) return false
  }
  return true
}

function takeCards(groups: Map<number, number[]>, rank: number, count: number): number[] {
  return (groups.get(rank) || []).slice(0, count)
}

function findSequence(
  groups: Map<number, number[]>,
  countPerRank: number,
  length: number,
  minStartRank: number,
): number[] | null {
  const ranks = getRanksWithAtLeast(groups, countPerRank)
  for (let start = minStartRank + 1; start <= 12 - length; start++) {
    const wanted = Array.from({ length }, (_, index) => start + index)
    if (wanted.every((rank) => ranks.includes(rank))) {
      return wanted
    }
  }
  return null
}

function pickSingleSideCards(
  groups: Map<number, number[]>,
  excludedRanks: Set<number>,
  count: number,
): number[] | null {
  const picked: number[] = []
  const candidates: { rank: number; cards: number[] }[] = []
  for (const [rank, cards] of groups.entries()) {
    if (excludedRanks.has(rank)) continue
    if (cards.length === 4) continue // 避免拆炸弹
    if (cards.length > 0) {
      candidates.push({ rank, cards })
    }
  }

  // 优先按拥有张数升序，张数相同则按 rank 升序
  candidates.sort((a, b) => {
    if (a.cards.length !== b.cards.length) {
      return a.cards.length - b.cards.length
    }
    return a.rank - b.rank
  })

  for (const item of candidates) {
    for (const cardId of item.cards) {
      picked.push(cardId)
      if (picked.length === count) return picked
    }
  }
  return null
}

function pickPairSideCards(
  groups: Map<number, number[]>,
  excludedRanks: Set<number>,
  pairCount: number,
): number[] | null {
  const picked: number[] = []
  const candidates: { rank: number; cards: number[] }[] = []
  for (const [rank, cards] of groups.entries()) {
    if (excludedRanks.has(rank)) continue
    if (cards.length === 4) continue // 避免拆炸弹
    if (cards.length >= 2) {
      candidates.push({ rank, cards })
    }
  }

  // 优先按拥有张数升序（如2张优先于3张，因为3张可能是三条），张数相同按 rank 升序
  candidates.sort((a, b) => {
    if (a.cards.length !== b.cards.length) {
      return a.cards.length - b.cards.length
    }
    return a.rank - b.rank
  })

  for (const item of candidates) {
    picked.push(...item.cards.slice(0, 2))
    if (picked.length === pairCount * 2) return picked
  }
  return null
}

export function detectCardPlay(cardIds: number[]): CardPlayAnalysis | null {
  if (cardIds.length === 0) return null

  const cards = [...cardIds]
  const n = cards.length
  const counts = getRankCounts(cards)
  const groups = groupCardsByRank(cards)
  const countGroups = new Map<number, number[]>()

  for (const [rank, count] of counts.entries()) {
    const ranks = countGroups.get(count) || []
    ranks.push(rank)
    countGroups.set(count, ranks)
  }
  for (const ranks of countGroups.values()) {
    ranks.sort((a, b) => a - b)
  }

  if (n === 2 && cards.includes(52) && cards.includes(53)) {
    return { kind: 'rocket', mainRank: 14, length: 1, cards }
  }

  if (n === 1) {
    return { kind: 'single', mainRank: getCardRank(cards[0]!), length: 1, cards }
  }

  if (n === 2 && counts.size === 1) {
    return { kind: 'pair', mainRank: [...counts.keys()][0]!, length: 1, cards }
  }

  if (n === 4 && counts.size === 1) {
    return { kind: 'bomb', mainRank: [...counts.keys()][0]!, length: 1, cards }
  }

  if (n === 3 && counts.size === 1) {
    return { kind: 'triple', mainRank: [...counts.keys()][0]!, length: 1, cards }
  }

  if (n === 4 && countGroups.get(3)?.length === 1) {
    return { kind: 'triple_one', mainRank: countGroups.get(3)![0]!, length: 1, cards }
  }

  if (n === 5 && countGroups.get(3)?.length === 1 && countGroups.get(2)?.length === 1) {
    return { kind: 'triple_two', mainRank: countGroups.get(3)![0]!, length: 1, cards }
  }

  if (n >= 5 && [...counts.values()].every((count) => count === 1)) {
    const ranks = [...counts.keys()].sort((a, b) => a - b)
    if (isConsecutive(ranks)) {
      return { kind: 'straight', mainRank: ranks[0]!, length: n, cards }
    }
  }

  if (n >= 6 && n % 2 === 0 && [...counts.values()].every((count) => count === 2)) {
    const ranks = [...counts.keys()].sort((a, b) => a - b)
    if (isConsecutive(ranks)) {
      return { kind: 'double_straight', mainRank: ranks[0]!, length: n / 2, cards }
    }
  }

  const tripleRanks = [...counts.entries()]
    .filter(([rank, count]) => rank < 12 && count >= 3)
    .map(([rank]) => rank)
    .sort((a, b) => a - b)

  for (const [kind, divisor] of [
    ['airplane', 3],
    ['airplane_single', 4],
    ['airplane_pair', 5],
  ] as const) {
    if (n % divisor !== 0) continue
    const length = n / divisor
    if (length < 2) continue
    for (let i = 0; i <= tripleRanks.length - length; i++) {
      const seq = tripleRanks.slice(i, i + length)
      if (!isConsecutive(seq)) continue
      const seqSet = new Set(seq)
      const sideCards = cards.filter((cardId) => !seqSet.has(getCardRank(cardId)))
      if (kind === 'airplane' && sideCards.length === 0) {
        return { kind, mainRank: seq[0]!, length, cards }
      }
      if (kind === 'airplane_single' && sideCards.length === length) {
        return { kind, mainRank: seq[0]!, length, cards }
      }
      if (kind === 'airplane_pair' && sideCards.length === length * 2) {
        const sideCounts = getRankCounts(sideCards)
        if ([...sideCounts.values()].every((count) => count === 2)) {
          return { kind, mainRank: seq[0]!, length, cards }
        }
      }
    }
  }

  if (n === 6 && countGroups.get(4)?.length === 1) {
    return { kind: 'four_two_single', mainRank: countGroups.get(4)![0]!, length: 1, cards }
  }

  if (n === 8 && countGroups.get(4)?.length === 1) {
    const mainRank = countGroups.get(4)![0]!
    const sideRanks = [...counts.keys()].filter((rank) => rank !== mainRank)
    const sidePairCount = sideRanks.reduce((total, rank) => total + Math.floor((counts.get(rank) || 0) / 2), 0)
    if (sidePairCount === 2) {
      return { kind: 'four_two_pair', mainRank, length: 1, cards }
    }
  }

  return null
}

export function canBeatCardPlay(current: CardPlayAnalysis, last: CardPlayAnalysis): boolean {
  if (current.kind === 'rocket') return true
  if (last.kind === 'rocket') return false

  if (current.kind === 'bomb' && last.kind !== 'bomb') return true
  if (current.kind !== 'bomb' && last.kind === 'bomb') return false

  if (current.kind !== last.kind) return false
  if (current.length !== last.length) return false
  return current.mainRank > last.mainRank
}

function findOpeningPlay(hand: number[]): number[] {
  if (hand.length === 0) return []

  const sortedHand = sortCardIds(hand, false)
  const hasRocket = hand.includes(52) && hand.includes(53)
  const groups = groupCardsByRank(hand)
  const ranks = [...groups.keys()].sort((a, b) => a - b)

  const singleRanks: number[] = []
  const pairRanks: number[] = []
  const tripleRanks: number[] = []
  const bombRanks: number[] = []

  for (const rank of ranks) {
    // 如果有王炸，大小王不当成独立单张首发
    if (hasRocket && (rank === 13 || rank === 14)) {
      continue
    }
    const cards = groups.get(rank) || []
    if (cards.length === 1) {
      singleRanks.push(rank)
    } else if (cards.length === 2) {
      pairRanks.push(rank)
    } else if (cards.length === 3) {
      tripleRanks.push(rank)
    } else if (cards.length === 4) {
      bombRanks.push(rank)
    }
  }

  // 1. 优先出最小的独立单张
  if (singleRanks.length > 0) {
    const minRank = Math.min(...singleRanks)
    return groups.get(minRank) || []
  }

  // 2. 其次出最小的对子
  if (pairRanks.length > 0) {
    const minRank = Math.min(...pairRanks)
    return groups.get(minRank) || []
  }

  // 3. 再次出最小的三张
  if (tripleRanks.length > 0) {
    const minRank = Math.min(...tripleRanks)
    return groups.get(minRank) || []
  }

  // 4. 最后出最小的炸弹
  if (bombRanks.length > 0) {
    const minRank = Math.min(...bombRanks)
    return groups.get(minRank) || []
  }

  // 5. 实在不行出王炸
  if (hasRocket) {
    return [52, 53]
  }

  return [sortedHand[0]!]
}

function findBombOrRocket(hand: number[], lastPlay: CardPlayAnalysis): number[] {
  const groups = groupCardsByRank(hand)
  const bombs = [...groups.entries()]
    .filter(([, cards]) => cards.length === 4)
    .map(([rank, cards]) => ({ rank, cards }))
    .sort((a, b) => a.rank - b.rank)

  for (const bomb of bombs) {
    if (lastPlay.kind !== 'bomb' || bomb.rank > lastPlay.mainRank) {
      return bomb.cards.slice(0, 4)
    }
  }

  if (hand.includes(52) && hand.includes(53) && lastPlay.kind !== 'rocket') {
    return [52, 53]
  }

  return []
}

function findSameKindPlay(hand: number[], lastPlay: CardPlayAnalysis): number[] {
  const groups = groupCardsByRank(hand)
  const ranks = [...groups.keys()].sort((a, b) => a - b)

  for (const rank of ranks) {
    if (rank <= lastPlay.mainRank) continue
    const cards = groups.get(rank) || []
    if (lastPlay.kind === 'single' && cards.length >= 1) return cards.slice(0, 1)
    if (lastPlay.kind === 'pair' && cards.length >= 2) return cards.slice(0, 2)
    if (lastPlay.kind === 'triple' && cards.length >= 3) return cards.slice(0, 3)
    if (lastPlay.kind === 'triple_one' && cards.length >= 3) {
      const side = pickSingleSideCards(groups, new Set([rank]), 1)
      if (side) return [...cards.slice(0, 3), ...side]
    }
    if (lastPlay.kind === 'triple_two' && cards.length >= 3) {
      const side = pickPairSideCards(groups, new Set([rank]), 1)
      if (side) return [...cards.slice(0, 3), ...side]
    }
    if (lastPlay.kind === 'four_two_single' && cards.length >= 4) {
      const side = pickSingleSideCards(groups, new Set([rank]), 2)
      if (side) return [...cards.slice(0, 4), ...side]
    }
    if (lastPlay.kind === 'four_two_pair' && cards.length >= 4) {
      const side = pickPairSideCards(groups, new Set([rank]), 2)
      if (side) return [...cards.slice(0, 4), ...side]
    }
  }

  if (lastPlay.kind === 'straight' || lastPlay.kind === 'double_straight') {
    const countPerRank = lastPlay.kind === 'straight' ? 1 : 2
    const seq = findSequence(groups, countPerRank, lastPlay.length, lastPlay.mainRank)
    if (seq) return seq.flatMap((rank) => takeCards(groups, rank, countPerRank))
  }

  if (
    lastPlay.kind === 'airplane' ||
    lastPlay.kind === 'airplane_single' ||
    lastPlay.kind === 'airplane_pair'
  ) {
    const seq = findSequence(groups, 3, lastPlay.length, lastPlay.mainRank)
    if (!seq) return []
    const mainCards = seq.flatMap((rank) => takeCards(groups, rank, 3))
    const excluded = new Set(seq)

    if (lastPlay.kind === 'airplane') return mainCards
    if (lastPlay.kind === 'airplane_single') {
      const side = pickSingleSideCards(groups, excluded, lastPlay.length)
      return side ? [...mainCards, ...side] : []
    }
    const side = pickPairSideCards(groups, excluded, lastPlay.length)
    return side ? [...mainCards, ...side] : []
  }

  if (lastPlay.kind === 'bomb') {
    return findBombOrRocket(hand, lastPlay)
  }

  return []
}

export function findSuggestedPlay(hand: number[], lastCards: number[] = []): number[] {
  const lastPlay = detectCardPlay(lastCards)
  if (!lastPlay) return sortCardIds(findOpeningPlay(hand))

  const sameKind = findSameKindPlay(hand, lastPlay)
  if (sameKind.length > 0) return sortCardIds(sameKind)

  if (lastPlay.kind !== 'rocket') {
    return sortCardIds(findBombOrRocket(hand, lastPlay))
  }

  return []
}

export function findAllPlayableHints(hand: number[], lastCards: number[] = []): number[][] {
  const groups = groupCardsByRank(hand)
  const ranks = [...groups.keys()].sort((a, b) => a - b)
  const hints: number[][] = []

  const lastPlay = detectCardPlay(lastCards)

  if (!lastPlay) {
    // 自由出牌模式
    const hasRocket = hand.includes(52) && hand.includes(53)

    // 1. 单张（如果有王炸，大小王不作独立单张首发）
    for (const rank of ranks) {
      if (hasRocket && (rank === 13 || rank === 14)) continue
      hints.push(groups.get(rank)!.slice(0, 1))
    }

    // 2. 对子
    for (const rank of ranks) {
      if (groups.get(rank)!.length >= 2) {
        hints.push(groups.get(rank)!.slice(0, 2))
      }
    }

    // 3. 顺子（长度从 5 到 12，且 rank < 12 也就是最大到 A）
    const straightRanks = getRanksWithAtLeast(groups, 1)
    for (let len = 5; len <= 12; len++) {
      for (let start = 0; start <= 12 - len; start++) {
        const wanted = Array.from({ length: len }, (_, i) => start + i)
        if (wanted.every(r => straightRanks.includes(r))) {
          hints.push(wanted.flatMap(r => groups.get(r)!.slice(0, 1)))
        }
      }
    }

    // 4. 连对（长度从 3 到 10 对，且 rank < 12 也就是最大到 A）
    const doubleStraightRanks = getRanksWithAtLeast(groups, 2)
    for (let len = 3; len <= 10; len++) {
      for (let start = 0; start <= 12 - len; start++) {
        const wanted = Array.from({ length: len }, (_, i) => start + i)
        if (wanted.every(r => doubleStraightRanks.includes(r))) {
          hints.push(wanted.flatMap(r => groups.get(r)!.slice(0, 2)))
        }
      }
    }

    // 5. 三条
    for (const rank of ranks) {
      if (groups.get(rank)!.length >= 3) {
        hints.push(groups.get(rank)!.slice(0, 3))
      }
    }

    // 6. 三带一
    for (const rank of ranks) {
      if (groups.get(rank)!.length >= 3) {
        const side = pickSingleSideCards(groups, new Set([rank]), 1)
        if (side) {
          hints.push([...groups.get(rank)!.slice(0, 3), ...side])
        }
      }
    }

    // 7. 三带二
    for (const rank of ranks) {
      if (groups.get(rank)!.length >= 3) {
        const side = pickPairSideCards(groups, new Set([rank]), 1)
        if (side) {
          hints.push([...groups.get(rank)!.slice(0, 3), ...side])
        }
      }
    }

    // 8. 飞机不带（长度从 2 开始，且 rank < 12 也就是最大到 A）
    const airplaneRanks = getRanksWithAtLeast(groups, 3)
    for (let len = 2; len <= 6; len++) {
      for (let start = 0; start <= 12 - len; start++) {
        const wanted = Array.from({ length: len }, (_, i) => start + i)
        if (wanted.every(r => airplaneRanks.includes(r))) {
          hints.push(wanted.flatMap(r => groups.get(r)!.slice(0, 3)))
        }
      }
    }

    // 9. 飞机带单
    for (let len = 2; len <= 5; len++) {
      for (let start = 0; start <= 12 - len; start++) {
        const wanted = Array.from({ length: len }, (_, i) => start + i)
        if (wanted.every(r => airplaneRanks.includes(r))) {
          const mainCards = wanted.flatMap(r => groups.get(r)!.slice(0, 3))
          const side = pickSingleSideCards(groups, new Set(wanted), len)
          if (side) {
            hints.push([...mainCards, ...side])
          }
        }
      }
    }

    // 10. 飞机带双
    for (let len = 2; len <= 4; len++) {
      for (let start = 0; start <= 12 - len; start++) {
        const wanted = Array.from({ length: len }, (_, i) => start + i)
        if (wanted.every(r => airplaneRanks.includes(r))) {
          const mainCards = wanted.flatMap(r => groups.get(r)!.slice(0, 3))
          const side = pickPairSideCards(groups, new Set(wanted), len)
          if (side) {
            hints.push([...mainCards, ...side])
          }
        }
      }
    }

    // 11. 炸弹
    for (const rank of ranks) {
      if (groups.get(rank)!.length === 4) {
        hints.push(groups.get(rank)!.slice(0, 4))
      }
    }

    // 12. 王炸
    if (hasRocket) {
      hints.push([52, 53])
    }

  } else {
    // 跟牌模式
    const lastMainRank = lastPlay.mainRank

    switch (lastPlay.kind) {
      case 'single':
        for (const rank of ranks) {
          if (rank > lastMainRank) {
            hints.push(groups.get(rank)!.slice(0, 1))
          }
        }
        break

      case 'pair':
        for (const rank of ranks) {
          if (rank > lastMainRank && groups.get(rank)!.length >= 2) {
            hints.push(groups.get(rank)!.slice(0, 2))
          }
        }
        break

      case 'triple':
        for (const rank of ranks) {
          if (rank > lastMainRank && groups.get(rank)!.length >= 3) {
            hints.push(groups.get(rank)!.slice(0, 3))
          }
        }
        break

      case 'triple_one':
        for (const rank of ranks) {
          if (rank > lastMainRank && groups.get(rank)!.length >= 3) {
            const side = pickSingleSideCards(groups, new Set([rank]), 1)
            if (side) {
              hints.push([...groups.get(rank)!.slice(0, 3), ...side])
            }
          }
        }
        break

      case 'triple_two':
        for (const rank of ranks) {
          if (rank > lastMainRank && groups.get(rank)!.length >= 3) {
            const side = pickPairSideCards(groups, new Set([rank]), 1)
            if (side) {
              hints.push([...groups.get(rank)!.slice(0, 3), ...side])
            }
          }
        }
        break

      case 'straight': {
        const straightRanks = getRanksWithAtLeast(groups, 1)
        const len = lastPlay.length
        for (let start = lastMainRank + 1; start <= 12 - len; start++) {
          const wanted = Array.from({ length: len }, (_, i) => start + i)
          if (wanted.every(r => straightRanks.includes(r))) {
            hints.push(wanted.flatMap(r => groups.get(r)!.slice(0, 1)))
          }
        }
        break
      }

      case 'double_straight': {
        const doubleStraightRanks = getRanksWithAtLeast(groups, 2)
        const len = lastPlay.length
        for (let start = lastMainRank + 1; start <= 12 - len; start++) {
          const wanted = Array.from({ length: len }, (_, i) => start + i)
          if (wanted.every(r => doubleStraightRanks.includes(r))) {
            hints.push(wanted.flatMap(r => groups.get(r)!.slice(0, 2)))
          }
        }
        break
      }

      case 'airplane': {
        const airplaneRanks = getRanksWithAtLeast(groups, 3)
        const len = lastPlay.length
        for (let start = lastMainRank + 1; start <= 12 - len; start++) {
          const wanted = Array.from({ length: len }, (_, i) => start + i)
          if (wanted.every(r => airplaneRanks.includes(r))) {
            hints.push(wanted.flatMap(r => groups.get(r)!.slice(0, 3)))
          }
        }
        break
      }

      case 'airplane_single': {
        const airplaneRanks = getRanksWithAtLeast(groups, 3)
        const len = lastPlay.length
        for (let start = lastMainRank + 1; start <= 12 - len; start++) {
          const wanted = Array.from({ length: len }, (_, i) => start + i)
          if (wanted.every(r => airplaneRanks.includes(r))) {
            const mainCards = wanted.flatMap(r => groups.get(r)!.slice(0, 3))
            const side = pickSingleSideCards(groups, new Set(wanted), len)
            if (side) {
              hints.push([...mainCards, ...side])
            }
          }
        }
        break
      }

      case 'airplane_pair': {
        const airplaneRanks = getRanksWithAtLeast(groups, 3)
        const len = lastPlay.length
        for (let start = lastMainRank + 1; start <= 12 - len; start++) {
          const wanted = Array.from({ length: len }, (_, i) => start + i)
          if (wanted.every(r => airplaneRanks.includes(r))) {
            const mainCards = wanted.flatMap(r => groups.get(r)!.slice(0, 3))
            const side = pickPairSideCards(groups, new Set(wanted), len)
            if (side) {
              hints.push([...mainCards, ...side])
            }
          }
        }
        break
      }

      case 'four_two_single':
        for (const rank of ranks) {
          if (rank > lastMainRank && groups.get(rank)!.length === 4) {
            const side = pickSingleSideCards(groups, new Set([rank]), 2)
            if (side) {
              hints.push([...groups.get(rank)!.slice(0, 4), ...side])
            }
          }
        }
        break

      case 'four_two_pair':
        for (const rank of ranks) {
          if (rank > lastMainRank && groups.get(rank)!.length === 4) {
            const side = pickPairSideCards(groups, new Set([rank]), 2)
            if (side) {
              hints.push([...groups.get(rank)!.slice(0, 4), ...side])
            }
          }
        }
        break

      case 'bomb':
        for (const rank of ranks) {
          if (rank > lastMainRank && groups.get(rank)!.length === 4) {
            hints.push(groups.get(rank)!.slice(0, 4))
          }
        }
        break
    }

    // 炸弹和王炸跟牌兜底
    if (lastPlay.kind !== 'rocket') {
      for (const rank of ranks) {
        const isLargerBomb = lastPlay.kind === 'bomb' ? rank > lastMainRank : true
        if (groups.get(rank)!.length === 4 && isLargerBomb) {
          const bombCards = groups.get(rank)!.slice(0, 4)
          // 避免与同牌型中的炸弹重复添加
          if (!hints.some(h => h.length === 4 && getCardRank(h[0]) === rank)) {
            hints.push(bombCards)
          }
        }
      }
      if (hand.includes(52) && hand.includes(53)) {
        hints.push([52, 53])
      }
    }
  }

  // 排序每个提示结果
  return hints.map(h => sortCardIds(h))
}

export function getPlayKindLabel(kind: CardPlayKind): string {
  return PLAY_KIND_LABELS[kind]
}

export function formatCardIds(cardIds: number[]): string {
  return sortCardIds(cardIds)
    .map((cardId) => {
      const card = getCardDisplay(cardId)
      return card.suit === 'joker' ? `${card.rank}王` : `${card.rank}${card.suitSymbol}`
    })
    .join(' ')
}

export function sortPlayedCards(cardIds: number[]): number[] {
  if (cardIds.length === 0) return []
  
  const play = detectCardPlay(cardIds)
  if (!play) {
    // 兜底：直接从小到大升序排序
    return sortCardIds(cardIds, false)
  }
  
  // 依靠牌型进行分选排序
  const counts = getRankCounts(cardIds)
  
  // 主牌张数判定
  let mainCount = 0
  if (
    play.kind === 'triple_one' || 
    play.kind === 'triple_two' || 
    play.kind === 'airplane_single' || 
    play.kind === 'airplane_pair' || 
    play.kind === 'triple' || 
    play.kind === 'airplane'
  ) {
    mainCount = 3
  } else if (play.kind === 'four_two_single' || play.kind === 'four_two_pair') {
    mainCount = 4
  }
  
  if (mainCount > 0) {
    const mainCards: number[] = []
    const sideCards: number[] = []
    const groups = groupCardsByRank(cardIds)
    
    for (const cardId of cardIds) {
      const rank = getCardRank(cardId)
      const cards = groups.get(rank) || []
      if (cards.length >= mainCount) {
        mainCards.push(cardId)
      } else {
        sideCards.push(cardId)
      }
    }
    
    // 主牌部分从小到大排序
    const sortedMain = sortCardIds(mainCards, false)
    // 副牌/带牌部分从小到大排序
    const sortedSide = sortCardIds(sideCards, false)
    
    return [...sortedMain, ...sortedSide]
  }
  
  // 对于单张、对子、顺子、连对、炸弹等单一牌型，一律直接从小到大排序
  return sortCardIds(cardIds, false)
}
