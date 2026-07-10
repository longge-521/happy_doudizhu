// frontend/src/composables/useSoundEngine.ts
// 斗地主音效引擎 — CDN 动态音频加载版，原汁原味欢乐斗地主语音包与 BGM

export type SoundName =
  | 'matchSuccess'
  | 'dealCard'
  | 'selectCard'
  | 'flipBottomCard'
  | 'playCard'
  | 'tick'
  | 'tickUrgent'
  | 'chatMsg'
  | 'redeal'
  | 'btnClick'
  | 'doubling'
  | 'showCards'
  | 'mingpai'
  | 'callLandlord'
  // 人声及特殊牌型
  | 'callLandlord'
  | 'robLandlord'
  | 'skipCall'
  | 'skipRob'
  | 'landlordDecided'
  | 'pass'
  | 'bomb'
  | 'fifty_k_true'
  | 'fifty_k_false'
  | 'rocket'
  | 'airplane'
  | 'straight'
  | 'double_straight'
  | 'three_one'
  | 'three_two'
  | 'jiabei'
  | 'bujiabei'
  | 'superDouble'
  // 特效物理音效
  | 'bomb_effect'
  | 'plane_effect'
  | 'shunzi_effect'
  // 胜负 BGM
  | 'gameWin'
  | 'gameLose'
  | 'win'
  | 'lose'
  | `${number}`
  | `pair${number}`
  | `three_one${number}`
  | `msgChatMsg${string}`
  | 'baojing1'
  | 'baojing2'

export type BgmName = 'lobby' | 'game'
export type BgmStyle = 'bright' | 'classic'

interface PlaySoundOptions {
  volumeBoost?: number
}

interface SoundSettings {
  masterVolume: number    // 0~1
  sfxEnabled: boolean
  bgmEnabled: boolean
  sfxVolume: number       // 0~1
  bgmVolume: number       // 0~1
  bgmStyle: BgmStyle
  voiceGender: 'male' | 'female' | 'auto'
  customVoiceEnabled: boolean
}

// ─── 全局状态单例 ───
let audioCtx: AudioContext | null = null
let masterGain: GainNode | null = null
let sfxGain: GainNode | null = null
let bgmGain: GainNode | null = null

// 经典斗地主音频源基础路径 (使用 jsDelivr 加速 GitHub 资源，防止 Raw 链接因网络波动拉取失败)
const BASE_CDN_URL = 'https://cdn.jsdelivr.net/gh/yaozy15/landlord@master/'

// 音频 Buffer 内存缓存
const audioBufferCache: Map<string, AudioBuffer> = new Map()
// 音频解码进行中的 Promise 缓存，防重复拉取
const loadingPromises: Map<string, Promise<AudioBuffer>> = new Map()

// BGM 使用 HTML5 Audio 以节省内存并实现流畅的流式加载和循环
let currentBgmAudio: HTMLAudioElement | null = null
let currentBgmName: BgmName | null = null
let currentBgmStyle: BgmStyle | null = null

const SETTINGS_KEY = 'hmp_sound_settings'
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
let settings: SoundSettings = { ...DEFAULT_SETTINGS }

export const QUICK_CHAT_VOLUME_BOOST = 1.0

export function getQuickChatVoiceSound(msgId?: number): SoundName | null {
  if (typeof msgId !== 'number' || !Number.isInteger(msgId) || msgId < 0 || msgId >= 12) return null
  const formattedId = String(msgId + 1).padStart(2, '0')
  return `msgChatMsg${formattedId}` as SoundName
}

const BGM_CONFIG = {
  lobby: {
    gain: 1.8,
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

function clampVolume(v: number): number {
  return Math.max(0, Math.min(1, v))
}

function calculateBgmVolume(name: BgmName): number {
  return clampVolume(settings.bgmVolume * settings.masterVolume * BGM_CONFIG[name].gain)
}

function getBgmFile(name: BgmName, style: BgmStyle): string {
  return BGM_CONFIG[name].sources[style]
}

// ─── 初始化配置与持久化 ───
function loadSettings() {
  try {
    const saved = localStorage.getItem(SETTINGS_KEY)
    if (saved) {
      const parsed = JSON.parse(saved)
      settings = { ...DEFAULT_SETTINGS, ...parsed }
    }
  } catch { /* ignore */ }
}

function saveSettings() {
  try {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings))
  } catch { /* ignore */ }
}

