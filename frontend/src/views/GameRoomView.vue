<!-- frontend/src/views/GameRoomView.vue -->
<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { usePlayerStore } from '@/stores/playerStore'
import { useGameStore } from '@/stores/gameStore'
import { useGameWebSocket, playDoubleChoiceSound } from '@/composables/useGameWebSocket'
import { useSoundEngine } from '@/composables/useSoundEngine'
import {
  canBeatCardPlay,
  detectCardPlay,
  formatCardIds,
  getCardDisplay,
  getPlayKindLabel,
  sortCardIds,
  sortPlayedCards,
} from '@/utils/cardUtils'
import PlayerSeat from '@/components/PlayerSeat.vue'
import HandCards from '@/components/HandCards.vue'
import PokerCard from '@/components/PokerCard.vue'
import SettlementModal from '@/components/SettlementModal.vue'
import SettingsModal from '@/components/SettingsModal.vue'
import { CHAT_PRESETS } from '@/constants/chatPresets'
import { useRoomVoiceChat } from '@/composables/useRoomVoiceChat'

const router = useRouter()
const playerStore = usePlayerStore()
const gameStore = useGameStore()
const { connect, disconnect, sendAction } = useGameWebSocket()
const { playSound, startBgm, stopBgm, toggleSfx, toggleBgm, getSettings, setMasterVolume, setSfxVolume, setBgmVolume, unlock: unlockAudio } = useSoundEngine()

// 閻犱礁澧介悿鍡涙閵忊剝绶查柟璨夊啫鐓?
const showSettings = ref(false)
const soundSettings = ref(getSettings())
function refreshSoundSettings() { soundSettings.value = getSettings() }

const isMockMode = new URLSearchParams(window.location.search).get('mock') === 'true'

if (isMockMode) {
  // Setup 级别的 Mock 注入
  playerStore.playerId = 'mock_player'
  playerStore.nickname = '雀圣斗地王'
  playerStore.username = 'mock_user'
  playerStore.beans = 9999999
  playerStore.rankTitle = '至尊斗皇III'

  const mockPlayMode = new URLSearchParams(window.location.search).get('play_mode') || 'no_shuffle'
  gameStore.playMode = mockPlayMode as 'classic' | 'no_shuffle' | 'fifty_k'

  gameStore.roomId = 'mock_room_888'
  gameStore.gamePhase = 'PLAYING'
  gameStore.baseScore = 300
  gameStore.multiplier = 64
  if (gameStore.playMode === 'fifty_k') {
    gameStore.landlord = ''
    gameStore.currentTurn = 'mock_player'
    gameStore.wsConnected = true
    gameStore.bottomCards = []
    gameStore.players = [
      { id: 'mock_player', nickname: '雀圣斗地王', isAi: false, isOnline: true, remaining: 20, isLandlord: false, isSelf: true },
      { id: 'ai_left', nickname: '发牌大户 (AI)', isAi: true, isOnline: true, remaining: 17, isLandlord: false, isSelf: false },
      { id: 'ai_right', nickname: '明牌炸弹 (AI)', isAi: true, isOnline: true, remaining: 17, isLandlord: false, isSelf: false }
    ]
    gameStore.scores = {
      'mock_player': 25,
      'ai_left': 10,
      'ai_right': 45
    }
  } else {
    gameStore.landlord = 'mock_player'
    gameStore.currentTurn = 'mock_player'
    gameStore.wsConnected = true
    gameStore.bottomCards = [51, 47, 43]
    gameStore.players = [
      { id: 'mock_player', nickname: '雀圣斗地王', isAi: false, isOnline: true, remaining: 20, isLandlord: true, isSelf: true },
      { id: 'ai_left', nickname: '发牌大户 (AI)', isAi: true, isOnline: true, remaining: 17, isLandlord: false, isSelf: false },
      { id: 'ai_right', nickname: '明牌炸弹 (AI)', isAi: true, isOnline: true, remaining: 17, isLandlord: false, isSelf: false }
    ]
  }
  if (gameStore.playMode === 'no_shuffle') {
    // 不洗牌模式下，发牌 Mock 优先分段并保留炸弹：大王, 小王, 四个2, 四个A, 四个K, 四个Q
    gameStore.myHand = [53, 52, 51, 50, 49, 48, 47, 46, 45, 44, 43, 42, 41, 40, 39, 38, 37, 36, 35, 34]
  } else {
    gameStore.myHand = [53, 52, 50, 49, 48, 46, 45, 44, 42, 41, 40, 38, 37, 36, 34, 33, 32, 30, 29, 28]
  }
  gameStore.lastPlay = {
    player: 'ai_right',
    cards: [1],
    cardType: 'single'
  }
}

// 校验登录状态
if (!isMockMode && (!playerStore.playerId || !playerStore.nickname)) {
  router.push('/login')
}

const showChatMenu = ref(false)
const roomPlayerIds = () => gameStore.players.map(player => player.id).filter(Boolean)
const roomVoice = useRoomVoiceChat({
  selfPlayerId: playerStore.playerId,
  roomPlayerIds,
  sendAction,
})

async function handleToggleVoice() {
  playSound('btnClick')
  await roomVoice.toggleVoice()
}

// 闁稿﹥甯熼鎼佸籍閹偊鍚€闁哄啳娉涘▍?
const timeLeft = ref(15)
let timerInterval: number | null = null
const idleRoundCount = ref(0)

// 闁瑰灚顭囬绋课熼垾宕囩闁绘鍩栭埀顑挎缁楀矂鏌呴弰蹇曞竼
const isAutoPlay = ref(false)

function toggleAutoplay() {
  const next = !isAutoPlay.value
  isAutoPlay.value = next
  sendAction({ action: 'set_auto_play', enabled: next })
}

// 濞撴熬绠戦幆澶愬箥濡⒈鍚€闁告瑥锕ょ紞瀣礈瀹ュ懏绀€闁告艾鐗忔慨鎼佸箑娓氬﹦绀夐柤濂変簻婵晜绂掗敐鍡椻叺
watch(
  [() => gameStore.isMyTurn, isAutoPlay],
  ([isMyTurn, autoPlay]) => {
    if (isMyTurn && autoPlay) {
      sendAction({ action: 'set_auto_play', enabled: true })
    }
  },
  { immediate: true }
)

watch(
  () => gameStore.autoPlayPlayers,
  (players) => {
    isAutoPlay.value = players.includes(playerStore.playerId)
  },
  { immediate: true }
)

// 游戏结束或闲置时自动重置托管状态
watch(
  () => gameStore.gamePhase,
  (newPhase) => {
    if (newPhase === 'IDLE' || newPhase === 'SETTLING') {
      isAutoPlay.value = false
    }
  }
)

const hasHandledTimeout = ref(false)

function getDoubleChoiceLabel(choice?: string) {
  if (choice === 'double') return '加倍'
  if (choice === 'super') return '超级加倍'
  if (choice === 'none') return '不加倍'
  return ''
}

const showDoublingPanel = computed(() => {
  if (gameStore.playMode === 'fifty_k') return false
  return gameStore.gamePhase === 'DOUBLING' &&
         !gameStore.doublingChoices[playerStore.playerId]
})

// 能否叫地主/抢地主判断
const hasSomeoneCalled = computed(() => {
  return gameStore.callRound === 2 || Object.values(gameStore.callScores).some((score) => score > 0)
})

const highestCallScore = computed(() => {
  return Math.max(0, ...Object.values(gameStore.callScores))
})

const nextCallScore = computed(() => {
  return hasSomeoneCalled.value ? Math.min(highestCallScore.value + 1, 3) : 1
})

const callActionLabel = computed(() => {
  return hasSomeoneCalled.value ? '抢地主' : '叫地主'
})

const passCallLabel = computed(() => {
  return hasSomeoneCalled.value ? '不抢' : '不叫'
})

// 閻犱緤绱曢悾濠氭偝閳轰緡鍟€闁革负鍔嶉崺褔姊荤紙鐘哄幀闁汇劌瀚ù澶屸偓鐢垫嚀妤犲洦鎷呭鍛毎濞达絽绋勭槐娆愩亜閻戞ɑ顦ч梺钘夌墛鐢挾鏁崘璺ㄧ
const orderedSeats = computed(() => {
  const myId = playerStore.playerId
  const pList = gameStore.players
  if (pList.length < 3) return []

  const myIndex = pList.findIndex((p) => p.id === myId)
  if (myIndex === -1) {
    return [
      { player: pList[0]!, position: 'left' as const },
      { player: pList[1]!, position: 'right' as const },
      { player: pList[2]!, position: 'bottom' as const }
    ]
  }

  const rightPlayer = pList[(myIndex + 1) % 3]!
  const leftPlayer = pList[(myIndex + 2) % 3]!
  const selfPlayer = pList[myIndex]!

  // 注入加倍状态描述
  const decoratedLeft = {
    ...leftPlayer,
    doubling: getDoubleChoiceLabel(gameStore.doublingChoices[leftPlayer.id]),
    fiftyKScore: gameStore.playMode === 'fifty_k' ? (gameStore.scores[leftPlayer.id] || 0) : undefined,
    beans: gameStore.beanBalances[leftPlayer.id] ?? (leftPlayer.id === playerStore.playerId ? playerStore.beans : 0)
  }
  const decoratedRight = {
    ...rightPlayer,
    doubling: getDoubleChoiceLabel(gameStore.doublingChoices[rightPlayer.id]),
    fiftyKScore: gameStore.playMode === 'fifty_k' ? (gameStore.scores[rightPlayer.id] || 0) : undefined,
    beans: gameStore.beanBalances[rightPlayer.id] ?? (rightPlayer.id === playerStore.playerId ? playerStore.beans : 0)
  }
  const decoratedSelf = {
    ...selfPlayer,
    doubling: getDoubleChoiceLabel(gameStore.doublingChoices[selfPlayer.id]),
    fiftyKScore: gameStore.playMode === 'fifty_k' ? (gameStore.scores[selfPlayer.id] || 0) : undefined,
    beans: gameStore.beanBalances[selfPlayer.id] ?? (selfPlayer.id === playerStore.playerId ? playerStore.beans : 0)
  }

  return [
    { player: decoratedLeft, position: 'left' as const },
    { player: decoratedRight, position: 'right' as const },
    { player: decoratedSelf, position: 'bottom' as const }
  ]
})

// 闁煎疇妫勯幆浣规交閸モ晛顤?
const canPass = computed(() => {
  return gameStore.lastPlay.player !== null && gameStore.lastPlay.player !== playerStore.playerId
})

const lastCardsToBeat = computed(() => {
  if (!gameStore.lastPlay.player || gameStore.lastPlay.player === playerStore.playerId) return []
  return gameStore.lastPlay.cards || []
})

const hintState = ref<{ allHints: number[][]; currentIndex: number } | null>(null)
const isHintLoading = ref(false)

