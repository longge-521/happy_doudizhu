<!-- frontend/src/views/GameRoomView.vue -->
<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { usePlayerStore } from '@/stores/playerStore'
import { useGameStore } from '@/stores/gameStore'
import { useGameWebSocket } from '@/composables/useGameWebSocket'
import {
  canBeatCardPlay,
  detectCardPlay,
  findSuggestedPlay,
  formatCardIds,
  getCardDisplay,
  getPlayKindLabel,
  sortCardIds,
  sortPlayedCards,
} from '@/utils/cardUtils'
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

// 倒计时计时器
const timeLeft = ref(15)
let timerInterval: number | null = null
const idleRoundCount = ref(0)

// 托管模式状态与逻辑
const isAutoPlay = ref(false)

function toggleAutoplay() {
  isAutoPlay.value = !isAutoPlay.value
}

// 侦听托管及当前回合状态，自动代打
watch(
  [() => gameStore.isMyTurn, isAutoPlay],
  ([isMyTurn, autoPlay]) => {
    if (isMyTurn && autoPlay) {
      setTimeout(() => {
        if (gameStore.isMyTurn && isAutoPlay.value) {
          handleTimeout()
        }
      }, 500)
    }
  },
  { immediate: true }
)

// 游戏结束或闲置时自动重置托管状态
watch(
  () => gameStore.gamePhase,
  (newPhase) => {
    if (newPhase === 'IDLE' || newPhase === 'SETTLING') {
      isAutoPlay.value = false
    }
  }
)

// 模拟加倍状态记录
const localDoublingState = ref<Record<string, string>>({})
const myDoublingChoice = ref('') // 'double' | 'super' | 'none'
const showDoublingPanel = computed(() => {
  // 当处于 PLAYING 阶段且还没有人打出任何牌，且自己还没有选择加倍时，显示加倍浮层
  return gameStore.gamePhase === 'PLAYING' &&
         gameStore.allPlayedCards.length === 0 &&
         !myDoublingChoice.value
})

// 能否叫地主/抢地主判断
const hasSomeoneCalled = computed(() => {
  return gameStore.callRound === 2 || Object.values(gameStore.callScores).some((score) => score > 0)
})

const highestCallScore = computed(() => {
  return Math.max(0, ...Object.values(gameStore.callScores))
})

const nextCallScore = computed(() => {
  return hasSomeoneCalled.value ? Math.min(highestCallScore.value + 1, 3) : 1
})

const callActionLabel = computed(() => {
  return hasSomeoneCalled.value ? '抢地主' : '叫地主'
})

const passCallLabel = computed(() => {
  return hasSomeoneCalled.value ? '不抢' : '不叫'
})

// 计算玩家在房间中的相对座位定位（顺时针排布）
const orderedSeats = computed(() => {
  const myId = playerStore.playerId
  const pList = gameStore.players
  if (pList.length < 3) return []

  const myIndex = pList.findIndex((p) => p.id === myId)
  if (myIndex === -1) {
    return [
      { player: pList[0]!, position: 'left' as const },
      { player: pList[1]!, position: 'right' as const },
      { player: pList[2]!, position: 'bottom' as const }
    ]
  }

  const rightPlayer = pList[(myIndex + 1) % 3]!
  const leftPlayer = pList[(myIndex + 2) % 3]!
  const selfPlayer = pList[myIndex]!

  // 注入加倍状态描述
  const decoratedLeft = { ...leftPlayer, doubling: localDoublingState.value[leftPlayer.id] }
  const decoratedRight = { ...rightPlayer, doubling: localDoublingState.value[rightPlayer.id] }
  const decoratedSelf = { ...selfPlayer, doubling: localDoublingState.value[selfPlayer.id] }

  return [
    { player: decoratedLeft, position: 'left' as const },
    { player: decoratedRight, position: 'right' as const },
    { player: decoratedSelf, position: 'bottom' as const }
  ]
})

// 能否过牌
const canPass = computed(() => {
  return gameStore.lastPlay.player !== null && gameStore.lastPlay.player !== playerStore.playerId
})

const lastCardsToBeat = computed(() => {
  if (!gameStore.lastPlay.player || gameStore.lastPlay.player === playerStore.playerId) return []
  return gameStore.lastPlay.cards || []
})

const playSuggestion = computed(() => {
  if (gameStore.gamePhase !== 'PLAYING' || !gameStore.isMyTurn) return null

  const cards = findSuggestedPlay(gameStore.myHand, lastCardsToBeat.value)
  const play = detectCardPlay(cards)
  const isLeading = lastCardsToBeat.value.length === 0

  if (!cards.length || !play) {
    return {
      canPlay: false,
      cards: [] as number[],
      text: '要不起，建议不出',
    }
  }

  const label = getPlayKindLabel(play.kind)
  return {
    canPlay: true,
    cards,
    text: `${isLeading ? '建议先出' : '要得起，建议出'}：${formatCardIds(cards)}（${label}）`,
  }
})

const suggestedCards = computed(() => {
  return playSuggestion.value?.canPlay ? playSuggestion.value.cards : []
})

const selectedPlayState = computed(() => {
  if (gameStore.selectedCards.length === 0) {
    return { valid: false, message: '' }
  }

  const selectedPlay = detectCardPlay(gameStore.selectedCards)
  if (!selectedPlay) {
    return { valid: false, message: '当前选择不是合法牌型' }
  }

  const lastPlay = detectCardPlay(lastCardsToBeat.value)
  if (!lastPlay) {
    return { valid: true, message: getPlayKindLabel(selectedPlay.kind) }
  }

  if (!canBeatCardPlay(selectedPlay, lastPlay)) {
    return { valid: false, message: '当前选择压不过上家' }
  }

  return { valid: true, message: getPlayKindLabel(selectedPlay.kind) }
})

const canSubmitSelected = computed(() => {
  return gameStore.selectedCards.length > 0 && selectedPlayState.value.valid
})