function ensureContext(): AudioContext {
  if (!audioCtx) {
    audioCtx = new AudioContext()

    masterGain = audioCtx.createGain()
    masterGain.gain.value = settings.masterVolume
    masterGain.connect(audioCtx.destination)

    sfxGain = audioCtx.createGain()
    sfxGain.gain.value = settings.sfxVolume
    sfxGain.connect(masterGain)

    bgmGain = audioCtx.createGain()
    bgmGain.gain.value = settings.bgmVolume
    bgmGain.connect(masterGain)
  }

  if (audioCtx.state === 'suspended') {
    audioCtx.resume()
  }

  return audioCtx
}

// ─── 音效文件映射表 ───
const soundPaths: Record<string, string> = {
  // 特效物理音效
  bomb_effect: 'Special_Bomb.ogg',
  plane_effect: 'Special_plane.ogg',
  shunzi_effect: 'shunzi.ogg',
  
  // 胜负与界面
  gameWin: 'common/win.mp3',
  gameLose: 'common/lose.mp3',
}

// ─── Web Audio API 本地合成辅助（对于发牌和点击，本地生成比网络拉取更流畅且零延迟） ───
function playLocalDealCard(ctx: AudioContext, dest: AudioNode) {
  const t = ctx.currentTime
  
  // 检查是否在测试环境或缺少核心 API
  if (typeof ctx.createBuffer !== 'function' || typeof ctx.createBiquadFilter !== 'function') {
    // 简易回退：清脆的 sine 波
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.type = 'sine'
    osc.frequency.setValueAtTime(1000, t)
    gain.gain.setValueAtTime(0.05, t)
    gain.gain.exponentialRampToValueAtTime(0.001, t + 0.04)
    osc.connect(gain)
    gain.connect(dest)
    osc.start(t)
    osc.stop(t + 0.05)
    return
  }

  // 1. 模拟牌飞出的“唰”声（高频带通滤波噪声）
  try {
    const bufferSize = ctx.sampleRate * 0.08 // 80ms
    const buffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate)
    const data = buffer.getChannelData(0)
    for (let i = 0; i < bufferSize; i++) {
      data[i] = Math.random() * 2 - 1
    }
    const noise = ctx.createBufferSource()
    noise.buffer = buffer
    
    const filter = ctx.createBiquadFilter()
    filter.type = 'bandpass'
    filter.frequency.setValueAtTime(2200, t) // 模拟清脆纸张破空声
    filter.Q.setValueAtTime(1.5, t)
    
    const noiseGain = ctx.createGain()
    noiseGain.gain.setValueAtTime(0.12, t)
    noiseGain.gain.exponentialRampToValueAtTime(0.001, t + 0.07)
    
    noise.connect(filter)
    filter.connect(noiseGain)
    noiseGain.connect(dest)
    noise.start(t)
    noise.stop(t + 0.08)
  } catch (e) {
    console.warn('SoundEngine: Failed to play synthesized noise:', e)
  }

  // 2. 模拟扑克牌微弱的弹性撞击“啪”声（温和正弦波）
  try {
    const osc = ctx.createOscillator()
    const oscGain = ctx.createGain()
    osc.type = 'sine'
    osc.frequency.setValueAtTime(600, t) // 600Hz 饱满温和
    osc.frequency.exponentialRampToValueAtTime(300, t + 0.04) // 频率下滑
    
    oscGain.gain.setValueAtTime(0.05, t)
    oscGain.gain.exponentialRampToValueAtTime(0.001, t + 0.04)
    
    osc.connect(oscGain)
    oscGain.connect(dest)
    osc.start(t)
    osc.stop(t + 0.05)
  } catch (e) {
    console.warn('SoundEngine: Failed to play synthesized tone:', e)
  }
}

function playLocalSelectCard(ctx: AudioContext, dest: AudioNode) {
  const t = ctx.currentTime
  const osc = ctx.createOscillator()
  const gain = ctx.createGain()
  osc.type = 'sine'
  osc.frequency.setValueAtTime(1800, t)
  gain.gain.setValueAtTime(0.06, t)
  gain.gain.exponentialRampToValueAtTime(0.001, t + 0.02)
  osc.connect(gain)
  gain.connect(dest)
  osc.start(t)
  osc.stop(t + 0.03)
}

function playLocalBtnClick(ctx: AudioContext, dest: AudioNode) {
  const t = ctx.currentTime
  const osc = ctx.createOscillator()
  const gain = ctx.createGain()
  osc.type = 'sine'
  osc.frequency.setValueAtTime(1300, t)
  gain.gain.setValueAtTime(0.08, t)
  gain.gain.exponentialRampToValueAtTime(0.001, t + 0.04)
  osc.connect(gain)
  gain.connect(dest)
  osc.start(t)
  osc.stop(t + 0.05)
}