const hintButtonText = computed(() => {
  if (!hintState.value || hintState.value.allHints.length === 0) return '提示'
  return `提示 ${hintState.value.currentIndex + 1}/${hintState.value.allHints.length}`
})

const playSuggestion = computed(() => {
  if (gameStore.gamePhase !== 'PLAYING' || !gameStore.isMyTurn) return null

  const cards = gameStore.aiHintCandidates.find((candidate) => candidate.length > 0) || []
  const play = detectCardPlay(cards, gameStore.playMode)
  const isLeading = lastCardsToBeat.value.length === 0

  if (!cards.length || !play) {
    return {
      canPlay: false,
      cards: [] as number[],
      text: '要不起，建议不出',
    }
  }

  const label = getPlayKindLabel(play.kind)
  return {
    canPlay: true,
    cards,
    text: `${isLeading ? 'AI 建议先出' : 'AI 建议出'}：${formatCardIds(cards)}（${label}）`,
  }
})

const suggestedCards = computed(() => {
  return playSuggestion.value?.canPlay ? playSuggestion.value.cards : []
})

const selectedPlayState = computed(() => {
  if (gameStore.selectedCards.length === 0) {
    return { valid: false, message: '' }
  }

  const selectedPlay = detectCardPlay(gameStore.selectedCards, gameStore.playMode)
  if (!selectedPlay) {
    return { valid: false, message: '当前选择不是合法牌型' }
  }

  const lastPlay = detectCardPlay(lastCardsToBeat.value, gameStore.playMode)
  if (!lastPlay) {
    return { valid: true, message: getPlayKindLabel(selectedPlay.kind) }
  }

  if (!canBeatCardPlay(selectedPlay, lastPlay, gameStore.playMode)) {
    return { valid: false, message: '当前选择压不过上家' }
  }

  return { valid: true, message: getPlayKindLabel(selectedPlay.kind) }
})

const canSubmitSelected = computed(() => {
  return gameStore.selectedCards.length > 0 && selectedPlayState.value.valid
})

// 閻犱焦澹嗘晶婵嬪闯閵娾斁鍋撻弰蹇曞竼

// 璁扮墝鍣ㄩ€昏緫
const discardCounts = computed(() => {
  // 缁忓吀鏄剧ず椤哄簭锛氬ぇ鐜嬨€佸皬鐜嬨€?銆丄銆並銆丵銆丣銆?0銆?銆?銆?銆?銆?銆?銆?
  const keys = ['大', '小', '2', 'A', 'K', 'Q', 'J', '10', '9', '8', '7', '6', '5', '4', '3']
  const counts: Record<string, number> = {
    '大': 1, '小': 1, '2': 4, 'A': 4, 'K': 4, 'Q': 4, 'J': 4, '10': 4, '9': 4, '8': 4, '7': 4, '6': 4, '5': 4, '4': 4, '3': 4
  }

  // 鍑忓幓鑷繁鎵嬬墝
  for (const cId of gameStore.myHand) {
    const d = getCardDisplay(cId)
    if (d.suit === 'joker') {
      if (d.rank === '大') counts['大'] = (counts['大'] ?? 0) - 1
      if (d.rank === '小') counts['小'] = (counts['小'] ?? 0) - 1
    } else {
      if (counts[d.rank] !== undefined) counts[d.rank] = (counts[d.rank] ?? 0) - 1
    }
  }

  // 鍑忓幓鍏ㄥ満宸插嚭鐗?
  for (const cId of gameStore.allPlayedCards) {
    const d = getCardDisplay(cId)
    if (d.suit === 'joker') {
      if (d.rank === '大') counts['大'] = (counts['大'] ?? 0) - 1
      if (d.rank === '小') counts['小'] = (counts['小'] ?? 0) - 1
    } else {
      if (counts[d.rank] !== undefined) counts[d.rank] = (counts[d.rank] ?? 0) - 1
    }
  }

  return keys.map(k => ({ key: k, count: Math.max(0, counts[k] ?? 0) }))
})

interface GoldBean {
  id: number
  x: number
  y: number
  scale: number
  opacity: number
  duration: number
}

interface FloatingText {
  id: number
  x: number
  y: number
  scoreGained: string
  beansGained: string
}

const activeBeans = ref<GoldBean[]>([])
const floatingTexts = ref<FloatingText[]>([])
let beanIdCounter = 0
let floatIdCounter = 0

function getSeatCenter(position: 'left' | 'right' | 'bottom') {
  const el = document.querySelector(`.play-seat-zone.${position} .avatar-block`)
  if (el) {
    const rect = el.getBoundingClientRect()
    return {
      x: rect.left + rect.width / 2,
      y: rect.top + rect.height / 2
    }
  }
  if (position === 'left') return { x: 100, y: window.innerHeight / 2 }
  if (position === 'right') return { x: window.innerWidth - 100, y: window.innerHeight / 2 }
  return { x: 100, y: window.innerHeight - 100 }
}

function playBeansFlyAnimation(winnerId: string, scoreGained: number, beanChanges: Record<string, number>) {
  const seats = orderedSeats.value
  const winnerSeat = seats.find(s => s.player.id === winnerId)
  if (!winnerSeat) return

  const winnerPos = winnerSeat.position
  const winnerCenter = getSeatCenter(winnerPos)

  const losers = seats.filter(s => s.player.id !== winnerId)
  const beansList: GoldBean[] = []

  losers.forEach(loser => {
    const loserCenter = getSeatCenter(loser.position)
    const lChange = beanChanges[loser.player.id] || 0
    if (lChange === 0) return

    for (let i = 0; i < 15; i++) {
      const id = ++beanIdCounter
      const offsetX = (Math.random() - 0.5) * 40
      const offsetY = (Math.random() - 0.5) * 40
      const bean: GoldBean = {
        id,
        x: loserCenter.x + offsetX,
        y: loserCenter.y + offsetY,
        scale: 0.6 + Math.random() * 0.5,
        opacity: 1,
        duration: 0.7 + Math.random() * 0.5
      }
      activeBeans.value.push(bean)
      beansList.push(bean)
    }
  })

  setTimeout(() => {
    beansList.forEach(bean => {
      const target = activeBeans.value.find(b => b.id === bean.id)
      if (target) {
        target.x = winnerCenter.x
        target.y = winnerCenter.y
        target.scale = 0.7
      }
    })
  }, 50)

  setTimeout(() => {
    const idsToRemove = new Set(beansList.map(b => b.id))
    activeBeans.value = activeBeans.value.filter(b => !idsToRemove.has(b.id))

    playSound('btnClick')

    const winnerChange = beanChanges[winnerId] || 0
    const floatId = ++floatIdCounter
    floatingTexts.value.push({
      id: floatId,
      x: winnerCenter.x - 50,
      y: winnerCenter.y - 65,
      scoreGained: scoreGained > 0 ? `+${scoreGained}分` : '',
      beansGained: winnerChange > 0 ? `+${winnerChange}豆` : ''
    })

    losers.forEach(loser => {
      const change = beanChanges[loser.player.id] || 0
      if (change !== 0) {
        const loserCenter = getSeatCenter(loser.position)
        const lFloatId = ++floatIdCounter
        floatingTexts.value.push({
          id: lFloatId,
          x: loserCenter.x - 50,
          y: loserCenter.y - 65,
          scoreGained: '',
          beansGained: change.toString()
        })
        setTimeout(() => {
          floatingTexts.value = floatingTexts.value.filter(f => f.id !== lFloatId)
        }, 1800)
      }
    })

    setTimeout(() => {
      floatingTexts.value = floatingTexts.value.filter(f => f.id !== floatId)
    }, 1800)
  }, 1200)
}

function handleTrickSettledEvent(e: CustomEvent) {
  const data = e.detail
  if (data.current_scores) {
    for (const [pId, val] of Object.entries(data.current_scores)) {
      gameStore.scores[pId] = val as number
    }
  }
  if (data.bean_balances) {
    gameStore.beanBalances = { ...data.bean_balances }
    if (data.bean_balances[playerStore.playerId] !== undefined) {
      playerStore.beans = data.bean_balances[playerStore.playerId]
    }
  }
  playBeansFlyAnimation(data.winner_id, data.score_gained, data.bean_changes)
}

function triggerMockTrickSettled() {
  window.dispatchEvent(new CustomEvent('hmp_trick_settled', {
    detail: {
      winner_id: 'mock_player',
      score_gained: 25,
      bean_changes: {
        'mock_player': 2000,
        'ai_left': -1000,
        'ai_right': -1000
      },
      current_scores: {
        'mock_player': (gameStore.scores['mock_player'] || 0) + 25,
        'ai_left': gameStore.scores['ai_left'] || 0,
        'ai_right': gameStore.scores['ai_right'] || 0
      }
    }
  }))
}

function triggerMockGameOver() {
  gameStore.settlement = {
    winner: 'mock_player',
    winnerSide: 'farmer',
    scores: {
      'mock_player': 65,
      'ai_left': 25,
      'ai_right': 0
    },
    multiplier: 1,
    allHands: {
      'mock_player': [],
      'ai_left': [8],
      'ai_right': [28]
    },
    fifty_k_settlement: {
      winner_id: 'mock_player',
      harvested_scores: {
        'mock_player': 15,
        'ai_left': -5,
        'ai_right': -10
      }
    },
    rank_changes: null
  }
  gameStore.gamePhase = 'SETTLING'
}

onMounted(() => {
  unlockAudio()
  window.addEventListener('hmp_trick_settled', handleTrickSettledEvent as EventListener)

  if (isMockMode) {
    return
  }

  if (!gameStore.wsConnected) {
    connect()
  } else {
    // 濞戞捁顕ф慨鈺呭触鐏炵虎鍔勯柡鍫氬亾闁哄倻澧楅崺褔姊婚弶鎴犳拱闁告柨灏呯槐婵嬫⒓閸欏鍓惧鍫嗗啫娉涢悹鍝勭枃濞村棗顕欓幆鎵閻庝絻澹堥崵褔鎮╅懜纰樺亾娴ｉ鐟濋柛姘湰椤?
    sendAction({ action: 'sync_room_state' })
  }

  // 濠碘€冲€归悘澶婎啅閹绘帗韬繛鎾虫啞閸ㄦ瑦绋夐銊х闁告凹鍨版慨鈺冣偓鐢垫嚀閻?BGM
  if (gameStore.gamePhase !== 'IDLE' && gameStore.gamePhase !== 'MATCHING') {
    startBgm('game')
  }

  // 开启倒计时检测
  timerInterval = window.setInterval(() => {
    const now = Date.now() / 1000
    if (gameStore.turnDeadline) {
      const oldTimeLeft = timeLeft.value
      const newTimeLeft = Math.max(0, Math.ceil(gameStore.turnDeadline - now))
      timeLeft.value = newTimeLeft

      // 闁稿﹥甯熼鎼佸籍閼稿灚妯婄紒娑欐煥閿涙劙鏁嶉崼婊呯煂閺夌儐鍠栭崺宀勬嚊椤忓嫮绠掗柡鍐啇缁?
      if (gameStore.isMyTurn && newTimeLeft > 0 && newTimeLeft !== oldTimeLeft) {
        if (newTimeLeft <= 3) {
          playSound('tickUrgent')
        } else if (newTimeLeft <= 5) {
          playSound('tick')
        }
      }

      // 鐟滅増鎸搁埀顒佸笩椤撴悂寮捄铏圭Ш闂傚棙婀圭粭鏍嫉婢跺﹦绐″璺哄閹﹪鎮╅懜纰樺亾娴ｈ顦?
      if (newTimeLeft === 0) {
        if (gameStore.gamePhase === 'LANDLORD_CONFIRM' && gameStore.awaitingLandlordShow) {
          if (gameStore.landlord === playerStore.playerId && !hasHandledTimeout.value) {
            hasHandledTimeout.value = true
            handleLandlordShow(false)
          }
        } else if (showDoublingPanel.value) {
          // 加倍阶段超时，自动选择“不加倍”
          if (!hasHandledTimeout.value) {
            hasHandledTimeout.value = true
            chooseDoubling('none')
          }
        } else if (gameStore.isMyTurn) {
          // 出牌/叫地主阶段超时操作
          if (!hasHandledTimeout.value) {
            hasHandledTimeout.value = true
            handleTimeout()
          }
        }
      }
    }
  }, 200)
})