// 记牌器逻辑
const discardCounts = computed(() => {
  // 经典显示顺序：大王、小王、2、A、K、Q、J、10、9、8、7、6、5、4、3
  const keys = ['大', '小', '2', 'A', 'K', 'Q', 'J', '10', '9', '8', '7', '6', '5', '4', '3']
  const counts: Record<string, number> = {
    '大': 1, '小': 1, '2': 4, 'A': 4, 'K': 4, 'Q': 4, 'J': 4, '10': 4, '9': 4, '8': 4, '7': 4, '6': 4, '5': 4, '4': 4, '3': 4
  }

  // 减去自己手牌
  for (const cId of gameStore.myHand) {
    const d = getCardDisplay(cId)
    if (d.suit === 'joker') {
      if (d.rank === '大') counts['大'] = (counts['大'] ?? 0) - 1
      if (d.rank === '小') counts['小'] = (counts['小'] ?? 0) - 1
    } else {
      if (counts[d.rank] !== undefined) counts[d.rank] = (counts[d.rank] ?? 0) - 1
    }
  }

  // 减去全场已出牌
  for (const cId of gameStore.allPlayedCards) {
    const d = getCardDisplay(cId)
    if (d.suit === 'joker') {
      if (d.rank === '大') counts['大'] = (counts['大'] ?? 0) - 1
      if (d.rank === '小') counts['小'] = (counts['小'] ?? 0) - 1
    } else {
      if (counts[d.rank] !== undefined) counts[d.rank] = (counts[d.rank] ?? 0) - 1
    }
  }

  return keys.map(k => ({ key: k, count: Math.max(0, counts[k] ?? 0) }))
})

onMounted(() => {
  if (!gameStore.wsConnected) {
    connect()
  } else {
    // 主动同步最新房间局势，防止大厅跳转延迟导致状态不同步
    sendAction({ action: 'sync_room_state' })
  }

  // 开启倒计时检测
  timerInterval = window.setInterval(() => {
    const now = Date.now() / 1000
    if (gameStore.turnDeadline) {
      const oldTimeLeft = timeLeft.value
      const newTimeLeft = Math.max(0, Math.ceil(gameStore.turnDeadline - now))
      timeLeft.value = newTimeLeft

      // 当倒计时归零且有待处理状态时
      if (newTimeLeft === 0 && oldTimeLeft > 0) {
        if (showDoublingPanel.value) {
          // 加倍阶段超时，自动选择“不加倍”
          chooseDoubling('none')
        } else if (gameStore.isMyTurn) {
          // 出牌/叫地主阶段超时操作
          handleTimeout()
        }
      }
    }
  }, 200)
})

onUnmounted(() => {
  if (timerInterval) clearInterval(timerInterval)
})

// 超时自动操作逻辑
function handleTimeout() {
  if (!isAutoPlay.value) {
    idleRoundCount.value++
    if (idleRoundCount.value >= 2) {
      isAutoPlay.value = true // 累计两轮无操作，自动进入托管模式
    }
  }
  if (gameStore.gamePhase === 'CALLING') {
    // 叫地主阶段超时，自动选择“不叫”
    handleSkipCall(true)
  } else if (gameStore.gamePhase === 'PLAYING') {
    // 出牌阶段超时：若能要得起，则自动出推荐的牌型；要不起才过牌
    if (suggestedCards.value && suggestedCards.value.length > 0) {
      sendAction({
        action: 'play_cards',
        cards: suggestedCards.value
      })
      gameStore.clearSelection()
    } else {
      // 确实要不起，或者只能过牌
      handlePass(true)
    }
  }
}

// 叫地主操作
function handleCall() {
  idleRoundCount.value = 0
  sendAction({ action: 'call_landlord', score: nextCallScore.value })
}

// 不叫/不抢操作
function handleSkipCall(isAuto = false) {
  if (!isAuto) {
    idleRoundCount.value = 0
  }
  sendAction({ action: 'skip_call' })
}

// 出牌操作
function handlePlayCards() {
  if (!canSubmitSelected.value) return
  idleRoundCount.value = 0
  sendAction({
    action: 'play_cards',
    cards: gameStore.selectedCards
  })
  gameStore.clearSelection()
}

// 不要/过牌操作
function handlePass(isAuto = false) {
  if (!isAuto) {
    idleRoundCount.value = 0
  }
  sendAction({ action: 'pass_turn' })
  gameStore.clearSelection()
}

function applySuggestion() {
  if (!playSuggestion.value?.canPlay) return
  gameStore.selectCards(playSuggestion.value.cards)
}

// 发送聊天短语
function handleSendChat(msgId: number) {
  sendAction({ action: 'chat', msg_id: msgId })
  showChatMenu.value = false
}

// 模拟选择加倍
function chooseDoubling(type: 'double' | 'super' | 'none') {
  myDoublingChoice.value = type
  let label = '不加倍'
  if (type === 'double') {
    label = '加倍'
    gameStore.multiplier *= 2 // 视觉加倍
  } else if (type === 'super') {
    label = '超级加倍'
    gameStore.multiplier *= 4 // 视觉超级加倍
  }

  // 注入自己状态
  localDoublingState.value[playerStore.playerId] = label
  // 通过聊天接口向其他玩家广播加倍状态
  sendAction({ action: 'chat', msg_id: CHAT_PRESETS.length + (type === 'double' ? 1 : type === 'super' ? 2 : 0) })

  // 重置出牌倒计时为满额 15 秒
  gameStore.turnDeadline = Date.now() / 1000 + 15
  timeLeft.value = 15

  // 让机器人也随即做出选择，制造真实的牌局体验
  setTimeout(() => {
    for (const p of gameStore.players) {
      if (p.isAi && !localDoublingState.value[p.id]) {
        const aiChoices: Array<'double' | 'none'> = ['double', 'none']
        const rand = aiChoices[Math.floor(Math.random() * aiChoices.length)]!
        localDoublingState.value[p.id] = rand === 'double' ? '加倍' : '不加倍'
      }
    }
  }, 800)
}