function playLocalTick(ctx: AudioContext, dest: AudioNode, urgent: boolean) {
  const t = ctx.currentTime
  const osc = ctx.createOscillator()
  const gain = ctx.createGain()
  osc.type = urgent ? 'square' : 'sine'
  osc.frequency.setValueAtTime(urgent ? 1200 : 1000, t)
  gain.gain.setValueAtTime(urgent ? 0.2 : 0.12, t)
  gain.gain.exponentialRampToValueAtTime(0.001, t + 0.04)
  osc.connect(gain)
  gain.connect(dest)
  osc.start(t)
  osc.stop(t + 0.05)
}

// 华丽的上行 C 大调和弦琶音（匹配成功）
function playLocalMatchSuccess(ctx: AudioContext, dest: AudioNode) {
  const t = ctx.currentTime
  const notes = [523.25, 659.25, 783.99, 1046.50] // C5, E5, G5, C6
  notes.forEach((freq, idx) => {
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.type = 'sine'
    osc.frequency.setValueAtTime(freq, t + idx * 0.08)
    
    gain.gain.setValueAtTime(0, t + idx * 0.08)
    gain.gain.linearRampToValueAtTime(0.12, t + idx * 0.08 + 0.015)
    gain.gain.exponentialRampToValueAtTime(0.001, t + idx * 0.08 + 0.35)
    
    osc.connect(gain)
    gain.connect(dest)
    osc.start(t + idx * 0.08)
    osc.stop(t + idx * 0.08 + 0.4)
  })
}

// 明牌音效：一个亮丽、上扬的和弦音效加上翻牌的感觉
function playLocalShowCards(ctx: AudioContext, dest: AudioNode) {
  const t = ctx.currentTime
  const notes = [587.33, 739.99, 880.00, 1174.66] // D5, F#5, A5, D6
  notes.forEach((freq, idx) => {
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.type = 'triangle'
    osc.frequency.setValueAtTime(freq, t + idx * 0.06)
    
    gain.gain.setValueAtTime(0, t + idx * 0.06)
    gain.gain.linearRampToValueAtTime(0.12, t + idx * 0.06 + 0.01)
    gain.gain.exponentialRampToValueAtTime(0.001, t + idx * 0.06 + 0.3)
    
    osc.connect(gain)
    gain.connect(dest)
    osc.start(t + idx * 0.06)
    osc.stop(t + idx * 0.06 + 0.35)
  })
}

// 经典的清脆金币撞击声（加倍）
function playLocalDoubling(ctx: AudioContext, dest: AudioNode) {
  const t = ctx.currentTime
  const notes = [987.77, 1318.51] // B5, E6
  notes.forEach((freq, idx) => {
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    // 用 triangle 波带来一点清脆的回响
    osc.type = 'triangle'
    osc.frequency.setValueAtTime(freq, t + idx * 0.08)
    
    gain.gain.setValueAtTime(0, t + idx * 0.08)
    gain.gain.linearRampToValueAtTime(0.15, t + idx * 0.08 + 0.01)
    gain.gain.exponentialRampToValueAtTime(0.001, t + idx * 0.08 + 0.25)
    
    osc.connect(gain)
    gain.connect(dest)
    osc.start(t + idx * 0.08)
    osc.stop(t + idx * 0.08 + 0.3)
  })
}

// 经典的清脆加倍短和弦音效，即使 TTS 缺失也有清脆声响
function playLocalJiabei(ctx: AudioContext, dest: AudioNode) {
  const t = ctx.currentTime
  const notes = [523.25, 783.99] // C5, G5
  notes.forEach((freq, idx) => {
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.type = 'sine'
    osc.frequency.setValueAtTime(freq, t + idx * 0.08)
    
    gain.gain.setValueAtTime(0, t + idx * 0.08)
    gain.gain.linearRampToValueAtTime(0.12, t + idx * 0.08 + 0.01)
    gain.gain.exponentialRampToValueAtTime(0.001, t + idx * 0.08 + 0.18)
    
    osc.connect(gain)
    gain.connect(dest)
    osc.start(t + idx * 0.08)
    osc.stop(t + idx * 0.08 + 0.22)
  })
}

// 经典的超级加倍上扬和弦音效
function playLocalSuperDouble(ctx: AudioContext, dest: AudioNode) {
  const t = ctx.currentTime
  const notes = [523.25, 659.25, 783.99] // C5, E5, G5
  notes.forEach((freq, idx) => {
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.type = 'sine'
    osc.frequency.setValueAtTime(freq, t + idx * 0.07)
    
    gain.gain.setValueAtTime(0, t + idx * 0.07)
    gain.gain.linearRampToValueAtTime(0.12, t + idx * 0.07 + 0.01)
    gain.gain.exponentialRampToValueAtTime(0.001, t + idx * 0.07 + 0.2)
    
    osc.connect(gain)
    gain.connect(dest)
    osc.start(t + idx * 0.07)
    osc.stop(t + idx * 0.07 + 0.25)
  })
}

