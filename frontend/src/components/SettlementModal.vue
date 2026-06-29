<!-- frontend/src/components/SettlementModal.vue -->
<script setup lang="ts">
import { ref, computed } from 'vue'
import { usePlayerStore } from '@/stores/playerStore'
import { getCardDisplay, sortCardIds, sortPlayedCards } from '@/utils/cardUtils'

const props = defineProps<{
  settlement: {
    winner: string
    winnerSide: 'landlord' | 'farmer'
    scores: Record<string, number>
    multiplier: number
    allHands?: Record<string, number[]>
  }
  players: Array<{ id: string; nickname: string; isLandlord?: boolean }>
  lastPlayedCards?: Record<string, number[]>
}>()

const emit = defineEmits<{
  (e: 'close'): void
}>()

const playerStore = usePlayerStore()

// 获取玩家的剩余牌（按牌力降序排列）
function getRemainingCards(playerId: string) {
  const hands = props.settlement.allHands?.[playerId] || []
  return sortCardIds(hands, true)
}

function getCardText(cardId: number) {
  const display = getCardDisplay(cardId)
  if (cardId === 52) return '小王'
  if (cardId === 53) return '大王'
  return display.suitSymbol + display.rank
}

function getCardColor(cardId: number) {
  const display = getCardDisplay(cardId)
  return display.color // 'red' | 'black'
}

// 当前玩家是否胜利
const isWin = computed(() => {
  const myScore = props.settlement.scores[playerStore.playerId] || 0
  return myScore > 0
})

// 计算自己赢了多少欢乐豆
const myBeansChange = computed(() => {
  return props.settlement.scores[playerStore.playerId] || 0
})

// 计算底分（可以用结算分数除以倍数算出来，或者从 room 的 baseScore 中取，但因为这里 scores = self.multiplier * self.base_score, 所以可以直接 scores / multiplier 取绝对值）
const computedBaseScore = computed(() => {
  // 找出任意一个非地主（农民）的玩家算底分以防除以2倍的地主分
  const farmer = props.players.find(p => !p.isLandlord)
  if (farmer) {
    const score = Math.abs(props.settlement.scores[farmer.id] || 0)
    return props.settlement.multiplier > 0 ? Math.ceil(score / props.settlement.multiplier) : 10
  }
  return 10
})

// 连胜与积分数值模拟
const streakCount = computed(() => {
  return isWin.value ? 2 : 0
})

// 头衔积分变动
const titleScoreChange = computed(() => {
  return isWin.value ? 11 : -8
})

function getRankMaxStars(rid: number): number {
  if (rid < 10) return 3
  if (rid < 22) return 4
  return 5
}

const starChangeDesc = computed(() => {
  if (isWin.value) {
    const isBomb = props.settlement.multiplier >= 4
    return isBomb ? '爆发胜利 +2 ★' : '胜利 +1 ★'
  } else {
    const rid = playerStore.rankId
    const srank = playerStore.subRank
    const starCount = playerStore.stars
    
    if (rid < 10) {
      return '新手保护，不扣星'
    }
    if (srank === 4 && starCount === 0) {
      if (rid < 22) {
        return '大段保护，不扣星'
      } else {
        return '降级跌出大段 -1 ★'
      }
    }
    return '失败扣星 -1 ★'
  }
})
</script>

