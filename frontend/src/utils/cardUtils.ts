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
