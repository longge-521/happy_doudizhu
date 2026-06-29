<script setup lang="ts">
import { RouterView } from 'vue-router'
</script>

<template>
  <RouterView />
</template>

<style>
/* 全局重置，保障全屏纸牌桌面布局 */
html, body, #app {
  margin: 0;
  padding: 0;
  width: 100%;
  height: 100%;
  background-color: #0d2f11;
  overflow: hidden;
}
</style>