// 不加倍的低沉下落音效
function playLocalBujiabei(ctx: AudioContext, dest: AudioNode) {
  const t = ctx.currentTime
  const notes = [392.00, 329.63] // G4, E4
  notes.forEach((freq, idx) => {
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.type = 'sine'
    osc.frequency.setValueAtTime(freq, t + idx * 0.08)
    
    gain.gain.setValueAtTime(0, t + idx * 0.08)
    gain.gain.linearRampToValueAtTime(0.08, t + idx * 0.08 + 0.01)
    gain.gain.exponentialRampToValueAtTime(0.001, t + idx * 0.08 + 0.15)
    
    osc.connect(gain)
    gain.connect(dest)
    osc.start(t + idx * 0.08)
    osc.stop(t + idx * 0.08 + 0.2)
  })
}

// 快速向上扫频的啵声（聊天气泡）
function playLocalChatMsg(ctx: AudioContext, dest: AudioNode) {
  const t = ctx.currentTime
  const osc = ctx.createOscillator()
  const gain = ctx.createGain()
  osc.type = 'sine'
  
  // 快速频率扫描，从 400Hz 到 1200Hz
  osc.frequency.setValueAtTime(400, t)
  osc.frequency.exponentialRampToValueAtTime(1200, t + 0.08)
  
  gain.gain.setValueAtTime(0.12, t)
  gain.gain.exponentialRampToValueAtTime(0.001, t + 0.08)
  
  osc.connect(gain)
  gain.connect(dest)
  osc.start(t)
  osc.stop(t + 0.09)
}

// 纸牌翻转声，由发牌声略微拉长
function playLocalFlipBottomCard(ctx: AudioContext, dest: AudioNode) {
  const t = ctx.currentTime
  const osc = ctx.createOscillator()
  const gain = ctx.createGain()
  osc.type = 'triangle'
  osc.frequency.setValueAtTime(1000, t)
  osc.frequency.exponentialRampToValueAtTime(300, t + 0.08)
  
  gain.gain.setValueAtTime(0.06, t)
  gain.gain.exponentialRampToValueAtTime(0.001, t + 0.08)
  
  osc.connect(gain)
  gain.connect(dest)
  osc.start(t)
  osc.stop(t + 0.09)
}

// 模拟卡牌“啪”敲击桌面落下的物理声
function playLocalPlayCard(ctx: AudioContext, dest: AudioNode) {
  const t = ctx.currentTime
  // 1. 高频纸张碰触桌面硬物的打击声
  const clickOsc = ctx.createOscillator()
  const clickGain = ctx.createGain()
  clickOsc.type = 'triangle'
  clickOsc.frequency.setValueAtTime(900, t)
  clickOsc.frequency.exponentialRampToValueAtTime(150, t + 0.04)
  
  clickGain.gain.setValueAtTime(0.12, t)
  clickGain.gain.exponentialRampToValueAtTime(0.001, t + 0.04)
  
  clickOsc.connect(clickGain)
  clickGain.connect(dest)
  clickOsc.start(t)
  clickOsc.stop(t + 0.05)

  // 2. 低频桌面共鸣的空气垫动静
  const thudOsc = ctx.createOscillator()
  const thudGain = ctx.createGain()
  thudOsc.type = 'sine'
  thudOsc.frequency.setValueAtTime(150, t)
  thudOsc.frequency.linearRampToValueAtTime(80, t + 0.05)
  
  thudGain.gain.setValueAtTime(0.2, t)
  thudGain.gain.exponentialRampToValueAtTime(0.001, t + 0.06)
  
  thudOsc.connect(thudGain)
  thudGain.connect(dest)
  thudOsc.start(t)
  thudOsc.stop(t + 0.07)
}

