// frontend/src/stores/playerStore.ts
import { defineStore } from 'pinia'
import { ref } from 'vue'

export const usePlayerStore = defineStore('player', () => {
  const playerId = ref(localStorage.getItem('hmp_player_id') || '')
  const nickname = ref(localStorage.getItem('hmp_nickname') || '')
  const username = ref(localStorage.getItem('hmp_username') || '')
  const authToken = ref(localStorage.getItem('hmp_game_auth_token') || '')
  const beans = ref(10000)
  const totalGames = ref(0)
  const winRate = ref(0)
  const rankId = ref(1)
  const subRank = ref(4)
  const stars = ref(0)
  const rankTitle = ref('包身工IV')

  function authHeaders(): Record<string, string> {
    return authToken.value ? { Authorization: `Bearer ${authToken.value}` } : {}
  }

  function setSession(id: string, name: string, accountName: string, token: string) {
    playerId.value = id
    nickname.value = name
    username.value = accountName
    authToken.value = token
    localStorage.setItem('hmp_player_id', id)
    localStorage.setItem('hmp_nickname', name)
    localStorage.setItem('hmp_username', accountName)
    localStorage.setItem('hmp_game_auth_token', token)
  }

  async function fetchProfile() {
    if (!playerId.value) return
    try {
      const res = await fetch(`/api/game/profile/${playerId.value}`, {
        headers: authHeaders(),
      })
      if (res.ok) {
        const data = await res.json()
        beans.value = data.beans
        totalGames.value = data.total_games
        winRate.value = data.win_rate || 0
        rankId.value = data.rank_id || 1
        subRank.value = data.sub_rank || 4
        stars.value = data.stars || 0
        rankTitle.value = data.rank_title || '包身工IV'
      }
    } catch (e) {
      console.error('Failed to fetch player profile:', e)
    }
  }

  async function register(accountName: string, password: string, name: string): Promise<{ ok: boolean; error?: string }> {
    const normalized = accountName.trim().toLowerCase()
    const displayName = name.trim()
    if (!normalized || normalized.length < 3) {
      return { ok: false, error: '账号至少需要 3 个字符' }
    }
    if (!/^[a-zA-Z0-9_-]+$/.test(normalized)) {
      return { ok: false, error: '账号只能包含字母、数字、下划线或短横线' }
    }
    if (password.length < 4) {
      return { ok: false, error: '密码至少需要 4 位' }
    }
    if (!displayName) {
      return { ok: false, error: '请输入玩家昵称' }
    }

    try {
      const res = await fetch('/api/game/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: normalized,
          password: password,
          nickname: displayName
        })
      })
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}))
        return { ok: false, error: errData.detail || '注册失败' }
      }
      const data = await res.json()
      if (data.ok) {
        setSession(data.player_id, data.nickname, data.username, data.auth_token)
        await fetchProfile()
        return { ok: true }
      }
      return { ok: false, error: '注册返回异常' }
    } catch (e: any) {
      return { ok: false, error: e.message || '网络连接失败' }
    }
  }

  async function login(accountName: string, password: string): Promise<{ ok: boolean; error?: string }> {
    const normalized = accountName.trim().toLowerCase()
    if (!normalized) {
      return { ok: false, error: '请输入账号' }
    }
    if (!password) {
      return { ok: false, error: '请输入密码' }
    }

    try {
      const res = await fetch('/api/game/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: normalized,
          password: password
        })
      })
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}))
        return { ok: false, error: errData.detail || '密码不正确或登录失败' }
      }
      const data = await res.json()
      if (data.ok) {
        setSession(data.player_id, data.nickname, data.username, data.auth_token)
        await fetchProfile()
        return { ok: true }
      }
      return { ok: false, error: '登录返回异常' }
    } catch (e: any) {
      return { ok: false, error: e.message || '网络连接失败' }
    }
  }

  function logout() {
    playerId.value = ''
    nickname.value = ''
    username.value = ''
    authToken.value = ''
    localStorage.removeItem('hmp_player_id')
    localStorage.removeItem('hmp_nickname')
    localStorage.removeItem('hmp_username')
    localStorage.removeItem('hmp_game_auth_token')
  }

  async function modifyBeans(newBeans: number): Promise<{ ok: boolean; error?: string }> {
    if (newBeans < 0) {
      return { ok: false, error: '欢乐豆不能为负数' }
    }
    try {
      const res = await fetch(`/api/game/profile/${playerId.value}/beans`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({ beans: newBeans })
      })
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}))
        return { ok: false, error: errData.detail || '修改欢乐豆失败' }
      }
      const data = await res.json()
      beans.value = data.beans
      return { ok: true }
    } catch (e: any) {
      return { ok: false, error: e.message || '网络连接失败' }
    }
  }

  async function modifyRank(rid: number, srank: number, starCount: number): Promise<{ ok: boolean; error?: string }> {
    try {
      const res = await fetch(`/api/game/profile/${playerId.value}/rank`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({ rank_id: rid, sub_rank: srank, stars: starCount })
      })
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}))
        return { ok: false, error: errData.detail || '修改排位失败' }
      }
      const data = await res.json()
      rankId.value = data.rank_id
      subRank.value = data.sub_rank
      stars.value = data.stars
      await fetchProfile()
      return { ok: true }
    } catch (e: any) {
      return { ok: false, error: e.message || '网络连接失败' }
    }
  }

  return {
    playerId, nickname, username, authToken, beans, totalGames, winRate,
    rankId, subRank, stars, rankTitle,
    register, login, logout, fetchProfile, modifyBeans, modifyRank
  }
})