<template>
  <div class="modal-overlay">
    <div class="glass-panel settlement-board">
      <!-- 连胜 / 失败 横幅 -->
      <div class="streak-banner" :class="{ win: isWin, lose: !isWin }">
        <h1 class="streak-title">
          <span v-if="isWin">🎉 {{ streakCount > 0 ? streakCount + '连胜' : '胜利' }} 🎉</span>
          <span v-else>💀 败北 💀</span>
        </h1>
      </div>

      <!-- 段位头衔成长框 -->
      <div class="level-growth-card">
        <div class="user-avatar-circle">👤</div>
        <div class="growth-detail">
          <div class="growth-rank-row">
            <span class="rank-name-badge" style="background: linear-gradient(135deg, #ffd700 0%, #ff8f00 100%); color: #3e2723;">{{ playerStore.rankTitle }}</span>
            <span class="rank-new-tag" v-if="isWin">RANK UP!</span>
            <div class="stars-gold">
              <template v-if="playerStore.rankId < 36">
                <span 
                  v-for="idx in getRankMaxStars(playerStore.rankId)" 
                  :key="idx" 
                  class="star-g" 
                  :class="{ 'opacity-3': idx > playerStore.stars }"
                >
                  ★
                </span>
              </template>
              <template v-else>
                <span class="star-g">★</span>
                <span style="color: #ffd700; font-size: 0.85rem; font-weight: bold; margin-left: 4px;">至尊: {{ playerStore.stars }}★</span>
              </template>
            </div>
          </div>
          <div class="progress-bar-row">
            <div class="progress-label" v-if="playerStore.rankId < 36">
              段位星级: {{ playerStore.stars }} / {{ getRankMaxStars(playerStore.rankId) }}
            </div>
            <div class="progress-label" v-else>
              至尊巅峰
            </div>
            <div class="progress-track">
              <div class="progress-fill" :style="{ width: playerStore.rankId < 36 ? (playerStore.stars / getRankMaxStars(playerStore.rankId) * 100) + '%' : '100%' }"></div>
            </div>
            <span class="score-added-glow" :class="{ win: isWin }" style="white-space: nowrap;">
              {{ starChangeDesc }}
            </span>
          </div>
        </div>
      </div>

      <!-- 三方详细结算列表 -->
      <div class="settlement-detail-table">
        <div class="detail-th">
          <span>昵称</span>
          <span>底分</span>
          <span>倍数</span>
          <span>欢乐豆</span>
        </div>

        <div
          v-for="p in players"
          :key="p.id"
          class="detail-tr-wrapper"
        >
          <div
            class="detail-tr"
            :class="{ 'is-self-row': p.id === playerStore.playerId }"
          >
            <!-- 名字与地主图标 -->
            <div class="name-cell">
              <span v-if="p.isLandlord" class="role-hat">👑</span>
              <span v-else class="role-hat">👨‍🌾</span>
              <span class="player-name truncate">{{ p.nickname }}</span>
            </div>

            <!-- 底分 -->
            <div class="center-cell">{{ computedBaseScore }}</div>

            <!-- 倍数 (地主显示2倍倍数，农民显示基础倍数) -->
            <div class="center-cell">
              {{ p.isLandlord ? settlement.multiplier * 2 : settlement.multiplier }}
            </div>

            <!-- 输赢数值 -->
            <div class="score-cell">
              <span
                class="beans-change-text"
                :class="{
                  positive: (settlement.scores[p.id] || 0) > 0,
                  negative: (settlement.scores[p.id] || 0) < 0
                }"
              >
                {{ (settlement.scores[p.id] || 0) >= 0 ? '+' : '' }}{{ settlement.scores[p.id] || 0 }}
              </span>
              <!-- 非自己可以显示加好友按钮 -->
              <button v-if="p.id !== playerStore.playerId" class="btn-add-friend" title="加好友">+</button>
            </div>
          </div>

          <!-- 显示玩家剩余手牌 -->
          <div v-if="getRemainingCards(p.id).length > 0" class="remaining-cards-box">
            <span class="remaining-title">余牌:</span>
            <div class="remaining-cards-list">
              <span
                v-for="cardId in getRemainingCards(p.id)"
                :key="cardId"
                class="mini-card-badge"
                :class="getCardColor(cardId)"
              >
                {{ getCardText(cardId) }}
              </span>
            </div>
          </div>
          <!-- 如果是赢家且打完了，展示他的最后一手绝杀牌 -->
          <div v-else-if="(props.lastPlayedCards?.[p.id]?.length ?? 0) > 0" class="remaining-cards-box">
            <span class="remaining-title" style="color: #ffd54f;">绝杀:</span>
            <div class="remaining-cards-list">
              <span
                v-for="cardId in sortPlayedCards(props.lastPlayedCards?.[p.id] || [])"
                :key="cardId"
                class="mini-card-badge"
                :class="getCardColor(cardId)"
                style="border-color: #ffd54f;"
              >
                {{ getCardText(cardId) }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- 底部控制按钮 -->
      <div class="settlement-footer-buttons">
        <button class="btn-play-hot" @click="emit('close')">
          玩热门玩法
        </button>
        <button class="btn-play-continue" @click="emit('close')">
          继续游戏
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.75);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 100;
  backdrop-filter: blur(8px);
}

.settlement-board {
  width: 95%;
  max-width: 480px;
  background: radial-gradient(circle at center, #1b305a 0%, #0c152b 100%);
  border: 2px solid #ffd700;
  border-radius: 20px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.6);
  padding: 0;
  overflow: hidden;
  animation: zoom-in 0.28s cubic-bezier(0.175, 0.885, 0.32, 1.275);
}

@keyframes zoom-in {
  from { transform: scale(0.8); opacity: 0; }
  to { transform: scale(1); opacity: 1; }
}

/* 连胜横幅 */
.streak-banner {
  padding: 18px 0;
  text-align: center;
  box-shadow: 0 3px 10px rgba(0,0,0,0.4);
}

