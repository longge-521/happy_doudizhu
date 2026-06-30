<!-- frontend/src/views/LobbyView.vue -->
<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { usePlayerStore } from '@/stores/playerStore'
import { useGameStore } from '@/stores/gameStore'
import { useGameWebSocket } from '@/composables/useGameWebSocket'
import { useSoundEngine } from '@/composables/useSoundEngine'
import SettingsModal from '@/components/SettingsModal.vue'

const router = useRouter()
const playerStore = usePlayerStore()
const gameStore = useGameStore()
const { connect, disconnect, sendAction } = useGameWebSocket()
const { playSound, startBgm, stopBgm, unlock: unlockAudio } = useSoundEngine()

const isMockMode = new URLSearchParams(window.location.search).get('mock') === 'true'

// 校验登录状态
if (!isMockMode && (!playerStore.playerId || !playerStore.nickname)) {
  router.push('/login')
}

const leaderboard = ref<any[]>([])
const showLeaderboard = ref(false)
const matchingCount = ref(0)
const matchTime = ref(0)
const showSuccessState = ref(false)
const showSettings = ref(false)
const featureNotice = ref({
  visible: false,
  title: '',
  message: ''
})
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

const RANK_NAMES = [
  "", "包身工", "短工", "长工", "中农", "富农", "掌柜", "商人", "小财主", "大财主",
  "县尉", "县丞", "县令", "通判", "主事", "知府", "员外郎", "郎中", "侍郎", "巡抚",
  "总督", "尚书", "大学士", "太保", "太傅", "太师", "三等伯", "二等伯", "一等伯",
  "三等侯", "二等侯", "一等侯", "辅国公", "镇国公", "郡王", "亲王", "至尊"
]

const showEditBeansModal = ref(false)
const inputBeansValue = ref(10000)
const editBeansError = ref('')
const showProfileModal = ref(false)
const avatarInputValue = ref('')
const avatarSaveError = ref('')
const avatarImageFailed = ref(false)

const inputRankId = ref(1)
const inputSubRank = ref(4)
const inputStars = ref(0)
const editRankError = ref('')

function getRankMaxStars(rid: number): number {
  if (rid < 10) return 3
  if (rid < 22) return 4
  return 5
}

function openEditBeansModal() {
  inputBeansValue.value = playerStore.beans
  editBeansError.value = ''
  
  // 段位初始化参数
  inputRankId.value = playerStore.rankId
  inputSubRank.value = playerStore.subRank
  inputStars.value = playerStore.stars
  editRankError.value = ''
  
  showEditBeansModal.value = true
}

function openProfileModal() {
  avatarInputValue.value = playerStore.avatarUrl || ''
  avatarSaveError.value = ''
  avatarImageFailed.value = false
  showProfileModal.value = true
}

function openFeatureNotice(title: string, message = '该功能正在开发中，敬请期待！') {
  featureNotice.value = {
    visible: true,
    title,
    message
  }
}

function closeFeatureNotice() {
  featureNotice.value.visible = false
}

function handleHelpClick() {
  openFeatureNotice('玩法帮助', '玩法说明和新手引导正在完善中，敬请期待！')
}

function handleSidebarClick(item: any) {
  if (item.active) {
    openFeatureNotice('经典玩法', '当前已经在经典玩法大厅。')
    return
  }
  openFeatureNotice(item.name)
}

function handleDiamondClick() {
  openFeatureNotice('钻石商城', '钻石充值和商城功能正在开发中，敬请期待！')
}

function handleFriendRoomClick() {
  openFeatureNotice('好友房', '好友房功能正在开发中，敬请期待！')
}

function handleProfileClick() {
  openProfileModal()
}

async function handleSaveAvatar() {
  avatarSaveError.value = ''
  const result = await playerStore.modifyAvatar(avatarInputValue.value)
  if (!result.ok) {
    avatarSaveError.value = result.error || '头像保存失败'
    return
  }
  avatarInputValue.value = playerStore.avatarUrl || ''
  avatarImageFailed.value = false
}

async function handleClearAvatar() {
  avatarSaveError.value = ''
  const result = await playerStore.modifyAvatar('')
  if (!result.ok) {
    avatarSaveError.value = result.error || '头像清空失败'
    return
  }
  avatarInputValue.value = ''
  avatarImageFailed.value = false
}

function handleAvatarImageError() {
  avatarImageFailed.value = true
}

async function handleSaveBeans() {
  if (inputBeansValue.value < 0) {
    editBeansError.value = '欢乐豆数量不能为负数！'
    return
  }
  
  // 1. 保存欢乐豆
  const resBeans = await playerStore.modifyBeans(inputBeansValue.value)
  if (!resBeans.ok) {
    editBeansError.value = resBeans.error || '保存欢乐豆失败'
    return
  }

  // 2. 保存段位等级
  const maxStars = getRankMaxStars(inputRankId.value)
  if (inputStars.value > maxStars && inputRankId.value < 36) {
    editRankError.value = `当前段位最高只能设定为 ${maxStars} 颗星！`
    return
  }
  
  const resRank = await playerStore.modifyRank(inputRankId.value, inputSubRank.value, inputStars.value)
  if (resRank.ok) {
    showEditBeansModal.value = false
    await loadLobbyData()
  } else {
    editRankError.value = resRank.error || '保存排位失败'
  }
}

function selectTier(tier: any) {
  const minRequired = TIER_MIN_BEANS[tier.baseScore] || 0
  if (playerStore.beans < minRequired) {
    openFeatureNotice('欢乐豆不足', `您的欢乐豆不足以进入【${tier.name}】！入场门槛为 ${formatBeans(minRequired)} 欢乐豆。`)
    return
  }
  selectedTier.value = tier
  selectedBaseScore.value = tier.baseScore
  showReadyPage.value = true
}

function handleLobbyStartClick() {
  const minRequired = TIER_MIN_BEANS[selectedTier.value.baseScore] || 0
  if (playerStore.beans < minRequired) {
    openFeatureNotice('欢乐豆不足', `您的欢乐豆不足以进入【${selectedTier.value.name}】！入场门槛为 ${formatBeans(minRequired)} 欢乐豆。`)
    return
  }
  showReadyPage.value = true
}

// 加载个人属性与排行榜
async function loadLobbyData() {
  try {
    await playerStore.fetchProfile()

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
    stopBgm()
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
  unlockAudio()
  if (isMockMode) {
    playerStore.playerId = 'mock_player'
    playerStore.nickname = '雀圣斗地王'
    playerStore.username = 'mock_user'
    playerStore.beans = 9999999
    playerStore.rankTitle = '至尊斗皇III'
    playerStore.totalGames = 2048
    playerStore.winRate = 72.8
    playerStore.stars = 4
    playerStore.subRank = 1
    
    leaderboard.value = [
      { player_id: 'mock_player', nickname: '雀圣斗地王', beans: 9999999, rank_title: '至尊斗皇III', win_rate: 72.8, total_games: 2048 },
      { player_id: 'p2', nickname: '发牌大户', beans: 5880000, rank_title: '至尊斗皇I', win_rate: 65.4, total_games: 1500 },
      { player_id: 'p3', nickname: '农民专业户', beans: 3200000, rank_title: '傲世斗王IV', win_rate: 58.2, total_games: 890 },
      { player_id: 'p4', nickname: '明牌炸弹人', beans: 1200000, rank_title: '傲世斗王I', win_rate: 61.0, total_games: 450 },
      { player_id: 'p5', nickname: '小王在此', beans: 980000, rank_title: '强力斗魂V', win_rate: 51.5, total_games: 300 }
    ]
  } else {
    startBgm('lobby')
    loadLobbyData()
    // 连接 WebSocket，如果是断线重连，会自动收到 reconnected 事件并触发上面的 watch 跳转
    connect()
  }
})

