<!-- frontend/src/components/SettingsModal.vue -->
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { usePlayerStore } from '@/stores/playerStore'
import { useSoundEngine } from '@/composables/useSoundEngine'

const props = defineProps<{
  show: boolean
}>()

const emit = defineEmits<{
  (e: 'close'): void
}>()

const playerStore = usePlayerStore()
const {
  playSound,
  toggleSfx,
  toggleBgm,
  setVoiceGender,
  setCustomVoice,
  getSettings
} = useSoundEngine()

// 选项卡状态
type TabName = 'sound' | 'game' | 'privacy' | 'feedback' | 'version'
const activeTab = ref<TabName>('sound')

// 获取与加载声音设置状态
const sfxSettings = ref(getSettings())
const localGender = ref<'male' | 'female' | 'auto'>(sfxSettings.value.voiceGender)

function updateSettings() {
  sfxSettings.value = getSettings()
  localGender.value = sfxSettings.value.voiceGender
}

function handleToggleSfx() {
  playSound('btnClick')
  toggleSfx()
  updateSettings()
}

function handleToggleBgm() {
  playSound('btnClick')
  toggleBgm()
  updateSettings()
}

function handleGenderChange(gender: 'male' | 'female') {
  playSound('btnClick')
  // 如果点击已选择的，则切回 auto (即自适应)；否则设为选中的
  if (localGender.value === gender) {
    setVoiceGender('auto')
  } else {
    setVoiceGender(gender)
  }
  updateSettings()
}

function handleToggleCustomVoice() {
  playSound('btnClick')
  setCustomVoice(!sfxSettings.value.customVoiceEnabled)
  updateSettings()
}

// ─── 游戏设置状态 (Local Storage 持久化) ───
const showTitleBadge = ref(true)
const verticalCards = ref(true)

function loadGameSettings() {
  showTitleBadge.value = localStorage.getItem('hmp_show_title_badge') !== 'false'
  verticalCards.value = localStorage.getItem('hmp_vertical_cards') !== 'false'
}

function toggleTitleBadge() {
  playSound('btnClick')
  showTitleBadge.value = !showTitleBadge.value
  localStorage.setItem('hmp_show_title_badge', showTitleBadge.value ? 'true' : 'false')
}

function toggleVerticalCards() {
  playSound('btnClick')
  verticalCards.value = !verticalCards.value
  localStorage.setItem('hmp_vertical_cards', verticalCards.value ? 'true' : 'false')
}

// ─── 隐私设置状态 (Local Storage 持久化) ───
const showRecord = ref(true)
const receiveEmoji = ref(true)
const showHonor = ref(false)
const showRank = ref(false)
const showGeo = ref(true)
const recommendFriend = ref(true)
const friendApply = ref(true)
const nearbyInvite = ref(true)

function loadPrivacySettings() {
  showRecord.value = localStorage.getItem('hmp_privacy_show_record') !== 'false'
  receiveEmoji.value = localStorage.getItem('hmp_privacy_receive_emoji') !== 'false'
  showHonor.value = localStorage.getItem('hmp_privacy_show_honor') === 'true'
  showRank.value = localStorage.getItem('hmp_privacy_show_rank') === 'true'
  showGeo.value = localStorage.getItem('hmp_privacy_show_geo') !== 'false'
  recommendFriend.value = localStorage.getItem('hmp_privacy_recommend_friend') !== 'false'
  friendApply.value = localStorage.getItem('hmp_privacy_friend_apply') !== 'false'
  nearbyInvite.value = localStorage.getItem('hmp_privacy_nearby_invite') !== 'false'
}

function togglePrivacy(key: string, refObj: any) {
  playSound('btnClick')
  refObj.value = !refObj.value
  localStorage.setItem(key, refObj.value ? 'true' : 'false')
}

// ─── 反馈逻辑 ───
const feedbackText = ref('')
const feedbackSent = ref(false)
const feedbackToast = ref('')

function sendFeedback() {
  playSound('btnClick')
  if (!feedbackText.value.trim()) {
    triggerToast('请输入您的反馈内容后再发送哦！')
    return
  }
  feedbackSent.value = true
  feedbackText.value = ''
  triggerToast('反馈发送成功！感谢您的宝贵建议！')
  setTimeout(() => {
    feedbackSent.value = false
  }, 3000)
}