// ─── 浏览器 Web Speech API 朗读辅助，用以优雅退化叫牌/加倍等缺失的真人音效 ───
function playSpeechSynthesis(text: string, gender: 'male' | 'female'): boolean {
  if (typeof window === 'undefined' || !window.speechSynthesis) return false
  if (typeof SpeechSynthesisUtterance === 'undefined') return false
  try {
    const voices = window.speechSynthesis.getVoices()
    const zhVoices = voices.filter(v => v.lang.includes('zh') || v.lang.includes('ZH'))

    const speakAction = () => {
      const utterance = new SpeechSynthesisUtterance(text)
      utterance.lang = 'zh-CN'
      
      const currentVoices = window.speechSynthesis.getVoices()
      const currentZhVoices = currentVoices.filter(v => v.lang.includes('zh') || v.lang.includes('ZH'))
      
      if (currentZhVoices.length > 0) {
        let selectedVoice: SpeechSynthesisVoice | undefined = currentZhVoices[0]
        if (gender === 'female') {
          const female = currentZhVoices.find(v => {
            const name = v.name.toLowerCase()
            return name.includes('ting') || name.includes('xiao') || name.includes('yu') || name.includes('mei')
          })
          if (female) selectedVoice = female
        } else {
          const male = currentZhVoices.find(v => {
            const name = v.name.toLowerCase()
            return name.includes('kang') || name.includes('yun') || name.includes('zhi') || name.includes('qiang')
          })
          if (male) selectedVoice = male
        }
        if (selectedVoice) {
          utterance.voice = selectedVoice
        }
      }
      
      utterance.rate = 1.2
      utterance.pitch = gender === 'female' ? 1.25 : 0.85
      utterance.volume = Math.min(1, settings.sfxVolume * settings.masterVolume * QUICK_CHAT_VOLUME_BOOST)
      
      window.speechSynthesis.speak(utterance)
    }

    // 避开 Chrome 浏览器 cancel() 紧跟 speak() 时概率性导致的静音 bug
    if (window.speechSynthesis.speaking || window.speechSynthesis.pending) {
      window.speechSynthesis.cancel()
      setTimeout(speakAction, 80)
    } else {
      // 首次播报或未占线时直接播放
      speakAction()
    }
    return true
  } catch (err) {
    console.warn('SoundEngine: TTS 播放失败:', err)
    return false
  }
}

// ─── 异步加载与音频解码 ───
async function fetchAndDecodeAudio(ctx: AudioContext, url: string): Promise<AudioBuffer> {
  const cached = audioBufferCache.get(url)
  if (cached) return cached

  // 防抖，同一链接同时只加载一次
  let promise = loadingPromises.get(url)
  if (!promise) {
    promise = (async () => {
      try {
        const response = await fetch(url)
        const arrayBuffer = await response.arrayBuffer()
        const audioBuffer = await ctx.decodeAudioData(arrayBuffer)
        audioBufferCache.set(url, audioBuffer)
        return audioBuffer
      } catch (err) {
        console.error(`SoundEngine: 无法加载/解码音频: ${url}`, err)
        throw err
      } finally {
        loadingPromises.delete(url)
      }
    })()
    loadingPromises.set(url, promise)
  }
  return promise
}

