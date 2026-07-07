import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { usePlayerStore } from '../playerStore'

function mockFetch(response: unknown, ok = true) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok,
    json: () => Promise.resolve(response),
  }))
}

describe('playerStore avatar profile state', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
    setActivePinia(createPinia())
  })

  it('hydrates avatarUrl from fetched profile data', async () => {
    localStorage.setItem('hmp_player_id', 'player123')
    localStorage.setItem('hmp_nickname', 'TestNick')
    localStorage.setItem('hmp_game_auth_token', 'token123')
    setActivePinia(createPinia())
    const store = usePlayerStore()
    mockFetch({
      nickname: 'TestNick',
      beans: 12000,
      total_games: 10,
      win_rate: 0.6,
      rank_id: 2,
      sub_rank: 3,
      stars: 1,
      rank_title: '短工III',
      avatar_url: 'https://example.com/avatar.png',
    })

    await store.fetchProfile()

    expect(store.avatarUrl).toBe('https://example.com/avatar.png')
    expect(localStorage.getItem('hmp_avatar_url')).toBe('https://example.com/avatar.png')
  })

  it('updates avatarUrl through profile avatar api', async () => {
    localStorage.setItem('hmp_player_id', 'player123')
    localStorage.setItem('hmp_nickname', 'TestNick')
    localStorage.setItem('hmp_game_auth_token', 'token123')
    setActivePinia(createPinia())
    const store = usePlayerStore()
    mockFetch({
      ok: true,
      player_id: 'player123',
      avatar_url: 'https://example.com/new-avatar.png',
    })

    const result = await store.modifyAvatar('https://example.com/new-avatar.png')

    expect(result.ok).toBe(true)
    expect(store.avatarUrl).toBe('https://example.com/new-avatar.png')
    expect(fetch).toHaveBeenCalledWith('/api/game/profile/player123/update', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: 'Bearer token123',
      },
      body: JSON.stringify({
        nickname: 'TestNick',
        avatar_url: 'https://example.com/new-avatar.png',
      }),
    })
  })

  it('clears avatarUrl when api returns null', async () => {
    localStorage.setItem('hmp_player_id', 'player123')
    localStorage.setItem('hmp_nickname', 'TestNick')
    localStorage.setItem('hmp_avatar_url', 'https://example.com/old.png')
    localStorage.setItem('hmp_game_auth_token', 'token123')
    setActivePinia(createPinia())
    const store = usePlayerStore()
    mockFetch({ ok: true, player_id: 'player123', avatar_url: null })

    const result = await store.modifyAvatar('')

    expect(result.ok).toBe(true)
    expect(store.avatarUrl).toBe('')
    expect(localStorage.getItem('hmp_avatar_url')).toBeNull()
  })

  it('clears cached avatar when session changes and profile fetch is not ok', async () => {
    localStorage.setItem('hmp_player_id', 'old-player')
    localStorage.setItem('hmp_nickname', 'OldNick')
    localStorage.setItem('hmp_username', 'old-user')
    localStorage.setItem('hmp_game_auth_token', 'old-token')
    localStorage.setItem('hmp_avatar_url', 'https://example.com/old-avatar.png')
    setActivePinia(createPinia())

    const store = usePlayerStore()
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          ok: true,
          player_id: 'new-player',
          nickname: 'NewNick',
          username: 'new-user',
          auth_token: 'new-token',
        }),
      })
      .mockResolvedValueOnce({
        ok: false,
        json: () => Promise.resolve({ detail: 'profile unavailable' }),
      })
    vi.stubGlobal('fetch', fetchMock)

    const result = await store.login('new-user', 'pass123')

    expect(result.ok).toBe(true)
    expect(store.playerId).toBe('new-player')
    expect(store.avatarUrl).toBe('')
    expect(localStorage.getItem('hmp_avatar_url')).toBeNull()
  })
})
