# 欢乐斗地主 BGM 优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 优化欢乐斗地主大厅与牌局 BGM：提高大厅默认听感，支持牌局轻快/经典曲风，并在轻快曲源失败时回退经典曲源。

**Architecture:** 继续以 `frontend/src/composables/useSoundEngine.ts` 作为音频统一入口，不新增全局状态库。新增集中式 BGM 配置、`bgmStyle` 设置字段、最终音量计算函数和 HTMLAudio 错误回退逻辑，测试通过 mock `Audio` 和 `localStorage` 验证行为。

**Tech Stack:** Vue 3、TypeScript、Vite、Vitest、浏览器 `HTMLAudioElement`。

## Global Constraints

- 禁止批量删除文件或目录。
- 文档生成使用中文。
- 只修改必要代码，不重构无关文件。
- 不直接接入或复制未授权的腾讯欢乐斗地主原始音乐资源。
- 不改变后端或 WebSocket 协议。
- 保持现有主音量、音效音量、BGM 音量、音效开关和 BGM 开关语义不变。

---

## File Structure

- Modify: `frontend/src/composables/useSoundEngine.ts`
  - 负责声音设置读取/保存、BGM 曲源选择、音量计算、播放和回退。
- Create: `frontend/src/composables/__tests__/useSoundEngine.spec.ts`
  - 负责验证 BGM 默认音量、设置兼容、曲风选择和失败回退。

---

### Task 1: BGM 默认音量和设置兼容测试

**Files:**
- Create: `frontend/src/composables/__tests__/useSoundEngine.spec.ts`
- Modify: `frontend/src/composables/useSoundEngine.ts`

**Interfaces:**
- Consumes: `useSoundEngine()`
- Produces: `getSettings(): Readonly<SoundSettings>` 返回包含 `bgmStyle: 'bright' | 'classic'`
- Produces: `startBgm(name: BgmName): void` 使用场景增益计算 BGM 音量

- [ ] **Step 1: Write the failing test**

```ts
import { beforeEach, describe, expect, test, vi } from 'vitest'

const createdAudios: MockAudio[] = []

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
    createdAudios.length = 0
    localStorage.clear()
    vi.stubGlobal('Audio', MockAudio)
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
    expect(lobbyVolume).toBeCloseTo(0.37975, 5)
    expect(gameVolume).toBeCloseTo(0.245, 5)
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
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test:unit -- src/composables/__tests__/useSoundEngine.spec.ts`

Expected: FAIL because `bgmStyle` does not exist and lobby/game BGM volume currently both use `settings.bgmVolume * settings.masterVolume`.

- [ ] **Step 3: Write minimal implementation**

In `useSoundEngine.ts`, add:

```ts
export type BgmStyle = 'bright' | 'classic'

interface SoundSettings {
  masterVolume: number
  sfxEnabled: boolean
  bgmEnabled: boolean
  sfxVolume: number
  bgmVolume: number
  bgmStyle: BgmStyle
  voiceGender: 'male' | 'female' | 'auto'
  customVoiceEnabled: boolean
}

const DEFAULT_SETTINGS: SoundSettings = {
  masterVolume: 0.7,
  sfxEnabled: true,
  bgmEnabled: true,
  sfxVolume: 0.8,
  bgmVolume: 0.35,
  bgmStyle: 'bright',
  voiceGender: 'auto',
  customVoiceEnabled: false,
}
```

Add `calculateBgmVolume(name)` so lobby uses `1.55` and game uses `1.0`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm run test:unit -- src/composables/__tests__/useSoundEngine.spec.ts`

Expected: PASS for the two tests in this task.

---

### Task 2: BGM 曲风选择和失败回退

**Files:**
- Modify: `frontend/src/composables/__tests__/useSoundEngine.spec.ts`
- Modify: `frontend/src/composables/useSoundEngine.ts`

**Interfaces:**
- Consumes: `setBgmStyle(style: BgmStyle): void`
- Produces: `startBgm('game')` uses bright source by default and classic source when `bgmStyle` is `classic`
- Produces: light/bright source error falls back to classic source

- [ ] **Step 1: Write the failing test**

Append tests:

```ts
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test:unit -- src/composables/__tests__/useSoundEngine.spec.ts`

Expected: FAIL because `setBgmStyle` does not exist and `startBgm` has no fallback logic.

- [ ] **Step 3: Write minimal implementation**

In `useSoundEngine.ts`, add:

```ts
const BGM_CONFIG = {
  lobby: {
    gain: 1.55,
    sources: {
      bright: 'background.mp3',
      classic: 'background.mp3',
    },
  },
  game: {
    gain: 1,
    sources: {
      bright: 'background.mp3',
      classic: 'playing.mp3',
    },
  },
} satisfies Record<BgmName, { gain: number; sources: Record<BgmStyle, string> }>
```

Update `startBgm(name)` to pick `settings.bgmStyle`, bind `onerror`, and retry classic when a non-classic source fails.

Add:

```ts
function setBgmStyle(style: BgmStyle) {
  settings.bgmStyle = style
  saveSettings()
}
```

Return `setBgmStyle` from `useSoundEngine()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm run test:unit -- src/composables/__tests__/useSoundEngine.spec.ts`

Expected: PASS for all `useSoundEngine BGM` tests.

---

### Task 3: Full frontend verification

**Files:**
- Modify: `frontend/src/composables/useSoundEngine.ts`
- Test: `frontend/src/composables/__tests__/useSoundEngine.spec.ts`

**Interfaces:**
- Consumes: all prior task changes
- Produces: verified frontend audio behavior

- [ ] **Step 1: Run focused unit tests**

Run: `cd frontend && npm run test:unit -- src/composables/__tests__/useSoundEngine.spec.ts`

Expected: PASS.

- [ ] **Step 2: Run existing composable tests**

Run: `cd frontend && npm run test:unit -- src/composables/__tests__`

Expected: PASS.

- [ ] **Step 3: Run type check**

Run: `cd frontend && npm run type-check`

Expected: PASS. If existing unrelated TypeScript errors appear, record them with file paths and do not hide them.

- [ ] **Step 4: Review diff**

Run: `git diff -- frontend/src/composables/useSoundEngine.ts frontend/src/composables/__tests__/useSoundEngine.spec.ts docs/superpowers/plans/2026-06-29-doudizhu-audio-bgm.md`

Expected: Diff only contains BGM settings, tests, and this plan.
