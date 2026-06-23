<!-- frontend/src/views/LobbyView.vue -->
<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { usePlayerStore } from '@/stores/playerStore'
import { useGameStore } from '@/stores/gameStore'
import { useGameWebSocket } from '@/composables/useGameWebSocket'

const router = useRouter()
const playerStore = usePlayerStore()
const gameStore = useGameStore()
const { connect, disconnect, sendAction } = useGameWebSocket()

// 校验登录状态
if (!playerStore.playerId || !playerStore.nickname) {
  router.push('/login')
}

const leaderboard = ref<any[]>([])
const matchingCount = ref(0)
const matchTime = ref(0)
let matchTimer: number | null = null

// 加载个人属性与排行榜
async function loadLobbyData() {
  try {
    const resProfile = await fetch(`/api/game/profile/${playerStore.playerId}`)
    if (resProfile.ok) {
      const data = await resProfile.json()
      playerStore.beans = data.beans
      playerStore.totalGames = data.total_games
      playerStore.winRate = data.win_rate
    }
    
    const resLeader = await fetch('/api/game/leaderboard')
    if (resLeader.ok) {
      leaderboard.value = await resLeader.json()
    }
  } catch (e) {
    console.error('加载大厅数据失败:', e)
  }
}

// 自动重连或进入房间检测
watch(() => gameStore.gamePhase, (newPhase) => {
  if (['CALLING', 'PLAYING', 'SETTLING'].includes(newPhase)) {
    router.push(`/game/${gameStore.roomId}`)
  }
})

// 监听连接成功后自动发送匹配动作
watch(() => gameStore.wsConnected, (connected) => {
  if (connected && gameStore.gamePhase === 'MATCHING') {
    sendAction({ action: 'join_match', nickname: playerStore.nickname })
  }
})

onMounted(() => {
  loadLobbyData()
  // 连接 WebSocket，如果是断线重连，会自动收到 reconnected 事件并触发上面的 watch 跳转
  connect()
})

onUnmounted(() => {
  stopMatchTimer()
})

function startMatchTimer() {
  matchTime.value = 0
  matchTimer = window.setInterval(() => {
    matchTime.value++
  }, 1000)
}

function stopMatchTimer() {
  if (matchTimer) {
    clearInterval(matchTimer)
    matchTimer = null
  }
}

function handleStartMatch() {
  gameStore.gamePhase = 'MATCHING'
  startMatchTimer()
  if (gameStore.wsConnected) {
    sendAction({ action: 'join_match', nickname: playerStore.nickname })
  } else {
    connect()
  }
}

function handleCancelMatch() {
  stopMatchTimer()
  if (gameStore.wsConnected) {
    sendAction({ action: 'cancel_match' })
  }
  gameStore.gamePhase = 'IDLE'
}

function handleLogout() {
  disconnect()
  gameStore.reset()
  playerStore.logout()
  router.push('/login')
}

// 格式化计时器
function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60).toString().padStart(2, '0')
  const s = (seconds % 60).toString().padStart(2, '0')
  return `${m}:${s}`
}
</script>

<template>
  <div class="game-table lobby-container">
    <!-- 头部导航栏 -->
    <header class="lobby-header glass-panel">
      <div class="header-logo">
        <span class="logo-emoji">🃏</span>
        <h2>游戏大厅</h2>
      </div>
      <div class="user-brief">
        <span>欢迎您，<strong>{{ playerStore.nickname }}</strong></span>
        <button class="btn-logout" @click="handleLogout">退出</button>
      </div>
    </header>

    <!-- 主体双栏布局 -->
    <main class="lobby-main">
      <!-- 左侧：个人档案及匹配区 -->
      <section class="lobby-left">
        <!-- 档案卡片 -->
        <div class="glass-panel profile-card">
          <div class="profile-avatar">👤</div>
          <div class="profile-info">
            <h3>{{ playerStore.nickname }}</h3>
            <p class="profile-id">ID: {{ playerStore.playerId }}</p>
            <div class="profile-stats">
              <div class="stat-item">
                <span class="stat-label">欢乐豆</span>
                <span class="stat-value beans-highlight">🪙 {{ playerStore.beans }}</span>
              </div>
              <div class="stat-item">
                <span class="stat-label">胜场率</span>
                <span class="stat-value">{{ (playerStore.winRate * 100).toFixed(0) }}%</span>
              </div>
              <div class="stat-item">
                <span class="stat-label">总场次</span>
                <span class="stat-value">{{ playerStore.totalGames }}局</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 游戏入口与匹配面板 -->
        <div class="glass-panel action-panel flex-center">
          <template v-if="gameStore.gamePhase === 'MATCHING'">
            <div class="matching-status">
              <div class="spinner"></div>
              <h4>正在匹配中...</h4>
              <p class="match-timer">{{ formatTime(matchTime) }}</p>
              <p class="match-tip">（匹配排队人数多时将自动补充机器人席位）</p>
              <button class="btn-secondary-premium cancel-btn" @click="handleCancelMatch">
                取消匹配
              </button>
            </div>
          </template>

          <template v-else>
            <div class="idle-status">
              <div class="game-teaser">
                <h3>经典三人斗地主</h3>
                <p>实时联网对抗，AI 极致智能托管</p>
              </div>
              <button class="btn-premium play-btn" @click="handleStartMatch">
                开始匹配
              </button>
            </div>
          </template>
        </div>
      </section>

      <!-- 右侧：排行榜 -->
      <section class="lobby-right">
        <div class="glass-panel leaderboard-card">
          <h3 class="leaderboard-title">🪙 欢乐豆富豪榜</h3>
          <div class="leaderboard-list">
            <div class="list-header">
              <span class="rank-col">排名</span>
              <span class="name-col">玩家</span>
              <span class="beans-col">欢乐豆</span>
              <span class="rate-col">胜率</span>
            </div>
            <div
              v-for="item in leaderboard"
              :key="item.player_id"
              class="list-row"
              :class="{ 'is-self': item.player_id === playerStore.playerId }"
            >
              <span class="rank-col">
                <span v-if="item.rank === 1" class="rank-medal">🥇</span>
                <span v-else-if="item.rank === 2" class="rank-medal">🥈</span>
                <span v-else-if="item.rank === 3" class="rank-medal">🥉</span>
                <span v-else>{{ item.rank }}</span>
              </span>
              <span class="name-col truncate">{{ item.nickname }}</span>
              <span class="beans-col yellow-text">{{ item.beans }}</span>
              <span class="rate-col">{{ (item.win_rate * 100).toFixed(0) }}%</span>
            </div>
            <div v-if="leaderboard.length === 0" class="no-data">
              暂无排行榜数据
            </div>
          </div>
        </div>
      </section>
    </main>
  </div>
