<!-- frontend/src/views/GameRoomView.vue -->
<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { usePlayerStore } from '@/stores/playerStore'
import { useGameStore } from '@/stores/gameStore'
import { useGameWebSocket } from '@/composables/useGameWebSocket'
import PlayerSeat from '@/components/PlayerSeat.vue'
import HandCards from '@/components/HandCards.vue'
import PokerCard from '@/components/PokerCard.vue'
import SettlementModal from '@/components/SettlementModal.vue'

const router = useRouter()
const playerStore = usePlayerStore()
const gameStore = useGameStore()
const { connect, disconnect, sendAction } = useGameWebSocket()

// 校验登录状态
if (!playerStore.playerId || !playerStore.nickname) {
  router.push('/login')
}

// 预设快捷聊天语
const CHAT_PRESETS = [
  "快点吧，等得我花都谢了！",
  "合作愉快，合作愉快！",
  "大牌在后头，千万别放他！",
  "不要走，决战到天亮！",
  "你是地主派来的卧底吧？"
]
const showChatMenu = ref(false)

// 计算玩家在房间中的相对座位定位（顺时针排布）
const orderedSeats = computed(() => {
  const myId = playerStore.playerId
  const pList = gameStore.players
  if (pList.length < 3) return []

  const myIndex = pList.findIndex((p) => p.id === myId)
  if (myIndex === -1) {
    // 若不存在，默认按顺序输出
    return [
      { player: pList[0]!, position: 'left' as const },
      { player: pList[1]!, position: 'right' as const },
      { player: pList[2]!, position: 'bottom' as const }
    ]
  }

  // 顺时针：左侧为前一人，右侧为后一人
  const rightPlayer = pList[(myIndex + 1) % 3]!
  const leftPlayer = pList[(myIndex + 2) % 3]!
  const selfPlayer = pList[myIndex]!

  return [
    { player: leftPlayer, position: 'left' as const },
    { player: rightPlayer, position: 'right' as const },
    { player: selfPlayer, position: 'bottom' as const }
  ]
})

// 能否过牌（仅当本轮非首个出牌者且上家不是自己时才可以过牌）
const canPass = computed(() => {
  return gameStore.lastPlay.player !== null && gameStore.lastPlay.player !== playerStore.playerId
})

onMounted(() => {
  if (!gameStore.wsConnected) {
    connect()
  }
})

onUnmounted(() => {
  // 不在此处主动断开 WS 连接，以保障玩家切出页面时不轻易掉线托管
})

// 叫地主操作
function handleCall(score: number) {
  sendAction({ action: 'call_landlord', score })
}

// 不叫操作
function handleSkipCall() {
  sendAction({ action: 'skip_call' })
}

// 出牌操作
function handlePlayCards() {
  if (gameStore.selectedCards.length === 0) return
  sendAction({
    action: 'play_cards',
    cards: gameStore.selectedCards
  })
  gameStore.clearSelection()
}

// 不要/过牌操作
function handlePass() {
  sendAction({ action: 'pass_turn' })
  gameStore.clearSelection()
}

// 发送聊天短语
function handleSendChat(msgId: number) {
  sendAction({ action: 'chat', msg_id: msgId })
  showChatMenu.value = false
}

// 关闭结算面板，重置数据并返回大厅
function handleCloseSettlement() {
  gameStore.reset()
  router.push('/lobby')
}

// 退出房间
function handleExitRoom() {
  if (confirm('确定要退出当前游戏吗？这将会使您托管或流失积分！')) {
    disconnect()
    gameStore.reset()
    router.push('/lobby')
  }
}
</script>