onUnmounted(() => {
  window.removeEventListener('hmp_trick_settled', handleTrickSettledEvent as EventListener)
  if (timerInterval) clearInterval(timerInterval)
  roomVoice.dispose()
  stopBgm()
})

// 閻℃帒鎳忓鍌炴嚊椤忓嫬袟闁瑰灝绉崇紞鏃堟焻閺勫繒甯?
function handleTimeout() {
  if (!isAutoPlay.value) {
    idleRoundCount.value++
    if (idleRoundCount.value >= 2) {
      isAutoPlay.value = true // 累计两轮无操作，自动进入托管模式
      sendAction({ action: 'set_auto_play', enabled: true })
      return
    }
  }
  if (gameStore.gamePhase === 'CALLING') {
    // 叫地主阶段超时，自动选择“不叫”
    handleSkipCall(true)
  } else if (gameStore.gamePhase === 'PLAYING') {
    if (isAutoPlay.value) {
      sendAction({ action: 'set_auto_play', enabled: true })
      return
    }
    handlePass(true)
  }
}

// 叫地主操作
function handleCall() {
  playSound('btnClick')
  idleRoundCount.value = 0
  sendAction({ action: 'call_landlord', score: nextCallScore.value })
}

// 濞戞挸绉磋ぐ?濞戞挸绉垫慨鐘诲箼瀹ュ嫮绋?
function handleSkipCall(isAuto = false) {
  if (!isAuto) {
    playSound('btnClick')
    idleRoundCount.value = 0
  }
  sendAction({ action: 'skip_call' })
}

function handleShowCards(multiplier: number) {
  playSound('btnClick')
  sendAction({ action: 'show_cards', multiplier })
}

function handleLandlordShow(show: boolean) {
  playSound('btnClick')
  sendAction({ action: 'landlord_show', show })
}

function getLandlordNickname() {
  const l = gameStore.players.find(p => p.id === gameStore.landlord)
  return l ? l.nickname : '地主'
}

// 闁告垼娅ｆ晶婵嬪箼瀹ュ嫮绋?
function handlePlayCards() {
  if (!canSubmitSelected.value) return
  playSound('btnClick')
  idleRoundCount.value = 0
  sendAction({
    action: 'play_cards',
    cards: gameStore.selectedCards
  })
  gameStore.clearSelection()
}

// 濞戞挸绉烽々?閺夆晛娲ㄦ晶婵嬪箼瀹ュ嫮绋?
function handlePass(isAuto = false) {
  if (!isAuto) {
    playSound('btnClick')
    idleRoundCount.value = 0
  }
  sendAction({ action: 'pass_turn' })
  gameStore.clearSelection()
}

function selectHintAt(index: number) {
  const playableHints = gameStore.aiHintCandidates.filter((cards) => cards.length > 0)
  if (playableHints.length === 0) return
  hintState.value = {
    allHints: playableHints,
    currentIndex: index % playableHints.length,
  }
  gameStore.selectCards(playableHints[hintState.value.currentIndex] || [])
}

function applySuggestion() {
  if (gameStore.gamePhase !== 'PLAYING' || !gameStore.isMyTurn || isHintLoading.value) return
  playSound('btnClick')

  if (!hintState.value || hintState.value.allHints.length === 0) {
    if (gameStore.aiHintCandidates.length > 0) {
      selectHintAt(0)
      return
    }
    isHintLoading.value = true
    sendAction({ action: 'get_ai_hints' })
    return
  }

  selectHintAt(hintState.value.currentIndex + 1)
}

// 发送聊天短语
function handleSendChat(msgId: number) {
  playSound('btnClick')
  sendAction({ action: 'chat', msg_id: msgId })
  showChatMenu.value = false
}

// 选择加倍
function chooseDoubling(type: 'double' | 'super' | 'none') {
  playSound('btnClick')
  playDoubleChoiceSound(type, playerStore.playerId)
  idleRoundCount.value = 0
  sendAction({ action: 'choose_double', choice: type })
}

// 闁稿繑濞婂Λ瀵哥磼閹惧墎鏆梻鍫涘灪濠㈡﹢鏁嶅畝鍕缂傚喚鍠楅弳鐔煎箲椤旇壈瀚欓弶鈺傛煥濞叉牗寰勮瀹?
function handleCloseSettlement() {
  const currentMode = gameStore.playMode || 'classic'
  gameStore.reset()
  router.push(`/lobby?play_mode=${currentMode}`)
}

// 退出房间
function handleExitRoom() {
  playSound('btnClick')
  if (confirm('确定要退出当前游戏吗？这将会使您托管或流失积分！')) {
    stopBgm()
    disconnect()
    const currentMode = gameStore.playMode || 'classic'
    gameStore.reset()
    router.push(`/lobby?play_mode=${currentMode}`)
  }
}

// 获取结算阶段某个玩家的余牌
function getSettleRemainingCards(playerId: string): number[] {
  if (!gameStore.settlement || !gameStore.settlement.allHands) return []
  const hands = gameStore.settlement.allHands[playerId] || []
  return sortCardIds(hands)
}

// 闁烩晜鍨甸幆?errorMsg闁挎稑濂旂粩鎾籍閿旇姤绠掗柛濠勩€嬬槐婵嬪捶?2.5 缂佸甯掗幃妤呮嚊椤忓嫬袟婵烇絺鈧啿姣夋繛鎴濈墕閵?
watch(
  () => gameStore.errorMsg,
  (newVal) => {
    if (newVal) {
      setTimeout(() => {
        gameStore.errorMsg = ''
      }, 2500)
    }
  }
)

function clearHintCache() {
  hintState.value = null
  isHintLoading.value = false
  gameStore.clearAiHintCandidates()
}

watch(
  () => gameStore.aiHintCandidates,
  (candidates) => {
    isHintLoading.value = false
    if (gameStore.gamePhase === 'PLAYING' && gameStore.isMyTurn && candidates.length > 0 && !hintState.value) {
      selectHintAt(0)
    }
  },
  { deep: true }
)

// 闁烩晜鍨甸幆澶愬炊閻愬弶鍊ら柟瀛樼墬閻栧爼骞嬭箛娑欌枆婵炲牆鐏氶弫濂稿矗濮楀牏绀夊璺虹С缂嶅懐鎼鹃崨顔筋槯濠㈣泛瀚幃濠囧冀閸ヮ亶鍞?
watch(
  [() => gameStore.currentTurn, () => gameStore.gamePhase],
  () => {
    hasHandledTimeout.value = false
    clearHintCache()
  }
)

watch(
  () => gameStore.myHand,
  () => {
    clearHintCache()
  },
  { deep: true }
)

watch(
  () => gameStore.lastPlay,
  () => {
    clearHintCache()
  },
  { deep: true }
)

// 闁烩晜鍨甸幆澶愭煂瀹ュ棙鐓€婵炲弶顨堟晶?
watch(
  () => gameStore.gamePhase,
  (newPhase, oldPhase) => {
    if (newPhase === 'DEALING' && oldPhase === 'CALLING') {
      gameStore.showRedealNotice = true
      setTimeout(() => {
        gameStore.showRedealNotice = false
      }, 1800)
    }
  }
)
</script>

