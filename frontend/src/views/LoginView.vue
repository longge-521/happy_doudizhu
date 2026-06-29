<!-- frontend/src/views/LoginView.vue -->
<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { usePlayerStore } from '@/stores/playerStore'

const router = useRouter()
const playerStore = usePlayerStore()

const mode = ref<'login' | 'register'>('login')
const accountInput = ref(localStorage.getItem('hmp_username') || '')
const passwordInput = ref('')
const nicknameInput = ref(localStorage.getItem('hmp_nickname') || '')
const error = ref('')
const showDebugConsole = import.meta.env.DEV

if (playerStore.playerId && playerStore.nickname) {
  router.push('/lobby')
}

const title = computed(() => mode.value === 'login' ? '账号登录' : '注册账号')
const submitText = computed(() => mode.value === 'login' ? '登录进入大厅' : '注册并进入大厅')

function switchMode(nextMode: 'login' | 'register') {
  mode.value = nextMode
  error.value = ''
}

async function handleSubmit() {
  const account = accountInput.value.trim()
  const password = passwordInput.value
  const nickname = nicknameInput.value.trim()

  const result = mode.value === 'login'
    ? await playerStore.login(account, password)
    : await playerStore.register(account, password, nickname)

  if (!result.ok) {
    error.value = result.error || '操作失败，请重试'
    return
  }

  router.push('/lobby')
}
</script>

<template>
  <div class="login-platform">
    <button v-if="showDebugConsole" class="btn-console-entrance" @click="router.push('/console')">
      ⚙️ 系统调试控制台
    </button>
    <section class="login-shell">
      <div class="brand-side">
        <span class="logo-emoji">🃏</span>
        <h1 class="logo-title">欢乐斗地主</h1>
        <p class="logo-subtitle">固定账号进入大厅，战绩和欢乐豆跟着你走</p>
      </div>

      <div class="glass-panel login-card">
        <div class="mode-tabs" role="tablist" aria-label="登录方式">
          <button
            type="button"
            class="mode-tab"
            :class="{ active: mode === 'login' }"
            @click="switchMode('login')"
          >
            登录
          </button>
          <button
            type="button"
            class="mode-tab"
            :class="{ active: mode === 'register' }"
            @click="switchMode('register')"
          >
            注册
          </button>
        </div>

        <form @submit.prevent="handleSubmit" class="login-form">
          <h2>{{ title }}</h2>

          <label class="input-group" for="account">
            <span>账号</span>
            <input
              id="account"
              v-model="accountInput"
              type="text"
              placeholder="输入账号"
              maxlength="24"
              autocomplete="username"
              @input="error = ''"
            />
          </label>

          <label class="input-group" for="password">
            <span>密码</span>
            <input
              id="password"
              v-model="passwordInput"
              type="password"
              placeholder="输入密码"
              maxlength="32"
              autocomplete="current-password"
              @input="error = ''"
            />
          </label>

          <label v-if="mode === 'register'" class="input-group" for="nickname">
            <span>玩家昵称</span>
            <input
              id="nickname"
              v-model="nicknameInput"
              type="text"
              placeholder="显示在牌桌上的名字"
              maxlength="12"
              autocomplete="nickname"
              @input="error = ''"
            />
          </label>

          <span v-if="error" class="error-text">{{ error }}</span>

          <button type="submit" class="btn-premium login-btn">
            {{ submitText }}
          </button>
        </form>
      </div>
    </section>
  </div>
</template>

<style>
.login-platform {
  min-height: 100vh;
  width: 100vw;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 28px;
  color: #fff;
  overflow: hidden;
  box-sizing: border-box;
  font-family: 'Outfit', 'Inter', system-ui, -apple-system, sans-serif;
  background:
    radial-gradient(circle at 62% 42%, rgba(78, 178, 255, 0.9), rgba(25, 87, 170, 0.94) 42%, rgba(10, 41, 95, 1) 76%),
    linear-gradient(135deg, #14356f 0%, #1f7cc8 100%);
}

.login-platform .login-shell {
  width: min(880px, 100%);
  display: grid;
  grid-template-columns: 1fr 380px;
  gap: 36px;
  align-items: center;
}

.login-platform .brand-side {
  color: #fff;
  text-shadow: 0 3px 10px rgba(0, 0, 0, 0.35);
}

.login-platform .logo-emoji {
  font-size: 4rem;
  display: block;
  margin-bottom: 12px;
}

.login-platform .logo-title {
  font-size: clamp(2.4rem, 6vw, 4.8rem);
  line-height: 1;
  font-weight: 900;
  margin: 0;
  color: #fff;
}

.login-platform .logo-subtitle {
  max-width: 360px;
  margin: 18px 0 0;
  font-size: 1.05rem;
  color: rgba(255, 255, 255, 0.82);
}

.login-platform .login-card {
  padding: 22px;
}

.login-platform .mode-tabs {
  display: grid;
  grid-template-columns: 1fr 1fr;
  padding: 4px;
  border-radius: 8px;
  background: rgba(7, 28, 72, 0.56);
  margin-bottom: 20px;
}

.login-platform .mode-tab {
  border: none;
  border-radius: 6px;
  padding: 10px 0;
  color: rgba(255, 255, 255, 0.72);
  background: transparent;
  font-weight: 900;
  cursor: pointer;
}

.login-platform .mode-tab.active {
  color: #33210a;
  background: linear-gradient(135deg, #ffe082 0%, #ff9f1a 100%);
}

.login-platform .login-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.login-platform .login-form h2 {
  margin: 0 0 4px;
  font-size: 1.35rem;
  font-weight: 900;
  color: #fff;
}

.login-platform .input-group {
  display: flex;
  flex-direction: column;
  gap: 7px;
  color: rgba(255, 255, 255, 0.8);
  font-size: 0.9rem;
  font-weight: 800;
}

.login-platform .input-group input {
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.18);
  border-radius: 8px;
  padding: 12px 14px;
  color: #ffffff;
  font-size: 1rem;
  outline: none;
  transition: border-color 0.2s, box-shadow 0.2s, background 0.2s;
}

.login-platform .input-group input:focus {
  border-color: #ffca28;
  background: rgba(255, 255, 255, 0.14);
  box-shadow: 0 0 0 3px rgba(255, 202, 40, 0.16);
}

.login-platform .error-text {
  color: #ffb4a8;
  font-size: 0.86rem;
  font-weight: 700;
}

.login-platform .login-btn {
  padding: 13px;
  font-size: 1.05rem;
  margin-top: 6px;
}

@media (max-width: 760px) {
  .login-platform {
    padding: 18px;
  }

  .login-platform .login-shell {
    grid-template-columns: 1fr;
    gap: 22px;
  }

  .login-platform .brand-side {
    text-align: center;
  }

  .login-platform .logo-subtitle {
    margin-left: auto;
    margin-right: auto;
  }
}

.btn-console-entrance {
  position: absolute;
  top: 24px;
  left: 24px;
  background: rgba(255, 255, 255, 0.08);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border: 1.5px solid rgba(255, 255, 255, 0.25);
  color: #ffffff;
  padding: 8px 20px;
  border-radius: 20px;
  font-weight: 800;
  font-size: 0.9rem;
  cursor: pointer;
  box-shadow: 0 4px 12px rgba(0,0,0,0.3);
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  gap: 6px;
  z-index: 10;
}

.btn-console-entrance:hover {
  background: rgba(255, 255, 255, 0.18);
  transform: scale(1.03);
  border-color: #ffd700;
  box-shadow: 0 0 12px rgba(255, 215, 0, 0.4);
}
</style>