// 关闭结算面板，重置数据并返回大厅
function handleCloseSettlement() {
  gameStore.reset()
  myDoublingChoice.value = ''
  localDoublingState.value = {}
  router.push('/lobby')
}

// 退出房间
function handleExitRoom() {
  if (confirm('确定要退出当前游戏吗？这将会使您托管或流失积分！')) {
    disconnect()
    gameStore.reset()
    myDoublingChoice.value = ''
    localDoublingState.value = {}
    router.push('/lobby')
  }
}

// 获取结算阶段某个玩家的余牌
function getSettleRemainingCards(playerId: string): number[] {
  if (!gameStore.settlement || !gameStore.settlement.allHands) return []
  const hands = gameStore.settlement.allHands[playerId] || []
  return sortCardIds(hands)
}

// 监听 errorMsg，一旦有值，在 2.5 秒后自动淡出消失
watch(
  () => gameStore.errorMsg,
  (newVal) => {
    if (newVal) {
      setTimeout(() => {
        gameStore.errorMsg = ''
      }, 2500)
    }
  }
)

// 监听重新洗牌
watch(
  () => gameStore.gamePhase,
  (newPhase, oldPhase) => {
    if (newPhase === 'DEALING' && oldPhase === 'CALLING') {
      gameStore.showRedealNotice = true
      setTimeout(() => {
        gameStore.showRedealNotice = false
      }, 1800)
    }
  }
)
</script>