function triggerToast(msg: string) {
  feedbackToast.value = msg
  setTimeout(() => {
    feedbackToast.value = ''
  }, 2000)
}

// ─── 版本复制玩家ID ───
const copySuccess = ref(false)
function copyPlayerId() {
  playSound('btnClick')
  if (navigator.clipboard) {
    navigator.clipboard.writeText(playerStore.playerId).then(() => {
      copySuccess.value = true
      setTimeout(() => copySuccess.value = false, 1500)
    })
  } else {
    // 降级复制
    const input = document.createElement('input')
    input.value = playerStore.playerId
    document.body.appendChild(input)
    input.select()
    document.execCommand('copy')
    document.body.removeChild(input)
    copySuccess.value = true
    setTimeout(() => copySuccess.value = false, 1500)
  }
}

// ─── 未开发模块提示 ───
function showFeatureNotice(title: string) {
  playSound('btnClick')
  alert(`【${title}】功能正在加急开发中，敬请期待！`)
}

onMounted(() => {
  updateSettings()
  loadGameSettings()
  loadPrivacySettings()
})
</script>

<template>
  <div v-if="show" class="settings-modal-overlay" @click.self="emit('close')">
    <div class="settings-modal-card">
      
      <!-- 左侧边栏导航 -->
      <div class="settings-sidebar">
        <div class="settings-sidebar-title">设置</div>
        
        <div class="settings-tabs-list">
          <button 
            class="tab-btn" 
            :class="{ active: activeTab === 'sound' }"
            @click="activeTab = 'sound'; playSound('btnClick')"
          >
            音效
          </button>
          <button 
            class="tab-btn" 
            :class="{ active: activeTab === 'game' }"
            @click="activeTab = 'game'; playSound('btnClick')"
          >
            游戏
          </button>
          <button 
            class="tab-btn" 
            :class="{ active: activeTab === 'privacy' }"
            @click="activeTab = 'privacy'; playSound('btnClick')"
          >
            隐私
          </button>
          <button 
            class="tab-btn" 
            :class="{ active: activeTab === 'feedback' }"
            @click="activeTab = 'feedback'; playSound('btnClick')"
          >
            反馈
          </button>
          <button 
            class="tab-btn" 
            :class="{ active: activeTab === 'version' }"
            @click="activeTab = 'version'; playSound('btnClick')"
          >
            版本
          </button>
        </div>
      </div>

      <!-- 右侧主体内容区 -->
      <div class="settings-content-wrapper">
        <!-- 关闭按钮 -->
        <button class="settings-close-x" @click="emit('close'); playSound('btnClick')">×</button>

        <!-- 1. 音效标签内容 -->
        <div v-if="activeTab === 'sound'" class="settings-tab-pane">
          
          <!-- 音效设置 -->
          <div class="settings-section">
            <div class="section-title">◆ 音效设置</div>
            <div class="settings-section-row grid-2">
              <div class="setting-item-toggle">
                <span>游戏音效</span>
                <div class="original-switch" :class="{ open: sfxSettings.sfxEnabled }" @click="handleToggleSfx">
                  <div class="switch-ball">♠</div>
                  <span class="switch-txt">{{ sfxSettings.sfxEnabled ? '开' : '关' }}</span>
                </div>
              </div>

              <div class="setting-item-toggle">
                <span>游戏音乐</span>
                <div class="original-switch" :class="{ open: sfxSettings.bgmEnabled }" @click="handleToggleBgm">
                  <div class="switch-ball">♠</div>
                  <span class="switch-txt">{{ sfxSettings.bgmEnabled ? '开' : '关' }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 语音设置 -->
          <div class="settings-section" style="margin-top: 24px;">
            <div class="section-title">◆ 语音设置</div>
            <div class="settings-section-row grid-2">
              <div class="setting-item-checkbox">
                <span>语音性别</span>
                <div class="checkbox-group">
                  <label class="custom-checkbox" @click="handleGenderChange('male')">
                    <span class="checkbox-box" :class="{ checked: localGender === 'male' }">
                      <span v-if="localGender === 'male'" class="check-mark">✔</span>
                    </span>
                    <span class="checkbox-label">男</span>
                  </label>
                  <label class="custom-checkbox" @click="handleGenderChange('female')">
                    <span class="checkbox-box" :class="{ checked: localGender === 'female' }">
                      <span v-if="localGender === 'female'" class="check-mark">✔</span>
                    </span>
                    <span class="checkbox-label">女</span>
                  </label>
                </div>
              </div>

              <div class="setting-item-toggle">
                <span>全员个性语音</span>
                <div class="original-switch" :class="{ open: sfxSettings.customVoiceEnabled }" @click="handleToggleCustomVoice">
                  <div class="switch-ball">♠</div>
                  <span class="switch-txt">{{ sfxSettings.customVoiceEnabled ? '开' : '关' }}</span>
                </div>
                <button class="settings-help-btn" @click="showFeatureNotice('个性语音说明')">?</button>
              </div>
            </div>
          </div>
        </div>

        <!-- 2. 游戏标签内容 -->
        <div v-if="activeTab === 'game'" class="settings-tab-pane flex-between-layout">
          <div>
            <!-- 游戏设置 -->
            <div class="settings-section">
              <div class="section-title">◆ 游戏设置</div>
              <div class="settings-section-row">
                <div class="setting-item-toggle">
                  <span>头衔展示</span>
                  <div class="original-switch" :class="{ open: showTitleBadge }" @click="toggleTitleBadge">
                    <div class="switch-ball">♠</div>
                    <span class="switch-txt">{{ showTitleBadge ? '开' : '关' }}</span>
                  </div>
                </div>
              </div>
            </div>

            <!-- 其它玩法设置 -->
            <div class="settings-section" style="margin-top: 24px;">
              <div class="section-title">◆ 斗地主玩法设置</div>
              <div class="settings-section-row">
                <div class="setting-item-toggle">
                  <span>手牌竖排展示</span>
                  <div class="original-switch" :class="{ open: verticalCards }" @click="toggleVerticalCards">
                    <div class="switch-ball">♠</div>
                    <span class="switch-txt">{{ verticalCards ? '开' : '关' }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 底部大黄色药丸按钮 -->
          <div class="game-actions-footer">
            <button class="yellow-pill-btn" @click="showFeatureNotice('新手教程')">新手教程</button>
            <button class="yellow-pill-btn" @click="showFeatureNotice('游戏规则')">规 则</button>
          </div>
        </div>

        <!-- 3. 隐私标签内容 -->
        <div v-if="activeTab === 'privacy'" class="settings-tab-pane flex-between-layout">
          <div class="scroll-container">
            <!-- 隐私设置 -->
            <div class="settings-section">
              <div class="section-title">
                ◆ 隐私设置
                <span class="settings-help-btn mini-help" @click="showFeatureNotice('隐私权指引')">?</span>
              </div>
              <div class="settings-section-row grid-2">
                <div class="setting-item-toggle">
                  <span>显示我的战绩</span>
                  <div class="original-switch" :class="{ open: showRecord }" @click="togglePrivacy('hmp_privacy_show_record', showRecord)">
                    <div class="switch-ball">♠</div>
                    <span class="switch-txt">{{ showRecord ? '开' : '关' }}</span>
                  </div>
                </div>
                <div class="setting-item-toggle">
                  <span>接收互动表情</span>
                  <div class="original-switch" :class="{ open: receiveEmoji }" @click="togglePrivacy('hmp_privacy_receive_emoji', receiveEmoji)">
                    <div class="switch-ball">♠</div>
                    <span class="switch-txt">{{ receiveEmoji ? '开' : '关' }}</span>
                  </div>
                </div>
                <div class="setting-item-toggle">
                  <span>显示历史荣誉</span>
                  <div class="original-switch" :class="{ open: showHonor }" @click="togglePrivacy('hmp_privacy_show_honor', showHonor)">
                    <div class="switch-ball">♠</div>
                    <span class="switch-txt">{{ showHonor ? '开' : '关' }}</span>
                  </div>
                </div>
                <div class="setting-item-toggle">
                  <span>显示我的排名</span>
                  <div class="original-switch" :class="{ open: showRank }" @click="togglePrivacy('hmp_privacy_show_rank', showRank)">
                    <div class="switch-ball">♠</div>
                    <span class="switch-txt">{{ showRank ? '开' : '关' }}</span>
                  </div>
                </div>
                <div class="setting-item-toggle">
                  <span>显示地理位置</span>
                  <div class="original-switch" :class="{ open: showGeo }" @click="togglePrivacy('hmp_privacy_show_geo', showGeo)">
                    <div class="switch-ball">♠</div>
                    <span class="switch-txt">{{ showGeo ? '开' : '关' }}</span>
                  </div>
                </div>
                <div class="setting-item-toggle">
                  <span>隐私管理</span>
                  <button class="settings-action-nav-btn" @click="showFeatureNotice('隐私授权管理')">设置 &gt;</button>
                </div>
              </div>
            </div>

            <!-- 好友同玩 -->
            <div class="settings-section" style="margin-top: 20px;">
              <div class="section-title">◆ 好友同玩</div>
              <div class="settings-section-row grid-2">
                <div class="setting-item-toggle">
                  <span>推荐好友提示</span>
                  <div class="original-switch" :class="{ open: recommendFriend }" @click="togglePrivacy('hmp_privacy_recommend_friend', recommendFriend)">
                    <div class="switch-ball">♠</div>
                    <span class="switch-txt">{{ recommendFriend ? '开' : '关' }}</span>
                  </div>
                  <button class="settings-help-btn" @click="showFeatureNotice('推荐好友')">?</button>
                </div>
                <div class="setting-item-toggle">
                  <span>好友申请</span>
                  <div class="original-switch" :class="{ open: friendApply }" @click="togglePrivacy('hmp_privacy_friend_apply', friendApply)">
                    <div class="switch-ball">♠</div>
                    <span class="switch-txt">{{ friendApply ? '开' : '关' }}</span>
                  </div>
                </div>
                <div class="setting-item-toggle">
                  <span>附近的人邀请</span>
                  <div class="original-switch" :class="{ open: nearbyInvite }" @click="togglePrivacy('hmp_privacy_nearby_invite', nearbyInvite)">
                    <div class="switch-ball">♠</div>
                    <span class="switch-txt">{{ nearbyInvite ? '开' : '关' }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 隐私底边协议法律链接 -->
          <div class="privacy-links-footer">
            <span @click="showFeatureNotice('用户协议')">棋牌游戏用户协议</span>
            <span @click="showFeatureNotice('隐私保护指南')">隐私保护指南</span>
            <span @click="showFeatureNotice('儿童隐私保护')">儿童隐私保护协议</span>
            <span @click="showFeatureNotice('第三方列表')">第三方信息共享清单</span>
            <span @click="showFeatureNotice('个人信息清单')">个人信息清单</span>
          </div>
        </div>

        <!-- 4. 反馈标签内容 -->
        <div v-if="activeTab === 'feedback'" class="settings-tab-pane">
          <!-- 常见问题 -->
          <div class="settings-section">
            <div class="section-title">◆ 常见问题</div>
            <div class="faq-row-buttons">
              <button class="faq-btn" @click="feedbackText = '反馈：我的头衔莫名其妙降级了，请协助核对排位星星。'">头衔降级了</button>
              <button class="faq-btn" @click="feedbackText = '反馈：游戏中听不到配音和人声，BGM正常。'">语音问题</button>
              <button class="faq-btn" @click="feedbackText = '反馈：整局游戏没有任何声音，静音设置已检查正常。'">没有声音</button>
              <button class="faq-btn" @click="feedbackText = '反馈：充值后欢乐豆没有到账。'">充值不到账</button>
              <button class="faq-btn" @click="showFeatureNotice('更多常见问题')">更多 &gt;</button>
            </div>
          </div>

          <!-- 反馈问题输入框 -->
          <div class="settings-section" style="margin-top: 20px;">
            <div class="section-title">◆ 反馈问题</div>
            <textarea 
              class="feedback-textarea" 
              placeholder="请先阅读常见问题，如没有解决请再输入您的问题，并留下微信号/QQ/手机号"
              v-model="feedbackText"
            ></textarea>
          </div>

          <!-- 底部反馈操纵区域 -->
          <div class="feedback-footer">
            <span class="feedback-sub-tip">您还可以关注“腾讯客服”微信公众号，获取更多帮助</span>
            <div class="feedback-actions">
              <button class="upload-log-btn" @click="showFeatureNotice('日志上传')">
                <span class="log-icon">📄</span> 上传日志
              </button>
              <button class="send-feedback-btn" @click="sendFeedback">发 送</button>
            </div>
          </div>
        </div>

        <!-- 5. 版本标签内容 -->
        <div v-if="activeTab === 'version'" class="settings-tab-pane">
          <!-- 版本主海报 -->
          <div class="version-banner">
            <div class="version-banner-bg">
              <div class="banner-title">欢乐斗地主</div>
              <div class="banner-sub">2.6.73.1.pcmina</div>
              <div class="banner-id-row">
                <span>id: {{ playerStore.playerId }}</span>
                <span class="copy-id-link" @click="copyPlayerId">
                  {{ copySuccess ? '已复制！' : '复制id' }}
                </span>
              </div>
              <div class="banner-prod">prod.o 3.16.1</div>
            </div>
          </div>

          <!-- 健康提示以及版本声明 -->
          <div class="version-disclaimer-box">
            <p>本网络游戏适合年满12周岁以上的用户使用。为了您的健康，请合理控制游戏时间。</p>
            <p class="warning-title">健康游戏公告：</p>
            <p>抵制不良游戏，拒绝盗版游戏。注意自我保护，谨防受骗上当。适度游戏益脑，沉迷游戏伤身。合理安排时间，享受健康生活。</p>
            <p>粤网文[2014]0633-233号；文网游备字〔2016〕M-CBG 0247 号；（总）网出证（粤）字第057号；新广出审[2017]5360号；</p>
            <p>ISBN 978-7-7979-8873-5；著作权人：腾讯科技（深圳）有限公司；出版单位：深圳市腾讯计算机系统有限公司。运营者：深圳市腾讯计算机系统有限公司。</p>
          </div>
        </div>

      </div>

      <!-- 反馈结果提示漂浮泡 -->
      <transition name="fade">
        <div v-if="feedbackToast" class="feedback-toast-bubble">
          {{ feedbackToast }}
        </div>
      </transition>
    </div>
  </div>
</template>

<style scoped>
/* 蒙层背景 */
.settings-modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  background: rgba(0, 0, 0, 0.55);
  backdrop-filter: blur(4px);
  z-index: 999;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* 核心面板卡片 */
.settings-modal-card {
  width: 760px;
  height: 440px;
  background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%);
  border: 4px solid #90caf9;
  box-shadow: 0 12px 36px rgba(0, 0, 0, 0.4), inset 0 2px 5px rgba(255, 255, 255, 0.6);
  border-radius: 20px;
  display: flex;
  overflow: hidden;
  position: relative;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  color: #1e3a8a;
  animation: modalScaleIn 0.25s cubic-bezier(0.175, 0.885, 0.32, 1.275);
}

@keyframes modalScaleIn {
  from { opacity: 0; transform: scale(0.9); }
  to { opacity: 1; transform: scale(1); }
}

/* 左侧导航栏 */
.settings-sidebar {
  width: 150px;
  background: linear-gradient(to bottom, #3949ab 0%, #1a237e 100%);
  display: flex;
  flex-direction: column;
  border-right: 3px solid #1565c0;
}

.settings-sidebar-title {
  padding: 16px 0;
  text-align: center;
  font-size: 24px;
  font-weight: 900;
  color: #ffffff;
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.5);
  letter-spacing: 4px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.15);
}

.settings-tabs-list {
  display: flex;
  flex-direction: column;
  flex: 1;
}

.tab-btn {
  background: transparent;
  border: none;
  color: #c5cae9;
  font-size: 16px;
  font-weight: 700;
  padding: 14px 0;
  cursor: pointer;
  transition: all 0.2s;
  text-align: center;
  position: relative;
}

.tab-btn:hover {
  color: #ffffff;
  background: rgba(255, 255, 255, 0.08);
}

/* 激活的标签 (金黄色渐变底色) */
.tab-btn.active {
  color: #3e2723;
  background: linear-gradient(to right, #ffb300, #ff8f00);
  text-shadow: none;
  font-weight: 900;
  border-left: 5px solid #ff3d00;
  box-shadow: inset -2px 0 5px rgba(0,0,0,0.15);
}

/* 右侧内容包裹区 */
.settings-content-wrapper {
  flex: 1;
  padding: 24px 30px;
  display: flex;
  flex-direction: column;
  position: relative;
  background: rgba(227, 242, 253, 0.85);
}

/* 头部关闭按钮 */
.settings-close-x {
  position: absolute;
  top: 10px;
  right: 18px;
  background: none;
  border: none;
  font-size: 32px;
  font-weight: 700;
  color: #1e3a8a;
  cursor: pointer;
  transition: transform 0.2s, color 0.2s;
  z-index: 10;
  line-height: 1;
}

.settings-close-x:hover {
  color: #d32f2f;
  transform: scale(1.15) rotate(90deg);
}

/* 主面板滚动或容器 */
.settings-tab-pane {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding-top: 10px;
}

.scroll-container {
  overflow-y: auto;
  max-height: 310px;
  padding-right: 8px;
}

.scroll-container::-webkit-scrollbar {
  width: 6px;
}
.scroll-container::-webkit-scrollbar-thumb {
  background: #90caf9;
  border-radius: 4px;
}

/* 模块容器和区块 */
.settings-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.section-title {
  font-size: 15px;
  font-weight: 900;
  color: #1565c0;
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 2px;
}

.settings-section-row {
  background: #f1f8e9; /* 轻盈浅绿灰 */
  border: 1px solid #c8e6c9;
  border-radius: 8px;
  padding: 10px 18px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.settings-section-row.grid-2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

/* 开关行样式 */
.setting-item-toggle,
.setting-item-checkbox {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 14px;
  font-weight: 700;
  color: #2e7d32;
  position: relative;
}

/* 经典桃心滑动开关 */
.original-switch {
  width: 68px;
  height: 26px;
  background: #b0bec5;
  border: 2px solid #90a4ae;
  border-radius: 13px;
  position: relative;
  cursor: pointer;
  transition: background-color 0.2s;
  display: flex;
  align-items: center;
}

.original-switch.open {
  background: linear-gradient(135deg, #ffd54f 0%, #ffb300 100%);
  border-color: #ffb300;
}

.switch-ball {
  width: 22px;
  height: 22px;
  background: #ffffff;
  border-radius: 50%;
  position: absolute;
  left: 2px;
  top: 0px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #b0bec5;
  font-size: 14px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.3);
  transition: transform 0.2s, color 0.2s;
  user-select: none;
}

.original-switch.open .switch-ball {
  transform: translateX(40px);
  color: #ff7043; /* 桃心红色 */
}

.switch-txt {
  font-size: 12px;
  font-weight: 900;
  position: absolute;
  color: #ffffff;
  pointer-events: none;
}

.original-switch:not(.open) .switch-txt {
  right: 10px;
  color: #ffffff;
}

.original-switch.open .switch-txt {
  left: 10px;
  color: #3e2723;
}

/* 问号小帮助按钮 */
.settings-help-btn {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #78909c;
  color: #ffffff;
  border: none;
  font-size: 11px;
  font-weight: 900;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  position: absolute;
  right: -24px;
}

.settings-help-btn:hover {
  background: #546e7a;
}

.settings-help-btn.mini-help {
  position: static;
  width: 14px;
  height: 14px;
  font-size: 9px;
}

/* 复选框/单选组 */
.checkbox-group {
  display: flex;
  gap: 18px;
}

.custom-checkbox {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
}

.checkbox-box {
  width: 18px;
  height: 18px;
  border: 2px solid #78909c;
  border-radius: 4px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: #ffffff;
  transition: all 0.2s;
}

.checkbox-box.checked {
  border-color: #ff8f00;
  background: #ffa000;
}

.check-mark {
  color: #ffffff;
  font-size: 11px;
  font-weight: 900;
}

.checkbox-label {
  font-size: 13px;
  font-weight: 700;
  color: #37474f;
}

.settings-action-nav-btn {
  background: linear-gradient(to bottom, #cfd8dc, #b0bec5);
  border: 1px solid #78909c;
  border-radius: 12px;
  padding: 2px 12px;
  font-size: 12px;
  font-weight: 700;
  color: #37474f;
  cursor: pointer;
}

.settings-action-nav-btn:hover {
  background: #b0bec5;
}

/* 游戏选项卡底部动作 */
.flex-between-layout {
  justify-content: space-between;
}

.game-actions-footer {
  display: flex;
  justify-content: center;
  gap: 30px;
  margin-top: 14px;
  margin-bottom: 5px;
}

/* 大黄色圆角 pill 按钮 */
.yellow-pill-btn {
  background: linear-gradient(135deg, #ffee58 0%, #fdd835 50%, #fbc02d 100%);
  border: 2px solid #ffee58;
  box-shadow: 0 4px 10px rgba(245, 127, 23, 0.35);
  border-radius: 20px;
  padding: 8px 32px;
  color: #5d4037;
  font-size: 15px;
  font-weight: 900;
  cursor: pointer;
  transition: transform 0.15s, box-shadow 0.15s;
}

.yellow-pill-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 14px rgba(245, 127, 23, 0.45);
}

/* 隐私底部链接 */
.privacy-links-footer {
  display: flex;
  justify-content: center;
  flex-wrap: wrap;
  gap: 8px 12px;
  font-size: 10px;
  color: #1e88e5;
  text-decoration: underline;
  cursor: pointer;
  margin-top: 10px;
}

.privacy-links-footer span:hover {
  color: #1565c0;
}

/* 常见问题常见按键 */
.faq-row-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 4px 0;
}

.faq-btn {
  background: #ffffff;
  border: 1px solid #b0bec5;
  border-radius: 6px;
  padding: 5px 12px;
  font-size: 12px;
  font-weight: 700;
  color: #37474f;
  cursor: pointer;
  transition: background 0.15s;
}

.faq-btn:hover {
  background: #eceff1;
  border-color: #90a4ae;
}

/* 反馈文本域 */
.feedback-textarea {
  width: 100%;
  height: 90px;
  border: 1px solid #b0bec5;
  border-radius: 6px;
  padding: 8px 12px;
  font-size: 12px;
  color: #37474f;
  resize: none;
  background: #ffffff;
  box-sizing: border-box;
}

.feedback-textarea:focus {
  outline: none;
  border-color: #1565c0;
  box-shadow: 0 0 4px rgba(21, 101, 192, 0.2);
}

/* 反馈底部操作 */
.feedback-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 14px;
}

.feedback-sub-tip {
  font-size: 11px;
  color: #546e7a;
}

.feedback-actions {
  display: flex;
  gap: 12px;
}

.upload-log-btn {
  background: #e0f2f1;
  border: 1px solid #80cbc4;
  border-radius: 18px;
  padding: 6px 14px;
  font-size: 13px;
  font-weight: 700;
  color: #00796b;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 4px;
}

.upload-log-btn:hover {
  background: #b2dfdb;
}

.send-feedback-btn {
  background: linear-gradient(to bottom, #ffd54f, #ffb300);
  border: 1.5px solid #ffa000;
  border-radius: 18px;
  padding: 6px 28px;
  font-size: 13px;
  font-weight: 900;
  color: #3e2723;
  cursor: pointer;
}

.send-feedback-btn:hover {
  background: #ffb300;
  transform: scale(1.03);
}

/* 版本控制板块 */
.version-banner {
  background: linear-gradient(135deg, #1e88e5 0%, #1565c0 100%);
  border-radius: 10px;
  padding: 16px 22px;
  color: #ffffff;
  box-shadow: 0 4px 10px rgba(0,0,0,0.15);
  margin-bottom: 12px;
}

.version-banner-bg {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.banner-title {
  font-size: 22px;
  font-weight: 900;
  letter-spacing: 2px;
  text-shadow: 0 1px 3px rgba(0,0,0,0.4);
}

.banner-sub {
  font-size: 11px;
  opacity: 0.85;
}

.banner-id-row {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 12px;
  margin-top: 4px;
}

.copy-id-link {
  color: #ffe082;
  text-decoration: underline;
  cursor: pointer;
  font-weight: 700;
}

.copy-id-link:hover {
  color: #ffd54f;
}

.banner-prod {
  font-size: 10px;
  opacity: 0.6;
}

.version-disclaimer-box {
  background: #eceff1;
  border: 1px solid #cfd8dc;
  border-radius: 8px;
  padding: 10px 14px;
  max-height: 160px;
  overflow-y: auto;
  font-size: 10px;
  line-height: 1.5;
  color: #546e7a;
}

.version-disclaimer-box p {
  margin: 0 0 6px 0;
}

.version-disclaimer-box .warning-title {
  color: #d84315;
  font-weight: 900;
}

/* 浮动飘字反馈气泡 */
.feedback-toast-bubble {
  position: absolute;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(0, 0, 0, 0.8);
  color: #ffffff;
  padding: 8px 24px;
  border-radius: 20px;
  font-size: 13px;
  font-weight: 700;
  z-index: 99;
  pointer-events: none;
}

.fade-enter-active, .fade-leave-active {
  transition: opacity 0.3s;
}
.fade-enter-from, .fade-leave-to {
  opacity: 0;
}
</style>