onUnmounted(() => {
  stopMatchTimer()
  stopBgm()
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
  playSound('btnClick')
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
  playSound('btnClick')
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
  openFeatureNotice('510K玩法', '510K玩法正在加急开发中，敬请期待！')
}
</script>

<template>
  <div class="game-table lobby-modern-container">
    <template v-if="!showReadyPage">
      <!-- 顶部状态栏 -->
      <header class="lobby-top-bar">
        <div class="top-left">
          <button class="btn-back" type="button" aria-label="退出登录" @click="handleLogout">
            <div class="btn-back-circle">
              <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                <path d="M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z"/>
              </svg>
            </div>
            <span class="back-text">退出</span>
          </button>
          <button class="info-help-btn" type="button" @click="handleHelpClick">?</button>
        </div>

        <div class="top-center-assets">
          <!-- 欢乐豆 -->
          <div class="asset-pill gold-beans" @click="openEditBeansModal" style="cursor: pointer;">
            <span class="asset-icon">
              <svg class="asset-svg" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <defs>
                  <linearGradient id="gold_bean_grad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stop-color="#fff176" />
                    <stop offset="50%" stop-color="#fbc02d" />
                    <stop offset="100%" stop-color="#f57f17" />
                  </linearGradient>
                </defs>
                <circle cx="12" cy="12" r="10" fill="url(#gold_bean_grad)" stroke="#ffe082" stroke-width="1.5" />
                <circle cx="12" cy="12" r="7" fill="none" stroke="#f57c00" stroke-width="1" stroke-dasharray="2 1" />
                <rect x="10" y="7" width="4" height="10" rx="1" fill="#fff59d" stroke="#f57c00" stroke-width="0.8" />
              </svg>
            </span>
            <span class="asset-amount">{{ formatBeans(playerStore.beans) }}</span>
            <span class="asset-plus">+</span>
          </div>
          <!-- 钻石 -->
          <div class="asset-pill diamonds" @click="handleDiamondClick" style="cursor: pointer;">
            <span class="asset-icon">
              <svg class="asset-svg" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <defs>
                  <linearGradient id="diamond_grad" x1="0" y1="0" x2="1" y2="1">
                    <stop offset="0%" stop-color="#e0f7fa" />
                    <stop offset="40%" stop-color="#4dd0e1" />
                    <stop offset="100%" stop-color="#006064" />
                  </linearGradient>
                </defs>
                <polygon points="12,2 20,8 17,20 7,20 4,8" fill="url(#diamond_grad)" stroke="#b2ebf2" stroke-width="1.5" />
                <line x1="12" y1="2" x2="12" y2="20" stroke="rgba(255,255,255,0.4)" stroke-width="0.8" />
                <line x1="4" y1="8" x2="20" y2="8" stroke="rgba(255,255,255,0.3)" stroke-width="0.8" />
              </svg>
            </span>
            <span class="asset-amount">0</span>
            <span class="asset-plus">+</span>
          </div>
        </div>

        <div class="top-right-leaderboard" style="display: flex; gap: 12px; align-items: center;">
          <button class="btn-leaderboard-toggle" @click="showLeaderboard = !showLeaderboard">
            <span class="trophy-mini">🏆</span> 排行榜
          </button>
          <button class="btn-leaderboard-toggle" @click="showSettings = true; playSound('btnClick')" style="background: linear-gradient(135deg, #90caf9 0%, #1e88e5 100%); border-color: #bbdefb; color: #ffffff; text-shadow: 0 1px 1px rgba(0,0,0,0.35);">
            ⚙️ 设置
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
            @click="handleSidebarClick(item)"
          >
            <span v-if="item.active" class="sidebar-star-icon">
              <svg viewBox="0 0 24 24" width="16" height="16" fill="#ffd700">
                <path d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"/>
              </svg>
            </span>
            <span class="item-text">{{ item.name }}</span>
            <!-- 角标 -->
            <span v-if="item.badge" class="item-badge" :class="item.badge === '热门' ? 'hot' : 'recent'">
              {{ item.badge === '最近' ? '精选' : item.badge }}
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
              :class="[tier.colorClass, { selected: selectedBaseScore === tier.baseScore, 'recommend-card': tier.id === 'primary' }]"
              @click="selectTier(tier)"
            >
              <!-- 推荐角标 -->
              <div class="recommend-badge" v-if="tier.id === 'primary'">推荐</div>

              <!-- 选中高亮光环 -->
              <div class="selected-glow" v-if="selectedBaseScore === tier.baseScore"></div>

              <!-- 内嵌高自适应矢量拟物 3D SVG 背景图标 -->
              <!-- 1. 新手场麻将發 -->
              <div class="card-bg-icon" v-if="tier.id === 'novice'">
                <svg viewBox="0 0 100 130" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <defs>
                    <linearGradient id="mahjong_front" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stop-color="#ffffff" />
                      <stop offset="85%" stop-color="#f0f4f8" />
                      <stop offset="100%" stop-color="#d9e2ec" />
                    </linearGradient>
                    <linearGradient id="mahjong_back" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stop-color="#00b0ff" />
                      <stop offset="40%" stop-color="#00e676" />
                      <stop offset="100%" stop-color="#00796b" />
                    </linearGradient>
                    <linearGradient id="fa_grad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stop-color="#00e676" />
                      <stop offset="100%" stop-color="#1b5e20" />
                    </linearGradient>
                    <filter id="fa_shadow" x="-10%" y="-10%" width="120%" height="120%">
                      <feDropShadow dx="1" dy="2" stdDeviation="1.5" flood-color="#000000" flood-opacity="0.5" />
                    </filter>
                  </defs>
                  <rect x="7" y="11" width="76" height="106" rx="10" fill="rgba(0,0,0,0.4)" />
                  <rect x="7" y="11" width="76" height="102" rx="10" fill="url(#mahjong_back)" />
                  <rect x="7" y="5" width="76" height="96" rx="8" fill="url(#mahjong_front)" stroke="#b0bec5" stroke-width="1" />
                  <text x="45" y="70" font-size="44" font-weight="900" fill="url(#fa_grad)" filter="url(#fa_shadow)" font-family="Microsoft YaHei, SimHei, sans-serif" text-anchor="middle">發</text>
                </svg>
              </div>

              <!-- 2. 初级场德州筹码 -->
              <div class="card-bg-icon" v-if="tier.id === 'primary'">
                <svg viewBox="0 0 120 120" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <defs>
                    <radialGradient id="chip_body" cx="50%" cy="50%" r="50%" fx="30%" fy="30%">
                      <stop offset="0%" stop-color="#4fc3f7" />
                      <stop offset="70%" stop-color="#0288d1" />
                      <stop offset="100%" stop-color="#01579b" />
                    </radialGradient>
                    <linearGradient id="chip_inner" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stop-color="#0288d1" />
                      <stop offset="100%" stop-color="#0d47a1" />
                    </linearGradient>
                    <linearGradient id="chip_spade" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stop-color="#ffee58" />
                      <stop offset="100%" stop-color="#ff8f00" />
                    </linearGradient>
                    <filter id="chip_shadow">
                      <feDropShadow dx="2" dy="5" stdDeviation="3" flood-color="#000000" flood-opacity="0.6" />
                    </filter>
                  </defs>
                  <circle cx="60" cy="60" r="48" fill="url(#chip_body)" filter="url(#chip_shadow)" stroke="#ffffff" stroke-width="2" />
                  <circle cx="60" cy="60" r="44" fill="none" stroke="#ffffff" stroke-width="6" stroke-dasharray="14 10" opacity="0.85" />
                  <circle cx="60" cy="60" r="44" fill="none" stroke="#00e5ff" stroke-width="4" stroke-dasharray="8 16" />
                  <circle cx="60" cy="60" r="32" fill="url(#chip_inner)" stroke="#ffffff" stroke-width="1.5" />
                  <path d="M 60 36 C 60 28 43 28 43 43 C 43 54 60 64 60 74 C 60 64 77 54 77 43 C 77 28 60 28 60 36 Z" fill="url(#chip_spade)" filter="url(#fa_shadow)" />
                  <path d="M 60 68 L 48 83 L 72 83 Z" fill="url(#chip_spade)" />
                </svg>
              </div>

              <!-- 3. 普通场黑桃紫水晶 -->
              <div class="card-bg-icon" v-if="tier.id === 'common'">
                <svg viewBox="0 0 120 120" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <defs>
                    <linearGradient id="crystal_grad1" x1="0" y1="0" x2="1" y2="1">
                      <stop offset="0%" stop-color="#e040fb" />
                      <stop offset="100%" stop-color="#4a148c" />
                    </linearGradient>
                    <linearGradient id="crystal_grad2" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stop-color="#ea80fc" />
                      <stop offset="100%" stop-color="#ab47bc" />
                    </linearGradient>
                    <linearGradient id="crystal_grad3" x1="1" y1="0" x2="0" y2="1">
                      <stop offset="0%" stop-color="#ba68c8" />
                      <stop offset="100%" stop-color="#311b92" />
                    </linearGradient>
                    <filter id="crystal_shadow">
                      <feDropShadow dx="3" dy="6" stdDeviation="4" flood-color="#000000" flood-opacity="0.65" />
                    </filter>
                  </defs>
                  <g filter="url(#crystal_shadow)">
                    <polygon points="60,15 95,45 60,75 25,45" fill="url(#crystal_grad2)" />
                    <polygon points="60,75 95,45 95,85 60,110" fill="url(#crystal_grad3)" />
                    <polygon points="60,75 25,45 25,85 60,110" fill="url(#crystal_grad1)" />
                    <polyline points="25,45 60,75 95,45" fill="none" stroke="#f3e5f5" stroke-width="2" opacity="0.7" />
                    <line x1="60" y1="75" x2="60" y2="110" stroke="#f3e5f5" stroke-width="2.5" opacity="0.8" />
                    <path d="M 60 40 C 60 33 46 33 46 45 C 46 54 60 62 60 70 C 60 62 74 54 74 45 C 74 33 60 33 60 40 Z" fill="#ffffff" opacity="0.3" />
                  </g>
                </svg>
              </div>

              <!-- 4. 中级场紫色星杯 -->
              <div class="card-bg-icon" v-if="tier.id === 'middle'">
                <svg viewBox="0 0 120 120" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <defs>
                    <linearGradient id="gold_cup" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stop-color="#fff59d" />
                      <stop offset="35%" stop-color="#fbc02d" />
                      <stop offset="100%" stop-color="#f57f17" />
                    </linearGradient>
                    <linearGradient id="purple_metal" x1="0" y1="0" x2="1" y2="1">
                      <stop offset="0%" stop-color="#e040fb" />
                      <stop offset="50%" stop-color="#7c4dff" />
                      <stop offset="100%" stop-color="#3f51b5" />
                    </linearGradient>
                    <filter id="cup_shadow">
                      <feDropShadow dx="2" dy="5" stdDeviation="3.5" flood-color="#000000" flood-opacity="0.6" />
                    </filter>
                  </defs>
                  <g filter="url(#cup_shadow)">
                    <rect x="40" y="90" width="40" height="12" rx="4" fill="url(#gold_cup)" stroke="#ffe082" stroke-width="1.2" />
                    <path d="M 46 90 L 52 74 L 68 74 L 74 90 Z" fill="url(#gold_cup)" />
                    <path d="M 32 30 C 32 63 45 74 60 74 C 75 74 88 63 88 30 Z" fill="url(#purple_metal)" stroke="url(#gold_cup)" stroke-width="2.5" />
                    <path d="M 32 36 C 18 36 18 56 32 56" stroke="url(#gold_cup)" stroke-width="5" stroke-linecap="round" fill="none" />
                    <path d="M 88 36 C 102 36 102 56 88 56" stroke="url(#gold_cup)" stroke-width="5" stroke-linecap="round" fill="none" />
                    <ellipse cx="60" cy="30" rx="28" ry="6" fill="url(#gold_cup)" />
                    <polygon points="60,35 63,44 72,44 65,50 67,59 60,53 53,59 55,50 48,44 57,44" fill="#ffd54f" stroke="#ff8f00" stroke-width="1" />
                  </g>
                </svg>
              </div>

              <!-- 5. 高级场红宝金皇冠 -->
              <div class="card-bg-icon" v-if="tier.id === 'advanced'">
                <svg viewBox="0 0 120 120" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <defs>
                    <linearGradient id="crown_gold" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stop-color="#ffffff" />
                      <stop offset="25%" stop-color="#ffe082" />
                      <stop offset="65%" stop-color="#ffb300" />
                      <stop offset="100%" stop-color="#ff6f00" />
                    </linearGradient>
                    <radialGradient id="ruby_grad" cx="50%" cy="50%" r="50%">
                      <stop offset="0%" stop-color="#ff5252" />
                      <stop offset="70%" stop-color="#e53935" />
                      <stop offset="100%" stop-color="#b71c1c" />
                    </radialGradient>
                    <filter id="crown_shadow">
                      <feDropShadow dx="3" dy="6" stdDeviation="4" flood-color="#000000" flood-opacity="0.65" />
                    </filter>
                  </defs>
                  <g filter="url(#crown_shadow)">
                    <path d="M 24 80 C 24 60 96 60 96 80 Z" fill="#b71c1c" opacity="0.85" />
                    <path d="M 22 80 L 16 38 L 40 58 L 60 22 L 80 58 L 104 38 L 98 80 Z" fill="url(#crown_gold)" stroke="#fff8e1" stroke-width="1.5" />
                    <ellipse cx="60" cy="80" rx="38" ry="8" fill="url(#crown_gold)" stroke="#fff8e1" stroke-width="1.5" />
                    <circle cx="16" cy="38" r="5" fill="#ffffff" />
                    <circle cx="40" cy="58" r="4.5" fill="#ffffff" />
                    <circle cx="60" cy="22" r="6" fill="#ffffff" />
                    <circle cx="80" cy="58" r="4.5" fill="#ffffff" />
                    <circle cx="104" cy="38" r="5" fill="#ffffff" />
                    <polygon points="60,62 68,72 60,82 52,72" fill="url(#ruby_grad)" stroke="#ffe082" stroke-width="1" />
                    <circle cx="34" cy="78" r="3" fill="url(#ruby_grad)" />
                    <circle cx="86" cy="78" r="3" fill="url(#ruby_grad)" />
                  </g>
                </svg>
              </div>

              <!-- 6. 顶级场黄金翼勋章 -->
              <div class="card-bg-icon" v-if="tier.id === 'top'">
                <svg viewBox="0 0 120 120" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <defs>
                    <linearGradient id="wing_gold" x1="0" y1="0" x2="1" y2="1">
                      <stop offset="0%" stop-color="#fff9c4" />
                      <stop offset="50%" stop-color="#fbc02d" />
                      <stop offset="100%" stop-color="#f57f17" />
                    </linearGradient>
                    <radialGradient id="pink_gem" cx="50%" cy="50%" r="50%">
                      <stop offset="0%" stop-color="#ff80ab" />
                      <stop offset="70%" stop-color="#ff4081" />
                      <stop offset="100%" stop-color="#c51162" />
                    </radialGradient>
                    <filter id="medal_shadow">
                      <feDropShadow dx="3" dy="6" stdDeviation="4.5" flood-color="#000000" flood-opacity="0.7" />
                    </filter>
                  </defs>
                  <g filter="url(#medal_shadow)">
                    <path d="M 20 40 C 5 45 10 80 42 88 M 100 40 C 115 45 110 80 78 88" stroke="url(#wing_gold)" stroke-width="8" stroke-linecap="round" fill="none" />
                    <path d="M 28 48 C 15 52 20 82 42 88 M 92 48 C 105 52 100 82 78 88" stroke="url(#wing_gold)" stroke-width="5" stroke-linecap="round" fill="none" />
                    <polygon points="60,40 76,52 70,72 50,72 44,52" fill="url(#pink_gem)" stroke="#ffffff" stroke-width="2" />
                    <circle cx="60" cy="59" r="30" fill="none" stroke="url(#wing_gold)" stroke-width="3" stroke-dasharray="6 4" />
                    <circle cx="60" cy="59" r="25" fill="none" stroke="#ffffff" stroke-width="1.5" opacity="0.5" />
                    <path d="M 50 30 L 46 20 L 54 24 L 60 16 L 66 24 L 74 20 L 70 30 Z" fill="url(#wing_gold)" stroke="#ffffff" stroke-width="1" />
                  </g>
                </svg>
              </div>

              <div class="card-inner">
                <div class="card-header-row">
                  <h3 class="tier-name">{{ tier.name }}</h3>
                </div>

                <div class="card-body-row">
                  <div class="tier-score-row">
                    <span class="score-tag">底分</span>
                    <span class="score-number">{{ tier.baseScore }}</span>
                  </div>
                </div>

                <div class="card-meta-row">
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
        <div class="bottom-user-card" @click="handleProfileClick">
          <div class="user-avatar-wrap">
            <img
              v-if="playerStore.avatarUrl && !avatarImageFailed"
              class="avatar-image"
              :src="playerStore.avatarUrl"
              alt="玩家头像"
              @error="handleAvatarImageError"
            />
            <span v-else class="avatar-emoji">👤</span>
          </div>
          <div class="user-meta">
            <div class="user-name-row">
              <span class="username truncate">{{ playerStore.nickname }}</span>
              <span class="title-badge">
                {{ playerStore.rankTitle }}
              </span>
            </div>
            <!-- 星星等级动态自适应渲染 -->
            <div class="stars-row">
              <template v-if="playerStore.rankId < 36">
                <!-- 循环渲染满星长度 -->
                <span 
                  v-for="index in getRankMaxStars(playerStore.rankId)" 
                  :key="index" 
                  class="star" 
                  :class="{ active: index <= playerStore.stars }"
                >
                  ★
                </span>
                <span class="star-text">{{ playerStore.stars }}/{{ getRankMaxStars(playerStore.rankId) }}</span>
              </template>
              <template v-else>
                <!-- 至尊展示为总星星数 -->
                <span class="star active">★</span>
                <span class="star-text">至尊星星: {{ playerStore.stars }}</span>
              </template>
            </div>
          </div>
        </div>

        <!-- 底部中间装饰箭头 -->
        <div class="bottom-center-arrow">
          <svg viewBox="0 0 24 24" width="24" height="24" fill="currentColor">
            <path d="M7.41 15.41L12 10.83l4.59 4.58L18 14l-6-6-6 6z"/>
          </svg>
        </div>

        <!-- 操作按钮区 -->
        <div class="bottom-actions-row">
          <!-- 好友房 -->
          <div class="action-btn-wrapper">
            <button class="btn-green-room" @click="handleFriendRoomClick">
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
            <div class="btn-back-circle">
              <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                <path d="M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z"/>
              </svg>
            </div>
            <span class="back-text">返回</span>
          </button>
        </div>
        <div class="top-right-hud" style="margin-left: auto; display: flex; gap: 12px; align-items: center;">
          <button class="btn-hud-tool" @click="showReadyPage = false">换桌</button>
          <button class="btn-leaderboard-toggle" @click="showSettings = true; playSound('btnClick')" style="background: linear-gradient(135deg, #90caf9 0%, #1e88e5 100%); border-color: #bbdefb; color: #ffffff; text-shadow: 0 1px 1px rgba(0,0,0,0.35);">
            ⚙️ 设置
          </button>
          <button class="info-help-btn" type="button" @click="handleHelpClick">?</button>
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
        <div class="bottom-user-card" @click="handleProfileClick">
          <div class="user-avatar-wrap">
            <img
              v-if="playerStore.avatarUrl && !avatarImageFailed"
              class="avatar-image"
              :src="playerStore.avatarUrl"
              alt="玩家头像"
              @error="handleAvatarImageError"
            />
            <span v-else class="avatar-emoji">👤</span>
          </div>
          <div class="user-meta">
            <div class="user-name-row">
              <span class="username truncate">{{ playerStore.nickname }}</span>
              <span class="title-badge">
                {{ playerStore.rankTitle }}
              </span>
            </div>
            <!-- 星星等级动态自适应渲染 -->
            <div class="stars-row">
              <template v-if="playerStore.rankId < 36">
                <!-- 循环渲染满星长度 -->
                <span 
                  v-for="index in getRankMaxStars(playerStore.rankId)" 
                  :key="index" 
                  class="star" 
                  :class="{ active: index <= playerStore.stars }"
                >
                  ★
                </span>
                <span class="star-text">{{ playerStore.stars }}/{{ getRankMaxStars(playerStore.rankId) }}</span>
              </template>
              <template v-else>
                <!-- 至尊展示为总星星数 -->
                <span class="star active">★</span>
                <span class="star-text">至尊星星: {{ playerStore.stars }}</span>
              </template>
            </div>
          </div>
        </div>

        <div class="ready-bottom-assets">
          <div class="asset-pill gold-beans" @click="openEditBeansModal" style="margin-top: 0; box-shadow: 0 2px 8px rgba(0,0,0,0.3); cursor: pointer;">
            <span class="asset-icon">
              <svg class="asset-svg" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <defs>
                  <linearGradient id="gold_bean_grad_ready" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stop-color="#fff176" />
                    <stop offset="50%" stop-color="#fbc02d" />
                    <stop offset="100%" stop-color="#f57f17" />
                  </linearGradient>
                </defs>
                <circle cx="12" cy="12" r="10" fill="url(#gold_bean_grad_ready)" stroke="#ffe082" stroke-width="1.5" />
                <circle cx="12" cy="12" r="7" fill="none" stroke="#f57c00" stroke-width="1" stroke-dasharray="2 1" />
                <rect x="10" y="7" width="4" height="10" rx="1" fill="#fff59d" stroke="#f57c00" stroke-width="0.8" />
              </svg>
            </span>
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
            <span class="name-col truncate" style="display: flex; align-items: center; gap: 6px;">
              {{ item.nickname }}
              <span class="rank-title-badge" style="font-size: 0.75rem; background: rgba(255,255,255,0.15); padding: 2px 6px; border-radius: 4px; color: #ffd700;">
                {{ item.rank_title || '包身工IV' }}
              </span>
            </span>
            <span class="beans-col yellow-text">{{ formatBeans(item.beans) }}</span>
            <span class="rate-col">{{ (item.win_rate * 100).toFixed(0) }}%</span>
          </div>
          <div v-if="leaderboard.length === 0" class="no-data">
            暂无排行榜数据
          </div>
        </div>
      </div>
    </div>

    <div v-if="showProfileModal" class="modal-overlay" @click.self="showProfileModal = false">
      <div class="glass-panel profile-modal">
        <div class="modal-header">
          <h3>个人资料</h3>
          <button class="btn-close" type="button" @click="showProfileModal = false">×</button>
        </div>

        <div class="profile-summary">
          <div class="profile-avatar-preview">
            <img
              v-if="playerStore.avatarUrl && !avatarImageFailed"
              class="profile-avatar-image"
              :src="playerStore.avatarUrl"
              alt="玩家头像"
              @error="handleAvatarImageError"
            />
            <span v-else class="profile-avatar-placeholder">👤</span>
          </div>
          <div class="profile-main-info">
            <div class="profile-nickname">{{ playerStore.nickname }}</div>
            <div class="profile-account">账号：{{ playerStore.username || '未绑定' }}</div>
            <div class="profile-player-id">ID：{{ playerStore.playerId }}</div>
          </div>
        </div>

        <div class="profile-stats-grid">
          <div class="profile-stat"><span>欢乐豆</span><strong>{{ formatBeans(playerStore.beans) }}</strong></div>
          <div class="profile-stat"><span>总局数</span><strong>{{ playerStore.totalGames }}</strong></div>
          <div class="profile-stat"><span>胜率</span><strong>{{ (playerStore.winRate * 100).toFixed(0) }}%</strong></div>
          <div class="profile-stat"><span>段位</span><strong>{{ playerStore.rankTitle }}</strong></div>
        </div>

        <label class="profile-avatar-field">
          <span>头像图片 URL</span>
          <input
            v-model="avatarInputValue"
            class="profile-avatar-input"
            type="url"
            placeholder="https://example.com/avatar.png"
          />
        </label>
        <p v-if="avatarSaveError" class="profile-error">{{ avatarSaveError }}</p>

        <div class="profile-actions">
          <button class="btn-leaderboard-toggle profile-secondary-action" type="button" @click="handleClearAvatar">
            清空头像
          </button>
          <button class="btn-leaderboard-toggle" type="button" @click="handleSaveAvatar">
            保存头像
          </button>
        </div>
      </div>
    </div>

    <!-- 欢乐豆修改弹窗 -->
    <div v-if="showEditBeansModal" class="modal-overlay" @click.self="showEditBeansModal = false">
      <div class="glass-panel leaderboard-modal" style="max-width: 400px; padding: 24px;">
        <div class="modal-header" style="margin-bottom: 20px;">
          <h3>🪙 修改资产与排位</h3>
          <button class="btn-close" @click="showEditBeansModal = false">×</button>
        </div>
        <div class="modal-body" style="display: flex; flex-direction: column; gap: 16px; max-height: 50vh; overflow-y: auto;">
          <div style="display: flex; flex-direction: column; gap: 8px;">
            <label style="color: #ccc; font-size: 0.9rem; text-align: left;">请输入新的欢乐豆数量 (不少于 0)：</label>
            <input
              v-model.number="inputBeansValue"
              type="number"
              min="0"
              style="background: rgba(0,0,0,0.5); border: 1.5px solid rgba(255,255,255,0.2); border-radius: 8px; padding: 10px; color: #fff; font-size: 1.2rem; font-weight: bold; width: 100%; box-sizing: border-box;"
            />
            <p v-if="editBeansError" style="color: #f44336; margin: 0; font-size: 0.85rem; text-align: left;">{{ editBeansError }}</p>
          </div>
          
          <hr style="border: 0; border-top: 1px solid rgba(255,255,255,0.15); margin: 8px 0;" />

          <!-- 段位设定 -->
          <div style="display: flex; flex-direction: column; gap: 12px;">
            <h4 style="color: #ffd700; margin: 0; text-align: left;">🏆 定制段位信息</h4>
            
            <div style="display: flex; flex-direction: column; gap: 6px;">
              <label style="color: #ccc; font-size: 0.85rem; text-align: left;">头衔名称：</label>
              <select 
                v-model="inputRankId" 
                style="background: rgba(0,0,0,0.8); border: 1.5px solid rgba(255,255,255,0.25); border-radius: 8px; padding: 10px; color: #fff; font-size: 1rem; width: 100%; box-sizing: border-box;"
              >
                <option v-for="(name, idx) in RANK_NAMES" :key="idx" :value="idx" v-show="idx > 0">
                  {{ idx }}. {{ name }} (门槛: {{ getRankMaxStars(idx) }}星)
                </option>
              </select>
            </div>

            <div style="display: flex; gap: 12px;" v-show="inputRankId < 36">
              <div style="flex: 1; display: flex; flex-direction: column; gap: 6px;">
                <label style="color: #ccc; font-size: 0.85rem; text-align: left;">级别后缀：</label>
                <select 
                  v-model="inputSubRank" 
                  style="background: rgba(0,0,0,0.8); border: 1.5px solid rgba(255,255,255,0.25); border-radius: 8px; padding: 10px; color: #fff; font-size: 1rem; width: 100%;"
                >
                  <option :value="4">IV 级</option>
                  <option :value="3">III 级</option>
                  <option :value="2">II 级</option>
                  <option :value="1">I 级</option>
                </select>
              </div>
              <div style="flex: 1; display: flex; flex-direction: column; gap: 6px;">
                <label style="color: #ccc; font-size: 0.85rem; text-align: left;">当前星星：</label>
                <input 
                  v-model.number="inputStars" 
                  type="number" 
                  min="0" 
                  :max="getRankMaxStars(inputRankId)"
                  style="background: rgba(0,0,0,0.8); border: 1.5px solid rgba(255,255,255,0.25); border-radius: 8px; padding: 10px; color: #fff; font-size: 1rem; width: 100%; box-sizing: border-box;"
                />
              </div>
            </div>
            
            <div style="display: flex; flex-direction: column; gap: 6px;" v-show="inputRankId == 36">
              <label style="color: #ccc; font-size: 0.85rem; text-align: left;">至尊星星数：</label>
              <input 
                v-model.number="inputStars" 
                type="number" 
                min="0"
                style="background: rgba(0,0,0,0.8); border: 1.5px solid rgba(255,255,255,0.25); border-radius: 8px; padding: 10px; color: #fff; font-size: 1rem; width: 100%; box-sizing: border-box;"
              />
            </div>
            
            <p v-if="editRankError" style="color: #f44336; margin: 0; font-size: 0.85rem; text-align: left;">{{ editRankError }}</p>
          </div>
        </div>
        <div class="modal-footer" style="display: flex; justify-content: flex-end; gap: 12px; margin-top: 24px;">
          <button class="btn-leaderboard-toggle" @click="showEditBeansModal = false" style="background: rgba(255,255,255,0.1); color: #fff; border: 1px solid rgba(255,255,255,0.2);">取消</button>
          <button class="btn-leaderboard-toggle" @click="handleSaveBeans">确认保存</button>
        </div>
      </div>
    </div>

    <!-- 匹配状态全屏遮罩 -->
    <div v-if="featureNotice.visible" class="modal-overlay" @click.self="closeFeatureNotice">
      <div class="glass-panel feature-notice-modal">
        <div class="modal-header">
          <h3>{{ featureNotice.title }}</h3>
          <button class="btn-close" @click="closeFeatureNotice">×</button>
        </div>
        <p class="feature-notice-text">{{ featureNotice.message }}</p>
        <button class="btn-leaderboard-toggle feature-notice-confirm" @click="closeFeatureNotice">
          知道了
        </button>
      </div>
    </div>

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

    <!-- 原版风格设置弹窗 -->
    <SettingsModal :show="showSettings" @close="showSettings = false" />
  </div>
</template>

<style scoped>
.lobby-modern-container {
  display: flex;
  flex-direction: column;
  height: 100vh;
  justify-content: space-between;
  /* 极度深邃、具有丰富光影空间感的游戏大厅极光背景 */
  background: #020b1e;
  background-image: 
    radial-gradient(circle at 50% 25%, rgba(30, 136, 229, 0.55) 0%, transparent 60%),
    radial-gradient(circle at 10% 20%, rgba(13, 71, 161, 0.45) 0%, transparent 55%),
    radial-gradient(circle at 90% 80%, rgba(26, 35, 126, 0.35) 0%, transparent 50%),
    linear-gradient(to bottom, #001233 0%, #000814 100%);
  overflow: hidden;
  padding: 0;
  box-sizing: border-box;
  position: relative;
}

/* 底部起伏微光带 */
.lobby-modern-container::before {
  content: "";
  position: absolute;
  bottom: 0;
  left: -10%;
  width: 120%;
  height: 280px;
  background: radial-gradient(ellipse at bottom, rgba(33, 150, 243, 0.28) 0%, rgba(21, 101, 192, 0.08) 55%, rgba(0, 0, 0, 0) 80%);
  pointer-events: none;
  z-index: 1;
  filter: blur(10px);
}

/* 顶部状态栏 */
.lobby-top-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 30px;
  background: linear-gradient(to bottom, rgba(0, 0, 0, 0.6) 0%, rgba(0, 0, 0, 0) 100%);
  height: 64px;
  z-index: 10;
  box-sizing: border-box;
}

.top-left {
  display: flex;
  align-items: center;
  gap: 14px;
}

/* 经典返回键 - 圆润药丸型 */
.btn-back {
  background: linear-gradient(180deg, rgba(33, 150, 243, 0.32) 0%, rgba(21, 101, 192, 0.18) 100%);
  border: 1.5px solid rgba(144, 202, 249, 0.6);
  color: #fff;
  padding: 4px 18px 4px 6px;
  font-size: 1.1rem;
  font-weight: 800;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  border-radius: 9999px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.35), inset 0 2px 4px rgba(255,255,255,0.3);
  backdrop-filter: blur(8px);
  transition: all 0.2s cubic-bezier(0.175, 0.885, 0.32, 1.275);
  text-shadow: 0 2px 4px rgba(0,0,0,0.6);
}

