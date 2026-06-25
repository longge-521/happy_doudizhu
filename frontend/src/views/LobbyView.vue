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
const showLeaderboard = ref(false)
const matchingCount = ref(0)
const matchTime = ref(0)
const showSuccessState = ref(false)
let matchTimer: number | null = null

// 场次定义
const TIERS = [
  { id: 'novice', name: '新手场', baseScore: 20, limit: '1千-10万', online: 124331, colorClass: 'tier-novice' },
  { id: 'primary', name: '初级场', baseScore: 80, limit: '3千-40万', online: 25346, colorClass: 'tier-primary' },
  { id: 'common', name: '普通场', baseScore: 300, limit: '8千-150万', online: 5852, colorClass: 'tier-common' },
  { id: 'middle', name: '中级场', baseScore: 900, limit: '2.5万以上', online: 4001, colorClass: 'tier-middle' },
  { id: 'advanced', name: '高级场', baseScore: 2700, limit: '8万以上', online: 731, colorClass: 'tier-advanced' },
  { id: 'top', name: '顶级场', baseScore: 6000, limit: '30万以上', online: 427, colorClass: 'tier-top' },
]

const TIER_MIN_BEANS: Record<number, number> = {
  20: 1000,     // 新手场底分 20，最低 1,000 豆
  80: 3000,     // 初级场底分 80，最低 3,000 豆
  300: 8000,    // 普通场底分 300，最低 8,000 豆
  900: 25000,   // 中级场底分 900，最低 25,000 豆
  2700: 80000,  // 高级场底分 2700，最低 80,000 豆
  6000: 300000  // 顶级场底分 6000，最低 300,000 豆
}

const selectedBaseScore = ref(80) // 默认初级场 80 分
const selectedTier = ref(TIERS[1]!)
const showReadyPage = ref(false)

const showEditBeansModal = ref(false)
const inputBeansValue = ref(10000)
const editBeansError = ref('')

function openEditBeansModal() {
  inputBeansValue.value = playerStore.beans
  editBeansError.value = ''
  showEditBeansModal.value = true
}

async function handleSaveBeans() {
  if (inputBeansValue.value < 0) {
    editBeansError.value = '欢乐豆数量不能为负数！'
    return
  }
  const result = await playerStore.modifyBeans(inputBeansValue.value)
  if (result.ok) {
    showEditBeansModal.value = false
    await loadLobbyData() // 刷新大厅数据与排行榜
  } else {
    editBeansError.value = result.error || '保存失败'
  }
}

function selectTier(tier: any) {
  const minRequired = TIER_MIN_BEANS[tier.baseScore] || 0
  if (playerStore.beans < minRequired) {
    alert(`您的欢乐豆不足以进入【${tier.name}】！入场门槛为 ${formatBeans(minRequired)} 欢乐豆。`)
    return
  }
  selectedTier.value = tier
  selectedBaseScore.value = tier.baseScore
  showReadyPage.value = true
}

function handleLobbyStartClick() {
  const minRequired = TIER_MIN_BEANS[selectedTier.value.baseScore] || 0
  if (playerStore.beans < minRequired) {
    alert(`您的欢乐豆不足以进入【${selectedTier.value.name}】！入场门槛为 ${formatBeans(minRequired)} 欢乐豆。`)
    return
  }
  showReadyPage.value = true
}

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
    stopMatchTimer()
    showSuccessState.value = true
    setTimeout(() => {
      router.push(`/game/${gameStore.roomId}`)
    }, 1500)
  }
})