<template>
  <div class="game-table room-modern-layout">
    <!-- 大牌特效浮层 -->
    <div class="poker-effects-layer" :class="{ 'shake-screen': gameStore.activeEffect === 'bomb' }">
      <!-- 炸弹能量波 -->
      <div v-if="gameStore.activeEffect === 'bomb'" class="effect-bomb-shockwave">
        <div class="shockwave-ring"></div>
        <div class="shockwave-ring delay"></div>
      </div>
      <!-- 飞机划过 -->
      <div v-if="gameStore.activeEffect === 'plane'" class="effect-plane-flyby">
        <div class="plane-silhouette">✈️</div>
        <div class="plane-smoke"></div>
      </div>
    </div>

    <!-- 顶部状态栏 -->
    <header class="room-header">
      <div class="top-left-hud">
        <button class="btn-exit" @click="handleExitRoom" aria-label="退出">
          <span class="exit-arrow">↩</span>
        </button>

        <!-- 记牌器 -->
        <div v-if="gameStore.gamePhase === 'PLAYING' || gameStore.gamePhase === 'CALLING'" class="card-remembrancer">
          <div class="remembrancer-grid">
            <div
              v-for="item in discardCounts"
              :key="item.key"
              class="rem-col"
              :class="{ zero: item.count === 0, active: item.count > 0 }"
            >
              <span class="rem-key">{{ item.key }}</span>
              <span class="rem-count">{{ item.count }}</span>
            </div>
          </div>
        </div>
      </div>

      <div class="room-info">
        <span class="room-id">房间号: <strong>{{ gameStore.roomId }}</strong></span>
        <span class="base-score-badge">底分: <strong>{{ gameStore.baseScore }}</strong></span>
        <span class="multiplier-badge font-glow">倍数: <strong>{{ gameStore.multiplier }}倍</strong></span>
        
        <!-- 托管按钮 -->
        <button 
          v-if="gameStore.gamePhase === 'PLAYING' || gameStore.gamePhase === 'CALLING'"
          class="btn-autoplay"
          :class="{ active: isAutoPlay }"
          @click="toggleAutoplay"
        >
          {{ isAutoPlay ? '🤖 托管中 (点击取消)' : '🤖 开启托管' }}
        </button>
      </div>

      <div class="top-right-hud">
        <div class="bottom-cards-row">
          <div 
            v-for="(cId, index) in gameStore.bottomCards.length > 0 ? gameStore.bottomCards : [0, 0, 0]"
            :key="index"
            class="bottom-card-flip-container"
            :class="{ 'is-flipped': gameStore.bottomCards.length > 0 }"
          >
            <div class="bottom-card-inner" :style="{ transitionDelay: (index * 0.1) + 's' }">
              <div class="bottom-card-back">
                <PokerCard :card-id="0" :face-down="true" :no-hover="true" size="sm" />
              </div>
              <div class="bottom-card-front">
                <PokerCard :card-id="cId" :face-down="false" :no-hover="true" size="sm" />
              </div>
            </div>
          </div>
        </div>

        <div class="chat-trigger-area">
        <button class="btn-chat" @click="showChatMenu = !showChatMenu">
          💬 快捷语
        </button>
        <!-- 快捷语面板 -->
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
      </div>
    </header>

    <!-- 浮雕背景LOGO -->
    <div class="brand-logo-watermark">
      <div class="watermark-main">欢乐斗地主</div>
      <div class="watermark-sub">经典新手场 底分{{ gameStore.baseScore }}</div>
    </div>

    <!-- 桌面中央出牌与动作展示区 -->
    <div class="table-play-area">
      <div
        v-for="seat in orderedSeats"
        :key="seat.player.id"
        class="play-seat-zone"
        :class="[seat.position, { 'show-all-hands': gameStore.showAllHands }]"
      >
        <template v-if="!gameStore.showAllHands">
          <!-- 精美特效大字动作文本 -->
          <div
            v-if="gameStore.playerActions[seat.player.id]"
            class="action-text-fancy"
            :class="[
              (gameStore.playerActions[seat.player.id] === '不出' || 
               gameStore.playerActions[seat.player.id] === '不叫' || 
               gameStore.playerActions[seat.player.id] === '不抢' || 
               gameStore.playerActions[seat.player.id] === '不加倍') ? 'blue' : 'gold'
            ]"
          >
            {{ gameStore.playerActions[seat.player.id] }}
          </div>
          <!-- 牌型显示 -->
          <div
            v-else-if="gameStore.playerPlayedCards[seat.player.id] && gameStore.playerPlayedCards[seat.player.id]!.length > 0"
            class="played-cards-row"
            :class="{ 'shimmer-active': gameStore.activeEffect === 'shimmer' && gameStore.lastPlay.player === seat.player.id }"
          >
            <PokerCard
              v-for="cId in sortPlayedCards(gameStore.playerPlayedCards[seat.player.id] || [])"
              :key="cId"
              :card-id="cId"
              :no-hover="true"
              size="sm"
            />
          </div>
        </template>

        <!-- 结算明牌展示区 -->
        <template v-else>
          <div
            v-if="getSettleRemainingCards(seat.player.id).length > 0"
            class="settle-hands-list-center"
          >
            <div class="settle-remain-title">{{ seat.player.nickname }} 的余牌:</div>
            <div class="settle-remain-cards">
              <PokerCard
                v-for="(cId, index) in getSettleRemainingCards(seat.player.id)"
                :key="cId"
                :card-id="cId"
                :no-hover="true"
                size="sm"
                class="settle-remain-card"
                :style="{ marginLeft: index === 0 ? '0px' : '-28px', zIndex: index }"
              />
            </div>
          </div>
          <div v-else class="settle-finished-status">
            <span class="settle-finished-text">打完了</span>
            <!-- 展示赢家最后一次打出的绝杀牌 -->
            <div
              v-if="gameStore.playerPlayedCards[seat.player.id] && gameStore.playerPlayedCards[seat.player.id]!.length > 0"
              class="played-cards-row"
              style="margin-top: 8px;"
            >
              <PokerCard
                v-for="cId in sortPlayedCards(gameStore.playerPlayedCards[seat.player.id] || [])"
                :key="cId"
                :card-id="cId"
                :no-hover="true"
                size="sm"
              />
            </div>
          </div>
        </template>
      </div>
    </div>

    <!-- 中部座位渲染区 -->
    <div class="seats-container">
      <PlayerSeat
        v-for="seat in orderedSeats"
        :key="seat.player.id"
        :player="seat.player"
        :position="seat.position"
        :is-current-turn="gameStore.currentTurn === seat.player.id"
      />
    </div>

    <!-- 底部操作区与手牌区 -->
    <div class="player-bottom-area">
      <!-- 加倍决策行动面板 -->
      <div v-if="showDoublingPanel" class="action-bar-row">
        <div class="play-action-panel">
          <div class="actions-group">
            <button
              class="btn-action-call"
              style="background: linear-gradient(135deg, #ffca28 0%, #ff8f00 100%); border-color: #ffe082;"
              @click="chooseDoubling('double')"
            >
              加倍
            </button>
            
            <!-- 加倍阶段内联时钟计时器 -->
            <div class="turn-alarm-clock">
              <div class="clock-icon">⏰</div>
              <span class="time-left-digits">{{ timeLeft }}</span>
            </div>

            <button
              class="btn-action-call"
              style="background: linear-gradient(135deg, #ff7043 0%, #d84315 100%); border-color: #ffab91;"
              @click="chooseDoubling('super')"
            >
              超级加倍
            </button>
            
            <button
              class="btn-action-pass"
              @click="chooseDoubling('none')"
            >
              不加倍
            </button>
          </div>
        </div>
      </div>

      <!-- 错误气泡 -->
      <transition name="fade">
        <div v-if="gameStore.errorMsg" class="error-toast-bubble">
          <span>⚠️ {{ gameStore.errorMsg }}</span>
        </div>
      </transition>

      <!-- 轮到自己决策时的时钟倒计时与行动面板 -->
      <div v-if="gameStore.isMyTurn && !showDoublingPanel" class="action-bar-row">
        <!-- 叫地主阶段时钟计时器 -->
        <div v-if="gameStore.gamePhase === 'CALLING'" class="turn-alarm-clock">
          <div class="clock-icon">⏰</div>
          <span class="time-left-digits">{{ timeLeft }}</span>
        </div>

        <!-- 叫地主阶段按钮 -->
        <div v-if="gameStore.gamePhase === 'CALLING'" class="actions-group">
          <button class="btn-action-call" @click="handleCall">{{ callActionLabel }}</button>
          <button class="btn-action-pass" @click="handleSkipCall()">{{ passCallLabel }}</button>
        </div>

        <!-- 出牌阶段按钮 -->
        <div v-if="gameStore.gamePhase === 'PLAYING'" class="play-action-panel">
          <div
            v-if="gameStore.selectedCards.length > 0 && !selectedPlayState.valid"
            class="selection-warning"
          >
            {{ selectedPlayState.message }}
          </div>
          <div class="actions-group">
            <button
              class="btn-action-pass"
              :disabled="!canPass"
              @click="handlePass()"
            >
              不出
            </button>
            
            <!-- 出牌阶段内联时钟计时器 -->
            <div class="turn-alarm-clock">
              <div class="clock-icon">⏰</div>
              <span class="time-left-digits">{{ timeLeft }}</span>
            </div>

            <button
              class="btn-action-hint"
              :disabled="!playSuggestion?.canPlay"
              @click="applySuggestion"
            >
              提示
            </button>
            
            <button
              class="btn-action-call"
              :disabled="!canSubmitSelected"
              @click="handlePlayCards"
            >
              出牌
            </button>
          </div>
        </div>
      </div>

      <!-- 自己的手牌 -->
      <div class="self-hand-row">
        <HandCards :cards="gameStore.myHand" :hinted-cards="suggestedCards" size="lg" />
      </div>
    </div>

    <!-- 游戏结束左下角大字 -->
    <transition name="fade">
      <div v-if="gameStore.showGameOverBanner" class="game-over-finish-text">打完啦！！</div>
    </transition>

    <!-- 游戏结束浮空大字 -->
    <transition name="fade">
      <div v-if="gameStore.showWinnerBanner" class="game-over-banner-overlay">
        <div class="game-over-title font-glow">{{ gameStore.gameOverTitle }}</div>
      </div>
    </transition>

    <!-- 结算弹窗 -->
    <SettlementModal
      v-if="gameStore.gamePhase === 'SETTLING' && gameStore.settlement"
      :settlement="gameStore.settlement"
      :players="gameStore.players"
      :last-played-cards="gameStore.playerPlayedCards"
      @close="handleCloseSettlement"
    />

    <!-- 重新洗牌提示 -->
    <transition name="fade">
      <div v-if="gameStore.showRedealNotice" class="redeal-overlay glass-panel">
        <div class="redeal-content">
          <span class="redeal-text">无人叫牌，正在重新洗牌中... <span class="redeal-spin-icon">🔄</span></span>
        </div>
      </div>
    </transition>
  </div>
