import { beforeEach, describe, expect, test, vi } from 'vitest'

const createdAudios: MockAudio[] = []
let rejectNextPlay = false

class MockAudio {
  src: string
  loop = false
  volume = 0
  paused = true
  onerror: ((event: Event) => void) | null = null

  constructor(src: string) {
    this.src = src
    createdAudios.push(this)
  }

  play = vi.fn(() => {
    if (rejectNextPlay) {
      rejectNextPlay = false
      this.paused = true
      return Promise.reject(new Error('autoplay blocked'))
    }
    this.paused = false
    return Promise.resolve()
  })

  pause = vi.fn(() => {
    this.paused = true
  })
}

describe('useSoundEngine BGM', () => {
  beforeEach(() => {
    vi.resetModules()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    createdAudios.length = 0
    rejectNextPlay = false
    localStorage.clear()
    vi.stubGlobal('Audio', MockAudio)
    vi.spyOn(console, 'warn').mockImplementation(() => {})
  })

  test('uses a louder default volume for lobby BGM than game BGM', async () => {
    const { useSoundEngine } = await import('../useSoundEngine')

    const lobbyEngine = useSoundEngine()
    lobbyEngine.startBgm('lobby')
    const lobbyVolume = createdAudios[0]!.volume
    lobbyEngine.stopBgm()

    const gameEngine = useSoundEngine()
    gameEngine.startBgm('game')
    const gameVolume = createdAudios[1]!.volume

    expect(lobbyVolume).toBeGreaterThan(gameVolume)
    expect(lobbyVolume).toBeCloseTo(0.441, 5)
    expect(gameVolume).toBeCloseTo(0.245, 5)
  })

  test('retries blocked BGM playback on the next pointer interaction', async () => {
    rejectNextPlay = true
    const { useSoundEngine } = await import('../useSoundEngine')
    const engine = useSoundEngine()

    engine.startBgm('lobby')
    expect(createdAudios[0]!.play).toHaveBeenCalledTimes(1)

    await Promise.resolve()
    window.dispatchEvent(new Event('pointerdown'))

    expect(createdAudios[0]!.play).toHaveBeenCalledTimes(2)
  })

  test('fills missing bgmStyle with bright without losing saved settings', async () => {
    localStorage.setItem('hmp_sound_settings', JSON.stringify({
      masterVolume: 0.5,
      bgmVolume: 0.4,
      sfxEnabled: false,
    }))

    const { useSoundEngine } = await import('../useSoundEngine')
    const engine = useSoundEngine()

    expect(engine.getSettings()).toMatchObject({
      masterVolume: 0.5,
      bgmVolume: 0.4,
      sfxEnabled: false,
      bgmStyle: 'bright',
    })
  })

  test('uses classic game BGM after bgm style is set to classic', async () => {
    const { useSoundEngine } = await import('../useSoundEngine')
    const engine = useSoundEngine()

    engine.setBgmStyle('classic')
    engine.startBgm('game')

    expect(createdAudios[0]!.src).toContain('playing.mp3')
    expect(engine.getSettings().bgmStyle).toBe('classic')
  })

  test('falls back to classic game BGM when bright source fails', async () => {
    const { useSoundEngine } = await import('../useSoundEngine')
    const engine = useSoundEngine()

    engine.startBgm('game')
    expect(createdAudios[0]!.src).not.toContain('playing.mp3')

    createdAudios[0]!.onerror?.(new Event('error'))

    expect(createdAudios).toHaveLength(2)
    expect(createdAudios[1]!.src).toContain('playing.mp3')
  })
})