<template>
  <div class="game-table room-layout">
    <!-- 顶部控制导航栏 -->
    <header class="room-header">
      <button class="btn-exit" @click="handleExitRoom">🚪 退出</button>
      <div class="room-info">
        <span class="room-id">房间号: <strong>{{ gameStore.roomId }}</strong></span>
        <span class="multiplier-badge">倍数: <strong>{{ gameStore.multiplier }}X</strong></span>
      </div>
      <div class="chat-trigger-area">
        <button class="btn-secondary-premium chat-btn" @click="showChatMenu = !showChatMenu">
          💬 快捷语
        </button>
        <!-- 快捷语下拉抽屉 -->
        <div v-if="showChatMenu" class="chat-menu glass-panel">
          <div
            v-for="(text, idx) in CHAT_PRESETS"
            :key="idx"
            class="chat-menu-item"
            @click="handleSendChat(idx)"
          >
            {{ text }}
          </div>
        </div>
      </div>
    </header>

    <!-- 顶端底牌区域 -->
    <div class="bottom-cards-area">
      <div class="bottom-cards-row">
        <PokerCard
          v-for="(cId, index) in gameStore.bottomCards.length > 0 ? gameStore.bottomCards : [0, 0, 0]"
          :key="index"
          :card-id="cId"
          :face-down="gameStore.bottomCards.length === 0"
          :no-hover="true"
          size="sm"
        />
      </div>
      <p class="phase-label">
        <span v-if="gameStore.gamePhase === 'CALLING'">🗣️ 叫分阶段</span>
        <span v-else-if="gameStore.gamePhase === 'PLAYING'">⚔️ 出牌阶段</span>
        <span v-else-if="gameStore.gamePhase === 'DEALING'">🎴 发牌中...</span>
        <span v-else>等待开始...</span>
      </p>
    </div>

    <!-- 中部座位渲染区 -->
    <div class="seats-container">
      <PlayerSeat
        v-for="seat in orderedSeats"
        :key="seat.player.id"
        :player="seat.player"
        :position="seat.position"
        :is-current-turn="gameStore.currentTurn === seat.player.id"
        :last-played-cards="gameStore.playerPlayedCards[seat.player.id]"
        :last-action-text="gameStore.playerActions[seat.player.id]"
      />
    </div>

    <!-- 底部操作区与手牌区 -->
    <div class="player-bottom-area">
      <!-- 轮到自己出牌时的操作功能条 -->
      <div v-if="gameStore.isMyTurn" class="action-bar-row">
        <!-- 叫地主状态栏 -->
        <template v-if="gameStore.gamePhase === 'CALLING'">
          <button class="btn-action-premium" @click="handleCall(1)">1 分</button>
          <button class="btn-action-premium" @click="handleCall(2)">2 分</button>
          <button class="btn-action-premium" @click="handleCall(3)">3 分</button>
          <button class="btn-action-danger" @click="handleSkipCall">不 叫</button>
        </template>

        <!-- 出牌状态栏 -->
        <template v-if="gameStore.gamePhase === 'PLAYING'">
          <button
            class="btn-action-premium"
            :disabled="gameStore.selectedCards.length === 0"
            @click="handlePlayCards"
          >
            出 牌
          </button>
          <button
            class="btn-action-secondary"
            :disabled="!canPass"
            @click="handlePass"
          >
            不 出
          </button>
          <button class="btn-action-secondary" @click="gameStore.clearSelection()">
            重 置
          </button>
        </template>
      </div>

      <!-- 自己的手牌 -->
      <div class="self-hand-row">
        <HandCards :cards="gameStore.myHand" size="lg" />
      </div>
    </div>

    <!-- 结算弹窗 -->
    <SettlementModal
      v-if="gameStore.gamePhase === 'SETTLING' && gameStore.settlement"
      :settlement="gameStore.settlement"
      :players="gameStore.players"
      @close="handleCloseSettlement"
    />
  </div>
</template>

<style scoped>
.room-layout {
  display: flex;
  flex-direction: column;
  height: 100vh;
  justify-content: space-between;
  position: relative;
  overflow: hidden;
}

.room-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 15px 25px;
  background: rgba(0, 0, 0, 0.25);
  z-index: 20;
}