</template>

<style scoped>
.lobby-container {
  display: flex;
  flex-direction: column;
  padding: 20px;
  gap: 20px;
  box-sizing: border-box;
}

.lobby-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 15px 30px;
}

.header-logo {
  display: flex;
  align-items: center;
  gap: 10px;
}

.header-logo h2 {
  margin: 0;
  font-weight: 700;
}

.user-brief {
  display: flex;
  align-items: center;
  gap: 15px;
}

.btn-logout {
  background: rgba(239, 83, 80, 0.2);
  border: 1px solid rgba(239, 83, 80, 0.4);
  color: #ef5350;
  padding: 6px 12px;
  border-radius: 6px;
  cursor: pointer;
  font-weight: bold;
  transition: all 0.2s;
}

.btn-logout:hover {
  background: rgba(239, 83, 80, 0.3);
}

.lobby-main {
  display: flex;
  gap: 20px;
  flex: 1;
  height: calc(100vh - 120px);
}

.lobby-left {
  flex: 1.2;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.lobby-right {
  flex: 1;
}

.profile-card {
  display: flex;
  padding: 24px;
  gap: 20px;
  align-items: center;
}

.profile-avatar {
  font-size: 3.5rem;
  background: rgba(255, 255, 255, 0.1);
  width: 80px;
  height: 80px;
  border-radius: 50%;
  display: flex;
  justify-content: center;
  align-items: center;
}

.profile-info h3 {
  margin: 0 0 4px 0;
  font-size: 1.4rem;
}

.profile-id {
  margin: 0 0 16px 0;
  font-size: 0.85rem;
  opacity: 0.5;
}

.profile-stats {
  display: flex;
  gap: 24px;
}

.stat-item {
  display: flex;
  flex-direction: column;
}

.stat-label {
  font-size: 0.8rem;
  opacity: 0.6;
  margin-bottom: 4px;
}

.stat-value {
  font-weight: 700;
  font-size: 1.1rem;
}

.beans-highlight {
  color: #ffd700;
}

.action-panel {
  flex: 1;
  padding: 30px;
  text-align: center;
}

.flex-center {
  display: flex;
  justify-content: center;
  align-items: center;
}

.idle-status {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
}

.play-btn {
  padding: 18px 48px;
  font-size: 1.3rem;
  border-radius: 30px;
}

.matching-status {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 15px;
}

.match-timer {
  font-size: 2.5rem;
  font-weight: 800;
  color: #ffb300;
}

.match-tip {
  font-size: 0.8rem;
  opacity: 0.5;
}

.cancel-btn {
  padding: 10px 24px;
  font-size: 1rem;
  margin-top: 10px;
}

.spinner {
  width: 50px;
  height: 50px;
  border: 4px solid rgba(255, 255, 255, 0.1);
  border-top: 4px solid #ffb300;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.leaderboard-card {
  height: 100%;
  padding: 24px;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
}

.leaderboard-title {
  margin: 0 0 20px 0;
  font-size: 1.3rem;
  font-weight: 700;
}

.leaderboard-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow-y: auto;
  flex: 1;
}

.list-header, .list-row {
  display: flex;
  padding: 10px 12px;
  align-items: center;
  font-size: 0.95rem;
}

.list-header {
  font-weight: 700;
  opacity: 0.7;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.list-row {
  background: rgba(255, 255, 255, 0.04);
  border-radius: 8px;
}

.list-row.is-self {
  background: rgba(255, 215, 0, 0.15);
  border: 1px solid rgba(255, 215, 0, 0.3);
}

.rank-col { width: 50px; text-align: center; }
.name-col { flex: 1; padding: 0 10px; }
.beans-col { width: 90px; text-align: right; }
.rate-col { width: 70px; text-align: right; }

.yellow-text {
  color: #ffd700;
  font-weight: bold;
}

.truncate {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.no-data {
  text-align: center;
  padding: 40px;
  opacity: 0.5;
}
</style>