<template>
  <div class="game-table room-modern-layout" :class="{ 'no-shuffle-room': gameStore.playMode === 'no_shuffle', 'fifty-k-room': gameStore.playMode === 'fifty_k' }">
    <!-- 濠㈠爢鍛杺闁绘顫夐弲銉ッ归鑲╂勾 -->
    <div class="poker-effects-layer" :class="{ 'shake-screen': gameStore.activeEffect === 'bomb', 'fire-shaking': gameStore.activeEffect === 'bomb' && gameStore.playMode === 'no_shuffle' }">
      <!-- 炸弹冲击波 -->
      <div v-if="gameStore.activeEffect === 'bomb'" class="effect-bomb-shockwave" :class="{ 'fire-shockwave': gameStore.playMode === 'no_shuffle' }">
        <div class="shockwave-ring"></div>
        <div class="shockwave-ring delay"></div>
      </div>
      <!-- 濡炲鍋炲┃鈧柛鎺撳笩缁?-->
      <div v-if="gameStore.activeEffect === 'plane'" class="effect-plane-flyby">
        <div class="plane-silhouette">✈</div>
        <div class="plane-smoke"></div>
      </div>
    </div>

    <!-- 濡炪倕鐖奸崕鎾偐閼哥鍋撴担鍦焿 -->
    <header class="room-header">
      <div class="top-left-hud">
        <button class="btn-exit" @click="handleExitRoom" aria-label="退出">
          <span class="exit-arrow">↩</span>
        </button>

        <div v-if="gameStore.gamePhase === 'PLAYING' || gameStore.gamePhase === 'CALLING' || gameStore.gamePhase === 'DOUBLING'" class="card-remembrancer">
          <div class="remembrancer-heading">
            <span>牌型统计 ▲</span>
            <span class="remembrancer-fold">»</span>
          </div>
          <div class="remembrancer-grid">
            <div
              v-for="item in discardCounts"
              :key="item.key"
              class="rem-col"
              :class="{ zero: item.count === 0, active: item.count > 0 }"
            >
              <span class="rem-key">{{ item.key }}</span>
              <span class="rem-count">{{ item.count }}</span>
            </div>
          </div>
        </div>
      </div>

      <div class="room-info">
        <div class="score-status-pill">
          <span class="base-score-badge">底分: <strong>{{ gameStore.baseScore }}</strong></span>
          <span class="multiplier-badge font-glow">倍数: <strong>{{ gameStore.multiplier }}倍</strong></span>
          <span v-if="gameStore.playMode === 'no_shuffle'" class="no-shuffle-tag-neon">不洗牌场</span>
          <span v-else-if="gameStore.playMode === 'fifty_k'" class="no-shuffle-tag-neon" style="background: linear-gradient(135deg, #ffd700 0%, #ff8f00 100%); border-color: #ffeb3b; box-shadow: 0 0 8px rgba(255, 215, 0, 0.6); color: #3e2723;">510K各自为战</span>
        </div>

        <!-- 闁瑰灚顭囬鎼佸箰婢舵劖灏?-->
        <button
          v-if="gameStore.gamePhase === 'PLAYING' || gameStore.gamePhase === 'CALLING' || gameStore.gamePhase === 'DOUBLING'"
          class="btn-autoplay"
          :class="{ active: isAutoPlay }"
          @click="toggleAutoplay"
        >
          {{ isAutoPlay ? '托管中 (点击取消)' : '开启托管' }}
        </button>
      </div>

      <div class="top-right-hud">
        <div v-if="gameStore.playMode !== 'fifty_k'" class="bottom-cards-panel">
          <div class="bottom-cards-title">地主牌</div>
          <div class="bottom-cards-row">
            <div
              v-for="(cId, index) in gameStore.bottomCards.length > 0 ? gameStore.bottomCards : [0, 0, 0]"
              :key="index"
              class="bottom-card-flip-container"
              :class="{ 'is-flipped': gameStore.bottomCards.length > 0 }"
            >
              <div class="bottom-card-inner" :style="{ transitionDelay: (index * 0.1) + 's' }">
                <div class="bottom-card-back">
                  <PokerCard :card-id="0" :face-down="true" :no-hover="true" size="sm" />
                </div>
                <div class="bottom-card-front">
                  <PokerCard :card-id="cId" :face-down="false" :no-hover="true" size="sm" />
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="settings-control-area">
          <button class="btn-settings-toggle" @click="showSettings = true; playSound('btnClick')" title="设置">
            <span class="settings-gear">⚙</span>
            <span class="settings-label">设置</span>
          </button>
        </div>
      </div>
    </header>

    <!-- 婵炴惌LOGO -->
    <div class="brand-logo-watermark">
      <div v-if="gameStore.playMode === 'fifty_k'" class="watermark-main">510K各自为战</div>
      <div v-else class="watermark-main">欢乐斗地主</div>
      <div class="watermark-sub">
        <span v-if="gameStore.playMode === 'no_shuffle'">不洗牌新手场</span>
        <span v-else-if="gameStore.playMode === 'fifty_k'">510K新手场</span>
        <span v-else>经典新手场</span>
        底分{{ gameStore.baseScore }}
      </div>
    </div>

    <!-- 不洗牌模式中央 3D 浮雕印章 -->
    <div class="no-shuffle-stamp" v-if="gameStore.playMode === 'no_shuffle'">
      <span>不洗牌模式</span>
    </div>

    <!-- 510K 模式中央 3D 浮雕印章 -->
    <div class="no-shuffle-stamp fifty-k-stamp" v-if="gameStore.playMode === 'fifty_k'">
      <span>510K 各自为战</span>
    </div>

    <!-- 婵℃鐭傚鐗堢▔椤撶偑浜烽柛鎴ｆ婢ф繃绋夋惔鈥承楀ù锝嗙矊閻秶绮堥崫鍕殬 -->
    <div class="table-play-area">
      <div
        v-for="seat in orderedSeats"
        :key="seat.player.id"
        class="play-seat-zone"
        :class="[seat.position, { 'show-all-hands': gameStore.showAllHands }]"
      >
        <template v-if="!gameStore.showAllHands">
          <!-- 缂侇喖澧界欢銊╂偋鐟欏嫭娅忓鍫嗗啰鎽熼柛鏂诲妺缂嶆棃寮崶銊︽嫳 -->
          <div
            v-if="gameStore.playerActions[seat.player.id]"
            class="action-text-fancy"
            :class="[
              (gameStore.playerActions[seat.player.id] === '不出' ||
               gameStore.playerActions[seat.player.id] === '不叫' ||
               gameStore.playerActions[seat.player.id] === '不抢' ||
               gameStore.playerActions[seat.player.id] === '不加倍') ? 'blue' : 'gold'
            ]"
          >
            {{ gameStore.playerActions[seat.player.id] }}
          </div>
          <!-- 闁绘鑻悗鐑藉及閸撗佷粵 -->
          <div
            v-else-if="gameStore.playerPlayedCards[seat.player.id] && gameStore.playerPlayedCards[seat.player.id]!.length > 0"
            class="played-cards-row"
            :class="[
              { 'shimmer-active': gameStore.activeEffect === 'shimmer' && gameStore.lastPlay.player === seat.player.id },
              { 'wrap-cards': seat.position !== 'bottom' && gameStore.playerPlayedCards[seat.player.id]!.length > 8 }
            ]"
          >
            <PokerCard
              v-for="cId in sortPlayedCards(gameStore.playerPlayedCards[seat.player.id] || [])"
              :key="cId"
              :card-id="cId"
              :no-hover="true"
              size="sm"
            />
          </div>
        </template>

        <!-- 缂備焦鎸鹃悾濠氬及鎼达絽顤傞悘鐐存礈閵囨岸宕?-->
        <template v-else>
          <div
            v-if="getSettleRemainingCards(seat.player.id).length > 0"
            class="settle-hands-list-center"
          >
            <div class="settle-remain-title">{{ seat.player.nickname }} 的余牌:</div>
            <div class="settle-remain-cards">
              <PokerCard
                v-for="(cId, index) in getSettleRemainingCards(seat.player.id)"
                :key="cId"
                :card-id="cId"
                :no-hover="true"
                size="sm"
                class="settle-remain-card"
                :style="{ marginLeft: index === 0 ? '0px' : '-28px', zIndex: index }"
              />
            </div>
          </div>
          <div v-else class="settle-finished-status">
            <span class="settle-finished-text">打完了</span>
            <!-- 閻忕偞娲滈妵姘辨導閵忕媭鍟€闁哄牃鍋撻柛姘凹缁旀潙鈻庨埄鍐ㄢ叺闁告垼娅ｅ▓鎴犵磼濠靛洦绲婚柣?-->
            <div
              v-if="gameStore.playerPlayedCards[seat.player.id] && gameStore.playerPlayedCards[seat.player.id]!.length > 0"
              class="played-cards-row"
              style="margin-top: 8px;"
            >
              <PokerCard
                v-for="cId in sortPlayedCards(gameStore.playerPlayedCards[seat.player.id] || [])"
                :key="cId"
                :card-id="cId"
                :no-hover="true"
                size="sm"
              />
            </div>
          </div>
        </template>
      </div>
    </div>

    <!-- 濞戞搩鍙冮崕瀛樻償瑜岀紞鍛€掗崣澶屽帬闁?-->
    <div class="seats-container">
      <PlayerSeat
        v-for="seat in orderedSeats"
        :key="seat.player.id"
        :player="seat.player"
        :position="seat.position"
        :is-current-turn="gameStore.currentTurn === seat.player.id"
      />
    </div>

    <!-- 玩家操作栏区域 -->
    <div class="player-bottom-area">
      <!-- 发牌阶段随时可选的明牌按钮 -->
      <div v-if="gameStore.showCardsAvailableMultiplier !== null && !gameStore.showCardsPlayers[playerStore.playerId] && gameStore.playMode !== 'fifty_k'" class="action-bar-row">
        <button
          class="btn-action-call"
          style="background: linear-gradient(135deg, #ff7043 0%, #d84315 100%); border-color: #ffab91;"
          @click="handleShowCards(gameStore.showCardsAvailableMultiplier!)"
        >
          ⚡ 确认明牌 ×{{ gameStore.showCardsAvailableMultiplier }}
        </button>
      </div>

      <!-- 地主明牌确认面板 -->
      <div v-if="gameStore.gamePhase === 'LANDLORD_CONFIRM' && gameStore.awaitingLandlordShow && gameStore.playMode !== 'fifty_k'" class="action-bar-row">
        <div v-if="gameStore.landlord === playerStore.playerId" class="actions-group">
          <button
            class="btn-action-call"
            style="background: linear-gradient(135deg, #42a5f5 0%, #1565c0 100%); border-color: #90caf9;"
            @click="handleLandlordShow(true)"
          >
            明 牌
          </button>

          <div class="turn-alarm-clock">
            <div class="clock-icon">⏰</div>
            <span class="time-left-digits">{{ timeLeft }}</span>
          </div>

          <button
            class="btn-action-call"
            style="background: linear-gradient(135deg, #ff7043 0%, #d84315 100%); border-color: #ffab91;"
            @click="handleLandlordShow(false)"
          >
            出 牌
          </button>
        </div>
        <div v-else class="waiting-hint-text-wrapper">
          <div class="turn-alarm-clock inline-clock">
            <div class="clock-icon">⏰</div>
            <span class="time-left-digits">{{ timeLeft }}</span>
          </div>
          <div class="waiting-hint-text">
            等待地主 ({{ getLandlordNickname() }}) 选择...
          </div>
        </div>
      </div>

      <!-- 麦克风/叫地主操作 -->
      <div v-if="showDoublingPanel" class="action-bar-row">
        <div class="play-action-panel">
          <div class="actions-group">
            <button
              class="btn-action-call"
              style="background: linear-gradient(135deg, #ffca28 0%, #ff8f00 100%); border-color: #ffe082;"
              @click="chooseDoubling('double')"
            >
              加倍
            </button>

            <!-- 闁告梻濮撮埀顒€绉瑰Ο浣糕枔闂堟稑鏁堕柤杈ㄦ⒐濡炲倿鏌﹂悢娲诲悁闁哄啳娉涘▍?-->
            <div class="turn-alarm-clock">
              <div class="clock-icon">⏰</div>
              <span class="time-left-digits">{{ timeLeft }}</span>
            </div>

            <button
              class="btn-action-call"
              style="background: linear-gradient(135deg, #ff7043 0%, #d84315 100%); border-color: #ffab91;"
              @click="chooseDoubling('super')"
            >
              超级加倍
            </button>

            <button
              class="btn-action-pass"
              @click="chooseDoubling('none')"
            >
              不加倍
            </button>
          </div>
        </div>
      </div>

      <!-- 闂佹寧鐟ㄩ銈咁潩閺冣偓閸?-->
      <transition name="fade">
        <div v-if="gameStore.errorMsg" class="error-toast-bubble">
          <span>⚠ {{ gameStore.errorMsg }}</span>
        </div>
      </transition>

      <!-- 閺夌儐鍠栭崺宀勬嚊椤忓嫮绠掗柛鎰－閻°儵寮崜浣圭暠闁哄啫鐖奸幐鎾诲磹閹烘洦鍚€闁哄啯婀圭粭宀€鎮扮仦钘壭楅梻鍫涘灪濠?-->
      <div v-if="gameStore.isMyTurn && !showDoublingPanel" class="action-bar-row">
        <!-- 闁告瑯鍋勫﹢瀛樼▔婵犳碍鈻夋繛鍫濈仛濡炲倿鏌﹂悢娲诲悁闁哄啳娉涘▍?-->
        <!-- 闁告瑯鍋勫﹢瀛樼▔婵犳碍鈻夋繛鍫濈仛濡炲倿鏌﹂悢娲诲悁闁哄啳娉涘▍?-->
        <div v-if="gameStore.gamePhase === 'CALLING' && gameStore.playMode !== 'fifty_k'" class="turn-alarm-clock">
          <div class="clock-icon">⏰</div>
          <span class="time-left-digits">{{ timeLeft }}</span>
        </div>

        <!-- 闁告瑯鍋勫﹢瀛樼▔婵犳碍鈻夋繛鍫濈仛鐎垫粓鏌?-->
        <div v-if="gameStore.gamePhase === 'CALLING' && gameStore.playMode !== 'fifty_k'" class="actions-group">
          <button class="btn-action-call" @click="handleCall">{{ callActionLabel }}</button>
          <button class="btn-action-pass" @click="handleSkipCall()">{{ passCallLabel }}</button>
        </div>

        <!-- 闁告垼娅ｆ晶婵嬫⒓閼告鍞介柟绋款樀閹?-->
        <div v-if="gameStore.gamePhase === 'PLAYING'" class="play-action-panel">
          <div
            v-if="gameStore.selectedCards.length > 0 && !selectedPlayState.valid"
            class="selection-warning"
          >
            {{ selectedPlayState.message }}
          </div>
          <div class="actions-group">
            <button
              class="btn-action-pass"
              :disabled="!canPass"
              @click="handlePass()"
            >
              不出
            </button>

            <!-- 闁告垼娅ｆ晶婵嬫⒓閼告鍞介柛鎰嚀娴犲牓寮崼鏇熷閻犱讲鍓濆鍌炲闯?-->
            <div class="turn-alarm-clock">
              <div class="clock-icon">⏰</div>
              <span class="time-left-digits">{{ timeLeft }}</span>
            </div>

            <button
              class="btn-action-hint"
              :disabled="gameStore.gamePhase !== 'PLAYING' || !gameStore.isMyTurn || isHintLoading"
              @click="applySuggestion"
            >
              {{ hintButtonText }}
            </button>

            <button
              class="btn-action-call"
              :disabled="!canSubmitSelected"
              @click="handlePlayCards"
            >
              出牌
            </button>
          </div>
        </div>
      </div>

      <!-- 闁煎浜滅换渚€鎯冮崟顒€顤侀柣?-->
      <div class="self-hand-row">
        <HandCards :cards="gameStore.myHand" :hinted-cards="suggestedCards" size="lg" />
      </div>
    </div>

    <!-- 婵炴挸鎲￠崹娆戠磼閹惧瓨灏嗙€归潻缂氱粭鍛喆閹烘垯浜ｉ悗?-->
    <transition name="fade">
      <div v-if="gameStore.showGameOverBanner" class="game-over-finish-text">打完啦！！</div>
    </transition>

    <!-- 婵炴挸鎲￠崹娆戠磼閹惧瓨灏嗘繛鎼枤閳规牗寰勮閻?-->
    <transition name="fade">
      <div v-if="gameStore.showWinnerBanner" class="game-over-banner-overlay">
        <div class="game-over-title font-glow">{{ gameStore.gameOverTitle }}</div>
      </div>
    </transition>

    <!-- 缂備焦鎸鹃悾璇差嚕閸︻厾宕?-->
    <SettlementModal
      v-if="gameStore.gamePhase === 'SETTLING' && gameStore.settlement"
      :settlement="gameStore.settlement"
      :players="gameStore.players"
      :last-played-cards="gameStore.playerPlayedCards"
      :play-mode="gameStore.playMode"
      :base-score="gameStore.baseScore"
      @close="handleCloseSettlement"
    />

    <!-- 闂佹彃绉甸弻濠偯哄Δ鍐杺闁圭粯鍔楅妵?-->
    <transition name="fade">
      <div v-if="gameStore.showRedealNotice" class="redeal-overlay glass-panel">
        <div class="redeal-content">
          <span class="redeal-text">无人叫牌，正在重新洗牌中... <span class="redeal-spin-icon">🔄</span></span>
        </div>
      </div>
    </transition>

    <!-- 闁告鍠撴晶妤侇槹鎼淬垻澹愰悹浣稿⒔閻ゅ棗顕ｉ崷顓犲炊 -->
    <SettingsModal :show="showSettings" @close="showSettings = false" />

    <!-- 闁规潙娼″Λ鍧楀矗閸戙倗绀勭€归潻缂氱粭鍛喆閹烘垹娼旂紒鈧悮瀵哥 -->
    <div class="room-id-footer">
      房间号: <strong>{{ gameStore.roomId }}</strong>
    </div>

    <!-- 闊浂鍋呭畵搴ｆ嫚椤撯寬鏇㈠矗閹存繂闅橀柛鈺冨櫐缁辨瑩宕ｉ崗鍛憮閻熸瑦甯掗惈宥囩矆閻氬绀?-->
    <div class="chat-trigger-area">
      <button
        class="btn-voice"
        :class="{ active: roomVoice.isVoiceEnabled.value, connecting: roomVoice.isConnecting.value }"
        :title="roomVoice.isVoiceEnabled.value ? '关闭语音' : '开启语音'"
        @click="handleToggleVoice"
      >
        {{ roomVoice.isConnecting.value ? '连接中' : roomVoice.isVoiceEnabled.value ? '麦克风开' : '麦克风' }}
      </button>
      <button class="btn-chat" @click="showChatMenu = !showChatMenu">
        快捷语
      </button>
      <div v-if="roomVoice.voiceError.value" class="voice-error">
        {{ roomVoice.voiceError.value }}
      </div>
      <!-- 闊浂鍋呭畵搴ｆ嫚椤撱垺妗ㄩ柡?-->
      <div v-if="showChatMenu" class="chat-menu glass-panel">
        <div
          v-for="(text, idx) in CHAT_PRESETS"
          :key="idx"
          class="chat-menu-item"
          @click="handleSendChat(idx)"
        >
          {{ text }}
        </div>
      </div>
    </div>

    <!-- 飞金豆粒子动画层 -->
    <div class="beans-fly-container">
      <div
        v-for="bean in activeBeans"
        :key="bean.id"
        class="fly-gold-bean"
        :style="{
          left: bean.x + 'px',
          top: bean.y + 'px',
          transform: `scale(${bean.scale})`,
          transition: `all ${bean.duration}s cubic-bezier(0.25, 1, 0.5, 1)`,
          opacity: bean.opacity
        }"
      >
        🪙
      </div>

      <!-- 得分/金豆飘字 -->
      <div
        v-for="float in floatingTexts"
        :key="float.id"
        class="floating-score-text"
        :style="{
          left: float.x + 'px',
          top: float.y + 'px',
        }"
      >
        <span class="score-gain" v-if="float.scoreGained">{{ float.scoreGained }}</span>
        <span class="beans-gain" v-if="float.beansGained">{{ float.beansGained }}</span>
      </div>
    </div>

    <!-- Mock 模式下的吃分特效测试按钮 -->
    <div v-if="isMockMode && gameStore.playMode === 'fifty_k'" style="position: absolute; bottom: 80px; left: 20px; z-index: 1000;">
      <button
        @click="triggerMockTrickSettled"
        style="padding: 8px 16px; background: linear-gradient(135deg, #ffca28 0%, #ff8f00 100%); border: 1.5px solid #fff; border-radius: 8px; color: #3e2723; font-weight: 800; cursor: pointer; box-shadow: 0 4px 10px rgba(0,0,0,0.3);"
      >
        测试吃分飞豆动画
      </button>
      <button
        @click="triggerMockGameOver"
        style="padding: 8px 16px; margin-left: 10px; background: linear-gradient(135deg, #e040fb 0%, #7c4dff 100%); border: 1.5px solid #fff; border-radius: 8px; color: #fff; font-weight: 800; cursor: pointer; box-shadow: 0 4px 10px rgba(0,0,0,0.3);"
      >
        测试终局结算弹窗
      </button>
    </div>
  </div>
