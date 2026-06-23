// frontend/src/stores/playerStore.ts
import { defineStore } from 'pinia'
import { ref } from 'vue'

export const usePlayerStore = defineStore('player', () => {
  const playerId = ref(localStorage.getItem('hmp_player_id') || '')
  const nickname = ref(localStorage.getItem('hmp_nickname') || '')
  const beans = ref(10000)
  const totalGames = ref(0)
  const winRate = ref(0)

  function login(id: string, name: string) {
    playerId.value = id
    nickname.value = name
    localStorage.setItem('hmp_player_id', id)
    localStorage.setItem('hmp_nickname', name)
  }

  function logout() {
    playerId.value = ''
    nickname.value = ''
    localStorage.removeItem('hmp_player_id')
    localStorage.removeItem('hmp_nickname')
  }

  return { playerId, nickname, beans, totalGames, winRate, login, logout }
})
