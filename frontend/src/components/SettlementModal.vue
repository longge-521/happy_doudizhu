<!-- frontend/src/components/SettlementModal.vue -->
<script setup lang="ts">
import { computed } from 'vue'
import { usePlayerStore } from '@/stores/playerStore'

const props = defineProps<{
  settlement: {
    winner: string
    winnerSide: 'landlord' | 'farmer'
    scores: Record<string, number>
    multiplier: number
  }
  players: Array<{ id: string; nickname: string; isLandlord?: boolean }>
}>()

defineEmits<{
  (e: 'close'): void
}>()

const playerStore = usePlayerStore()

// 当前玩家是否胜利
const isWin = computed(() => {
  const myScore = props.settlement.scores[playerStore.playerId] || 0
  return myScore > 0
})
</script>

<template>
  <div class="modal-overlay">
    <div class="glass-panel settlement-board">
      <!-- 胜负大图标题 -->
      <div class="result-header" :class="{ win: isWin, lose: !isWin }">
        <h2 class="result-title">{{ isWin ? '🎉 胜利 🎉' : '💀 失败 💀' }}</h2>
        <p class="result-multiplier">当前倍数：{{ settlement.multiplier }} 倍</p>
      </div>

      <!-- 三方分数榜 -->
      <div class="scores-table">
        <div class="table-header">
          <span>玩家</span>
          <span>身份</span>
          <span>输赢欢乐豆</span>
        </div>
        <div
          v-for="p in players"
          :key="p.id"
          class="table-row"
          :class="{ 'is-self': p.id === playerStore.playerId }"
        >
          <span class="truncate">{{ p.nickname }}</span>
          <span>{{ p.isLandlord ? '👑 地主' : '👨‍🌾 农民' }}</span>
          <span
            class="score-change"
            :class="{
              positive: (settlement.scores[p.id] || 0) > 0,
              negative: (settlement.scores[p.id] || 0) < 0
            }"
          >
            {{ (settlement.scores[p.id] || 0) >= 0 ? '+' : '' }}{{ settlement.scores[p.id] || 0 }}
          </span>
        </div>
      </div>

      <!-- 返回大厅按钮 -->
      <button class="btn-premium back-lobby-btn" @click="$emit('close')">
        返回大厅
      </button>
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
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 100;
  backdrop-filter: blur(5px);
}

.settlement-board {
  width: 90%;
  max-width: 420px;
  padding: 30px;
  text-align: center;
  box-sizing: border-box;
  animation: zoom-in 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275);
}

@keyframes zoom-in {
  from { transform: scale(0.8); opacity: 0; }
  to { transform: scale(1); opacity: 1; }
}

.result-header {
  margin-bottom: 25px;
}

.result-title {
  font-size: 2.5rem;
  font-weight: 900;
  margin: 0 0 5px 0;
  text-shadow: 0 0 10px rgba(255, 255, 255, 0.2);
}

.result-header.win .result-title {
  color: #ffd700;
  background: linear-gradient(135deg, #fff176 0%, #ffd700 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.result-header.lose .result-title {
  color: #ef5350;
  background: linear-gradient(135deg, #e57373 0%, #d32f2f 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.result-multiplier {
  font-size: 1rem;
  opacity: 0.8;
  margin: 0;
}

.scores-table {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 30px;
}

.table-header, .table-row {
  display: grid;
  grid-template-columns: 2fr 1fr 1.5fr;
  padding: 10px 15px;
  align-items: center;
  font-size: 0.95rem;
}

.table-header {
  font-weight: bold;
  opacity: 0.7;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.table-row {
  background: rgba(255, 255, 255, 0.04);
  border-radius: 8px;
}

.table-row.is-self {
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.2);
}

.score-change {
  font-weight: bold;
  text-align: right;
}

.score-change.positive {
  color: #81c784;
}

.score-change.negative {
  color: #e57373;
}

.back-lobby-btn {
  padding: 12px 35px;
  font-size: 1.1rem;
  width: 100%;
}
</style>
