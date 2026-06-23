<!-- frontend/src/views/LoginView.vue -->
<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { usePlayerStore } from '@/stores/playerStore'

const router = useRouter()
const playerStore = usePlayerStore()

const nicknameInput = ref('')
const error = ref('')

// 若已登录则直接进入大厅
if (playerStore.playerId && playerStore.nickname) {
  router.push('/lobby')
}

function handleLogin() {
  const name = nicknameInput.value.trim()
  if (!name) {
    error.value = '请输入您的游戏昵称'
    return
  }
  
  // 随机生成玩家 ID 并写入 store 进行缓存
  const randomId = 'p_' + Math.floor(100000 + Math.random() * 900000)
  playerStore.login(randomId, name)
  router.push('/lobby')
}
</script>

<template>
  <div class="game-table flex-center">
    <div class="glass-panel login-card">
      <div class="logo-area">
        <span class="logo-emoji">🃏</span>
        <h1 class="logo-title">欢乐斗地主</h1>
        <p class="logo-subtitle">HMP Web Card Game</p>
      </div>

      <form @submit.prevent="handleLogin" class="login-form">
        <div class="input-group">
          <label for="nickname">玩家昵称</label>
          <input
            id="nickname"
            v-model="nicknameInput"
            type="text"
            placeholder="输入您的昵称..."
            maxlength="12"
            autocomplete="off"
            @input="error = ''"
          />
          <span v-if="error" class="error-text">{{ error }}</span>
        </div>

        <button type="submit" class="btn-premium login-btn">
          进入大厅
        </button>
      </form>
    </div>
  </div>
</template>

<style scoped>
.flex-center {
  display: flex;
  justify-content: center;
  align-items: center;
}

.login-card {
  width: 100%;
  max-width: 400px;
  padding: 40px 30px;
  text-align: center;
  box-sizing: border-box;
}

.logo-area {
  margin-bottom: 30px;
}

.logo-emoji {
  font-size: 4rem;
  display: block;
  margin-bottom: 10px;
  animation: float 3s ease-in-out infinite;
}

@keyframes float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-10px); }
}

.logo-title {
  font-size: 2.2rem;
  font-weight: 800;
  margin: 0;
  background: linear-gradient(135deg, #ffd700 0%, #ff8f00 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.logo-subtitle {
  font-size: 0.9rem;
  opacity: 0.6;
  margin: 5px 0 0 0;
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.input-group {
  display: flex;
  flex-direction: column;
  text-align: left;
  gap: 8px;
}

.input-group label {
  font-size: 0.9rem;
  font-weight: 600;
  opacity: 0.8;
}

.input-group input {
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 8px;
  padding: 12px 16px;
  color: #ffffff;
  font-size: 1rem;
  outline: none;
  transition: all 0.2s ease;
}

.input-group input:focus {
  border-color: #ffb300;
  background: rgba(255, 255, 255, 0.12);
  box-shadow: 0 0 10px rgba(255, 179, 0, 0.2);
}

.error-text {
  color: #ef5350;
  font-size: 0.8rem;
}

.login-btn {
  padding: 14px;
  font-size: 1.1rem;
  margin-top: 10px;
}
</style>
