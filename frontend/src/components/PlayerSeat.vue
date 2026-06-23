<!-- frontend/src/components/PlayerSeat.vue -->
<script setup lang="ts">
import PokerCard from './PokerCard.vue'

defineProps<{
  player: {
    id: string
    nickname: string
    isAi: boolean
    isOnline: boolean
    remaining?: number
    isLandlord?: boolean
  }
  position: 'left' | 'right' | 'bottom'
  isCurrentTurn: boolean
  lastPlayedCards?: number[]
  lastActionText?: string
}>()
</script>

<template>
  <div
    class="player-seat"
    :class="[position, { 'current-turn': isCurrentTurn, 'is-offline': !player.isOnline }]"
  >
    <!-- 头像信息卡片 -->
    <div class="avatar-block glass-panel">
      <!-- 地主农民身份皇冠 -->
      <span v-if="player.isLandlord" class="role-badge">👑 地主</span>
      <span v-else-if="player.isLandlord === false" class="role-badge farmer">👨‍🌾 农民</span>
      
      <div class="avatar-icon">
        {{ player.isAi ? '🤖' : '👤' }}
      </div>
      <div class="seat-name truncate">{{ player.nickname }}</div>
      
      <!-- 断线状态提示 -->
      <div v-if="!player.isOnline" class="offline-badge">断线</div>
    </div>

    <!-- 剩余手牌数量指示（仅左/右侧玩家显示） -->
    <div v-if="position !== 'bottom' && player.remaining !== undefined" class="cards-indicator">
      <div class="card-back-count">
        <PokerCard :card-id="0" :face-down="true" size="sm" />
        <span class="count-badge">{{ player.remaining }}</span>
      </div>
    </div>

    <!-- 动态动作展示区（过牌/叫分文字，或者打出的手牌） -->
    <div class="action-display-area" :class="position">
      <div v-if="lastActionText" class="bubble-action">
        {{ lastActionText }}
      </div>
      <div v-else-if="lastPlayedCards && lastPlayedCards.length > 0" class="played-cards-row">
        <PokerCard
          v-for="cId in lastPlayedCards"
          :key="cId"
          :card-id="cId"
          :no-hover="true"
          size="sm"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.player-seat {
  display: flex;
  align-items: center;
  gap: 15px;
  position: absolute;
  z-index: 10;
}

/* 屏幕中的定位 */
.player-seat.left {
  left: 40px;
  top: 35%;
  flex-direction: row;
}

.player-seat.right {
  right: 40px;
  top: 35%;
  flex-direction: row-reverse;
}

.player-seat.bottom {
  left: 40px;
  bottom: 30px;
  flex-direction: row;
}

/* 玻璃材质面板 */
.avatar-block {
  width: 90px;
  padding: 12px 6px;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 5px;
  position: relative;
  transition: all 0.25s ease;
}

.current-turn .avatar-block {
  border-color: #ffd700;
  box-shadow: 0 0 15px rgba(255, 215, 0, 0.45);
  transform: scale(1.06);
}

.avatar-icon {
  font-size: 2.2rem;
}

.seat-name {
  font-size: 0.8rem;
  max-width: 80px;
  font-weight: bold;
}

.is-offline {
  opacity: 0.55;
}

/* 身份标识（地主金橘色，农民绿色） */
.role-badge {
  position: absolute;
  top: -12px;
  background: #ff8f00;
  color: #ffffff;
  font-size: 0.7rem;
  font-weight: 800;
  padding: 2px 6px;
  border-radius: 10px;
  box-shadow: 0 2px 5px rgba(0,0,0,0.2);
}

.role-badge.farmer {
  background: #43a047;
}

.offline-badge {
  position: absolute;
  bottom: -10px;
  background: #e53935;
  color: white;
  font-size: 0.65rem;
  padding: 2px 6px;
  border-radius: 4px;
  font-weight: bold;
}

/* 剩余纸牌背面积累指示 */
.cards-indicator {
  display: flex;
  align-items: center;
}

.card-back-count {
  position: relative;
  display: flex;
  align-items: center;
}

.count-badge {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  background: rgba(0,0,0,0.8);
  color: #ffd700;
  font-size: 1.1rem;
  font-weight: 900;
  padding: 2px 8px;
  border-radius: 4px;
  border: 1.5px solid #ffd700;
  pointer-events: none;
}

/* 操作展示区（定位至牌桌中心方向） */
.action-display-area {
  position: absolute;
  display: flex;
  align-items: center;
  pointer-events: none;
}

.action-display-area.left {
  left: 170px;
  justify-content: flex-start;
}

.action-display-area.right {
  right: 170px;
  justify-content: flex-end;
}

.action-display-area.bottom {
  left: 120px;
  bottom: 60px;
  justify-content: flex-start;
}

.bubble-action {
  background: rgba(0, 0, 0, 0.75);
  border: 1px solid rgba(255, 255, 255, 0.25);
  color: #ffffff;
  padding: 8px 18px;
  border-radius: 18px;
  font-weight: bold;
  font-size: 0.95rem;
  white-space: nowrap;
}

.played-cards-row {
  display: flex;
  gap: 3px;
  background: rgba(0, 0, 0, 0.25);
  padding: 6px;
  border-radius: 6px;
}
</style>