describe('useSoundEngine quick chat voice', () => {
  beforeEach(() => {
    vi.resetModules()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    localStorage.clear()
    vi.spyOn(console, 'warn').mockImplementation(() => {})
  })

  test('speaks quick chat text even before browser voices are loaded', async () => {
    const speak = vi.fn()
    const getVoices = vi.fn(() => [])
    const cancel = vi.fn()

    class MockSpeechSynthesisUtterance {
      lang = ''
      rate = 1
      pitch = 1
      volume = 1
      voice?: SpeechSynthesisVoice

      constructor(public text: string) {}
    }

    vi.stubGlobal('SpeechSynthesisUtterance', MockSpeechSynthesisUtterance)
    Object.defineProperty(window, 'speechSynthesis', {
      value: {
        getVoices,
        speak,
        cancel,
        speaking: false,
        pending: false,
      },
      configurable: true,
    })

    const { useSoundEngine } = await import('../useSoundEngine')
    const engine = useSoundEngine()

    engine.playQuickChatVoice('大家好，很高兴见到各位。', 'p2')

    expect(speak).toHaveBeenCalledTimes(1)
    expect(speak.mock.calls[0]![0]).toMatchObject({
      text: '大家好，很高兴见到各位。',
      lang: 'zh-CN',
    })
  })

  test('uses landlord voice clip with boosted volume when quick chat has a mapped sound', async () => {
    const gains: Array<{ gain: { value: number }; connect: ReturnType<typeof vi.fn> }> = []
    const sources: Array<{ buffer: AudioBuffer | null; connect: ReturnType<typeof vi.fn>; start: ReturnType<typeof vi.fn> }> = []

    class MockAudioContext {
      state: AudioContextState = 'running'
      currentTime = 0
      destination = {}

      createGain = vi.fn(() => {
        const gain = { gain: { value: 0 }, connect: vi.fn() }
        gains.push(gain)
        return gain
      })

      createBufferSource = vi.fn(() => {
        const source = { buffer: null as AudioBuffer | null, connect: vi.fn(), start: vi.fn() }
        sources.push(source)
        return source
      })

      decodeAudioData = vi.fn(async () => ({} as AudioBuffer))
      resume = vi.fn(async () => {})
    }

    const fetchMock = vi.fn(async () => ({
      arrayBuffer: async () => new ArrayBuffer(1),
    }))

    vi.stubGlobal('AudioContext', MockAudioContext)
    vi.stubGlobal('fetch', fetchMock)

    const { QUICK_CHAT_VOLUME_BOOST, useSoundEngine } = await import('../useSoundEngine')
    const engine = useSoundEngine()

    await engine.playQuickChatVoice('大家好，很高兴见到各位。', 'p2', 0)

    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('msgChatMsg01.mp3'))
    expect(gains.length).toBe(3)
    expect(sources[0]!.start).toHaveBeenCalledWith(0)
  })

  test('loads female and male dedicated 510K clips without browser speech synthesis', async () => {
    const speak = vi.fn()
    const fetchMock = vi.fn()

    class MockSpeechSynthesisUtterance {
      lang = ''
      rate = 1
      pitch = 1
      volume = 1
      voice?: SpeechSynthesisVoice

      constructor(public text: string) {}
    }

    class MockAudioContext {
      state: AudioContextState = 'running'
      destination = {}

      createGain = vi.fn(() => ({ gain: { value: 0 }, connect: vi.fn() }))
      createBufferSource = vi.fn(() => ({ buffer: null, connect: vi.fn(), start: vi.fn() }))
      decodeAudioData = vi.fn(async () => ({} as AudioBuffer))
      resume = vi.fn(async () => {})
    }

    vi.stubGlobal('AudioContext', MockAudioContext)
    fetchMock.mockResolvedValue({ arrayBuffer: async () => new ArrayBuffer(1) })
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('SpeechSynthesisUtterance', MockSpeechSynthesisUtterance)
    Object.defineProperty(window, 'speechSynthesis', {
      value: {
        getVoices: vi.fn(() => []),
        speak,
        cancel: vi.fn(),
        speaking: false,
        pending: false,
      },
      configurable: true,
    })

    const { useSoundEngine } = await import('../useSoundEngine')
    const engine = useSoundEngine()

    const clips = [
      ['fifty_k_true', 'true_510k'],
      ['fifty_k_false', '510k'],
      ['club_three_first', 'club_three_first'],
    ] as const

    for (const gender of ['female', 'male'] as const) {
      engine.setVoiceGender(gender)
      for (const [soundName] of clips) {
        await engine.playSound(soundName, 'p2')
      }
    }

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual(
      ['female', 'male'].flatMap(gender =>
        clips.map(([, fileName]) => `/static/audio/fifty_k/${gender}/${fileName}.mp3`),
      ),
    )
    expect(speak).not.toHaveBeenCalled()
  })

  test('does not use browser speech synthesis when a local 510K WAV fetch fails', async () => {
    const speak = vi.fn()
    const createParam = () => ({
      setValueAtTime: vi.fn(),
      linearRampToValueAtTime: vi.fn(),
      exponentialRampToValueAtTime: vi.fn(),
    })
    const createOscillator = () => ({
      type: 'sine',
      frequency: createParam(),
      connect: vi.fn(),
      start: vi.fn(),
      stop: vi.fn(),
    })

    class MockAudioContext {
      state: AudioContextState = 'running'
      currentTime = 0
      destination = {}

      createGain = vi.fn(() => ({ gain: { value: 0, ...createParam() }, connect: vi.fn() }))
      createOscillator = vi.fn(createOscillator)
      resume = vi.fn(async () => {})
    }

    vi.stubGlobal('AudioContext', MockAudioContext)
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('WAV unavailable')))
    vi.stubGlobal('SpeechSynthesisUtterance', class {})
    Object.defineProperty(window, 'speechSynthesis', {
      value: {
        getVoices: vi.fn(() => []),
        speak,
        cancel: vi.fn(),
        speaking: false,
        pending: false,
      },
      configurable: true,
    })

    const { useSoundEngine } = await import('../useSoundEngine')
    const engine = useSoundEngine()
    engine.setVoiceGender('female')

    await engine.playSound('fifty_k_true', 'p2')
    await engine.playSound('fifty_k_false', 'p2')
    await engine.playSound('club_three_first', 'p2')

    expect(speak).not.toHaveBeenCalled()
  })
})