// ─── 公开接口组合式函数 ───
export function useSoundEngine() {
  loadSettings()

  /** 确定性别配音路径：根据设置或计算返回男声/女声路径 */
  function getGenderFolder(playerId?: string): string {
    if (settings.voiceGender === 'female') return 'female_voice/'
    if (settings.voiceGender === 'male') return 'male_voice/'

    if (!playerId) return 'female_voice/' // 默认女声
    let hash = 0
    for (let i = 0; i < playerId.length; i++) {
      hash += playerId.charCodeAt(i)
    }
    return hash % 2 === 0 ? 'female_voice/' : 'male_voice/'
  }

  function getSpeechGender(playerId?: string): 'male' | 'female' {
    if (settings.voiceGender === 'female') return 'female'
    if (settings.voiceGender === 'male') return 'male'
    return getGenderFolder(playerId).includes('female') ? 'female' : 'male'
  }

  /** 获取叫分人声音频文件名 */
  function getCallVoicePath(name: SoundName, genderFolder: string): string {
    switch (name) {
      case 'callLandlord': return `${genderFolder}jiaodizhu.ogg`
      case 'robLandlord': return `${genderFolder}qiangdizhu_1.ogg`
      case 'skipCall': return `${genderFolder}bujiao.ogg`
      case 'skipRob': return `${genderFolder}buqiang.ogg`
      case 'pass': return `${genderFolder}no_1.ogg`
      case 'bomb': return `${genderFolder}bomb.ogg`
      case 'rocket': return `${genderFolder}rocket.ogg`
      case 'airplane': return `${genderFolder}airplane.ogg`
      case 'straight': return `${genderFolder}shunzi.ogg`
      case 'double_straight': return `${genderFolder}continuous_pair.ogg`
      case 'three_one': return `${genderFolder}three_with_one.ogg`
      case 'three_two': return `${genderFolder}three_with_one_pair.ogg`
      case 'mingpai': return `${genderFolder}mingpai.ogg`
      case 'jiabei': {
        const ext = genderFolder.includes('female') ? 'mp3' : 'ogg'
        return `${genderFolder}jiabei.${ext}`
      }
      case 'bujiabei': {
        const ext = genderFolder.includes('female') ? 'mp3' : 'ogg'
        return `${genderFolder}bujiabei.${ext}`
      }
      case 'superDouble': {
        const ext = genderFolder.includes('female') ? 'mp3' : 'ogg'
        return `${genderFolder}chaojijiabei.${ext}`
      }
      default: {
        // 如果是数字（单牌），例如 "4" -> female_voice/4.ogg
        // 如果是对子，例如 "pair4" -> female_voice/pair4.ogg
        // 如果是三张/三带一，例如 "three_one4" -> female_voice/three_one4.ogg
        if (/^\d+$/.test(name) || name.startsWith('pair') || name.startsWith('three_one')) {
          return `${genderFolder}${name}.ogg`
        }
        return ''
      }
    }
  }

  /**
   * 播放音效
   * @param name 音效名
   * @param playerId 触发该音效的玩家ID（用以决定播放男声或女声）
   */
  async function playSound(name: SoundName, playerId?: string, options: PlaySoundOptions = {}) {
    if (!settings.sfxEnabled) return

    const ctx = ensureContext()
    if (!sfxGain) return

    if (name === 'superDouble' && getGenderFolder(playerId).includes('female')) {
      playLocalSuperDouble(ctx, sfxGain)
      setTimeout(() => {
        void playSound('jiabei', playerId, options)
      }, 120)
      return
    }

    // 如果 AudioContext 被挂起，在用户交互时强制恢复，彻底解决非交互事件静音问题
    if (ctx.state === 'suspended') {
      try {
        await ctx.resume()
      } catch (err) {
        console.warn('SoundEngine: 恢复 AudioContext 失败:', err)
      }
    }

    // 1. 本地合成的即时音效 (发牌、点击、倒计时)
    if (name === 'fifty_k_true' || name === 'fifty_k_false') {
      const spoken = name === 'fifty_k_true' ? '真510K' : '510K'
      if (!playSpeechSynthesis(spoken, getSpeechGender(playerId))) {
        playLocalPlayCard(ctx, sfxGain)
      }
      return
    }

    if (name === 'dealCard') {
      playLocalDealCard(ctx, sfxGain)
      return
    }
    if (name === 'selectCard') {
      playLocalSelectCard(ctx, sfxGain)
      return
    }
    if (name === 'btnClick') {
      playLocalBtnClick(ctx, sfxGain)
      return
    }
    if (name === 'tick') {
      playLocalTick(ctx, sfxGain, false)
      return
    }
    if (name === 'tickUrgent') {
      playLocalTick(ctx, sfxGain, true)
      return
    }
    if (name === 'matchSuccess') {
      playLocalMatchSuccess(ctx, sfxGain)
      return
    }
    if (name === 'doubling') {
      playLocalDoubling(ctx, sfxGain)
      return
    }
    if (name === 'showCards') {
      playLocalShowCards(ctx, sfxGain)
      return
    }
    if (name === 'chatMsg') {
      playLocalChatMsg(ctx, sfxGain)
      return
    }
    if (name === 'flipBottomCard') {
      playLocalFlipBottomCard(ctx, sfxGain)
      return
    }
    if (name === 'playCard') {
      playLocalPlayCard(ctx, sfxGain)
      return
    }

    // 2. 网络配音/特效音效
    let fileUrl = ''
    const genderFolder = getGenderFolder(playerId)

    if (name.startsWith('msgChatMsg') || name === 'baojing1' || name === 'baojing2') {
      const isBoy = genderFolder.includes('male')
      const genderDir = isBoy ? 'boy' : 'girl'
      fileUrl = `https://cdn.jsdelivr.net/gh/ZhouWeikuan/DouDiZhu@master/code/res/sounds/${genderDir}/${name}.mp3`
    } else {
      let relativePath = ''
      const voicePath = getCallVoicePath(name, genderFolder)
      
      if (voicePath) {
        relativePath = voicePath
      } else if (soundPaths[name]) {
        relativePath = soundPaths[name]!
      } else {
        // 其它普通音效兜底处理
        if (name === 'redeal') relativePath = 'female_voice/chupai_3.ogg'
      }

      const isLocalAudio = name === 'jiabei' || name === 'bujiabei' || name === 'superDouble' || name === 'gameWin' || name === 'gameLose'
      fileUrl = isLocalAudio
        ? `/static/audio/${relativePath}`
        : `${BASE_CDN_URL}${relativePath}`
    }

    try {
      const buffer = await fetchAndDecodeAudio(ctx, fileUrl)
      if (ctx.state === 'suspended') return

      const source = ctx.createBufferSource()
      source.buffer = buffer
      if (options.volumeBoost && options.volumeBoost !== 1) {
        const boostGain = ctx.createGain()
        boostGain.gain.value = options.volumeBoost
        source.connect(boostGain)
        boostGain.connect(sfxGain)
      } else {
        source.connect(sfxGain)
      }
      source.start(0)
    } catch (err) {
      console.warn(`SoundEngine: 播放音效失败 [${name}]:`, err)
      // 如果加倍语音加载失败，降级播放本地电子和弦音效
      if (name === 'jiabei') playLocalJiabei(ctx, sfxGain)
      else if (name === 'superDouble') playLocalSuperDouble(ctx, sfxGain)
      else if (name === 'bujiabei') playLocalBujiabei(ctx, sfxGain)
      else if (name === 'mingpai') {
        playSpeechSynthesis('明牌', getSpeechGender(playerId))
      }
    }
  }

  async function playQuickChatVoice(text: string, playerId?: string, msgId?: number) {
    if (!settings.sfxEnabled) return

    const trimmedText = text.trim()
    if (!trimmedText) return

    const voiceSound = getQuickChatVoiceSound(msgId)
    if (voiceSound) {
      await playSound(voiceSound, playerId)
      return
    }

    const playedBySpeech = playSpeechSynthesis(trimmedText, getSpeechGender(playerId))
    if (playedBySpeech) return

    try {
      const ctx = ensureContext()
      if (sfxGain) {
        playLocalChatMsg(ctx, sfxGain)
      }
    } catch (err) {
      console.warn('SoundEngine: 快捷语播放失败:', err)
    }
  }

  /** 播放/切换背景乐 (BGM) */
  function startBgm(name: BgmName, fallbackStyle?: BgmStyle) {
    if (!settings.bgmEnabled) return

    const bgmStyle = fallbackStyle ?? settings.bgmStyle
    const bgmFile = getBgmFile(name, bgmStyle)
    const fileUrl = `${BASE_CDN_URL}${bgmFile}`

    if (currentBgmAudio && currentBgmName === name && currentBgmStyle === bgmStyle) {
      // 已在播放相同的 BGM，继续播放
      if (currentBgmAudio.paused) {
        currentBgmAudio.play().catch(() => {})
      }
      return
    }

    // 停止当前 BGM
    stopBgm()

    currentBgmName = name
    currentBgmStyle = bgmStyle
    currentBgmAudio = new Audio(fileUrl)
    currentBgmAudio.loop = true
    currentBgmAudio.volume = calculateBgmVolume(name)
    currentBgmAudio.onerror = () => {
      if (bgmStyle !== 'classic') {
        startBgm(name, 'classic')
      } else {
        console.warn(`SoundEngine: BGM 播放失败 [${name}:${bgmStyle}]`)
      }
    }

    currentBgmAudio.play().catch(err => {
      console.warn('SoundEngine: BGM 播放受阻，等待用户交互:', err)
      // 浏览器刷新后常会拦截自动播放，等待下一次真实用户交互再恢复。
      const unlockEvents = ['pointerdown', 'click', 'touchstart', 'keydown'] as const
      const unlockHandler = () => {
        if (currentBgmAudio && currentBgmAudio.paused && settings.bgmEnabled) {
          currentBgmAudio.play().catch(() => {})
        }
        unlockEvents.forEach(eventName => {
          window.removeEventListener(eventName, unlockHandler)
        })
      }
      unlockEvents.forEach(eventName => {
        window.addEventListener(eventName, unlockHandler)
      })
    })
  }

  /** 停止背景乐 */
  function stopBgm() {
    if (currentBgmAudio) {
      currentBgmAudio.pause()
      currentBgmAudio = null
      currentBgmName = null
      currentBgmStyle = null
    }
  }

  // ─── 音量控制与属性修改 ───

  function setMasterVolume(v: number) {
    settings.masterVolume = Math.max(0, Math.min(1, v))
    if (masterGain) masterGain.gain.value = settings.masterVolume
    if (currentBgmAudio && currentBgmName) {
      currentBgmAudio.volume = calculateBgmVolume(currentBgmName)
    }
    saveSettings()
  }

  function setSfxVolume(v: number) {
    settings.sfxVolume = Math.max(0, Math.min(1, v))
    if (sfxGain) sfxGain.gain.value = settings.sfxVolume
    saveSettings()
  }

  function setBgmVolume(v: number) {
    settings.bgmVolume = clampVolume(v)
    if (bgmGain) bgmGain.gain.value = settings.bgmVolume
    if (currentBgmAudio && currentBgmName) {
      currentBgmAudio.volume = calculateBgmVolume(currentBgmName)
    }
    saveSettings()
  }

  function toggleSfx(enabled?: boolean) {
    settings.sfxEnabled = enabled ?? !settings.sfxEnabled
    saveSettings()
  }

  function toggleBgm(enabled?: boolean) {
    settings.bgmEnabled = enabled ?? !settings.bgmEnabled
    if (!settings.bgmEnabled) {
      stopBgm()
    } else if (currentBgmName) {
      // 重新开启 BGM 播放
      startBgm(currentBgmName)
    }
    saveSettings()
  }

  function getSettings(): Readonly<SoundSettings> {
    return { ...settings }
  }

  function setVoiceGender(gender: 'male' | 'female' | 'auto') {
    settings.voiceGender = gender
    saveSettings()
  }

  function setCustomVoice(enabled: boolean) {
    settings.customVoiceEnabled = enabled
    saveSettings()
  }

  function setBgmStyle(style: BgmStyle) {
    settings.bgmStyle = style
    saveSettings()
  }

  /** 在后台静默预加载所有常见叫牌、出牌和特效音效，完全消除首次播放的网络延迟 */
  function preloadAllSounds() {
    const ctx = ensureContext()
    if (!ctx) return

    const genders = ['female_voice/', 'male_voice/']
    const urls: string[] = []

    // 1. 基础特效音与胜负音
    Object.values(soundPaths).forEach(file => {
      urls.push(`${BASE_CDN_URL}${file}`)
    })

    // 2. 叫分、加倍和牌型语音
    const genericVoices = [
      'jiaodizhu.ogg', 'qiangdizhu_1.ogg', 'bujiao.ogg', 'buqiang.ogg', 'no_1.ogg',
      'bomb.ogg', 'rocket.ogg', 'airplane.ogg', 'shunzi.ogg', 'continuous_pair.ogg',
      'three_with_one.ogg', 'three_with_one_pair.ogg', 'jiabei.ogg', 'bujiabei.ogg', 'chaojijiabei.ogg'
    ]

    genders.forEach(gender => {
      // 叫分通用音效
      genericVoices.forEach(voice => {
        urls.push(`${BASE_CDN_URL}${gender}${voice}`)
      })
      // 单张 3~17
      for (let i = 3; i <= 17; i++) {
        urls.push(`${BASE_CDN_URL}${gender}${i}.ogg`)
      }
      // 对子 3~15
      for (let i = 3; i <= 15; i++) {
        urls.push(`${BASE_CDN_URL}${gender}pair${i}.ogg`)
      }
      // 三张 3~15
      for (let i = 3; i <= 15; i++) {
        urls.push(`${BASE_CDN_URL}${gender}three_one${i}.ogg`)
      }
    })

    // 3. 经典男女快捷聊声原声音频预加载
    for (let i = 1; i <= 12; i++) {
      const formatted = String(i).padStart(2, '0')
      urls.push(`https://cdn.jsdelivr.net/gh/ZhouWeikuan/DouDiZhu@master/code/res/sounds/boy/msgChatMsg${formatted}.mp3`)
      urls.push(`https://cdn.jsdelivr.net/gh/ZhouWeikuan/DouDiZhu@master/code/res/sounds/girl/msgChatMsg${formatted}.mp3`)
    }

    // 在后台静默并发加载（浏览器和 CDN 自动并发下载，加载一次便缓存在内存 Map 中）
    urls.forEach(url => {
      fetchAndDecodeAudio(ctx, url).catch(() => {
        // 静默处理，忽略个别失效的加载
      })
    })
  }

  function unlock() {
    const ctx = ensureContext()
    
    const tryUnlock = () => {
      if (ctx.state === 'suspended') {
        ctx.resume().then(() => {
          preloadAllSounds()
        }).catch(() => {})
      } else {
        preloadAllSounds()
      }
    }
    
    if (ctx.state === 'suspended') {
      // 注册一次性监听器，在用户下一次点击页面任何位置时，立即自动唤醒并预载所有音频
      window.addEventListener('click', tryUnlock, { once: true })
      window.addEventListener('touchstart', tryUnlock, { once: true })
    } else {
      preloadAllSounds()
    }
  }

  return {
    playSound,
    playQuickChatVoice,
    startBgm,
    stopBgm,
    setMasterVolume,
    setSfxVolume,
    setBgmVolume,
    toggleSfx,
    toggleBgm,
    setBgmStyle,
    setVoiceGender,
    setCustomVoice,
    getSettings,
    unlock,
  }
}