.btn-back:hover {
  background: linear-gradient(180deg, rgba(33, 150, 243, 0.48) 0%, rgba(21, 101, 192, 0.28) 100%);
  border-color: rgba(144, 202, 249, 0.85);
  transform: scale(1.05);
  box-shadow: 0 6px 18px rgba(33, 150, 243, 0.5), inset 0 2px 4px rgba(255,255,255,0.4);
}

.btn-back-circle {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.25);
  display: flex;
  justify-content: center;
  align-items: center;
  box-shadow: inset 0 1px 2px rgba(255,255,255,0.35);
}

.back-text {
  letter-spacing: 1.5px;
  text-shadow: 0 1.5px 3px rgba(0,0,0,0.7);
}

.info-help-btn {
  background: rgba(255, 255, 255, 0.12);
  border: 1px solid rgba(255, 255, 255, 0.3);
  color: #ffffff;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: inline-flex;
  justify-content: center;
  align-items: center;
  font-weight: 900;
  font-size: 0.95rem;
  cursor: pointer;
  padding: 0;
  box-shadow: 0 2px 5px rgba(0,0,0,0.25);
  transition: all 0.2s;
}

.info-help-btn:hover {
  background: rgba(255, 255, 255, 0.3);
  transform: scale(1.1);
}

.top-center-assets {
  display: flex;
  gap: 28px; /* 增加间距给探出的金豆留空间 */
}