</template>

<style scoped>
.room-modern-layout {
  display: flex;
  flex-direction: column;
  height: 100vh;
  position: relative;
  overflow: hidden;
  background:
    radial-gradient(circle at 50% 42%, rgba(122, 196, 255, 0.75) 0%, rgba(42, 129, 216, 0.9) 34%, rgba(33, 82, 157, 0.98) 70%),
    linear-gradient(135deg, #244b9b 0%, #2e78c4 52%, #27437f 100%);
  color: #ffffff;
}

/* 濡炪倕鐖奸崕鎾偐閼哥鍋撴担鍦焿 */
.room-header {
  display: grid;
  grid-template-columns: minmax(360px, 1fr) auto minmax(260px, 1fr);
  align-items: start;
  gap: 20px;
  min-height: 118px;
  padding: 10px 12px;
  background: linear-gradient(to bottom, rgba(9, 28, 73, 0.58) 0%, rgba(9, 28, 73, 0) 100%);
  z-index: 30;
}

.top-left-hud,
.top-right-hud {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.top-right-hud {
  justify-content: flex-end;
  align-items: flex-start;
  gap: 16px;
}

.btn-exit {
  width: 36px;
  height: 36px;
  flex: 0 0 auto;
  background: rgba(255, 255, 255, 0.16);
  border: 2px solid rgba(255, 255, 255, 0.65);
  color: #ffffff;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 700;
  display: flex;
  justify-content: center;
  align-items: center;
  text-shadow: 0 2px 3px rgba(0,0,0,0.45);
}

.exit-arrow {
  font-size: 1.35rem;
  line-height: 1;
}

.btn-exit:hover {
  background: rgba(255, 255, 255, 0.25);
}

.room-info {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  gap: 8px;
  min-width: 240px;
  white-space: nowrap;
}

.score-status-pill {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 28px;
  min-width: 238px;
  min-height: 48px;
  padding: 0 24px;
  border-radius: 26px;
  background: rgba(16, 42, 86, 0.45);
  border: 1px solid rgba(205, 224, 255, 0.25);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.16),
    0 8px 18px rgba(0, 0, 0, 0.16);
}

.room-id, .base-score-badge, .multiplier-badge {
  font-size: 1rem;
  font-weight: 700;
  text-shadow: 0 1px 3px rgba(0,0,0,0.6);
}

.multiplier-badge {
  color: #ffd700;
  font-weight: bold;
}

.font-glow {
  text-shadow: 0 0 8px rgba(255, 215, 0, 0.6);
}

.chat-trigger-area {
  position: absolute;
  bottom: 20px;
  right: 20px;
  z-index: 100;
  display: flex;
  align-items: flex-end;
  gap: 8px;
}

.btn-chat,
.btn-voice {
  border: 1px solid #ffd54f;
  color: #3e2723;
  min-width: 76px;
  min-height: 34px;
  padding: 6px 12px;
  border-radius: 20px;
  font-weight: bold;
  cursor: pointer;
  white-space: nowrap;
}

.btn-chat {
  background: linear-gradient(to bottom, #ffb300, #ff8f00);
}

.btn-voice {
  background: linear-gradient(to bottom, #b3e5fc, #4fc3f7);
  border-color: #e1f5fe;
}

.btn-voice.active {
  background: linear-gradient(to bottom, #81c784, #43a047);
  color: #fff;
  border-color: #c8e6c9;
}

.btn-voice.connecting {
  opacity: 0.78;
}

.voice-error {
  position: absolute;
  right: 0;
  bottom: 44px;
  width: 220px;
  padding: 8px 10px;
  border-radius: 6px;
  background: rgba(86, 19, 19, 0.9);
  color: #fff3e0;
  font-size: 0.8rem;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
}

.chat-menu {
  position: absolute;
  right: 0;
  bottom: 44px;
  width: min(300px, calc(100vw - 40px));
  max-height: min(420px, calc(100vh - 140px));
  overflow-y: auto;
  padding: 8px 0;
  display: flex;
  flex-direction: column;
  z-index: 50;
}

.room-id-footer {
  position: absolute;
  bottom: 20px;
  left: 20px;
  font-size: 0.85rem;
  color: rgba(255, 255, 255, 0.45);
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.6);
  z-index: 100;
  pointer-events: none;
}

.chat-menu-item {
  padding: 10px 16px;
  font-size: 0.85rem;
  cursor: pointer;
  transition: all 0.2s;
  text-align: left;
}

.chat-menu-item:hover {
  background: rgba(255, 255, 255, 0.15);
  color: #ffd700;
}

.bottom-cards-row {
  display: flex;
  justify-content: center;
  gap: 4px;
  flex: 0 0 auto;
  padding: 0 6px 7px;
}

.bottom-cards-panel {
  width: 188px;
  padding: 8px 6px 6px;
  border-radius: 8px;
  background: rgba(7, 28, 67, 0.55);
  border: 1px solid rgba(205, 224, 255, 0.3);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.13),
    0 7px 18px rgba(0, 0, 0, 0.18);
}

.bottom-cards-title {
  margin-bottom: 5px;
  color: rgba(221, 231, 255, 0.86);
  font-size: 0.95rem;
  font-weight: 800;
  line-height: 1;
  text-align: center;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.55);
}

/* 閻犱焦澹嗘晶婵嬪闯?*/
.card-remembrancer {
  width: clamp(340px, 31vw, 420px);
  overflow: hidden;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.92);
  color: #283348;
  border: 1px solid rgba(205, 224, 255, 0.28);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25);
}

