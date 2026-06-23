<!-- frontend/src/components/PokerCard.vue -->
<script setup lang="ts">
import { computed } from 'vue'
import { getCardDisplay } from '@/utils/cardUtils'

const props = withDefaults(
  defineProps<{
    cardId: number
    selected?: boolean
    faceDown?: boolean
    size?: 'sm' | 'md' | 'lg'
    noHover?: boolean
  }>(),
  {
    selected: false,
    faceDown: false,
    size: 'md',
    noHover: false,
  }
)

const card = computed(() => getCardDisplay(props.cardId))
const isJoker = computed(() => card.value.suit === 'joker')
</script>

<template>
  <div
    v-if="faceDown"
    class="poker-card face-down no-hover"
    :class="`size-${size}`"
  />
  <div
    v-else
    class="poker-card"
    :class="[
      card.color,
      `size-${size}`,
      { selected: selected, 'no-hover': noHover, 'is-joker': isJoker }
    ]"
  >
    <!-- 大小王布局 -->
    <template v-if="isJoker">
      <div class="joker-text">{{ card.rank }}王</div>
    </template>

    <!-- 常规花色布局 -->
    <template v-else>
      <div class="card-corner corner-top">
        <span class="card-rank">{{ card.rank }}</span>
        <span class="card-suit-mini">{{ card.suitSymbol }}</span>
      </div>
      <div class="card-center">
        {{ card.suitSymbol }}
      </div>
      <div class="card-corner corner-bottom" style="transform: rotate(180deg);">
        <span class="card-rank">{{ card.rank }}</span>
        <span class="card-suit-mini">{{ card.suitSymbol }}</span>
      </div>
    </template>
  </div>
</template>