/* 磨砂资产胶囊 - 3D溢出版 */
.asset-pill {
  border-radius: 24px;
  display: flex;
  align-items: center;
  padding: 5px 6px 5px 22px; /* 增加 padding */
  gap: 8px;
  min-width: 160px; /* 增加宽度 */
  position: relative;
  backdrop-filter: blur(8px);
  box-sizing: border-box;
  transition: transform 0.2s, box-shadow 0.2s;
  overflow: visible; /* 必须溢出以保证 3D 浮雕感 */
}

.asset-pill:hover {
  transform: translateY(-2.5px);
}

.asset-pill.gold-beans {
  background: linear-gradient(180deg, rgba(30, 20, 5, 0.82) 0%, rgba(12, 8, 2, 0.95) 100%);
  border: 1.5px solid rgba(255, 215, 0, 0.45);
  box-shadow: 0 6px 15px rgba(0,0,0,0.5), inset 0 2px 5px rgba(0,0,0,0.65);
}

.asset-pill.diamonds {
  background: linear-gradient(180deg, rgba(8, 24, 40, 0.82) 0%, rgba(3, 10, 18, 0.95) 100%);
  border: 1.5px solid rgba(33, 150, 243, 0.45);
  box-shadow: 0 6px 15px rgba(0,0,0,0.5), inset 0 2px 5px rgba(0,0,0,0.65);
}