.remembrancer-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 30px;
  padding: 0 12px;
  color: rgba(234, 242, 255, 0.93);
  background: rgba(12, 42, 89, 0.82);
  font-size: 0.9rem;
  font-weight: 800;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.45);
}

.remembrancer-fold {
  color: rgba(234, 242, 255, 0.76);
  font-size: 1.35rem;
  line-height: 1;
}

.remembrancer-grid {
  display: grid;
  grid-template-columns: repeat(15, minmax(22px, 1fr));
}

.rem-col {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 58px;
  border-left: 1px solid rgba(40, 51, 72, 0.18);
  line-height: 1.05;
}

.rem-col:first-child {
  border-left: none;
}

.rem-key {
  font-size: 0.82rem;
  font-weight: 800;
  color: #2b3448;
}

.rem-count {
  margin-top: 8px;
  font-size: 0.92rem;
  font-weight: 900;
  color: #e96d1a;
}

.rem-col.zero {
  background: rgba(238, 238, 238, 0.7);
}

.rem-col.zero .rem-count {
  color: rgba(212, 106, 27, 0.24);
}

/* 婵炴惌鍣ｅú澶愬冀閸パ呯闁煎啿鏈▍?*/
.brand-logo-watermark {
  position: absolute;
  top: 41%;
  left: 50%;
  transform: translate(-50%, -50%);
  pointer-events: none;
  opacity: 0.08;
  text-align: center;
  z-index: 1;
}

.watermark-main {
  font-size: 5rem;
  font-weight: 900;
  letter-spacing: 6px;
}

.watermark-sub {
  font-size: 1.5rem;
  font-weight: bold;
  margin-top: 10px;
}

/* 閹煎洷鍌滅Т閻庡湱鎳撳▍?*/
.seats-container {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  pointer-events: none;
  z-index: 10;
}
.seats-container :deep(*) {
  pointer-events: auto;
}

/* 闁告梻濮撮埀顒€绉规导鍕磾?*/
.doubling-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.55);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 100;
  backdrop-filter: blur(5px);
}

.doubling-dialog {
  width: 90%;
  max-width: 400px;
  padding: 30px;
  text-align: center;
}

.doubling-dialog h3 {
  color: #ffd700;
  font-weight: 900;
  margin-bottom: 24px;
}

