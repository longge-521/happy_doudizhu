import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { usePlayerStore } from '@/stores/playerStore'
import { useGameStore } from '@/stores/gameStore'
import LobbyView from '../LobbyView.vue'

vi.mock('@/composables/useGameWebSocket', () => ({
  useGameWebSocket: () => ({
    connect: vi.fn(),
    disconnect: vi.fn(),
    sendAction: vi.fn(),
  }),
}))

vi.mock('@/composables/useSoundEngine', () => ({
  useSoundEngine: () => ({
    playSound: vi.fn(),
    startBgm: vi.fn(),
    stopBgm: vi.fn(),
    unlock: vi.fn(),
  }),
}))

vi.mock('@/components/SettingsModal.vue', () => ({
  default: {
    name: 'SettingsModal',
    template: '<div data-testid="settings-modal-stub" />',
  },
}))

const push = vi.fn()

vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
}))

function mountLobby(playerOverrides: Record<string, unknown> = {}) {
  localStorage.setItem('hmp_player_id', 'player123')
  localStorage.setItem('hmp_nickname', '请叫我longge')
  localStorage.setItem('hmp_username', 'longge')
  localStorage.setItem('hmp_game_auth_token', 'token123')
  localStorage.setItem('hmp_avatar_url', 'https://example.com/avatar.png')

  const pinia = createPinia()
  setActivePinia(pinia)

  const player = usePlayerStore()
  Object.assign(player, {
    playerId: 'player123',
    nickname: '请叫我longge',
    username: 'longge',
    avatarUrl: 'https://example.com/avatar.png',
    beans: 6820,
    totalGames: 12,
    winRate: 0.5,
    rankId: 2,
    subRank: 2,
    stars: 1,
    rankTitle: '短工II',
    modifyAvatar: vi.fn().mockResolvedValue({ ok: true }),
    fetchProfile: vi.fn().mockResolvedValue(undefined),
    modifyBeans: vi.fn().mockResolvedValue({ ok: true }),
    modifyRank: vi.fn().mockResolvedValue({ ok: true }),
    logout: vi.fn(),
    ...playerOverrides,
  })

  const game = useGameStore()
  Object.assign(game, {
    gamePhase: 'IDLE',
    wsConnected: false,
    reset: vi.fn(),
  })

  return mount(LobbyView, {
    global: {
      plugins: [pinia],
    },
  })
}

describe('LobbyView profile avatar UI', () => {
  beforeEach(() => {
    push.mockReset()
    localStorage.clear()
    vi.restoreAllMocks()
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [],
      }),
    )
  })

  it('labels the top-left action as logout', () => {
    const wrapper = mountLobby()

    expect(wrapper.find('.btn-back .back-text').text()).toBe('退出')
    expect(wrapper.find('.btn-back').attributes('aria-label')).toBe('退出登录')
  })

  it('renders avatar image in the bottom user card', () => {
    const wrapper = mountLobby()

    const image = wrapper.find('.bottom-user-card .avatar-image')
    expect(image.exists()).toBe(true)
    expect(image.attributes('src')).toBe('https://example.com/avatar.png')
  })

  it('opens profile modal from bottom user card', async () => {
    const wrapper = mountLobby()

    await wrapper.find('.bottom-user-card').trigger('click')

    expect(wrapper.find('.profile-modal').exists()).toBe(true)
    expect(wrapper.find('.profile-modal').text()).toContain('个人资料')
    expect(wrapper.find('input.profile-avatar-input').exists()).toBe(true)
  })

  it('opens the beans and rank editor in development builds', async () => {
    const wrapper = mountLobby()

    await wrapper.find('.asset-pill.gold-beans').trigger('click')

    expect(wrapper.text()).toContain('修改资产与排位')
  })
})