</template>

<style scoped>
.room-modern-layout {
  display: flex;
  flex-direction: column;
  height: 100vh;
  position: relative;
  overflow: hidden;
  background:
    radial-gradient(circle at 50% 42%, rgba(122, 196, 255, 0.75) 0%, rgba(42, 129, 216, 0.9) 34%, rgba(33, 82, 157, 0.98) 70%),
    linear-gradient(135deg, #244b9b 0%, #2e78c4 52%, #27437f 100%);
  color: #ffffff;
}

/* 顶部状态栏 */
.room-header {
  display: grid;
  grid-template-columns: minmax(420px, 1fr) auto minmax(280px, 1fr);
  align-items: center;
  gap: 18px;
  min-height: 74px;
  padding: 10px 22px;
  background: linear-gradient(to bottom, rgba(9, 28, 73, 0.58) 0%, rgba(9, 28, 73, 0) 100%);
  z-index: 30;
}

.top-left-hud,
.top-right-hud {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
}

.top-right-hud {
  justify-content: flex-end;
}

.btn-exit {
  width: 52px;
  height: 52px;
  flex: 0 0 auto;
  background: rgba(255, 255, 255, 0.16);
  border: 2px solid rgba(255, 255, 255, 0.65);
  color: #ffffff;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 700;
  display: flex;
  justify-content: center;
  align-items: center;
  text-shadow: 0 2px 3px rgba(0,0,0,0.45);
}

.exit-arrow {
  font-size: 2rem;
  line-height: 1;
}

.btn-exit:hover {
  background: rgba(255, 255, 255, 0.25);
}

.room-info {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 16px;
  min-width: 300px;
  white-space: nowrap;
}

.room-id, .base-score-badge, .multiplier-badge {
  font-size: 0.95rem;
  text-shadow: 0 1px 3px rgba(0,0,0,0.6);
}

.multiplier-badge {
  color: #ffd700;
  font-weight: bold;
}

.font-glow {
  text-shadow: 0 0 8px rgba(255, 215, 0, 0.6);
}

.btn-chat {
  background: linear-gradient(to bottom, #ffb300, #ff8f00);
  border: 1px solid #ffd54f;
  color: #3e2723;
  padding: 6px 16px;
  border-radius: 20px;
  font-weight: bold;
  cursor: pointer;
}

.chat-trigger-area {
  position: relative;
}

.chat-menu {
  position: absolute;
  right: 0;
  top: 40px;
  width: 220px;
  padding: 8px 0;
  display: flex;
  flex-direction: column;
  z-index: 50;
}

.chat-menu-item {
  padding: 10px 16px;
  font-size: 0.85rem;
  cursor: pointer;
  transition: all 0.2s;
  text-align: left;
}

.chat-menu-item:hover {
  background: rgba(255, 255, 255, 0.15);
  color: #ffd700;
}

.bottom-cards-row {
  display: flex;
  gap: 5px;
  flex: 0 0 auto;
  background: rgba(9, 31, 73, 0.48);
  padding: 5px 9px;
  border-radius: 6px;
  border: 1px solid rgba(255,255,255,0.26);
  box-shadow: inset 0 1px 4px rgba(0,0,0,0.24);
}

/* 记牌器 */
.card-remembrancer {
  width: clamp(430px, 48vw, 760px);
  overflow: hidden;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.94);
  color: #283348;
  border: 1px solid rgba(42, 68, 112, 0.28);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25);
}

.remembrancer-title {
  font-size: 0.75rem;
  font-weight: bold;
  color: #ffd700;
  text-align: center;
  margin-bottom: 4px;
  opacity: 0.8;
}

.remembrancer-grid {
  display: grid;
  grid-template-columns: repeat(15, minmax(28px, 1fr));
}

.rem-col {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 44px;
  border-left: 1px solid rgba(40, 51, 72, 0.18);
  line-height: 1.05;
}

.rem-col:first-child {
  border-left: none;
}

.rem-key {
  font-size: 0.86rem;
  font-weight: 800;
  color: #2b3448;
}

.rem-count {
  margin-top: 5px;
  font-size: 1rem;
  font-weight: 900;
  color: #d46a1b;
}

.rem-col.zero {
  background: rgba(238, 238, 238, 0.7);
}

.rem-col.zero .rem-count {
  color: rgba(212, 106, 27, 0.24);
}

/* 浮雕标志背景 */
.brand-logo-watermark {
  position: absolute;
  top: 41%;
  left: 50%;
  transform: translate(-50%, -50%);
  pointer-events: none;
  opacity: 0.08;
  text-align: center;
  z-index: 1;
}

.watermark-main {
  font-size: 5rem;
  font-weight: 900;
  letter-spacing: 6px;
}

.watermark-sub {
  font-size: 1.5rem;
  font-weight: bold;
  margin-top: 10px;
}

/* 座位容器 */
.seats-container {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  pointer-events: none;
  z-index: 10;
}
.seats-container :deep(*) {
  pointer-events: auto;
}

/* 加倍遮罩 */
.doubling-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.55);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 100;
  backdrop-filter: blur(5px);
}

.doubling-dialog {
  width: 90%;
  max-width: 400px;
  padding: 30px;
  text-align: center;
}

.doubling-dialog h3 {
  color: #ffd700;
  font-weight: 900;
  margin-bottom: 24px;
}