.doubling-buttons {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.btn-double {
  background: linear-gradient(135deg, #0288d1 0%, #01579b 100%);
  color: #fff;
  font-weight: 800;
  border: 1px solid #4fc3f7;
  padding: 12px;
  border-radius: 20px;
  cursor: pointer;
  font-size: 1.1rem;
}

.btn-super-double {
  background: linear-gradient(135deg, #ff8f00 0%, #d84315 100%);
  color: #fff;
  font-weight: 900;
  border: 1px solid #ffb74d;
  padding: 12px;
  border-radius: 20px;
  cursor: pointer;
  font-size: 1.2rem;
  box-shadow: 0 4px 10px rgba(216, 67, 21, 0.4);
}

.btn-no-double {
  background: rgba(255, 255, 255, 0.2);
  color: #fff;
  font-weight: bold;
  border: 1px solid rgba(255, 255, 255, 0.3);
  padding: 10px;
  border-radius: 20px;
  cursor: pointer;
}

.btn-double:hover, .btn-super-double:hover, .btn-no-double:hover {
  transform: scale(1.02);
}

/* 閹煎瓨娲熼崕鎾箥鐎ｎ剙顤傚☉鎾虫唉椤㈡垿宕濋妸锔惧焿 */
.player-bottom-area {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 100%;
  gap: 8px;
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 25;
}

.action-bar-row {
  display: flex;
  align-items: center;
  gap: 16px;
  background: rgba(9, 39, 83, 0.78);
  padding: 8px 18px;
  border-radius: 28px;
  border: 1.5px solid rgba(255, 255, 255, 0.24);
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
  animation: slide-up 0.25s cubic-bezier(0.175, 0.885, 0.32, 1.275);
}

@keyframes slide-up {
  from { transform: translateY(15px); opacity: 0; }
  to { transform: translateY(0); opacity: 1; }
}

/* 闂傚倸缍婇幐鎾诲冀瀹勬壆纭€ */
.turn-alarm-clock {
  display: flex;
  align-items: center;
  background: #ffb300;
  border-radius: 15px;
  padding: 4px 12px;
  border: 1.5px solid #ffe082;
  box-shadow: 0 2px 6px rgba(0,0,0,0.3);
}

.clock-icon {
  font-size: 1.1rem;
  animation: shake 0.5s infinite alternate;
}

@keyframes shake {
  from { transform: rotate(-10deg); }
  to { transform: rotate(10deg); }
}

.time-left-digits {
  color: #3e2723;
  font-size: 1.15rem;
  font-weight: 900;
  margin-left: 6px;
}

.actions-group {
  display: flex;
  gap: 12px;
  align-items: center;
}

.play-action-panel {
  display: flex;
  align-items: center;
  gap: 12px;
}

.play-hint-pill,
.selection-warning {
  max-width: min(42vw, 520px);
  min-height: 34px;
  display: inline-flex;
  align-items: center;
  padding: 5px 14px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.92);
  color: #24314d;
  font-size: 0.92rem;
  font-weight: 800;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.28);
}

.play-hint-pill.cant,
.selection-warning {
  color: #ffffff;
  background: rgba(59, 91, 167, 0.88);
  border: 1px solid rgba(185, 205, 255, 0.45);
}

/* 閻炴稑鑻慨鈺傚緞瑜庣€垫粓鏌?*/
.btn-action-call {
  background: linear-gradient(135deg, #ffb300 0%, #ff8f00 100%);
  color: #1a1a1a;
  font-weight: 900;
  border: none;
  padding: 10px 28px;
  border-radius: 20px;
  cursor: pointer;
  box-shadow: 0 4px 8px rgba(255, 143, 0, 0.3);
  font-size: 1.05rem;
}
.btn-action-call:hover:not(:disabled) {
  background: linear-gradient(135deg, #ffe082 0%, #ffb300 100%);
}
.btn-action-call:disabled {
  background: #757575;
  color: #9e9e9e;
  box-shadow: none;
  cursor: not-allowed;
}

.btn-action-pass {
  background: linear-gradient(135deg, #7fd9ff 0%, #6968e8 100%);
  color: #ffffff;
  font-weight: 800;
  border: none;
  padding: 10px 28px;
  border-radius: 20px;
  cursor: pointer;
  box-shadow: 0 4px 8px rgba(2, 136, 209, 0.3);
  font-size: 1.05rem;
}
.btn-action-pass:hover:not(:disabled) {
  background: linear-gradient(135deg, #b6ecff 0%, #8180ff 100%);
}
.btn-action-pass:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.btn-action-reset {
  background: rgba(255, 255, 255, 0.15);
  color: #ffffff;
  font-weight: bold;
  border: 1px solid rgba(255, 255, 255, 0.25);
  padding: 10px 24px;
  border-radius: 20px;
  cursor: pointer;
}
.btn-action-reset:hover {
  background: rgba(255, 255, 255, 0.25);
}

.btn-action-hint {
  background: linear-gradient(135deg, #8fb6ff 0%, #7366df 100%);
  color: #ffffff;
  font-weight: 900;
  border: none;
  padding: 10px 28px;
  border-radius: 20px;
  cursor: pointer;
  box-shadow: 0 4px 8px rgba(70, 75, 160, 0.32);
  font-size: 1.05rem;
}

.btn-action-hint:hover:not(:disabled) {
  background: linear-gradient(135deg, #b9d2ff 0%, #8e84ff 100%);
}

.btn-action-hint:disabled {
  opacity: 0.45;
  cursor: not-allowed;
  box-shadow: none;
}

.self-hand-row {
  width: 100%;
  max-width: min(92vw, 1120px);
}

/* 闁瑰灚顭囬鎼佸箰婢舵劖灏﹂柛鈺勬椤㈠懘宕ｆ繝鍌涘殤闁告艾鎽滄导鍛村矗閹存繂甯ㄩ柡宥呭槻缁?*/
.btn-autoplay {
  background: rgba(210, 225, 255, 0.24);
  border: 1px solid rgba(226, 238, 255, 0.42);
  border-radius: 16px;
  color: #fff;
  padding: 5px 17px;
  font-size: 13px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  transition: all 0.3s ease;
  font-weight: 700;
  line-height: 1;
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.18);
}

.btn-autoplay:hover {
  background: rgba(255, 255, 255, 0.3);
  transform: translateY(-1px);
}

.btn-autoplay.active {
  background: #ff5722;
  border-color: #ff5722;
  box-shadow: 0 0 10px rgba(255, 87, 34, 0.6);
  animation: pulse-autoplay 1.5s infinite alternate;
}

@keyframes pulse-autoplay {
  0% {
    transform: scale(1);
    box-shadow: 0 0 10px rgba(255, 87, 34, 0.6);
  }
  100% {
    transform: scale(1.05);
    box-shadow: 0 0 20px rgba(255, 87, 34, 0.9);
  }
}

@media (max-width: 1180px) {
  .room-header {
    grid-template-columns: 1fr auto;
  }

  .room-info {
    order: 3;
    grid-column: 1 / -1;
    min-width: 0;
    justify-content: center;
    margin-top: -6px;
  }

  .card-remembrancer {
    width: min(62vw, 680px);
  }

  .play-action-panel {
    flex-direction: column;
    align-items: stretch;
    gap: 7px;
  }

  .play-hint-pill,
  .selection-warning {
    max-width: 76vw;
    justify-content: center;
  }
}

@media (max-width: 780px) {
  .room-header {
    padding: 8px 10px;
    grid-template-columns: 1fr;
  }

  .top-left-hud,
  .top-right-hud,
  .room-info {
    justify-content: center;
  }

  .top-left-hud {
    flex-wrap: wrap;
  }

  .card-remembrancer {
    order: 2;
    width: calc(100vw - 20px);
  }

  .top-right-hud {
    flex-wrap: wrap;
  }

  .room-info {
    flex-wrap: wrap;
    gap: 8px;
  }

  .action-bar-row {
    flex-wrap: wrap;
    justify-content: center;
    border-radius: 18px;
  }
}

/* 婵℃鐭傚鐗堢▔椤撶偑浜烽柛鎴ｆ婢ф繈宕犻悜妯煎鐎?*/
.table-play-area {
  position: absolute;
  top: 30%;
  left: 20%;
  right: 20%;
  height: 35%;
  pointer-events: none;
  z-index: 15;
}

.play-seat-zone {
  position: absolute;
  display: flex;
  align-items: center;
  pointer-events: none;
}

.play-seat-zone.left {
  left: 20px;
  top: 15%;
  justify-content: flex-start;
}

.play-seat-zone.right {
  right: 20px;
  top: 15%;
  justify-content: flex-end;
}

.play-seat-zone.bottom {
  left: 50%;
  bottom: 20px;
  transform: translateX(-50%);
  justify-content: center;
}

.bubble-action {
  background: rgba(0, 0, 0, 0.8);
  border: 1.5px solid rgba(255, 255, 255, 0.2);
  color: #ffffff;
  padding: 8px 18px;
  border-radius: 18px;
  font-weight: bold;
  font-size: 0.95rem;
  white-space: nowrap;
  box-shadow: 0 4px 10px rgba(0,0,0,0.4);
}

.bubble-action.pass {
  background: rgba(3, 169, 244, 0.85);
  border-color: #80d8ff;
}

/* 闁绘顫夐弲銉р偓鍦嚀濞呮帗绋夋惔鈥冲伎閻忕偛绻樺〒鍧楀礉?*/
.poker-effects-layer {
  position: absolute;
  top: 0; left: 0; width: 100%; height: 100%;
  pointer-events: none;
  z-index: 99;
  overflow: hidden;
}
.poker-effects-layer.shake-screen {
  animation: screen-shake 0.4s ease-out;
}
@keyframes screen-shake {
  0%, 100% { transform: translate(0, 0); }
  10%, 90% { transform: translate(-3px, 2px); }
  30%, 70% { transform: translate(4px, -3px); }
  50% { transform: translate(-5px, 4px); }
}

/* 闁绘劗顭堥懘濠囧礃閹绘帒姣婃繛澶堝灩濠€鈧?*/
.effect-bomb-shockwave {
  position: absolute;
  top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  width: 100px; height: 100px;
}
.shockwave-ring {
  position: absolute;
  width: 100%; height: 100%;
  border-radius: 50%;
  border: 4px solid rgba(255, 179, 0, 0.8);
  box-shadow: 0 0 20px rgba(255, 87, 34, 0.6);
  animation: ripple 0.8s cubic-bezier(0.1, 0.8, 0.3, 1) forwards;
}
.shockwave-ring.delay {
  animation-delay: 0.2s;
}
@keyframes ripple {
  0% { transform: scale(0.5); opacity: 1; }
  100% { transform: scale(4); opacity: 0; border-width: 1px; }
}

/* 濡炲鍋炲┃鈧柣妤勵潐閺?*/
.effect-plane-flyby {
  position: absolute;
  top: 30%;
  width: 100%;
  height: 60px;
  display: flex;
  align-items: center;
  animation: plane-fly 1.2s cubic-bezier(0.25, 1, 0.5, 1) forwards;
}
.plane-silhouette {
  font-size: 2.5rem;
  transform: rotate(-15deg);
  filter: drop-shadow(0 0 10px rgba(255,255,255,0.8));
}
.plane-smoke {
  flex: 1;
  height: 6px;
  background: linear-gradient(to right, rgba(255,255,255,0) 0%, rgba(255,255,255,0.7) 100%);
  margin-left: -15px;
  border-radius: 3px;
  box-shadow: 0 0 10px rgba(255,255,255,0.4);
}
@keyframes plane-fly {
  from { left: -100px; opacity: 0; }
  10% { opacity: 1; }
  90% { opacity: 1; }
  to { left: 110%; opacity: 0; }
}

.played-cards-row {
  position: relative;
  display: flex;
  gap: 3px;
  background: rgba(0, 0, 0, 0.35);
  padding: 6px;
  border-radius: 6px;
  border: 1px solid rgba(255,255,255,0.08);
}

.played-cards-row.wrap-cards {
  flex-wrap: wrap;
  max-width: 252px;
}

.play-seat-zone.right .played-cards-row {
  justify-content: flex-end;
}
.poker-effects-layer + .played-cards-row::after,
.shimmer-active::after {
  content: '';
  position: absolute;
  top: 0; left: -100%; width: 50%; height: 100%;
  background: linear-gradient(to right, rgba(255,255,255,0) 0%, rgba(255, 215, 0, 0.4) 50%, rgba(255,255,255,0) 100%);
  transform: skewX(-25deg);
  animation: shimmer-flow 1.0s ease-out;
}
@keyframes shimmer-flow {
  from { left: -150%; }
  to { left: 150%; }
}

/* 闁绘顫夐弲銉﹀緞瑜嶉悺褔宕濋妸銈囩▕闁哄倸娲﹀﹢?*/
.action-text-fancy {
  font-size: 2.4rem;
  font-weight: 900;
  font-style: italic;
  white-space: nowrap;
  letter-spacing: 2px;
  animation: pop-up 0.25s cubic-bezier(0.175, 0.885, 0.32, 1.275);
}

.action-text-fancy.gold {
  color: #ffb300;
  text-shadow:
    0 0 10px rgba(255, 179, 0, 0.6),
    2px 2px 0px #ff6f00,
    4px 4px 6px rgba(0, 0, 0, 0.8);
}

.action-text-fancy.blue {
  color: #03a9f4;
  text-shadow:
    0 0 10px rgba(3, 169, 244, 0.6),
    2px 2px 0px #01579b,
    4px 4px 6px rgba(0, 0, 0, 0.8);
}

@keyframes pop-up {
  from { transform: scale(0.6); opacity: 0; }
  to { transform: scale(1); opacity: 1; }
}

/* 婵炴挸鎲￠崹娆戠磼閹惧瓨灏嗘繛鎼枤閳规牗寰勮閻?*/
.game-over-banner-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  z-index: 99;
  pointer-events: none;
  background: rgba(0, 0, 0, 0.2);
}

.game-over-title {
  font-size: 5rem;
  font-weight: 900;
  font-style: italic;
  color: #ffd700;
  text-shadow:
    0 0 20px rgba(255, 215, 0, 0.8),
    4px 4px 0px #e65100,
    8px 8px 15px rgba(0, 0, 0, 0.9);
  animation: banner-zoom 0.5s cubic-bezier(0.175, 0.885, 0.32, 1.275) both;
  letter-spacing: 6px;
}

.game-over-finish-text {
  position: absolute;
  left: 10%;
  bottom: 25%;
  font-size: 3.5rem;
  font-weight: 900;
  font-style: italic;
  color: #ff5722;
  transform: rotate(-15deg);
  text-shadow:
    0 0 15px rgba(255, 87, 34, 0.8),
    3px 3px 0px #bf360c,
    6px 6px 12px rgba(0, 0, 0, 0.9);
  animation: stamp-in 0.4s ease-out 0.3s both;
  z-index: 20;
}

@keyframes banner-zoom {
  0% { transform: scale(0.3); opacity: 0; }
  100% { transform: scale(1); opacity: 1; }
}

@keyframes stamp-in {
  0% { transform: rotate(-45deg) scale(2); opacity: 0; }
  100% { transform: rotate(-15deg) scale(1); opacity: 1; }
}

.fade-enter-active, .fade-leave-active {
  transition: opacity 0.5s;
}
.fade-enter-from, .fade-leave-to {
  opacity: 0;
}

/* 缂備焦鎸鹃悾濠氱嵁閹惰姤鎳欏ù锝嗙懅婢ф繃绋夋惔鈥冲殥闁瑰灚鎸搁悾顒勫箵閹邦喓浠?*/
.settle-hands-list-center {
  display: flex;
  flex-direction: column;
  align-items: center;
  background: rgba(0, 0, 0, 0.65);
  padding: 8px 12px;
  border-radius: 12px;
  border: 1.5px solid rgba(255, 255, 255, 0.2);
  box-shadow: 0 4px 15px rgba(0, 0, 0, 0.5);
}

.play-seat-zone.left.show-all-hands {
  left: calc(-20vw + 150px);
}
.play-seat-zone.right.show-all-hands {
  right: calc(-20vw + 150px);
}

.play-seat-zone.left .settle-hands-list-center {
  align-items: flex-start;
}
.play-seat-zone.right .settle-hands-list-center {
  align-items: flex-end;
}

.settle-remain-title {
  font-size: 0.85rem;
  color: #ffb300;
  font-weight: bold;
  margin-bottom: 5px;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.8);
}

.settle-remain-cards {
  display: flex;
  flex-wrap: wrap;
  max-width: 320px;
  row-gap: 6px;
  align-items: center;
  padding: 0 10px;
}

.settle-remain-card {
  transition: transform 0.2s ease;
}

.settle-finished-status {
  display: flex;
  justify-content: center;
  align-items: center;
  background: linear-gradient(135deg, #e65100 0%, #ff8f00 100%);
  border: 2px solid #ffd700;
  padding: 6px 18px;
  border-radius: 18px;
  box-shadow: 0 4px 15px rgba(230, 81, 0, 0.4);
  animation: pop-up 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275);
}

.settle-finished-text {
  color: #fff;
  font-weight: 900;
  font-size: 1.1rem;
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.6);
  letter-spacing: 2px;
}

/* 闂佹寧鐟ㄩ銈咁潩閺冣偓閸?*/
.error-toast-bubble {
  position: absolute;
  bottom: 80px;
  left: 50%;
  transform: translateX(-50%);
  background: linear-gradient(135deg, #e53935 0%, #b71c1c 100%);
  color: #fff;
  padding: 10px 20px;
  border-radius: 20px;
  font-weight: 700;
  box-shadow: 0 4px 15px rgba(0,0,0,0.3);
  border: 1.5px solid rgba(255,255,255,0.25);
  backdrop-filter: blur(8px);
  z-index: 100;
  animation: shake-toast 0.4s ease;
}
@keyframes shake-toast {
  0%, 100% { transform: translateX(-50%); }
  20%, 60% { transform: translateX(-54%); }
  40%, 80% { transform: translateX(-46%); }
}

/* 闂佹彃绉甸弻濠偯哄Δ鍐杺婵☆垼浜滅粻?*/
.redeal-overlay {
  position: absolute;
  top: 40%;
  left: 50%;
  transform: translate(-50%, -50%);
  padding: 18px 36px;
  border-radius: 12px;
  border: 2px solid #ffd54f;
  background: rgba(9, 39, 83, 0.9);
  color: #ffd54f;
  font-size: 1.3rem;
  font-weight: 900;
  z-index: 999;
  box-shadow: 0 8px 30px rgba(0,0,0,0.5);
  display: flex;
  align-items: center;
  justify-content: center;
}
.redeal-spin-icon {
  display: inline-block;
  animation: spin-redeal 1.2s linear infinite;
}
@keyframes spin-redeal {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* 3D 閹煎瓨娲滄晶婵堢礄閺勫繑绁?*/
.bottom-card-flip-container {
  perspective: 600px;
  width: 52px;
  height: 73px;
  margin: 0;
}
.bottom-card-inner {
  position: relative;
  width: 100%;
  height: 100%;
  transform-style: preserve-3d;
  transition: transform 0.6s cubic-bezier(0.175, 0.885, 0.32, 1.275);
}
.bottom-card-flip-container.is-flipped .bottom-card-inner {
  transform: rotateY(180deg);
}
.bottom-card-front, .bottom-card-back {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  backface-visibility: hidden;
}
.bottom-card-front {
  transform: rotateY(180deg);
}

.bottom-card-flip-container :deep(.poker-card.size-sm) {
  width: 52px;
  height: 73px;
  padding: 3px;
  border-radius: 5px;
}

/* ===== 闂傚﹨娅曢弲銉╁箳瑜嶉崺妤呮閵忊剝绶?===== */
.settings-control-area {
  position: relative;
  flex: 0 0 auto;
}

.btn-settings-toggle {
  width: 58px;
  min-height: 64px;
  padding: 7px 0 6px;
  background: rgba(18, 46, 92, 0.58);
  border: 1px solid rgba(210, 229, 255, 0.36);
  border-radius: 8px;
  color: rgba(238, 246, 255, 0.95);
  cursor: pointer;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 5px;
  transition: all 0.2s;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.16),
    0 6px 14px rgba(0, 0, 0, 0.2);
}

.btn-settings-toggle:hover {
  background: rgba(255, 255, 255, 0.28);
  transform: translateY(-1px);
}

.settings-gear {
  width: 36px;
  height: 36px;
  display: grid;
  place-items: center;
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.12);
  border: 1px solid rgba(255, 255, 255, 0.28);
  font-size: 24px;
  line-height: 1;
}

.settings-label {
  font-size: 13px;
  font-weight: 800;
  line-height: 1;
}

.sound-panel {
  position: absolute;
  right: 0;
  top: 52px;
  width: 220px;
  padding: 14px 16px;
  border-radius: 12px;
  z-index: 200;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.sound-panel-title {
  font-size: 14px;
  font-weight: 700;
  text-align: center;
  margin-bottom: 2px;
  color: #ffe082;
}

.sound-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.9);
}

.sound-toggle-btn {
  padding: 3px 12px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.4);
  background: rgba(255, 255, 255, 0.1);
  color: rgba(255, 255, 255, 0.6);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  min-width: 44px;
  text-align: center;
}

.sound-toggle-btn.active {
  background: rgba(76, 175, 80, 0.5);
  border-color: #66bb6a;
  color: #ffffff;
}

.sound-slider {
  flex: 1;
  max-width: 100px;
  height: 4px;
  accent-color: #ffe082;
  cursor: pointer;
}

.waiting-hint-text {
  color: #a5d6a7;
  font-size: 1.05rem;
  font-weight: 800;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.6);
}