.streak-banner.win {
  background: linear-gradient(to right, #ffca28, #ff8f00, #ffca28);
}

.streak-banner.lose {
  background: linear-gradient(to right, #78909c, #37474f, #78909c);
}

.streak-title {
  margin: 0;
  font-size: 2.1rem;
  font-weight: 900;
  color: #fff;
  letter-spacing: 2px;
  text-shadow: 0 2px 5px rgba(0, 0, 0, 0.4);
}

/* 段位成长卡 */
.level-growth-card {
  display: flex;
  align-items: center;
  background: rgba(255, 255, 255, 0.08);
  border-bottom: 1.5px solid rgba(255,255,255,0.1);
  padding: 16px 20px;
  gap: 16px;
}

.user-avatar-circle {
  width: 50px;
  height: 50px;
  border-radius: 50%;
  background: rgba(255,255,255,0.15);
  border: 2px solid #fff;
  display: flex;
  justify-content: center;
  align-items: center;
  font-size: 1.8rem;
}

.growth-detail {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.growth-rank-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.rank-name-badge {
  background: linear-gradient(to right, #e040fb, #7b1fa2);
  color: #fff;
  font-size: 0.75rem;
  font-weight: 900;
  padding: 2px 8px;
  border-radius: 6px;
}

.rank-new-tag {
  color: #ffd700;
  font-size: 0.65rem;
  font-weight: 900;
  font-style: italic;
  animation: bounce 0.4s infinite alternate;
}

@keyframes bounce {
  from { transform: translateY(0); }
  to { transform: translateY(-3px); }
}

.stars-gold {
  margin-left: auto;
  display: flex;
  gap: 2px;
  font-size: 0.85rem;
}

.star-g {
  color: #ffd700;
}

.opacity-3 {
  opacity: 0.3;
}

.progress-bar-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.progress-label {
  font-size: 0.75rem;
  opacity: 0.7;
}

.progress-track {
  flex: 1;
  height: 8px;
  background: rgba(0, 0, 0, 0.4);
  border-radius: 4px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(to right, #ffd54f, #ff8f00);
  border-radius: 4px;
}

.score-added-glow {
  font-weight: 900;
  font-size: 0.85rem;
}

.score-added-glow.win {
  color: #4caf50;
  text-shadow: 0 0 5px rgba(76, 175, 80, 0.5);
}

.score-added-glow:not(.win) {
  color: #f44336;
}

/* 结算列表 */
.settlement-detail-table {
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.detail-th, .detail-tr {
  display: grid;
  grid-template-columns: 2fr 1fr 1fr 1.8fr;
  padding: 8px 10px;
  align-items: center;
  font-size: 0.9rem;
}

.detail-th {
  font-weight: bold;
  opacity: 0.6;
  border-bottom: 1.5px solid rgba(255,255,255,0.15);
  padding-bottom: 6px;
}

.detail-tr-wrapper {
  display: flex;
  flex-direction: column;
  background: rgba(255, 255, 255, 0.03);
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.05);
  overflow: hidden;
}

.detail-tr {
  background: none;
  border: none;
}

.detail-tr.is-self-row {
  background: rgba(255, 202, 40, 0.12);
}

.name-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.role-hat {
  font-size: 1.15rem;
}

.player-name {
  font-weight: 800;
  color: #fff;
  max-width: 100px;
}

.center-cell {
  text-align: center;
  font-weight: 700;
}

.score-cell {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
}

.beans-change-text {
  font-weight: 900;
  font-size: 1.05rem;
}

.beans-change-text.positive {
  color: #ffd700;
  text-shadow: 0 1px 3px rgba(0,0,0,0.5);
}

.beans-change-text.negative {
  color: #90caf9;
}

.btn-add-friend {
  background: rgba(255,255,255,0.15);
  border: 1px solid rgba(255,255,255,0.25);
  color: #fff;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  display: flex;
  justify-content: center;
  align-items: center;
  font-weight: 900;
  cursor: pointer;
}

.btn-add-friend:hover {
  background: rgba(255,255,255,0.3);
}

/* 底部操作 */
.settlement-footer-buttons {
  display: flex;
  padding: 16px 20px 24px 20px;
  gap: 16px;
}

.btn-play-hot {
  flex: 1;
  background: linear-gradient(135deg, #039be5 0%, #01579b 100%);
  border: 1.5px solid #4fc3f7;
  color: #fff;
  font-weight: 900;
  padding: 12px;
  border-radius: 24px;
  font-size: 1.05rem;
  cursor: pointer;
  box-shadow: 0 4px 10px rgba(1, 87, 155, 0.4);
}

.btn-play-continue {
  flex: 1.3;
  background: linear-gradient(135deg, #ffca28 0%, #e65100 100%);
  border: 1.5px solid #ffe082;
  color: #fff;
  font-weight: 900;
  padding: 12px;
  border-radius: 24px;
  font-size: 1.15rem;
  cursor: pointer;
  box-shadow: 0 4px 12px rgba(230, 81, 0, 0.4);
}

.btn-play-hot:hover, .btn-play-continue:hover {
  transform: scale(1.02);
}

.truncate {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 余牌显示样式 */
.remaining-cards-box {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 14px 10px 14px;
  border-top: 1px dashed rgba(255, 255, 255, 0.08);
}

.remaining-title {
  font-size: 0.75rem;
  color: rgba(255, 255, 255, 0.45);
  font-weight: bold;
}

.remaining-cards-list {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.mini-card-badge {
  font-size: 0.75rem;
  font-weight: 800;
  padding: 1px 6px;
  border-radius: 4px;
  background: #ffffff;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.25);
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.mini-card-badge.red {
  color: #ff3b30;
  border: 1px solid rgba(255, 59, 48, 0.2);
}

.mini-card-badge.black {
  color: #1c1c1e;
  border: 1px solid rgba(28, 28, 30, 0.15);
}

</style>
