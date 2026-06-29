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
    doubling?: string
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
      <!-- 地主农民身份标签 -->
      <span v-if="player.isLandlord" class="role-badge landlord">👑 地主</span>
      <span v-else-if="player.isLandlord === false" class="role-badge farmer">👨‍🌾 农民</span>
      
      <div class="avatar-icon-circle" :class="{ 'is-landlord': player.isLandlord }">
        <span class="emoji-avatar">{{ player.isAi ? '🤖' : '👤' }}</span>
      </div>
      
      <div class="seat-name truncate">{{ player.nickname }}</div>
      
      <!-- 加倍状态标识 -->
      <div v-if="player.doubling" class="doubling-badge" :class="{ 'super': player.doubling.includes('超级') }">
        ⚡ {{ player.doubling }}
      </div>
      
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

    <!-- 动态动作展示区 -->
    <div class="action-display-area" :class="position">
      <div v-if="lastActionText" class="bubble-action" :class="{ pass: lastActionText === '不出' }">
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

/* 头像面板 */
.avatar-block {
  width: 96px;
  padding: 14px 6px;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  position: relative;
  transition: all 0.25s ease;
  background: rgba(0, 0, 0, 0.45);
  border: 1.5px solid rgba(255, 255, 255, 0.2);
}

.current-turn .avatar-block {
  border-color: #ffd700;
  box-shadow: 0 0 18px rgba(255, 215, 0, 0.6);
  transform: scale(1.08);
}

/* 圆形头像 */
.avatar-icon-circle {
  width: 50px;
  height: 50px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.15);
  border: 2px solid rgba(255, 255, 255, 0.4);
  display: flex;
  justify-content: center;
  align-items: center;
  box-shadow: 0 3px 6px rgba(0,0,0,0.3);
}

.avatar-icon-circle.is-landlord {
  border-color: #ffb300;
  background: rgba(255, 179, 0, 0.15);
  box-shadow: 0 0 8px rgba(255, 179, 0, 0.5);
}

.emoji-avatar {
  font-size: 1.8rem;
}

.seat-name {
  font-size: 0.85rem;
  max-width: 85px;
  font-weight: 800;
  color: #fff;
  text-shadow: 0 1px 2px rgba(0,0,0,0.8);
}

.is-offline {
  opacity: 0.55;
}

/* 角色标签 */
.role-badge {
  position: absolute;
  top: -12px;
  color: #ffffff;
  font-size: 0.7rem;
  font-weight: 900;
  padding: 2px 8px;
  border-radius: 10px;
  box-shadow: 0 2px 6px rgba(0,0,0,0.4);
  z-index: 5;
}

.role-badge.landlord {
  background: linear-gradient(135deg, #ffb300 0%, #ff6f00 100%);
  border: 1px solid #ffe082;
}

.role-badge.farmer {
  background: linear-gradient(135deg, #4caf50 0%, #1b5e20 100%);
  border: 1px solid #a5d6a7;
}

/* 加倍闪电标 */
.doubling-badge {
  background: linear-gradient(135deg, #ffca28 0%, #ff8f00 100%);
  color: #3e2723;
  font-size: 0.65rem;
  font-weight: 900;
  padding: 1px 6px;
  border-radius: 6px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.3);
  text-shadow: none;
  animation: pulse 1s infinite alternate;
}

.doubling-badge.super {
  background: linear-gradient(135deg, #ff5722 0%, #bf360c 100%);
  color: #ffffff;
  border: 1px solid #ffab91;
  box-shadow: 0 0 8px rgba(255, 87, 34, 0.6);
}

@keyframes pulse {
  from { transform: scale(1); }
  to { transform: scale(1.05); }
}

.offline-badge {
  position: absolute;
  bottom: -10px;
  background: #d32f2f;
  border: 1px solid #ef9a9a;
  color: white;
  font-size: 0.65rem;
  padding: 2px 6px;
  border-radius: 4px;
  font-weight: bold;
}

/* 纸牌背面积累 */
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
  background: rgba(0,0,0,0.85);
  color: #ffd700;
  font-size: 1.15rem;
  font-weight: 900;
  padding: 1px 8px;
  border-radius: 4px;
  border: 1.5px solid #ffd700;
  pointer-events: none;
  box-shadow: 0 0 10px rgba(255,215,0,0.4);
}

/* 动作展示 */
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
  background: rgba(0, 0, 0, 0.8);
  border: 1.5px solid rgba(255, 255, 255, 0.2);
  color: #ffffff;
  padding: 8px 18px;
  border-radius: 18px;
  font-weight: bold;
  font-size: 0.95rem;
  white-space: nowrap;
  box-shadow: 0 4px 10px rgba(0,0,0,0.4);
}

.bubble-action.pass {
  background: rgba(3, 169, 244, 0.85);
  border-color: #80d8ff;
}

.played-cards-row {
  display: flex;
  gap: 3px;
  background: rgba(0, 0, 0, 0.35);
  padding: 6px;
  border-radius: 6px;
  border: 1px solid rgba(255,255,255,0.08);
}
</style>