.waiting-hint-text-wrapper {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.inline-clock {
  margin: 0 auto;
}
/* 不洗牌专属主题背景 */
.game-table.room-modern-layout.no-shuffle-room {
  background: linear-gradient(135deg, #1d0909 0%, #3a1616 50%, #4e1919 100%) !important;
}

/* 中央 3D 浮雕印章 */
.no-shuffle-stamp {
  position: absolute;
  top: 52%;
  left: 50%;
  transform: translate(-50%, -50%) rotate(-12deg);
  border: 4px double rgba(212, 175, 55, 0.45);
  border-radius: 12px;
  padding: 8px 24px;
  font-family: "Microsoft YaHei", sans-serif;
  font-size: 2.2rem;
  font-weight: 900;
  color: rgba(212, 175, 55, 0.55);
  text-shadow: 1px 1px 0px rgba(0, 0, 0, 0.6),
               -1px -1px 0px rgba(255, 255, 255, 0.1),
               0 0 12px rgba(212, 175, 55, 0.2);
  letter-spacing: 4px;
  user-select: none;
  pointer-events: none;
  z-index: 1;
  box-shadow: inset 0 0 8px rgba(212, 175, 55, 0.2), 0 4px 15px rgba(0, 0, 0, 0.5);
  background: radial-gradient(circle, rgba(78, 25, 25, 0.3) 0%, rgba(29, 9, 9, 0.3) 100%);
}

.no-shuffle-stamp span {
  display: block;
}

/* 顶栏红色霓虹呼吸标签 */
.no-shuffle-tag-neon {
  margin-left: 10px;
  background: linear-gradient(135deg, #ff1744 0%, #d50000 100%);
  color: #ffffff;
  padding: 2px 10px;
  border-radius: 8px;
  font-size: 0.75rem;
  font-weight: 900;
  border: 1px solid #ff5252;
  box-shadow: 0 0 8px rgba(255, 23, 68, 0.6);
  text-shadow: 0 0 2px rgba(0, 0, 0, 0.5);
  letter-spacing: 0.5px;
  animation: neon-breath-red 1.5s infinite alternate;
}

@keyframes neon-breath-red {
  0% {
    box-shadow: 0 0 4px rgba(255, 23, 68, 0.4);
    border-color: rgba(255, 82, 82, 0.6);
  }
  100% {
    box-shadow: 0 0 12px rgba(255, 23, 68, 0.9), 0 0 20px rgba(255, 23, 68, 0.4);
    border-color: rgba(255, 82, 82, 1);
  }
}

/* 炽热火红炸弹特效 */
.effect-bomb-shockwave.fire-shockwave .shockwave-ring {
  border: 8px solid #ff3d00;
  box-shadow: 0 0 50px #ff3d00, inset 0 0 30px #d50000;
}

.poker-effects-layer.fire-shaking {
  background: rgba(213, 0, 0, 0.15) !important;
  animation: fire-flash 0.5s ease-out;
}

@keyframes fire-flash {
  0% { background: rgba(255, 61, 0, 0.4); }
  100% { background: rgba(213, 0, 0, 0); }
}

/* 510K 专属主题背景，高贵暗金黑夜风格 */
.game-table.room-modern-layout.fifty-k-room {
  background: linear-gradient(135deg, #0d1b2a 0%, #1b263b 50%, #0d1b2a 100%) !important;
}

.fifty-k-stamp {
  border: 4px double rgba(255, 215, 0, 0.65) !important;
  color: rgba(255, 215, 0, 0.75) !important;
  box-shadow: inset 0 0 10px rgba(255, 215, 0, 0.3), 0 4px 20px rgba(0, 0, 0, 0.6) !important;
  background: radial-gradient(circle, rgba(27, 38, 59, 0.4) 0%, rgba(13, 27, 42, 0.4) 100%) !important;
  animation: gold-glow-breath 2s infinite alternate;
}

@keyframes gold-glow-breath {
  0% {
    text-shadow: 1px 1px 0px rgba(0, 0, 0, 0.8), 0 0 8px rgba(255, 215, 0, 0.3);
    box-shadow: inset 0 0 10px rgba(255, 215, 0, 0.3), 0 4px 20px rgba(0, 0, 0, 0.6);
  }
  100% {
    text-shadow: 1px 1px 0px rgba(0, 0, 0, 0.8), 0 0 18px rgba(255, 215, 0, 0.8);
    box-shadow: inset 0 0 15px rgba(255, 215, 0, 0.5), 0 4px 25px rgba(255, 215, 0, 0.2);
  }
}

/* 飞金豆和得分飘字样式 */
.beans-fly-container {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  z-index: 9999;
}

.fly-gold-bean {
  position: absolute;
  font-size: 24px;
  line-height: 1;
  pointer-events: none;
  filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.5));
}

.floating-score-text {
  position: absolute;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  pointer-events: none;
  animation: float-up-fade 2s ease-out forwards;
  z-index: 10000;
}

.score-gain {
  font-size: 1.8rem;
  font-weight: 900;
  color: #ffeb3b;
  text-shadow: 0 0 8px rgba(255, 235, 59, 0.8), 2px 2px 0px #e65100;
  font-style: italic;
  letter-spacing: 1px;
}

.beans-gain {
  font-size: 1.4rem;
  font-weight: 800;
  color: #ffd700;
  text-shadow: 0 0 6px rgba(255, 215, 0, 0.8), 1.5px 1.5px 0px #b71c1c;
}

@keyframes float-up-fade {
  0% {
    transform: translateY(20px);
    opacity: 0.3;
  }
  15% {
    transform: translateY(0);
    opacity: 1;
  }
  80% {
    transform: translateY(-40px);
    opacity: 1;
  }
  100% {
    transform: translateY(-60px);
    opacity: 0;
  }
}
</style>