.asset-icon {
  width: 32px;
  height: 32px;
  display: flex;
  justify-content: center;
  align-items: center;
  position: absolute;
  left: -14px;  /* 向左大幅度突出 */
  top: -2px;   /* 向上探出 */
  transform: scale(1.38); /* 3D 变大 */
  filter: drop-shadow(0 3px 5px rgba(0,0,0,0.6));
  z-index: 2;
}

.asset-svg {
  width: 100%;
  height: 100%;
  overflow: visible;
}

.asset-amount {
  font-weight: 900;
  font-size: 1.15rem;
  flex: 1;
  margin-left: 8px;
  text-shadow: 0 2px 4px rgba(0,0,0,0.85);
  text-align: left;
}

.gold-beans .asset-amount {
  color: #ffd700;
}

.diamonds .asset-amount {
  color: #90caf9;
}

.asset-plus {
  background: linear-gradient(135deg, #ffee58 0%, #fbc02d 50%, #f57f17 100%);
  color: #3e2723;
  font-weight: 900;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  display: flex;
  justify-content: center;
  align-items: center;
  font-size: 1rem;
  cursor: pointer;
  box-shadow: 0 2px 5px rgba(0,0,0,0.4), inset 0 1.5px 1.5px rgba(255,255,255,0.6);
  border: 1px solid #fff59d;
  transition: all 0.15s;
  z-index: 3;
}

.asset-plus:hover {
  transform: scale(1.15) rotate(90deg);
  box-shadow: 0 3px 8px rgba(0,0,0,0.5), 0 0 6px rgba(255,215,0,0.6);
}

.btn-leaderboard-toggle {
  background: linear-gradient(135deg, #ffca28 0%, #ff8f00 100%);
  color: #3e2723;
  border: 1.5px solid #ffe082;
  padding: 6px 18px;
  border-radius: 16px;
  font-weight: 900;
  font-size: 0.95rem;
  cursor: pointer;
  box-shadow: 0 4px 10px rgba(0,0,0,0.35), inset 0 2px 3px rgba(255,255,255,0.3);
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  gap: 6px;
  text-shadow: 0 1px 1px rgba(255,255,255,0.25);
}

.btn-leaderboard-toggle:hover {
  transform: translateY(-2px) scale(1.03);
  box-shadow: 0 6px 15px rgba(255, 143, 0, 0.4);
}

.trophy-mini {
  font-size: 1.1rem;
}

/* 核心布局 */
.lobby-core-layout {
  display: flex;
  flex: 1;
  width: 100%;
  height: calc(100vh - 144px);
  z-index: 2;
}

/* 左侧侧边栏 */
.lobby-sidebar {
  width: 180px;
  display: flex;
  flex-direction: column;
  padding: 20px 0;
  background: linear-gradient(to right, rgba(0, 0, 0, 0.45) 0%, rgba(0, 0, 0, 0) 100%);
  gap: 12px;
}

.sidebar-item {
  position: relative;
  padding: 12px 18px 12px 24px;
  cursor: pointer;
  transition: all 0.25s cubic-bezier(0.175, 0.885, 0.32, 1.275);
  display: flex;
  align-items: center;
  border-radius: 0 30px 30px 0;
  margin-right: 14px;
  border: 1px solid transparent;
  gap: 8px;
}

.sidebar-item .item-text {
  font-size: 1.05rem;
  font-weight: 800;
  color: rgba(255, 255, 255, 0.6);
  text-shadow: 0 2px 4px rgba(0,0,0,0.6);
  transition: color 0.2s;
}

.sidebar-item:hover {
  background: rgba(255, 255, 255, 0.05);
  transform: translateX(4px);
}

.sidebar-item:hover .item-text {
  color: #fff;
}

/* 经典激活态 - 3D 渐变高光 */
.sidebar-item.active {
  background: linear-gradient(180deg, #ffca28 0%, #ff8f00 45%, #e65100 100%);
  border: 1.5px solid #ffe082;
  border-left: none;
  box-shadow: 0 6px 15px rgba(0, 0, 0, 0.45), 
              inset 0 2px 3px rgba(255, 255, 255, 0.5),
              0 0 10px rgba(255, 143, 0, 0.35);
  width: calc(100% - 10px); /* 宽度大幅拉伸，向右完整贴合 */
}

.sidebar-item.active:hover {
  background: linear-gradient(180deg, #ffd54f 0%, #ffa000 45%, #f57c00 100%);
}

.sidebar-item.active .item-text {
  color: #2e1c0c;
  font-weight: 900;
  text-shadow: 0 1px 1px rgba(255,255,255,0.35);
}

.sidebar-star-icon {
  display: flex;
  align-items: center;
  filter: drop-shadow(0 1px 2px rgba(0,0,0,0.5));
  animation: pulseGlow 1.5s infinite ease-in-out;
}

@keyframes pulseGlow {
  0%, 100% { transform: scale(1); filter: drop-shadow(0 1px 2px rgba(0,0,0,0.5)); }
  50% { transform: scale(1.15); filter: drop-shadow(0 1px 5px rgba(255,215,0,0.7)); }
}

.item-badge {
  position: absolute;
  top: -5px;
  right: 6px;
  font-size: 0.65rem;
  font-weight: 900;
  padding: 2px 7px;
  border-radius: 10px 10px 10px 0;
  color: #fff;
  box-shadow: 0 3px 6px rgba(0,0,0,0.35);
  transform: scale(0.85);
}

.item-badge.hot {
  background: linear-gradient(135deg, #ff1744 0%, #d50000 100%);
  border: 1px solid #ff8a80;
}

.item-badge.recent {
  background: linear-gradient(135deg, #ff6d00 0%, #dd2c00 100%);
  border: 1px solid #ffd180;
}

/* 中部场次区 */
.lobby-grid-main {
  flex: 1;
  padding: 15px 30px;
  overflow-y: auto;
  display: flex;
  align-items: center;
  z-index: 2;
}

.grid-container {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 26px;
  width: 100%;
}

.tier-card {
  position: relative;
  border-radius: 24px;
  cursor: pointer;
  aspect-ratio: 1.55 / 1;
  transition: all 0.28s cubic-bezier(0.175, 0.885, 0.32, 1.275);
  overflow: hidden; /* 切割倾斜缎带 */
  box-shadow: 0 10px 30px rgba(0,0,0,0.55), inset 0 1.5px 2px rgba(255,255,255,0.18);
  border: 2px solid rgba(255,255,255,0.12);
  box-sizing: border-box;
}

/* 卡片底部亮色微波起伏底纹 */
.tier-card::after {
  content: "";
  position: absolute;
  bottom: -45px;
  left: -10%;
  width: 120%;
  height: 90px;
  background: radial-gradient(ellipse at center, rgba(255, 255, 255, 0.22) 0%, rgba(255, 255, 255, 0.03) 60%, transparent 80%);
  filter: blur(5px);
  pointer-events: none;
  z-index: 1;
}

.tier-card:hover {
  transform: translateY(-8px) scale(1.035);
  box-shadow: 0 18px 40px rgba(0, 0, 0, 0.7), inset 0 2px 3px rgba(255,255,255,0.28);
  border-color: rgba(255, 255, 255, 0.35);
}

.tier-card.selected {
  border-color: #ffd700;
  box-shadow: 0 0 25px rgba(255, 215, 0, 0.65), inset 0 2px 2px rgba(255,255,255,0.3);
}

/* 初级推荐场金色高发光边框 */
.recommend-card {
  border: 2.5px solid #ffc107;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.55), 
              0 0 22px rgba(255, 193, 7, 0.45),
              inset 0 1.5px 2px rgba(255,255,255,0.25);
}

.recommend-card:hover {
  box-shadow: 0 18px 45px rgba(0, 0, 0, 0.7), 
              0 0 32px rgba(255, 193, 7, 0.65);
}

/* 右上角倾斜缎带推荐标 */
.recommend-badge {
  position: absolute;
  top: 12px;
  right: -26px;
  background: linear-gradient(135deg, #ffe082 0%, #ffb300 50%, #ff8f00 100%);
  color: #4e342e;
  font-size: 0.72rem;
  font-weight: 900;
  padding: 3px 28px;
  transform: rotate(45deg);
  box-shadow: 0 2px 6px rgba(0,0,0,0.4);
  z-index: 3;
  letter-spacing: 1px;
  text-shadow: 0 1px 0 rgba(255, 255, 255, 0.4);
  border: 1px solid rgba(255, 255, 255, 0.25);
}

.selected-glow {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  border: 2.5px solid #ffd700;
  border-radius: 22px;
  pointer-events: none;
  box-shadow: inset 0 0 20px rgba(255, 215, 0, 0.6);
  z-index: 3;
}

/* 3D 拟物大背景图标定位 */
.card-bg-icon {
  position: absolute;
  right: 32px;
  top: 40%;
  transform: translateY(-50%) rotate(-6deg);
  width: 120px;
  height: 120px;
  opacity: 0.95;
  pointer-events: none;
  z-index: 1;         /* 至于底层，不遮盖文字 */
  transition: transform 0.35s cubic-bezier(0.175, 0.885, 0.32, 1.275);
  filter: drop-shadow(0 6px 12px rgba(0,0,0,0.5));
}

.tier-card:hover .card-bg-icon {
  transform: translateY(-50%) scale(1.15) rotate(-12deg);
  filter: drop-shadow(0 10px 20px rgba(0,0,0,0.65));
}

.card-inner {
  padding: 20px 22px 14px 22px;
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  box-sizing: border-box;
  position: relative;
  z-index: 2;
  background: rgba(255, 255, 255, 0.02);
}

.tier-name {
  margin: 0;
  font-size: 1.55rem;
  font-style: italic;
  font-weight: 900;
  color: #fff;
  text-shadow: 0 2px 5px rgba(0,0,0,0.8), 0 1px 1px rgba(255,255,255,0.3);
  text-align: left;
  letter-spacing: 1px;
}

.tier-score-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
}

.score-tag {
  background: linear-gradient(135deg, #ff9800 0%, #f57c00 100%);
  color: #fff;
  font-size: 0.72rem;
  font-weight: 900;
  padding: 2px 7px;
  border-radius: 5px;
  box-shadow: 0 1.5px 3px rgba(0,0,0,0.4);
  border: 0.5px solid rgba(255,255,255,0.25);
}

.score-number {
  color: #ffd700;
  font-size: 2.8rem;
  font-weight: 900;
  line-height: 1;
  font-family: 'Arial Black', Impact, sans-serif;
  text-shadow: 0 3px 8px rgba(0,0,0,0.85), 0 0 12px rgba(255, 215, 0, 0.4);
}

/* 卡片底部元数据行 - 移除深色磨砂罩，融合高保真微光 */
.card-meta-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 0 0 0;
  z-index: 5;
  border-top: 1px solid rgba(255, 255, 255, 0.12);
  margin-top: 8px;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 0.82rem;
  font-weight: 800;
  color: rgba(255, 255, 255, 0.9);
  text-shadow: 0 1px 2px rgba(0,0,0,0.8);
}

.meta-icon {
  font-size: 0.92rem;
  filter: drop-shadow(0 1px 2px rgba(0,0,0,0.5));
}

/* 场次卡片配色 */
.tier-novice { background: linear-gradient(135deg, #388e3c 0%, #1b5e20 100%); }
.tier-primary { background: linear-gradient(135deg, #0288d1 0%, #01579b 100%); }
.tier-common { background: linear-gradient(135deg, #3949ab 0%, #1a237e 100%); }
.tier-middle { background: linear-gradient(135deg, #5e35b1 0%, #311b92 100%); }
.tier-advanced { background: linear-gradient(135deg, #d81b60 0%, #880e4f 100%); }
.tier-top { background: linear-gradient(135deg, #8e24aa 0%, #4a148c 100%); }

/* 底部操作栏 */
.lobby-bottom-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 30px;
  background: linear-gradient(to top, rgba(0, 0, 0, 0.8) 0%, rgba(0, 0, 0, 0.35) 50%, rgba(0, 0, 0, 0) 100%);
  height: 84px;
  box-sizing: border-box;
  z-index: 10;
  position: relative;
}

.bottom-user-card {
  display: flex;
  align-items: center;
  gap: 14px;
  cursor: pointer;
  transition: transform 0.2s;
}

.bottom-user-card:hover {
  transform: scale(1.03);
}

.user-avatar-wrap {
  width: 52px;
  height: 52px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.15);
  border: 2px solid #ffd700;
  display: flex;
  justify-content: center;
  align-items: center;
  font-size: 1.9rem;
  box-shadow: 0 0 12px rgba(255, 215, 0, 0.55), inset 0 2px 4px rgba(255,255,255,0.3);
  animation: avatarPulse 2.0s infinite ease-in-out;
}

.avatar-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 50%;
}

@keyframes avatarPulse {
  0%, 100% { box-shadow: 0 0 8px rgba(255, 215, 0, 0.45); }
  50% { box-shadow: 0 0 16px rgba(255, 215, 0, 0.75); }
}

.user-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
  text-align: left;
}

.user-name-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.username {
  font-weight: 900;
  font-size: 1.15rem;
  color: #fff;
  max-width: 110px;
  text-shadow: 0 2px 4px rgba(0,0,0,0.6);
}

.title-badge {
  background: linear-gradient(135deg, #ffd700 0%, #ff8f00 100%);
  color: #2e1c0c;
  font-size: 0.7rem;
  font-weight: 900;
  padding: 2px 8px;
  border-radius: 10px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.2);
}

.stars-row {
  display: flex;
  align-items: center;
  gap: 3px;
  font-size: 0.85rem;
}

.star {
  color: rgba(255, 255, 255, 0.22);
  text-shadow: 0 1px 2px rgba(0,0,0,0.5);
}

.star.active {
  color: #ffd700;
  text-shadow: 0 0 6px rgba(255, 215, 0, 0.6);
}

.star-text {
  margin-left: 6px;
  font-size: 0.8rem;
  font-weight: 800;
  color: rgba(255, 255, 255, 0.8);
}

/* 底部中央装饰拉箭 - 极美药丸形状 */
.bottom-center-arrow {
  position: absolute;
  left: 50%;
  bottom: 12px;
  transform: translateX(-50%);
  color: #fff;
  background: linear-gradient(180deg, rgba(33, 150, 243, 0.4) 0%, rgba(21, 101, 192, 0.2) 100%);
  border: 1.5px solid rgba(144, 202, 249, 0.4);
  border-radius: 20px 20px 0 0;
  padding: 4px 18px 0;
  cursor: pointer;
  transition: all 0.25s ease;
  box-shadow: 0 -3px 10px rgba(0, 0, 0, 0.3), 0 0 8px rgba(33, 150, 243, 0.25);
  backdrop-filter: blur(5px);
}

.bottom-center-arrow:hover {
  color: #ffd700;
  background: linear-gradient(180deg, rgba(33, 150, 243, 0.6) 0%, rgba(21, 101, 192, 0.3) 100%);
  border-color: rgba(255, 215, 0, 0.5);
  box-shadow: 0 -3px 15px rgba(255, 215, 0, 0.4), 0 0 12px rgba(255, 215, 0, 0.3);
}

.bottom-actions-row {
  display: flex;
  gap: 20px;
}

/* 3D 浮雕操作按钮 */
.btn-green-room {
  background: linear-gradient(180deg, #81c784 0%, #4caf50 45%, #2e7d32 100%);
  border-top: 2px solid #a5d6a7;
  border-left: 1.5px solid #a5d6a7;
  border-right: 1.5px solid #388e3c;
  border-bottom: 3.5px solid #1b5e20; /* 3D厚度 */
  border-radius: 30px;
  color: #fff;
  padding: 6px 36px;
  cursor: pointer;
  box-shadow: 0 6px 14px rgba(0, 0, 0, 0.45);
  display: flex;
  flex-direction: column;
  align-items: center;
  transition: all 0.12s ease;
  text-shadow: 0 -1.5px 1px rgba(0,0,0,0.5);
}

.btn-green-room:hover {
  background: linear-gradient(180deg, #a5d6a7 0%, #66bb6a 45%, #388e3c 100%);
  transform: translateY(-2px);
  box-shadow: 0 8px 18px rgba(0, 0, 0, 0.5);
}

.btn-green-room:active {
  transform: translateY(2px);
  border-bottom-width: 1px;
  box-shadow: 0 2px 6px rgba(0,0,0,0.6);
}

.btn-orange-start {
  background: linear-gradient(180deg, #ffd54f 0%, #ff9800 45%, #e65100 100%);
  border-top: 2.5px solid #fff59d;
  border-left: 1.5px solid #fff59d;
  border-right: 1.5px solid #f57c00;
  border-bottom: 4px solid #b71c1c; /* 3D厚度 */
  border-radius: 30px;
  color: #fff;
  padding: 6px 48px;
  cursor: pointer;
  box-shadow: 0 6px 14px rgba(0, 0, 0, 0.5);
  display: flex;
  flex-direction: column;
  align-items: center;
  transition: all 0.12s ease;
  text-shadow: 0 -1.5px 1px rgba(0,0,0,0.5);
}

.btn-orange-start:hover {
  background: linear-gradient(180deg, #ffe082 0%, #ffa726 45%, #f57c00 100%);
  transform: translateY(-2px);
  box-shadow: 0 8px 18px rgba(0, 0, 0, 0.55);
}

.btn-orange-start:active {
  transform: translateY(2.5px);
  border-bottom-width: 1px;
  box-shadow: 0 2px 6px rgba(0,0,0,0.6);
}

.btn-title {
  font-size: 1.25rem;
  font-weight: 900;
  text-shadow: 0 1px 3px rgba(0,0,0,0.6);
}

.btn-subtitle {
  font-size: 0.72rem;
  opacity: 0.95;
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
  background: rgba(0, 0, 0, 0.75);
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

.profile-modal {
  width: min(92vw, 460px);
  max-height: 86vh;
  overflow-y: auto;
  padding: 24px;
  box-sizing: border-box;
}

.profile-summary {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 18px;
}

.profile-avatar-preview {
  width: 82px;
  height: 82px;
  border-radius: 50%;
  border: 2px solid #ffd700;
  background: rgba(255, 255, 255, 0.14);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  flex: 0 0 auto;
}

.profile-avatar-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.profile-avatar-placeholder {
  font-size: 2.4rem;
}

.profile-main-info {
  min-width: 0;
  text-align: left;
}

.profile-nickname {
  font-size: 1.18rem;
  font-weight: 900;
  color: #fff;
  overflow-wrap: anywhere;
}

.profile-account,
.profile-player-id {
  margin-top: 6px;
  color: rgba(255, 255, 255, 0.72);
  font-size: 0.9rem;
}

.profile-stats-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 18px;
}

.profile-stat {
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 8px;
  padding: 10px;
  background: rgba(0, 0, 0, 0.22);
  display: flex;
  flex-direction: column;
  gap: 4px;
  text-align: left;
}

.profile-stat span {
  color: rgba(255, 255, 255, 0.68);
  font-size: 0.78rem;
}

.profile-stat strong {
  color: #ffd700;
  font-size: 1rem;
  overflow-wrap: anywhere;
}

.profile-avatar-field {
  display: flex;
  flex-direction: column;
  gap: 8px;
  text-align: left;
  color: rgba(255, 255, 255, 0.82);
  font-weight: 800;
}

.profile-avatar-input {
  width: 100%;
  box-sizing: border-box;
  border: 1.5px solid rgba(255, 255, 255, 0.22);
  border-radius: 8px;
  padding: 10px 12px;
  color: #fff;
  background: rgba(0, 0, 0, 0.45);
  font-size: 0.95rem;
}

.profile-error {
  color: #ff8a80;
  margin: 10px 0 0;
  text-align: left;
  font-weight: 700;
}

.profile-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 20px;
}

.profile-secondary-action {
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.2);
  color: #fff;
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

.feature-notice-modal {
  width: min(90vw, 360px);
  padding: 22px;
  border-radius: 14px;
  text-align: center;
  box-sizing: border-box;
}

.feature-notice-text {
  margin: 6px 0 22px;
  color: rgba(255, 255, 255, 0.86);
  line-height: 1.7;
  font-weight: 700;
}

.feature-notice-confirm {
  min-width: 110px;
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