.btn-exit {
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.25);
  color: #ffffff;
  padding: 8px 16px;
  border-radius: 20px;
  cursor: pointer;
  font-weight: 700;
  transition: all 0.2s;
}

.btn-exit:hover {
  background: rgba(255, 255, 255, 0.2);
}

.room-info {
  display: flex;
  gap: 15px;
}

.room-id, .multiplier-badge {
  font-size: 0.95rem;
}

.chat-trigger-area {
  position: relative;
}

.chat-btn {
  padding: 8px 18px;
  border-radius: 20px;
}

.chat-menu {
  position: absolute;
  right: 0;
  top: 45px;
  width: 220px;
  padding: 8px 0;
  display: flex;
  flex-direction: column;
  z-index: 40;
}

.chat-menu-item {
  padding: 10px 16px;
  font-size: 0.85rem;
  cursor: pointer;
  transition: all 0.2s;
  text-align: left;
}

.chat-menu-item:hover {
  background: rgba(255, 255, 255, 0.12);
  color: #ffd700;
}

/* 底牌摆放区 */
.bottom-cards-area {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-top: 15px;
  z-index: 10;
}

.bottom-cards-row {
  display: flex;
  gap: 8px;
  background: rgba(0, 0, 0, 0.3);
  padding: 8px 12px;
  border-radius: 8px;
}

.phase-label {
  font-size: 0.9rem;
  font-weight: 700;
  margin: 6px 0 0 0;
  opacity: 0.8;
  letter-spacing: 1px;
}

/* 座位容器 */
.seats-container {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  pointer-events: none;
}
.seats-container :deep(*) {
  pointer-events: auto; /* 保证座位组件内部点击如头像/出牌仍可交互 */
}

/* 玩家操作和手牌区 */
.player-bottom-area {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 100%;
  gap: 10px;
  z-index: 25;
}

/* 行动功能按钮 */
.action-bar-row {
  display: flex;
  gap: 12px;
  background: rgba(0, 0, 0, 0.4);
  padding: 10px 20px;
  border-radius: 30px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: 0 4px 15px rgba(0, 0, 0, 0.3);
  animation: slide-up 0.25s cubic-bezier(0.175, 0.885, 0.32, 1.275);
}

@keyframes slide-up {
  from { transform: translateY(15px); opacity: 0; }
  to { transform: translateY(0); opacity: 1; }
}

.btn-action-premium {
  background: linear-gradient(135deg, #ffb300 0%, #ff8f00 100%);
  color: #1a1a1a;
  font-weight: 800;
  border: none;
  padding: 10px 24px;
  border-radius: 20px;
  cursor: pointer;
  transition: all 0.2s;
  box-shadow: 0 4px 8px rgba(255, 143, 0, 0.3);
}
.btn-action-premium:hover {
  background: linear-gradient(135deg, #ffe082 0%, #ffb300 100%);
  transform: translateY(-1px);
}
.btn-action-premium:disabled {
  background: #757575;
  color: #9e9e9e;
  box-shadow: none;
  cursor: not-allowed;
}

.btn-action-secondary {
  background: rgba(255, 255, 255, 0.15);
  color: #ffffff;
  font-weight: 700;
  border: 1px solid rgba(255, 255, 255, 0.25);
  padding: 10px 24px;
  border-radius: 20px;
  cursor: pointer;
  transition: all 0.2s;
}
.btn-action-secondary:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.25);
}
.btn-action-secondary:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.btn-action-danger {
  background: rgba(239, 83, 80, 0.8);
  border: 1px solid #ef5350;
  color: white;
  font-weight: 700;
  padding: 10px 24px;
  border-radius: 20px;
  cursor: pointer;
  transition: all 0.2s;
}
.btn-action-danger:hover {
  background: rgba(239, 83, 80, 1);
}

.self-hand-row {
  width: 100%;
  max-width: 900px;
}
</style>
