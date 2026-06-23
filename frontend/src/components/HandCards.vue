<!-- frontend/src/components/HandCards.vue -->
<script setup lang="ts">
import { useGameStore } from '@/stores/gameStore'
import PokerCard from './PokerCard.vue'

defineProps<{
  cards: number[]
  size?: 'sm' | 'md' | 'lg'
}>()

const gameStore = useGameStore()

function handleCardClick(cardId: number) {
  gameStore.toggleCard(cardId)
}
</script>

<template>
  <div class="hand-cards-container">
    <div class="cards-overlap-row">
      <div
        v-for="(cardId, index) in cards"
        :key="cardId"
        class="card-wrapper"
        :style="{
          zIndex: index,
          marginRight: index === cards.length - 1 ? '0' : (size === 'sm' ? '-40px' : size === 'lg' ? '-65px' : '-52px')
        }"
        @click="handleCardClick(cardId)"
      >
        <PokerCard
          :card-id="cardId"
          :selected="gameStore.selectedCards.includes(cardId)"
          :size="size || 'md'"
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
  transition: all 0.15s ease;
}
</style>
