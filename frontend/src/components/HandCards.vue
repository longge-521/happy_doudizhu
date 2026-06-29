<!-- frontend/src/components/HandCards.vue -->
<script setup lang="ts">
import { ref, onUnmounted, watch } from 'vue'
import { useGameStore } from '@/stores/gameStore'
import PokerCard from './PokerCard.vue'

const props = defineProps<{
  cards: number[]
  hintedCards?: number[]
  size?: 'sm' | 'md' | 'lg'
}>()

const gameStore = useGameStore()

// 滑动选择状态
const isSelecting = ref(false)
const startIndex = ref(-1)
const currentIndex = ref(-1)

// 动态点亮计数器（用于发牌横向平滑点亮）
const visibleCount = ref(0)
const isDealing = ref(false)
let animateTimer = ref<any>(null)
let isDealingTimeout = ref<any>(null)
let hasAnimatedInThisDeal = false

function clearAnimateTimer() {
  if (animateTimer.value) {
    clearInterval(animateTimer.value)
    animateTimer.value = null
  }
  if (isDealingTimeout.value) {
    clearTimeout(isDealingTimeout.value)
    isDealingTimeout.value = null
  }
}

// 监听游戏阶段变化，一旦重新进入发牌或叫地主阶段，同步强制重置发牌动画状态
watch(() => gameStore.gamePhase, (newPhase) => {
  if (newPhase === 'CALLING' || newPhase === 'DEALING') {
    clearAnimateTimer()
    hasAnimatedInThisDeal = false
    visibleCount.value = 0
    isDealing.value = false
  }
}, { flush: 'sync' })

watch(() => props.cards, (newCards) => {
  if (!newCards || newCards.length === 0) {
    clearAnimateTimer()
    visibleCount.value = 0
    hasAnimatedInThisDeal = false // 手牌变空时，复位动画标记，准备下一局
    isDealing.value = false
    return
  }

  // 判定是否应当触发流式发牌：处于 CALLING 阶段，且在此局中尚未触发过发牌动画
  const shouldAnimate = gameStore.gamePhase === 'CALLING' && !hasAnimatedInThisDeal

  console.log('[DEBUG] HandCards cards updated:', {
    cardsCount: newCards.length,
    gamePhase: gameStore.gamePhase,
    hasAnimatedInThisDeal,
    shouldAnimate
  })

  if (shouldAnimate) {
    hasAnimatedInThisDeal = true
    isDealing.value = true
    clearAnimateTimer()
    visibleCount.value = 0
    
    let i = 0
    animateTimer.value = window.setInterval(() => {
      if (i < newCards.length) {
        visibleCount.value++
        i++
      } else {
        clearAnimateTimer()
        isDealingTimeout.value = window.setTimeout(() => {
          isDealing.value = false
          isDealingTimeout.value = null
        }, 500)
      }
    }, 120) // 每 120ms 发一张牌
  } else {
    // 局中出牌或者其它阶段，直接全显
    // 如果当前正在播放发牌动画，则在收到局势数据同步时绝对不要强行设为 false 从而强行终止发牌动画
    if (!isDealing.value) {
      isDealing.value = false
      if (!animateTimer.value) {
        visibleCount.value = newCards.length
      }
    }
  }
}, { immediate: true })

function startSelection(index: number) {
  isSelecting.value = true
  startIndex.value = index
  currentIndex.value = index
  window.addEventListener('mouseup', handleGlobalMouseUp)
}

function moveSelection(index: number) {
  if (isSelecting.value) {
    currentIndex.value = index
  }
}

function handleGlobalMouseUp() {
  if (isSelecting.value) {
    const start = Math.min(startIndex.value, currentIndex.value)
    const end = Math.max(startIndex.value, currentIndex.value)
    
    if (start >= 0 && end >= 0) {
      for (let i = start; i <= end; i++) {
        if (i < visibleCount.value) {
          const cardId = props.cards[i]
          if (cardId !== undefined) {
            gameStore.toggleCard(cardId)
          }
        }
      }
    }
    
    // 重置状态
    isSelecting.value = false
    startIndex.value = -1
    currentIndex.value = -1
  }
  window.removeEventListener('mouseup', handleGlobalMouseUp)
}

onUnmounted(() => {
  clearAnimateTimer()
  window.removeEventListener('mouseup', handleGlobalMouseUp)
})
</script>

<template>
  <div class="hand-cards-container">
    <div class="cards-overlap-row">
      <div
        v-for="(cardId, index) in cards"
        :key="cardId"
        class="card-wrapper"
        :class="{
          'is-swiping': isSelecting && index >= Math.min(startIndex, currentIndex) && index <= Math.max(startIndex, currentIndex),
          'card-hidden': isDealing && index >= visibleCount
        }"
        :style="{
          marginRight: index === cards.length - 1 ? '0' : (size === 'sm' ? '-40px' : size === 'lg' ? '-65px' : '-52px'),
          zIndex: index + 1
        }"
        @mousedown.prevent="startSelection(index)"
        @mouseenter="moveSelection(index)"
      >
        <PokerCard
          :card-id="cardId"
          :selected="gameStore.selectedCards.includes(cardId)"
          :hinted="hintedCards?.includes(cardId)"
          :size="size || 'md'"
          :class="{ 'is-dealing-card': isDealing && index < visibleCount }"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.hand-cards-container {
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 12px 0;
  width: 100%;
}

.cards-overlap-row {
  display: inline-flex;
  justify-content: center;
  align-items: flex-end;
  min-height: 170px; /* 留出卡牌选中上浮 24px 的高度差空间 */
}

.card-wrapper {
  position: relative;
  flex: 0 0 auto;
  transition: opacity 0.15s ease, filter 0.15s ease;
}

.card-wrapper :deep(.poker-card) {
  display: flex;
}

:deep(.poker-card.is-dealing-card) {
  animation: cardPopIn 0.4s cubic-bezier(0.25, 0.8, 0.25, 1) forwards;
}

@keyframes cardPopIn {
  from {
    opacity: 0;
    transform: translateX(80px) translateY(10px) scale(0.9);
  }
  to {
    opacity: 1;
    transform: translateX(0) translateY(0) scale(1);
  }
}

.card-wrapper.card-hidden {
  opacity: 0;
  pointer-events: none;
}

/* 滑动经过时的变暗及蓝色发光提示效果 */
.card-wrapper.is-swiping :deep(.poker-card) {
  filter: brightness(0.8) drop-shadow(0 0 8px rgba(0, 123, 255, 0.8));
}
</style>