.doubling-buttons {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.btn-double {
  background: linear-gradient(135deg, #0288d1 0%, #01579b 100%);
  color: #fff;
  font-weight: 800;
  border: 1px solid #4fc3f7;
  padding: 12px;
  border-radius: 20px;
  cursor: pointer;
  font-size: 1.1rem;
}

.btn-super-double {
  background: linear-gradient(135deg, #ff8f00 0%, #d84315 100%);
  color: #fff;
  font-weight: 900;
  border: 1px solid #ffb74d;
  padding: 12px;
  border-radius: 20px;
  cursor: pointer;
  font-size: 1.2rem;
  box-shadow: 0 4px 10px rgba(216, 67, 21, 0.4);
}

.btn-no-double {
  background: rgba(255, 255, 255, 0.2);
  color: #fff;
  font-weight: bold;
  border: 1px solid rgba(255, 255, 255, 0.3);
  padding: 10px;
  border-radius: 20px;
  cursor: pointer;
}

.btn-double:hover, .btn-super-double:hover, .btn-no-double:hover {
  transform: scale(1.02);
}

/* 底部手牌与行动栏 */
.player-bottom-area {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 100%;
  gap: 8px;
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 25;
}

.action-bar-row {
  display: flex;
  align-items: center;
  gap: 16px;
  background: rgba(9, 39, 83, 0.78);
  padding: 8px 18px;
  border-radius: 28px;
  border: 1.5px solid rgba(255, 255, 255, 0.24);
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
  animation: slide-up 0.25s cubic-bezier(0.175, 0.885, 0.32, 1.275);
}

@keyframes slide-up {
  from { transform: translateY(15px); opacity: 0; }
  to { transform: translateY(0); opacity: 1; }
}

/* 闹钟样式 */
.turn-alarm-clock {
  display: flex;
  align-items: center;
  background: #ffb300;
  border-radius: 15px;
  padding: 4px 12px;
  border: 1.5px solid #ffe082;
  box-shadow: 0 2px 6px rgba(0,0,0,0.3);
}

.clock-icon {
  font-size: 1.1rem;
  animation: shake 0.5s infinite alternate;
}

@keyframes shake {
  from { transform: rotate(-10deg); }
  to { transform: rotate(10deg); }
}

.time-left-digits {
  color: #3e2723;
  font-size: 1.15rem;
  font-weight: 900;
  margin-left: 6px;
}

.actions-group {
  display: flex;
  gap: 12px;
  align-items: center;
}

.play-action-panel {
  display: flex;
  align-items: center;
  gap: 12px;
}

.play-hint-pill,
.selection-warning {
  max-width: min(42vw, 520px);
  min-height: 34px;
  display: inline-flex;
  align-items: center;
  padding: 5px 14px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.92);
  color: #24314d;
  font-size: 0.92rem;
  font-weight: 800;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.28);
}

.play-hint-pill.cant,
.selection-warning {
  color: #ffffff;
  background: rgba(59, 91, 167, 0.88);
  border: 1px solid rgba(185, 205, 255, 0.45);
}

/* 行动大按钮 */
.btn-action-call {
  background: linear-gradient(135deg, #ffb300 0%, #ff8f00 100%);
  color: #1a1a1a;
  font-weight: 900;
  border: none;
  padding: 10px 28px;
  border-radius: 20px;
  cursor: pointer;
  box-shadow: 0 4px 8px rgba(255, 143, 0, 0.3);
  font-size: 1.05rem;
}
.btn-action-call:hover:not(:disabled) {
  background: linear-gradient(135deg, #ffe082 0%, #ffb300 100%);
}
.btn-action-call:disabled {
  background: #757575;
  color: #9e9e9e;
  box-shadow: none;
  cursor: not-allowed;
}

.btn-action-pass {
  background: linear-gradient(135deg, #7fd9ff 0%, #6968e8 100%);
  color: #ffffff;
  font-weight: 800;
  border: none;
  padding: 10px 28px;
  border-radius: 20px;
  cursor: pointer;
  box-shadow: 0 4px 8px rgba(2, 136, 209, 0.3);
  font-size: 1.05rem;
}
.btn-action-pass:hover:not(:disabled) {
  background: linear-gradient(135deg, #b6ecff 0%, #8180ff 100%);
}
.btn-action-pass:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.btn-action-reset {
  background: rgba(255, 255, 255, 0.15);
  color: #ffffff;
  font-weight: bold;
  border: 1px solid rgba(255, 255, 255, 0.25);
  padding: 10px 24px;
  border-radius: 20px;
  cursor: pointer;
}
.btn-action-reset:hover {
  background: rgba(255, 255, 255, 0.25);
}

.btn-action-hint {
  background: linear-gradient(135deg, #8fb6ff 0%, #7366df 100%);
  color: #ffffff;
  font-weight: 900;
  border: none;
  padding: 10px 28px;
  border-radius: 20px;
  cursor: pointer;
  box-shadow: 0 4px 8px rgba(70, 75, 160, 0.32);
  font-size: 1.05rem;
}

.btn-action-hint:hover:not(:disabled) {
  background: linear-gradient(135deg, #b9d2ff 0%, #8e84ff 100%);
}

.btn-action-hint:disabled {
  opacity: 0.45;
  cursor: not-allowed;
  box-shadow: none;
}

.self-hand-row {
  width: 100%;
  max-width: min(92vw, 1120px);
}

/* 托管按钮基础及呼吸灯发光样式 */
.btn-autoplay {
  background: rgba(255, 255, 255, 0.15);
  border: 1px solid rgba(255, 255, 255, 0.3);
  border-radius: 20px;
  color: #fff;
  padding: 4px 14px;
  font-size: 13px;
  cursor: pointer;
  margin-left: 12px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  transition: all 0.3s ease;
  font-weight: 500;
}

.btn-autoplay:hover {
  background: rgba(255, 255, 255, 0.3);
  transform: translateY(-1px);
}

.btn-autoplay.active {
  background: #ff5722;
  border-color: #ff5722;
  box-shadow: 0 0 10px rgba(255, 87, 34, 0.6);
  animation: pulse-autoplay 1.5s infinite alternate;
}

@keyframes pulse-autoplay {
  0% {
    transform: scale(1);
    box-shadow: 0 0 10px rgba(255, 87, 34, 0.6);
  }
  100% {
    transform: scale(1.05);
    box-shadow: 0 0 20px rgba(255, 87, 34, 0.9);
  }
}

@media (max-width: 1180px) {
  .room-header {
    grid-template-columns: 1fr auto;
  }

  .room-info {
    order: 3;
    grid-column: 1 / -1;
    min-width: 0;
    justify-content: center;
    margin-top: -6px;
  }

  .card-remembrancer {
    width: min(62vw, 680px);
  }

  .play-action-panel {
    flex-direction: column;
    align-items: stretch;
    gap: 7px;
  }

  .play-hint-pill,
  .selection-warning {
    max-width: 76vw;
    justify-content: center;
  }
}

@media (max-width: 780px) {
  .room-header {
    padding: 8px 10px;
    grid-template-columns: 1fr;
  }

  .top-left-hud,
  .top-right-hud,
  .room-info {
    justify-content: center;
  }

  .top-left-hud {
    flex-wrap: wrap;
  }

  .card-remembrancer {
    order: 2;
    width: calc(100vw - 20px);
  }

  .top-right-hud {
    flex-wrap: wrap;
  }

  .room-info {
    flex-wrap: wrap;
    gap: 8px;
  }

  .action-bar-row {
    flex-wrap: wrap;
    justify-content: center;
    border-radius: 18px;
  }
}

/* 桌面中央出牌区样式 */
.table-play-area {
  position: absolute;
  top: 30%;
  left: 20%;
  right: 20%;
  height: 35%;
  pointer-events: none;
  z-index: 15;
}

.play-seat-zone {
  position: absolute;
  display: flex;
  align-items: center;
  pointer-events: none;
}

.play-seat-zone.left {
  left: 20px;
  top: 15%;
  justify-content: flex-start;
}

.play-seat-zone.right {
  right: 20px;
  top: 15%;
  justify-content: flex-end;
}

.play-seat-zone.bottom {
  left: 50%;
  bottom: 20px;
  transform: translateX(-50%);
  justify-content: center;
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

/* 特效容器与全屏震动 */
.poker-effects-layer {
  position: absolute;
  top: 0; left: 0; width: 100%; height: 100%;
  pointer-events: none;
  z-index: 99;
  overflow: hidden;
}
.poker-effects-layer.shake-screen {
  animation: screen-shake 0.4s ease-out;
}
@keyframes screen-shake {
  0%, 100% { transform: translate(0, 0); }
  10%, 90% { transform: translate(-3px, 2px); }
  30%, 70% { transform: translate(4px, -3px); }
  50% { transform: translate(-5px, 4px); }
}

/* 炸弹冲击波圈 */
.effect-bomb-shockwave {
  position: absolute;
  top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  width: 100px; height: 100px;
}
.shockwave-ring {
  position: absolute;
  width: 100%; height: 100%;
  border-radius: 50%;
  border: 4px solid rgba(255, 179, 0, 0.8);
  box-shadow: 0 0 20px rgba(255, 87, 34, 0.6);
  animation: ripple 0.8s cubic-bezier(0.1, 0.8, 0.3, 1) forwards;
}
.shockwave-ring.delay {
  animation-delay: 0.2s;
}
@keyframes ripple {
  0% { transform: scale(0.5); opacity: 1; }
  100% { transform: scale(4); opacity: 0; border-width: 1px; }
}

/* 飞机特效 */
.effect-plane-flyby {
  position: absolute;
  top: 30%;
  width: 100%;
  height: 60px;
  display: flex;
  align-items: center;
  animation: plane-fly 1.2s cubic-bezier(0.25, 1, 0.5, 1) forwards;
}
.plane-silhouette {
  font-size: 2.5rem;
  transform: rotate(-15deg);
  filter: drop-shadow(0 0 10px rgba(255,255,255,0.8));
}
.plane-smoke {
  flex: 1;
  height: 6px;
  background: linear-gradient(to right, rgba(255,255,255,0) 0%, rgba(255,255,255,0.7) 100%);
  margin-left: -15px;
  border-radius: 3px;
  box-shadow: 0 0 10px rgba(255,255,255,0.4);
}
@keyframes plane-fly {
  from { left: -100px; opacity: 0; }
  10% { opacity: 1; }
  90% { opacity: 1; }
  to { left: 110%; opacity: 0; }
}

/* 顺子金色流光扫过 */
.played-cards-row {
  position: relative;
  overflow: hidden;
  display: flex;
  gap: 3px;
  background: rgba(0, 0, 0, 0.35);
  padding: 6px;
  border-radius: 6px;
  border: 1px solid rgba(255,255,255,0.08);
}
.poker-effects-layer + .played-cards-row::after,
.shimmer-active::after {
  content: '';
  position: absolute;
  top: 0; left: -100%; width: 50%; height: 100%;
  background: linear-gradient(to right, rgba(255,255,255,0) 0%, rgba(255, 215, 0, 0.4) 50%, rgba(255,255,255,0) 100%);
  transform: skewX(-25deg);
  animation: shimmer-flow 1.0s ease-out;
}
@keyframes shimmer-flow {
  from { left: -150%; }
  to { left: 150%; }
}

/* 特效大字动作文本 */
.action-text-fancy {
  font-size: 2.4rem;
  font-weight: 900;
  font-style: italic;
  white-space: nowrap;
  letter-spacing: 2px;
  animation: pop-up 0.25s cubic-bezier(0.175, 0.885, 0.32, 1.275);
}

.action-text-fancy.gold {
  color: #ffb300;
  text-shadow: 
    0 0 10px rgba(255, 179, 0, 0.6),
    2px 2px 0px #ff6f00,
    4px 4px 6px rgba(0, 0, 0, 0.8);
}

.action-text-fancy.blue {
  color: #03a9f4;
  text-shadow: 
    0 0 10px rgba(3, 169, 244, 0.6),
    2px 2px 0px #01579b,
    4px 4px 6px rgba(0, 0, 0, 0.8);
}

@keyframes pop-up {
  from { transform: scale(0.6); opacity: 0; }
  to { transform: scale(1); opacity: 1; }
}

/* 游戏结束浮空大字 */
.game-over-banner-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  z-index: 99;
  pointer-events: none;
  background: rgba(0, 0, 0, 0.2);
}

.game-over-title {
  font-size: 5rem;
  font-weight: 900;
  font-style: italic;
  color: #ffd700;
  text-shadow: 
    0 0 20px rgba(255, 215, 0, 0.8),
    4px 4px 0px #e65100,
    8px 8px 15px rgba(0, 0, 0, 0.9);
  animation: banner-zoom 0.5s cubic-bezier(0.175, 0.885, 0.32, 1.275) both;
  letter-spacing: 6px;
}

.game-over-finish-text {
  position: absolute;
  left: 10%;
  bottom: 25%;
  font-size: 3.5rem;
  font-weight: 900;
  font-style: italic;
  color: #ff5722;
  transform: rotate(-15deg);
  text-shadow: 
    0 0 15px rgba(255, 87, 34, 0.8),
    3px 3px 0px #bf360c,
    6px 6px 12px rgba(0, 0, 0, 0.9);
  animation: stamp-in 0.4s ease-out 0.3s both;
  z-index: 20;
}

@keyframes banner-zoom {
  0% { transform: scale(0.3); opacity: 0; }
  100% { transform: scale(1); opacity: 1; }
}

@keyframes stamp-in {
  0% { transform: rotate(-45deg) scale(2); opacity: 0; }
  100% { transform: rotate(-15deg) scale(1); opacity: 1; }
}

.fade-enter-active, .fade-leave-active {
  transition: opacity 0.5s;
}
.fade-enter-from, .fade-leave-to {
  opacity: 0;
}

/* 结算平铺余牌与已打完提示 */
.settle-hands-list-center {
  display: flex;
  flex-direction: column;
  align-items: center;
  background: rgba(0, 0, 0, 0.65);
  padding: 8px 12px;
  border-radius: 12px;
  border: 1.5px solid rgba(255, 255, 255, 0.2);
  box-shadow: 0 4px 15px rgba(0, 0, 0, 0.5);
}

.play-seat-zone.left.show-all-hands {
  left: calc(-20vw + 150px);
}
.play-seat-zone.right.show-all-hands {
  right: calc(-20vw + 150px);
}

.play-seat-zone.left .settle-hands-list-center {
  align-items: flex-start;
}
.play-seat-zone.right .settle-hands-list-center {
  align-items: flex-end;
}

.settle-remain-title {
  font-size: 0.85rem;
  color: #ffb300;
  font-weight: bold;
  margin-bottom: 5px;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.8);
}

.settle-remain-cards {
  display: flex;
  flex-wrap: wrap;
  max-width: 320px;
  row-gap: 6px;
  align-items: center;
  padding: 0 10px;
}

.settle-remain-card {
  transition: transform 0.2s ease;
}

.settle-finished-status {
  display: flex;
  justify-content: center;
  align-items: center;
  background: linear-gradient(135deg, #e65100 0%, #ff8f00 100%);
  border: 2px solid #ffd700;
  padding: 6px 18px;
  border-radius: 18px;
  box-shadow: 0 4px 15px rgba(230, 81, 0, 0.4);
  animation: pop-up 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275);
}

.settle-finished-text {
  color: #fff;
  font-weight: 900;
  font-size: 1.1rem;
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.6);
  letter-spacing: 2px;
}

/* 错误气泡 */
.error-toast-bubble {
  position: absolute;
  bottom: 80px;
  left: 50%;
  transform: translateX(-50%);
  background: linear-gradient(135deg, #e53935 0%, #b71c1c 100%);
  color: #fff;
  padding: 10px 20px;
  border-radius: 20px;
  font-weight: 700;
  box-shadow: 0 4px 15px rgba(0,0,0,0.3);
  border: 1.5px solid rgba(255,255,255,0.25);
  backdrop-filter: blur(8px);
  z-index: 100;
  animation: shake-toast 0.4s ease;
}
@keyframes shake-toast {
  0%, 100% { transform: translateX(-50%); }
  20%, 60% { transform: translateX(-54%); }
  40%, 80% { transform: translateX(-46%); }
}

/* 重新洗牌横幅 */
.redeal-overlay {
  position: absolute;
  top: 40%;
  left: 50%;
  transform: translate(-50%, -50%);
  padding: 18px 36px;
  border-radius: 12px;
  border: 2px solid #ffd54f;
  background: rgba(9, 39, 83, 0.9);
  color: #ffd54f;
  font-size: 1.3rem;
  font-weight: 900;
  z-index: 999;
  box-shadow: 0 8px 30px rgba(0,0,0,0.5);
  display: flex;
  align-items: center;
  justify-content: center;
}
.redeal-spin-icon {
  display: inline-block;
  animation: spin-redeal 1.2s linear infinite;
}
@keyframes spin-redeal {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* 3D 底牌翻转 */
.bottom-card-flip-container {
  perspective: 600px;
  width: 42px; /* 适配 sm 尺寸 */
  height: 58px;
  margin: 0 3px;
}
.bottom-card-inner {
  position: relative;
  width: 100%;
  height: 100%;
  transform-style: preserve-3d;
  transition: transform 0.6s cubic-bezier(0.175, 0.885, 0.32, 1.275);
}
.bottom-card-flip-container.is-flipped .bottom-card-inner {
  transform: rotateY(180deg);
}
.bottom-card-front, .bottom-card-back {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  backface-visibility: hidden;
}
.bottom-card-front {
  transform: rotateY(180deg);
}
</style>