// 监听连接成功后自动发送匹配动作
watch(() => gameStore.wsConnected, (connected) => {
  if (connected && gameStore.gamePhase === 'MATCHING') {
    sendAction({
      action: 'join_match',
      nickname: playerStore.nickname,
      base_score: selectedBaseScore.value
    })
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
  matchTime.value = 30
  matchTimer = window.setInterval(() => {
    if (matchTime.value > 0) {
      matchTime.value--
    } else {
      handleCancelMatch()
    }
  }, 1000)
}

function stopMatchTimer() {
  if (matchTimer) {
    clearInterval(matchTimer)
    matchTimer = null
  }
}

function handleStartMatch() {
  showSuccessState.value = false
  gameStore.gamePhase = 'MATCHING'
  startMatchTimer()
  if (gameStore.wsConnected) {
    sendAction({
      action: 'join_match',
      nickname: playerStore.nickname,
      base_score: selectedBaseScore.value
    })
  } else {
    connect()
  }
}

function handleCancelMatch() {
  showSuccessState.value = false
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

// 侧边栏菜单列表
const sidebarItems = [
  { name: '510K', badge: '热门' },
  { name: '不洗牌', badge: '' },
  { name: '欢乐经典', badge: '' },
  { name: '经典', badge: '最近', active: true },
  { name: '天地癞子', badge: '' },
  { name: '血流麻将', badge: '热门' },
  { name: '更多玩法', badge: '' }
]

// 资产数值格式化
function formatBeans(beans: number): string {
  if (beans >= 100000) {
    return (beans / 10000).toFixed(2) + '万'
  }
  if (beans >= 10000) {
    return (beans / 10000).toFixed(1) + '万'
  }
  return beans.toString()
}

function handleHotPlayHint() {
  alert('510K玩法正在加急开发中，敬请期待！')
}
</script>

<template>
  <div class="game-table lobby-modern-container">
    <template v-if="!showReadyPage">
      <!-- 顶部状态栏 -->
      <header class="lobby-top-bar">
        <div class="top-left">
          <button class="btn-back" @click="handleLogout">
            <span class="back-arrow">↩</span> 经典
          </button>
          <span class="info-help-btn">?</span>
        </div>

        <div class="top-center-assets">
          <!-- 欢乐豆 -->
          <div class="asset-pill gold-beans" @click="openEditBeansModal" style="cursor: pointer;">
            <span class="asset-icon">🪙</span>
            <span class="asset-amount">{{ formatBeans(playerStore.beans) }}</span>
            <span class="asset-plus">+</span>
          </div>
          <!-- 钻石 -->
          <div class="asset-pill diamonds">
            <span class="asset-icon">💎</span>
            <span class="asset-amount">0</span>
            <span class="asset-plus">+</span>
          </div>
        </div>

        <div class="top-right-leaderboard">
          <button class="btn-leaderboard-toggle" @click="showLeaderboard = !showLeaderboard">
            🏆 排行榜
          </button>
        </div>
      </header>

      <div class="lobby-core-layout">
        <!-- 左侧分类侧边栏 -->
        <aside class="lobby-sidebar">
          <div
            v-for="item in sidebarItems"
            :key="item.name"
            class="sidebar-item"
            :class="{ active: item.active }"
          >
            <span class="item-text">{{ item.name }}</span>
            <span v-if="item.badge" class="item-badge" :class="item.badge === '热门' ? 'hot' : 'recent'">
              {{ item.badge }}
            </span>
          </div>
        </aside>

        <!-- 中部场次卡片区 -->
        <main class="lobby-grid-main">
          <div class="grid-container">
            <div
              v-for="tier in TIERS"
              :key="tier.id"
              class="tier-card"
              :class="[tier.colorClass, { selected: selectedBaseScore === tier.baseScore }]"
              @click="selectTier(tier)"
            >
              <!-- 选中高亮光环 -->
              <div class="selected-glow" v-if="selectedBaseScore === tier.baseScore"></div>

              <div class="card-inner">
                <h3 class="tier-name">{{ tier.name }}</h3>

                <div class="tier-score-row">
                  <span class="score-tag">底分</span>
                  <span class="score-number">{{ tier.baseScore }}</span>
                </div>

                <div class="tier-meta-info">
                  <span class="meta-item online">
                    <span class="meta-icon">👤</span> {{ tier.online }}人
                  </span>
                  <span class="meta-item limit">
                    <span class="meta-icon">🪙</span> {{ tier.limit }}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </main>
      </div>

      <!-- 底部控制栏 -->
      <footer class="lobby-bottom-bar">
        <!-- 个人信息 -->
        <div class="bottom-user-card">
          <div class="user-avatar-wrap">
            <span class="avatar-emoji">👤</span>
          </div>
          <div class="user-meta">
            <div class="user-name-row">
              <span class="username truncate">{{ playerStore.nickname }}</span>
              <span class="title-badge">亲王IV</span>
            </div>
            <!-- 星星等级 -->
            <div class="stars-row">
              <span class="star active">★</span>
              <span class="star active">★</span>
              <span class="star active">★</span>
              <span class="star active">★</span>
              <span class="star active">★</span>
              <span class="star-text">5/5</span>
            </div>
          </div>
        </div>

        <!-- 操作按钮区 -->
        <div class="bottom-actions-row">
          <!-- 好友房 -->
          <div class="action-btn-wrapper">
            <button class="btn-green-room">
              <span class="btn-title">好友房</span>
              <span class="btn-subtitle font-glow">不结算欢乐豆</span>
            </button>
          </div>

          <!-- 快速开始 -->
          <div class="action-btn-wrapper">
            <button class="btn-orange-start" @click="handleLobbyStartClick">
              <span class="btn-title">快速开始</span>
              <span class="btn-subtitle">经典{{ selectedTier.name }}</span>
            </button>
          </div>
        </div>
      </footer>
    </template>

    <template v-else>
      <!-- 准备页顶部状态栏 -->
      <header class="lobby-top-bar">
        <div class="top-left">
          <button class="btn-back" @click="showReadyPage = false">
            <span class="back-arrow">↩</span> 返回
          </button>
        </div>
        <div class="top-right-hud" style="margin-left: auto; display: flex; gap: 12px; align-items: center;">
          <button class="btn-hud-tool" @click="showReadyPage = false">换桌</button>
          <span class="info-help-btn">?</span>
        </div>
      </header>

      <!-- 中部水印与说明 -->
      <div class="ready-brand-center">
        <div class="ready-logo">欢乐斗地主</div>
        <div class="ready-subtitle">经典{{ selectedTier.name }} 底分{{ selectedTier.baseScore }}</div>
      </div>

      <!-- 准备页核心操作按钮 -->
      <div class="ready-actions-panel">
        <button class="btn-ready-hot" @click="handleHotPlayHint">
          <span class="ready-btn-title">玩热门玩法</span>
          <span class="ready-btn-subtitle">510K玩法</span>
        </button>
        <button class="btn-ready-start" @click="handleStartMatch">
          开始游戏
        </button>
      </div>

      <!-- 底部个人信息与资产 -->
      <footer class="lobby-bottom-bar ready-bottom">
        <div class="bottom-user-card">
          <div class="user-avatar-wrap">
            <span class="avatar-emoji">👤</span>
          </div>
          <div class="user-meta">
            <div class="user-name-row">
              <span class="username truncate">{{ playerStore.nickname }}</span>
              <span class="title-badge">亲王IV</span>
            </div>
            <div class="stars-row">
              <span class="star active">★</span>
              <span class="star active">★</span>
              <span class="star active">★</span>
              <span class="star active">★</span>
              <span class="star active">★</span>
              <span class="star-text">5/5</span>
            </div>
          </div>
        </div>

        <div class="ready-bottom-assets">
          <div class="asset-pill gold-beans" style="margin-top: 0; box-shadow: 0 2px 8px rgba(0,0,0,0.3);">
            <span class="asset-icon">🪙</span>
            <span class="asset-amount">{{ formatBeans(playerStore.beans) }}</span>
          </div>
        </div>
      </footer>
    </template>

    <!-- 排行榜弹窗 -->
    <div v-if="showLeaderboard" class="modal-overlay" @click.self="showLeaderboard = false">
      <div class="glass-panel leaderboard-modal">
        <div class="modal-header">
          <h3>🏆 欢乐豆富豪榜</h3>
          <button class="btn-close" @click="showLeaderboard = false">×</button>
        </div>
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
            <span class="beans-col yellow-text">{{ formatBeans(item.beans) }}</span>
            <span class="rate-col">{{ (item.win_rate * 100).toFixed(0) }}%</span>
          </div>
          <div v-if="leaderboard.length === 0" class="no-data">
            暂无排行榜数据
          </div>
        </div>
      </div>
    </div>

    <!-- 欢乐豆修改弹窗 -->
    <div v-if="showEditBeansModal" class="modal-overlay" @click.self="showEditBeansModal = false">
      <div class="glass-panel leaderboard-modal" style="max-width: 400px; padding: 24px;">
        <div class="modal-header" style="margin-bottom: 20px;">
          <h3>🪙 修改欢乐豆数量</h3>
          <button class="btn-close" @click="showEditBeansModal = false">×</button>
        </div>
        <div class="modal-body" style="display: flex; flex-direction: column; gap: 16px;">
          <div style="display: flex; flex-direction: column; gap: 8px;">
            <label style="color: #ccc; font-size: 0.9rem; text-align: left;">请输入新的欢乐豆数量 (不少于 0)：</label>
            <input
              v-model.number="inputBeansValue"
              type="number"
              min="0"
              style="background: rgba(0,0,0,0.5); border: 1.5px solid rgba(255,255,255,0.2); border-radius: 8px; padding: 10px; color: #fff; font-size: 1.2rem; font-weight: bold; width: 100%; box-sizing: border-box;"
            />
          </div>
          <p v-if="editBeansError" style="color: #f44336; margin: 0; font-size: 0.85rem; text-align: left;">{{ editBeansError }}</p>
        </div>
        <div class="modal-footer" style="display: flex; justify-content: flex-end; gap: 12px; margin-top: 24px;">
          <button class="btn-leaderboard-toggle" @click="showEditBeansModal = false" style="background: rgba(255,255,255,0.1); color: #fff; border: 1px solid rgba(255,255,255,0.2);">取消</button>
          <button class="btn-leaderboard-toggle" @click="handleSaveBeans">确认保存</button>
        </div>
      </div>
    </div>

    <!-- 匹配状态全屏遮罩 -->
    <div v-if="gameStore.gamePhase === 'MATCHING' || showSuccessState" class="matching-overlay">
      <div class="matching-board glass-panel" :class="{ 'match-success-board': showSuccessState }">
        <template v-if="!showSuccessState">
          <div class="spinner-glow">
            <div class="circle"></div>
          </div>
          <h2>正在速配玩伴..</h2>
          <div class="match-time-digits">{{ formatTime(matchTime) }}</div>
          <p class="matching-detail">匹配场次：经典{{ selectedTier.name }} (底分 {{ selectedTier.baseScore }})</p>
          <button class="btn-cancel-matching" @click="handleCancelMatch">
            取消匹配
          </button>
        </template>
        <template v-else>
          <div class="success-animation">
            <span class="success-icon">🎉</span>
          </div>
          <h2 class="success-title">匹配成功！</h2>
          <p class="matching-detail success-detail">已为您匹配到玩家，正在进入对局...</p>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.lobby-modern-container {
  display: flex;
  flex-direction: column;
  height: 100vh;
  justify-content: space-between;
  background: radial-gradient(circle at center, #2196f3 0%, #0d47a1 100%);
  overflow: hidden;
  padding: 0;
  box-sizing: border-box;
}

/* 顶部状态栏 */
.lobby-top-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 24px;
  background: linear-gradient(to bottom, rgba(0, 0, 0, 0.4) 0%, rgba(0, 0, 0, 0) 100%);
  height: 60px;
  z-index: 10;
}

.top-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.btn-back {
  background: none;
  border: none;
  color: #fff;
  font-size: 1.4rem;
  font-weight: 800;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  text-shadow: 0 2px 4px rgba(0,0,0,0.5);
}

.back-arrow {
  font-size: 1.6rem;
}

.info-help-btn {
  background: rgba(255, 255, 255, 0.2);
  border: 1px solid rgba(255, 255, 255, 0.4);
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: inline-flex;
  justify-content: center;
  align-items: center;
  font-weight: bold;
  cursor: pointer;
}

.top-center-assets {
  display: flex;
  gap: 16px;
}

.asset-pill {
  background: rgba(0, 0, 0, 0.6);
  border: 1.5px solid rgba(255, 255, 255, 0.25);
  border-radius: 20px;
  display: flex;
  align-items: center;
  padding: 4px 12px;
  gap: 8px;
  min-width: 140px;
  box-shadow: inset 0 2px 4px rgba(0,0,0,0.5);
  position: relative;
}

.asset-icon {
  font-size: 1.2rem;
}

.asset-amount {
  color: #ffd700;
  font-weight: 800;
  font-size: 1rem;
  flex: 1;
  text-shadow: 0 1px 2px rgba(0,0,0,0.8);
}

.asset-plus {
  background: linear-gradient(135deg, #ffd54f 0%, #ff8f00 100%);
  color: #1a1a1a;
  font-weight: 900;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  display: flex;
  justify-content: center;
  align-items: center;
  font-size: 0.9rem;
  cursor: pointer;
  box-shadow: 0 2px 4px rgba(0,0,0,0.3);
}

.btn-leaderboard-toggle {
  background: linear-gradient(to bottom, #ffca28 0%, #ff8f00 100%);
  color: #3e2723;
  border: 1px solid #ffd54f;
  padding: 6px 16px;
  border-radius: 15px;
  font-weight: bold;
  cursor: pointer;
  box-shadow: 0 2px 8px rgba(0,0,0,0.4);
  transition: transform 0.1s;
}

.btn-leaderboard-toggle:hover {
  transform: scale(1.05);
}

/* 核心布局 */
.lobby-core-layout {
  display: flex;
  flex: 1;
  width: 100%;
  height: calc(100vh - 150px);
}

/* 左侧侧边栏 */
.lobby-sidebar {
  width: 150px;
  display: flex;
  flex-direction: column;
  padding: 10px 0;
  background: linear-gradient(to right, rgba(0, 0, 0, 0.45) 0%, rgba(0, 0, 0, 0) 100%);
  gap: 8px;
}

.sidebar-item {
  position: relative;
  padding: 12px 20px;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  border-radius: 0 20px 20px 0;
  margin-right: 10px;
}

.sidebar-item .item-text {
  font-size: 1.05rem;
  font-weight: bold;
  color: rgba(255, 255, 255, 0.7);
  text-shadow: 0 1px 2px rgba(0,0,0,0.5);
}

.sidebar-item.active {
  background: linear-gradient(to right, #ffd54f 0%, #ff8f00 100%);
  box-shadow: 0 4px 8px rgba(0,0,0,0.3);
}

.sidebar-item.active .item-text {
  color: #3e2723;
  font-weight: 800;
  text-shadow: none;
}

.item-badge {
  position: absolute;
  top: 2px;
  right: 12px;
  font-size: 0.65rem;
  font-weight: bold;
  padding: 1px 5px;
  border-radius: 6px;
  color: #fff;
  transform: scale(0.9);
}

.item-badge.hot {
  background: #f44336;
}

.item-badge.recent {
  background: #9c27b0;
}

/* 中部网格场次 */
.lobby-grid-main {
  flex: 1;
  padding: 20px 24px;
  overflow-y: auto;
  display: flex;
  align-items: center;
}

.grid-container {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
  width: 100%;
}

.tier-card {
  position: relative;
  border-radius: 12px;
  cursor: pointer;
  aspect-ratio: 1.6 / 1;
  transition: transform 0.2s, box-shadow 0.2s;
  overflow: hidden;
  box-shadow: 0 4px 15px rgba(0,0,0,0.3);
  border: 1.5px solid rgba(255,255,255,0.15);
}

.tier-card:hover {
  transform: translateY(-4px) scale(1.02);
}

.tier-card.selected {
  border-color: #ffd700;
  box-shadow: 0 0 20px rgba(255, 215, 0, 0.45);
}

.selected-glow {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  border: 2px solid #ffd700;
  border-radius: 12px;
  pointer-events: none;
  box-shadow: inset 0 0 15px rgba(255, 215, 0, 0.6);
  z-index: 2;
}

.card-inner {
  padding: 16px;
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  box-sizing: border-box;
}

.tier-name {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 800;
  color: #fff;
  text-shadow: 0 2px 4px rgba(0,0,0,0.5);
}

.tier-score-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.score-tag {
  background: #ff9800;
  color: #fff;
  font-size: 0.75rem;
  font-weight: bold;
  padding: 1px 6px;
  border-radius: 4px;
}

.score-number {
  color: #ffd700;
  font-size: 2.2rem;
  font-weight: 900;
  line-height: 1;
  text-shadow: 0 3px 6px rgba(0,0,0,0.6);
}

.tier-meta-info {
  display: flex;
  justify-content: space-between;
  font-size: 0.8rem;
  opacity: 0.9;
  text-shadow: 0 1px 2px rgba(0,0,0,0.8);
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

/* 场次卡片背景渐变配色 */
.tier-novice { background: linear-gradient(135deg, #4caf50 0%, #1b5e20 100%); }
.tier-primary { background: linear-gradient(135deg, #03a9f4 0%, #01579b 100%); }
.tier-common { background: linear-gradient(135deg, #3f51b5 0%, #1a237e 100%); }
.tier-middle { background: linear-gradient(135deg, #673ab7 0%, #311b92 100%); }
.tier-advanced { background: linear-gradient(135deg, #e91e63 0%, #880e4f 100%); }
.tier-top { background: linear-gradient(135deg, #9c27b0 0%, #4a148c 100%); }

/* 底部操作栏 */
.lobby-bottom-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 30px;
  background: linear-gradient(to top, rgba(0, 0, 0, 0.6) 0%, rgba(0, 0, 0, 0) 100%);
  height: 80px;
  box-sizing: border-box;
}

.bottom-user-card {
  display: flex;
  align-items: center;
  gap: 12px;
}

.user-avatar-wrap {
  width: 50px;
  height: 50px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.15);
  border: 1.5px solid #fff;
  display: flex;
  justify-content: center;
  align-items: center;
  font-size: 1.8rem;
  box-shadow: 0 2px 6px rgba(0,0,0,0.3);
}

.user-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.user-name-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.username {
  font-weight: bold;
  font-size: 1.05rem;
  color: #fff;
  max-width: 100px;
}

.title-badge {
  background: linear-gradient(to right, #e040fb, #9c27b0);
  color: #fff;
  font-size: 0.65rem;
  font-weight: 800;
  padding: 1px 6px;
  border-radius: 8px;
}

.stars-row {
  display: flex;
  align-items: center;
  gap: 2px;
  font-size: 0.8rem;
}

.star {
  color: rgba(255, 255, 255, 0.3);
}

.star.active {
  color: #ffd700;
}

.star-text {
  margin-left: 6px;
  font-size: 0.75rem;
  opacity: 0.8;
}

.bottom-actions-row {
  display: flex;
  gap: 20px;
}

.btn-green-room {
  background: linear-gradient(135deg, #81c784 0%, #2e7d32 100%);
  border: 1.5px solid #a5d6a7;
  border-radius: 28px;
  color: #fff;
  padding: 8px 32px;
  cursor: pointer;
  box-shadow: 0 4px 10px rgba(0,0,0,0.4);
  display: flex;
  flex-direction: column;
  align-items: center;
  transition: transform 0.1s;
}

.btn-orange-start {
  background: linear-gradient(135deg, #ffca28 0%, #f57c00 100%);
  border: 1.5px solid #ffe082;
  border-radius: 28px;
  color: #fff;
  padding: 8px 45px;
  cursor: pointer;
  box-shadow: 0 4px 10px rgba(0,0,0,0.4);
  display: flex;
  flex-direction: column;
  align-items: center;
  transition: transform 0.1s;
}

.btn-green-room:hover, .btn-orange-start:hover {
  transform: scale(1.04);
}

.btn-title {
  font-size: 1.2rem;
  font-weight: 900;
  text-shadow: 0 1px 3px rgba(0,0,0,0.6);
}

.btn-subtitle {
  font-size: 0.7rem;
  opacity: 0.9;
  font-weight: bold;
}

.font-glow {
  text-shadow: 0 0 5px rgba(255, 255, 255, 0.8);
}

/* 排行榜弹窗 */
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
  backdrop-filter: blur(8px);
}

.leaderboard-modal {
  width: 90%;
  max-width: 500px;
  height: 80vh;
  padding: 24px;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  border-bottom: 1.5px solid rgba(255, 255, 255, 0.15);
  padding-bottom: 10px;
}

.modal-header h3 {
  margin: 0;
  font-size: 1.4rem;
}

.btn-close {
  background: none;
  border: none;
  color: #fff;
  font-size: 1.8rem;
  cursor: pointer;
}

.leaderboard-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow-y: auto;
  flex: 1;
}

.list-header, .list-row {
  display: grid;
  grid-template-columns: 60px 1.5fr 1fr 1fr;
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
  border: 1px solid rgba(255,255,255,0.05);
}

.list-row.is-self {
  background: rgba(255, 215, 0, 0.15);
  border: 1px solid rgba(255, 215, 0, 0.3);
}

.rank-col { text-align: center; }
.name-col { padding: 0 10px; }
.beans-col { text-align: right; }
.rate-col { text-align: right; }

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

/* 准备页二级界面相关样式 */
.btn-hud-tool {
  background: rgba(255, 255, 255, 0.15);
  border: 1px solid rgba(255, 255, 255, 0.3);
  color: #fff;
  padding: 6px 16px;
  font-size: 0.95rem;
  border-radius: 18px;
  cursor: pointer;
  font-weight: 700;
  transition: all 0.2s ease;
  text-shadow: 0 1px 2px rgba(0,0,0,0.4);
}

.btn-hud-tool:hover {
  background: rgba(255, 255, 255, 0.3);
  transform: scale(1.05);
}

.ready-brand-center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex: 1;
  margin-top: -40px;
}

.ready-logo {
  font-size: 5rem;
  font-weight: 900;
  color: rgba(255, 255, 255, 0.15);
  background: linear-gradient(135deg, rgba(255,255,255,0.2) 0%, rgba(255,255,255,0.05) 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  user-select: none;
  letter-spacing: 12px;
  text-transform: uppercase;
  text-shadow: 1px 1px 0px rgba(255,255,255,0.05);
}

.ready-subtitle {
  font-size: 1.8rem;
  font-weight: 900;
  color: #ffffff;
  margin-top: 15px;
  text-shadow: 0 2px 8px rgba(0, 0, 0, 0.5);
  letter-spacing: 2px;
}

.ready-actions-panel {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 30px;
  padding: 20px;
  margin-bottom: 80px;
  z-index: 10;
}

.btn-ready-hot {
  width: 200px;
  height: 64px;
  border-radius: 32px;
  background: linear-gradient(135deg, #29b6f6 0%, #0288d1 100%);
  border: 2px solid #81d4fa;
  box-shadow: 0 6px 16px rgba(2, 136, 209, 0.4), inset 0 2px 4px rgba(255,255,255,0.3);
  color: #ffffff;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  transition: all 0.2s cubic-bezier(0.175, 0.885, 0.32, 1.275);
}

.btn-ready-hot .ready-btn-title {
  font-size: 1.25rem;
  font-weight: 900;
  text-shadow: 0 2px 4px rgba(0,0,0,0.3);
  letter-spacing: 1px;
}

.btn-ready-hot .ready-btn-subtitle {
  font-size: 0.75rem;
  opacity: 0.85;
  margin-top: 2px;
  font-weight: 700;
}

.btn-ready-hot:hover {
  transform: translateY(-4px) scale(1.03);
  box-shadow: 0 10px 24px rgba(2, 136, 209, 0.5);
}

.btn-ready-start {
  width: 220px;
  height: 68px;
  border-radius: 34px;
  background: linear-gradient(135deg, #ffca28 0%, #ff8f00 50%, #e65100 100%);
  border: 2.5px solid #ffe082;
  box-shadow: 0 8px 20px rgba(230, 81, 0, 0.45), inset 0 2px 4px rgba(255,255,255,0.4);
  color: #ffffff;
  font-size: 1.45rem;
  font-weight: 900;
  letter-spacing: 2px;
  cursor: pointer;
  text-shadow: 0 2px 4px rgba(0,0,0,0.4);
  display: flex;
  justify-content: center;
  align-items: center;
  transition: all 0.25s cubic-bezier(0.175, 0.885, 0.32, 1.275);
}

.btn-ready-start:hover {
  transform: translateY(-4px) scale(1.05);
  box-shadow: 0 12px 28px rgba(230, 81, 0, 0.6);
  background: linear-gradient(135deg, #ffd54f 0%, #ffa000 50%, #ef6c00 100%);
}

.ready-bottom {
  background: linear-gradient(to top, rgba(0,0,0,0.5) 0%, rgba(0,0,0,0) 100%);
  padding: 15px 30px 25px 30px;
}

.ready-bottom-assets {
  display: flex;
  align-items: center;
  margin-left: auto;
}

/* 匹配遮罩 */
.matching-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.75);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
  backdrop-filter: blur(10px);
}

/* 匹配看板 */
.matching-board {
  width: 90%;
  max-width: 420px;
  padding: 30px 24px;
  text-align: center;
  border-radius: 16px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 15px;
  animation: scaleIn 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}

@keyframes scaleIn {
  from {
    transform: scale(0.9);
    opacity: 0;
  }
  to {
    transform: scale(1);
    opacity: 1;
  }
}

/* 旋转加载动画 */
.spinner-glow {
  position: relative;
  width: 70px;
  height: 70px;
  display: flex;
  justify-content: center;
  align-items: center;
  margin-bottom: 5px;
}

.spinner-glow .circle {
  width: 60px;
  height: 60px;
  border: 4px solid rgba(255, 255, 255, 0.1);
  border-top-color: #ffd700;
  border-radius: 50%;
  animation: spin 1.2s linear infinite;
  box-shadow: 0 0 15px rgba(255, 215, 0, 0.3);
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.matching-board h2 {
  font-size: 1.5rem;
  font-weight: 900;
  color: #ffffff;
  margin: 0;
  letter-spacing: 1px;
}

.match-time-digits {
  font-size: 2.5rem;
  font-weight: 900;
  color: #ffb300;
  font-family: 'Courier New', Courier, monospace;
  text-shadow: 0 0 10px rgba(255, 179, 0, 0.5);
  margin: 5px 0;
}

.matching-detail {
  font-size: 0.9rem;
  color: rgba(255, 255, 255, 0.7);
  margin: 0;
}

.btn-cancel-matching {
  background: linear-gradient(135deg, #e53935 0%, #c62828 100%);
  color: #ffffff;
  border: 1px solid #ef5350;
  border-radius: 20px;
  padding: 8px 30px;
  font-weight: bold;
  font-size: 0.95rem;
  cursor: pointer;
  box-shadow: 0 4px 12px rgba(198, 40, 40, 0.4);
  transition: all 0.2s ease;
  margin-top: 10px;
}

.btn-cancel-matching:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(198, 40, 40, 0.6);
  background: linear-gradient(135deg, #ef5350 0%, #d32f2f 100%);
}

/* 匹配成功状态样式 */
.match-success-board {
  border-color: #ffd700 !important;
  box-shadow: 0 0 30px rgba(255, 215, 0, 0.3) !important;
}

.success-animation {
  width: 70px;
  height: 70px;
  background: rgba(255, 215, 0, 0.15);
  border: 2px solid #ffd700;
  border-radius: 50%;
  display: flex;
  justify-content: center;
  align-items: center;
  box-shadow: 0 0 20px rgba(255, 215, 0, 0.4);
  animation: pop 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
  margin-bottom: 5px;
}

.success-icon {
  font-size: 2.2rem;
}

@keyframes pop {
  0% { transform: scale(0); }
  100% { transform: scale(1); }
}

.success-title {
  color: #ffd700 !important;
  font-size: 1.8rem !important;
  text-shadow: 0 0 10px rgba(255, 215, 0, 0.3);
}

.success-detail {
  color: #a5d6a7 !important;
  font-weight: bold;
}
</style>
