<!-- frontend/src/views/DebugConsoleView.vue -->
<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()

// Token
const token = ref(localStorage.getItem('hmp_token') || new URLSearchParams(window.location.search).get('token') || '')

// WebSocket 调试连接状态
const clientId = ref('client_' + Math.random().toString(36).substring(2, 8))
const isConnected = ref(false)
const terminalLogs = ref<Array<{ time: string; text: string; type: 'system' | 'sent' | 'received' | 'error' }>>([])
const testMessage = ref('')
const testTarget = ref('')
let debugWs: WebSocket | null = null
let reconnectAttempts = 0
const MAX_RECONNECT = 5
let reconnectTimer: number | null = null
let isUserClose = false

// Active Tab
const activeTab = ref<'ws' | 'messages' | 'upload' | 'audit'>('ws')

// 站内信状态
const msgSender = ref('system')
const msgReceiver = ref(clientId.value)
const msgContent = ref('')
const msgFilter = ref<'all' | 'unread' | 'read'>('all')
const siteMessages = ref<any[]>([])
const unreadCount = ref(0)

// 上传状态 (滑动窗口分片并发 WebSocket 上传)
const uploadFile = ref<File | null>(null)
const isUploading = ref(false)
const uploadProgress = ref(0)
const uploadSpeed = ref('0 KB/s')
const uploadEta = ref('剩余时间: --')
const uploadRatio = ref('0 MB / 0 MB')
const uploadedFilesList = ref<any[]>([])

const WS_CHUNK_SIZE = 4 * 1024 * 1024 // 4MB 切片大小
const CONCURRENCY_LIMIT = 3          // 滑动窗口并发数
let wsUploadFile: File | null = null
let wsUploadId = ''
let wsTotalSize = 0
let wsTotalChunks = 0
let pendingChunksQueue: number[] = []
let queuePointer = 0
let inFlightCount = 0
let wsUploadedBytes = 0
let wsStartTime = 0
let speedSamples: Array<{ time: number; uploaded: number }> = []

// 审计日志状态
const auditLogs = ref<any[]>([])
const auditTotal = ref(0)
const auditPage = ref(1)
const auditLimit = ref(10)
const auditOperator = ref('')
const auditAction = ref('')
const auditStatus = ref('')
const hoverLogId = ref<number | null>(null) // 用于请求参数 JSON 气泡悬浮预览

// 初始化连接
function connectDebugWs() {
  if (debugWs && (debugWs.readyState === WebSocket.OPEN || debugWs.readyState === WebSocket.CONNECTING)) {
    isUserClose = true
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    debugWs.close()
    return
  }

  isUserClose = false
  reconnectAttempts = 0
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.host
  const wsUrl = `${protocol}//${host}/ws/${clientId.value}${token.value ? `?token=${encodeURIComponent(token.value)}` : ''}`

  logToTerminal(`正在建立 WebSocket 调试连接: ${wsUrl}`, 'system')
  
  debugWs = new WebSocket(wsUrl)

  debugWs.onopen = () => {
    isConnected.value = true
    reconnectAttempts = 0
    logToTerminal('WebSocket 调试连接成功！', 'system')
    loadMessages()
  }

  debugWs.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data)
      handleWsEvent(payload, event.data)
    } catch (e) {
      logToTerminal(event.data, 'received')
    }
  }

  debugWs.onclose = (event) => {
    isConnected.value = false
    logToTerminal(`WebSocket 调试连接已关闭 (Code: ${event.code})`, 'system')

    if (!isUserClose && reconnectAttempts < MAX_RECONNECT) {
      const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 30000)
      reconnectAttempts++
      logToTerminal(`连接非正常中断，将于 ${delay / 1000} 秒后尝试进行自动重连 (${reconnectAttempts}/${MAX_RECONNECT})...`, 'system')
      reconnectTimer = window.setTimeout(() => connectDebugWs(), delay)
    }
  }

  debugWs.onerror = (err) => {
    logToTerminal('WebSocket 握手或通信发生错误，请查看控制台。', 'error')
    console.error(err)
  }
}

function disconnectDebugWs() {
  isUserClose = true
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  if (debugWs) {
    debugWs.close()
    debugWs = null
  }
  isConnected.value = false
}

// 终端打印
function logToTerminal(text: string, type: 'system' | 'sent' | 'received' | 'error' = 'system') {
  const time = new Date().toLocaleTimeString()
  terminalLogs.value.push({ time, text, type })
  nextTick(() => {
    const el = document.getElementById('chatTerminalArea')
    if (el) el.scrollTop = el.scrollHeight
  })
}

// WS 业务分发
function handleWsEvent(payload: any, rawData: string) {
  if (!payload || !payload.type) {
    logToTerminal(rawData, 'received')
    return
  }

  const type = payload.type

  if (type === 'site_message') {
    // 收到站内信实时推送
    const msg = payload.data
    logToTerminal(`[收到实时推送消息] 发送人: ${msg.sender}, 内容: ${msg.content}`, 'received')
    unreadCount.value++
    // 播放浏览器简易蜂鸣提示
    playBeepSound()
    if (activeTab.value === 'messages') loadMessages()
  } 
  
  // 上传分片应答处理
  else if (type === 'upload_start_ack') {
    if (isUploading.value && payload.upload_id === wsUploadId) {
      if (payload.status === 'success') {
        // 请求断点续传查询
        debugWs?.send(JSON.stringify({ type: 'upload_resume', upload_id: wsUploadId }))
      } else {
        alert(payload.message || '上传初始化失败')
        resetUploadState()
      }
    }
  } 
  
  else if (type === 'upload_resume_ack') {
    if (isUploading.value && payload.upload_id === wsUploadId && payload.status === 'success') {
      const completedSet = new Set<number>(payload.completed_chunks || [])
      
      // 已传容量累计
      inFlightCount = 0
      wsUploadedBytes = 0
      if (!wsUploadFile) return

      for (const idx of completedSet) {
        const size = Math.min(wsTotalSize - (idx * WS_CHUNK_SIZE), WS_CHUNK_SIZE)
        wsUploadedBytes += size
      }

      if (completedSet.size > 0) {
        logToTerminal(`[断点续传] 服务器已含 ${completedSet.size} 个分片，自动跳过已传部分。`, 'system')
        updateProgressUI()
      }

      // 构建待发队列
      const pending: number[] = []
      for (let i = 0; i < wsTotalChunks; i++) {
        if (!completedSet.has(i)) pending.push(i)
      }

      if (pending.length === 0) {
        // 全部分片已在，直接合并
        logToTerminal('所有分片均已存在，请求合并文件中...', 'system')
        debugWs?.send(JSON.stringify({
          type: 'upload_merge',
          upload_id: wsUploadId,
          filename: wsUploadFile.name,
          total_chunks: wsTotalChunks
        }))
        return
      }

      pendingChunksQueue = pending
      queuePointer = 0
      wsStartTime = Date.now()

      // 按窗口并发发送
      for (let i = 0; i < CONCURRENCY_LIMIT; i++) {
        if (queuePointer < pendingChunksQueue.length) {
          sendBinaryChunk(pendingChunksQueue[queuePointer]!)
          queuePointer++
          inFlightCount++
        }
      }
    }
  } 
  
  else if (type === 'upload_chunk_ack') {
    if (isUploading.value && payload.upload_id === wsUploadId && payload.status === 'success') {
      const ackIndex = payload.chunk_index
      if (!wsUploadFile) return

      const size = Math.min(wsTotalSize - (ackIndex * WS_CHUNK_SIZE), WS_CHUNK_SIZE)
      wsUploadedBytes += size
      
      updateProgressUI()
      calcUploadSpeed()

      inFlightCount--

      // 滑窗推进
      if (queuePointer < pendingChunksQueue.length) {
        sendBinaryChunk(pendingChunksQueue[queuePointer]!)
        queuePointer++
        inFlightCount++
      } else if (inFlightCount === 0) {
        // 完成分片，请求合并
        uploadSpeed.value = '--'
        uploadEta.value = '正在拼命合并文件中...'
        debugWs?.send(JSON.stringify({
          type: 'upload_merge',
          upload_id: wsUploadId,
          filename: wsUploadFile.name,
          total_chunks: wsTotalChunks
        }))
      }
    }
  } 
  
  else if (type === 'upload_merge_ack') {
    if (isUploading.value && payload.upload_id === wsUploadId) {
      if (payload.status === 'success') {
        uploadProgress.value = 100
        uploadSpeed.value = '--'
        uploadEta.value = '合并成功'
        logToTerminal(`[大文件合并成功] 文件名: ${payload.filename}`, 'system')
        alert(`文件上传且合并成功！\n文件路径: ${payload.path}`)
        resetUploadState()
        loadUploadedFiles()
      } else {
        alert('文件分片合并错误：' + (payload.message || '未知错误'))
        resetUploadState()
      }
    }
  } 
  
  else if (type === 'site_message_ack') {
    if (payload.status === 'success') {
      logToTerminal(`[发送响应] 站内信投递成功(ID: ${payload.id})`, 'system')
    } else {
      logToTerminal(`[发送响应] 站内信投递失败: ${payload.message}`, 'error')
    }
  } 
  
  else {
    logToTerminal(rawData, 'received')
  }
}

// 发送二进制分片帧
function sendBinaryChunk(idx: number) {
  if (!wsUploadFile || !debugWs) return
  
  const blob = wsUploadFile.slice(idx * WS_CHUNK_SIZE, (idx + 1) * WS_CHUNK_SIZE)
  const reader = new FileReader()
  
  reader.onload = (e) => {
    if (!e.target?.result || !debugWs) return
    const chunkBytes = e.target.result as ArrayBuffer
    
    // 合成包：前 4 字节大端表示 chunk_index，后接切片 bytes
    const buffer = new ArrayBuffer(4 + chunkBytes.byteLength)
    const view = new DataView(buffer)
    view.setUint32(0, idx, false) // Big endian
    
    const uint8View = new Uint8Array(buffer)
    uint8View.set(new Uint8Array(chunkBytes), 4)
    
    debugWs.send(uint8View)
  }
  
  reader.readAsArrayBuffer(blob)
}

function updateProgressUI() {
  if (!wsUploadFile) return
  uploadProgress.value = (wsUploadedBytes / wsTotalSize) * 100
  const uploadedMb = (wsUploadedBytes / (1024 * 1024)).toFixed(2)
  const totalMb = (wsTotalSize / (1024 * 1024)).toFixed(2)
  uploadRatio.value = `${uploadedMb} MB / ${totalMb} MB`
}

function calcUploadSpeed() {
  const now = Date.now()
  speedSamples.push({ time: now, uploaded: wsUploadedBytes })
  
  // 保持2秒滑动窗口
  const cutoff = now - 2000
  speedSamples = speedSamples.filter(s => s.time > cutoff)

  let speedBytes = 0
  if (speedSamples.length >= 2) {
    const elapsed = (speedSamples[speedSamples.length - 1]!.time - speedSamples[0]!.time) / 1000
    const loaded = speedSamples[speedSamples.length - 1]!.uploaded - speedSamples[0]!.uploaded
    if (elapsed > 0) speedBytes = loaded / elapsed
  } else {
    const elapsed = (now - wsStartTime) / 1000
    if (elapsed > 0) speedBytes = wsUploadedBytes / elapsed
  }

  // 格式化速度显示
  if (speedBytes > 1024 * 1024) {
    uploadSpeed.value = `${(speedBytes / (1024 * 1024)).toFixed(2)} MB/s`
  } else if (speedBytes > 1024) {
    uploadSpeed.value = `${(speedBytes / 1024).toFixed(1)} KB/s`
  } else {
    uploadSpeed.value = `${speedBytes.toFixed(0)} B/s`
  }

  // 计算 ETA
  if (speedBytes > 0) {
    const remaining = (wsTotalSize - wsUploadedBytes) / speedBytes
    if (remaining < 60) {
      uploadEta.value = `剩余时间: ${Math.ceil(remaining)}秒`
    } else {
      uploadEta.value = `剩余时间: ${Math.floor(remaining / 60)}分${Math.ceil(remaining % 60)}秒`
    }
  }
}

// 模拟发送网页端文本消息
function sendBroadcastMessage() {
  if (!testMessage.value || !debugWs || debugWs.readyState !== WebSocket.OPEN) return
  
  const msg = { type: 'broadcast', message: testMessage.value }
  debugWs.send(JSON.stringify(msg))
  logToTerminal(`[发送广播] ${testMessage.value}`, 'sent')
  testMessage.value = ''
}

function sendPrivateMessage() {
  if (!testMessage.value || !testTarget.value || !debugWs || debugWs.readyState !== WebSocket.OPEN) return
  
  const msg = { type: 'send_to', target: testTarget.value, message: testMessage.value }
  debugWs.send(JSON.stringify(msg))
  logToTerminal(`[私聊发送至 ${testTarget.value}] ${testMessage.value}`, 'sent')
  testMessage.value = ''
}

// 蜂鸣音
function playBeepSound() {
  try {
    const audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)()
    const oscillator = audioCtx.createOscillator()
    const gainNode = audioCtx.createGain()
    oscillator.connect(gainNode)
    gainNode.connect(audioCtx.destination)
    oscillator.type = 'sine'
    oscillator.frequency.setValueAtTime(587.33, audioCtx.currentTime) // D5
    gainNode.gain.setValueAtTime(0.08, audioCtx.currentTime)
    oscillator.start()
    oscillator.stop(audioCtx.currentTime + 0.15)
  } catch (e) {}
}

// ---------------- 站内信 REST 接口 ----------------
async function loadMessages() {
  try {
    const res = await fetch(`/api/messages?receiver=${encodeURIComponent(clientId.value)}&status=${msgFilter.value}${token.value ? `&token=${encodeURIComponent(token.value)}` : ''}`)
    if (res.ok) {
      siteMessages.value = await res.json()
      if (msgFilter.value === 'all') {
        unreadCount.value = siteMessages.value.filter(m => m.is_read === 0).length
      } else if (msgFilter.value === 'unread') {
        unreadCount.value = siteMessages.value.length
      }
    }
  } catch (e) {
    console.error('拉取站内信失败:', e)
  }
}

async function markAsRead(id: number) {
  try {
    const headers: Record<string, string> = {}
    if (token.value) headers['Authorization'] = 'Bearer ' + token.value

    const res = await fetch(`/api/messages/${id}/read${token.value ? `?token=${encodeURIComponent(token.value)}` : ''}`, {
      method: 'POST',
      headers
    })
    if (res.ok) loadMessages()
  } catch (e) {
    console.error(e)
  }
}

async function markAllAsRead() {
  if (!confirm('确定将所有消息标记为已读？')) return
  try {
    const headers: Record<string, string> = {}
    if (token.value) headers['Authorization'] = 'Bearer ' + token.value

    const res = await fetch(`/api/messages/read-all?receiver=${encodeURIComponent(clientId.value)}${token.value ? `&token=${encodeURIComponent(token.value)}` : ''}`, {
      method: 'POST',
      headers
    })
    if (res.ok) loadMessages()
  } catch (e) {
    console.error(e)
  }
}

async function sendMockMessageApi() {
  if (!msgReceiver.value || !msgContent.value) {
    alert('请填写接收人和消息内容！')
    return
  }

  try {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    if (token.value) headers['Authorization'] = 'Bearer ' + token.value

    const res = await fetch(`/api/messages/send${token.value ? `?token=${encodeURIComponent(token.value)}` : ''}`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        sender: msgSender.value,
        receiver: msgReceiver.value,
        content: msgContent.value
      })
    })

    if (res.ok) {
      msgContent.value = ''
      alert('消息投递到 RabbitMQ 成功！')
      loadMessages()
    } else {
      const data = await res.json()
      alert('发送失败: ' + (data.detail || '未知错误'))
    }
  } catch (e) {
    alert('发送网络错误')
  }
}

// ---------------- 大文件上传 REST 接口 ----------------
async function loadUploadedFiles() {
  try {
    const res = await fetch(`/api/uploads${token.value ? `?token=${encodeURIComponent(token.value)}` : ''}`)
    if (res.ok) {
      uploadedFilesList.value = await res.json()
    }
  } catch (e) {
    console.error('拉取上传列表失败:', e)
  }
}

async function deleteFile(id: number, name: string) {
  if (!confirm(`确定删除文件 "${name}" 吗？此操作物理删除不可恢复！`)) return
  try {
    const headers: Record<string, string> = {}
    if (token.value) headers['Authorization'] = 'Bearer ' + token.value

    const res = await fetch(`/api/uploads/${id}${token.value ? `?token=${encodeURIComponent(token.value)}` : ''}`, {
      method: 'DELETE',
      headers
    })
    if (res.ok) {
      alert('删除成功！')
      loadUploadedFiles()
    } else {
      const data = await res.json()
      alert('删除失败: ' + (data.detail || '防跨越安全校验拦截'))
    }
  } catch (e) {
    console.error(e)
  }
}

// 拖拽与选择上传
function triggerFileInput() {
  document.getElementById('fileInputConsole')?.click()
}

function handleFileSelect(e: any) {
  if (e.target.files.length > 0) {
    handleStartUpload(e.target.files[0])
  }
}

function handleFileDrop(e: DragEvent) {
  if (e.dataTransfer && e.dataTransfer.files.length > 0) {
    handleStartUpload(e.dataTransfer.files[0]!)
  }
}

function handleStartUpload(file: File) {
  if (!debugWs || debugWs.readyState !== WebSocket.OPEN) {
    alert('请先连接右侧 WebSocket 服务！')
    return
  }
  if (isUploading.value) {
    alert('当前正有上传任务在进行！')
    return
  }

  isUploading.value = true
  wsUploadFile = file
  uploadFile.value = file
  const clean = file.name.replace(/[^\w\-]/g, '_')
  wsUploadId = clean + '_' + file.size
  wsTotalSize = file.size
  wsTotalChunks = Math.ceil(wsTotalSize / WS_CHUNK_SIZE)
  pendingChunksQueue = []
  queuePointer = 0
  inFlightCount = 0
  wsUploadedBytes = 0

  uploadSpeed.value = '0 KB/s'
  uploadEta.value = '排队中...'
  uploadRatio.value = `0 MB / ${(file.size / (1024 * 1024)).toFixed(2)} MB`

  // 1. 发送初始化
  debugWs.send(JSON.stringify({
    type: 'upload_start',
    upload_id: wsUploadId,
    filename: file.name
  }))
}

function abortUpload() {
  if (!isUploading.value) return
  if (confirm('确认终止并清理分片上传会话吗？')) {
    debugWs?.send(JSON.stringify({ type: 'upload_abort', upload_id: wsUploadId }))
    resetUploadState()
    logToTerminal('文件上传已被终止并释放缓存。', 'error')
  }
}

function resetUploadState() {
  isUploading.value = false
  wsUploadFile = null
  uploadFile.value = null
  wsUploadId = ''
  wsTotalSize = 0
  wsTotalChunks = 0
  pendingChunksQueue = []
  queuePointer = 0
  inFlightCount = 0
  wsUploadedBytes = 0
}

// ---------------- 审计日志 REST 接口 ----------------
async function loadAuditLogs(page: number) {
  auditPage.value = page
  try {
    let url = `/api/audit-logs?page=${page}&limit=${auditLimit.value}`
    if (auditOperator.value) url += `&operator=${encodeURIComponent(auditOperator.value)}`
    if (auditAction.value) url += `&action=${encodeURIComponent(auditAction.value)}`
    if (auditStatus.value) url += `&status=${encodeURIComponent(auditStatus.value)}`
    if (token.value) url += `&token=${encodeURIComponent(token.value)}`

    const res = await fetch(url)
    if (res.ok) {
      const data = await res.json()
      auditLogs.value = data.data || []
      auditTotal.value = data.total || 0
    }
  } catch (e) {
    console.error('拉取审计日志失败:', e)
  }
}

// 辅助格式化 JSON
function formatJSON(obj: any): string {
  if (!obj) return ''
  try {
    return JSON.stringify(obj, null, 2)
  } catch (e) {
    return String(obj)
  }
}

const isMockMode = new URLSearchParams(window.location.search).get('mock') === 'true'

// 生命周期
onMounted(() => {
  if (isMockMode) {
    isConnected.value = true
    terminalLogs.value = [
      { time: '02:00:01', text: '初始化 WebSocket 调试连接成功！', type: 'system' },
      { time: '02:00:03', text: '注册客户端成功 ID: client_readme', type: 'system' },
      { time: '02:00:15', text: '订阅频道: hmp:site_message', type: 'sent' },
      { time: '02:00:16', text: '收到广播订阅回执：success', type: 'received' }
    ]
    siteMessages.value = [
      { id: 1, sender: 'system', receiver: 'client_readme', content: '欢迎来到 HMP 系统调试控制台！', is_read: true, created_at: '2026-07-01 02:00:00' },
      { id: 2, sender: 'system', receiver: 'client_readme', content: '系统安全检查通过，未发现路径穿越隐患。', is_read: false, created_at: '2026-07-01 02:05:00' }
    ]
    unreadCount.value = 1
    
    isUploading.value = true
    uploadProgress.value = 78
    uploadSpeed.value = '2.4 MB/s'
    uploadEta.value = '剩余时间: 3秒'
    uploadRatio.value = '15.6 MB / 20.0 MB'
    
    auditLogs.value = [
      { id: 101, operator: 'mock_player', action: 'user_login', status: 'success', ip_address: '127.0.0.1', created_at: '2026-07-01 02:00:00', request_params: { username: 'mock_player' } },
      { id: 102, operator: 'mock_player', action: 'join_match', status: 'success', ip_address: '127.0.0.1', created_at: '2026-07-01 02:01:00', request_params: { base_score: 300 } },
      { id: 103, operator: 'mock_player', action: 'play_cards', status: 'success', ip_address: '127.0.0.1', created_at: '2026-07-01 02:02:15', request_params: { cards: [53, 52], card_type: 'rocket' } }
    ]
    auditTotal.value = 3
  } else {
    connectDebugWs()
  }
})

onUnmounted(() => {
  if (!isMockMode) {
    disconnectDebugWs()
  }
})

function handleTabChange(tab: 'ws' | 'messages' | 'upload' | 'audit') {
  activeTab.value = tab
  if (isMockMode) return
  if (tab === 'messages') loadMessages()
  if (tab === 'upload') loadUploadedFiles()
  if (tab === 'audit') loadAuditLogs(1)
}
</script>

<template>
  <div class="debug-console-page">
    <!-- 头部栏 -->
    <header class="console-header glass-panel">
      <div class="title-logo">
        <span class="logo-emoji">⚙️</span>
        <h2>HMP 系统调试控制台</h2>
      </div>
      
      <div class="token-input-field">
        <label>安全凭证Token:</label>
        <input v-model="token" type="password" placeholder="API_TOKEN (未配置则无需填写)" />
      </div>

      <div class="header-right">
        <button class="btn-primary" @click="router.push('/login')">返回游戏登录</button>
      </div>
    </header>

    <div class="console-body">
      <!-- 侧边导航 -->
      <aside class="console-menu glass-panel">
        <div class="menu-item" :class="{ active: activeTab === 'ws' }" @click="handleTabChange('ws')">
          <span>📡 WebSocket 自测</span>
        </div>
        <div class="menu-item" :class="{ active: activeTab === 'messages' }" @click="handleTabChange('messages')">
          <span>📨 分布式站内信</span>
          <span v-if="unreadCount > 0" class="badge">{{ unreadCount }}</span>
        </div>
        <div class="menu-item" :class="{ active: activeTab === 'upload' }" @click="handleTabChange('upload')">
          <span>📂 并发滑窗大文件上传</span>
        </div>
        <div class="menu-item" :class="{ active: activeTab === 'audit' }" @click="handleTabChange('audit')">
          <span>📋 全局审计日志</span>
        </div>
      </aside>

      <!-- 主要展示板 -->
      <main class="console-content-main glass-panel">
        
        <!-- Tab 1: WebSocket 调试 -->
        <section v-if="activeTab === 'ws'" class="panel-section ws-panel-layout">
          <div class="panel-left-terminal flex-col">
            <div class="panel-subtitle">通信终端回显日志</div>
            <div id="chatTerminalArea" class="terminal-screen">
              <div v-for="(log, i) in terminalLogs" :key="i" class="log-entry" :class="'log-' + log.type">
                [{{ log.time }}] {{ log.text }}
              </div>
            </div>
            <div class="terminal-sender">
              <input v-model="testMessage" type="text" placeholder="输入广播/私聊数据内容..." @keydown.enter="sendBroadcastMessage" />
              <button class="btn-orange" @click="sendBroadcastMessage">广播发送</button>
            </div>
            <div class="terminal-sender private-row">
              <input v-model="testTarget" type="text" placeholder="接收端Client ID..." />
              <button class="btn-blue" @click="sendPrivateMessage">定向私聊发送</button>
            </div>
          </div>

          <div class="panel-right-settings flex-col">
            <div class="panel-subtitle">物理机连接参数</div>
            <div class="config-card">
              <div class="input-item">
                <label>我的调试Client ID:</label>
                <input v-model="clientId" :disabled="isConnected" type="text" />
              </div>
              <div class="status-indicator">
                <span class="status-dot" :class="{ connected: isConnected }"></span>
                <span>连接状态: <strong>{{ isConnected ? '已连上' : '未连接' }}</strong></span>
              </div>
              <button v-if="!isConnected" class="btn-connect" @click="connectDebugWs">连接WS服务</button>
              <button v-else class="btn-disconnect" @click="disconnectDebugWs">断开连线</button>
            </div>
            <div class="terminal-readme">
              <h4>📋 功能提示</h4>
              <p>1. WS自测允许在本机模拟分布式实时广播和私聊。</p>
              <p>2. 同一浏览器打开多个页面、指定相同/不同 ID 可实现双向会话测试。</p>
            </div>
          </div>
        </section>

        <!-- Tab 2: 分布式站内信 -->
        <section v-if="activeTab === 'messages'" class="panel-section msg-panel-layout">
          <!-- 站内信发送 -->
          <div class="panel-left-form flex-col">
            <div class="panel-subtitle">发送模拟站内信 (进入 RabbitMQ 扇出 exchange)</div>
            <div class="msg-form-card">
              <div class="input-item">
                <label>发送者 ID (Sender):</label>
                <input v-model="msgSender" type="text" />
              </div>
              <div class="input-item">
                <label>接收者 ID (Receiver):</label>
                <input v-model="msgReceiver" type="text" />
              </div>
              <div class="input-item">
                <label>消息内容 (Content):</label>
                <textarea v-model="msgContent" placeholder="在此输入需要发送的站内信内容..." rows="4"></textarea>
              </div>
              <button class="btn-orange submit-msg-btn" @click="sendMockMessageApi">写入RabbitMQ发送</button>
            </div>
          </div>

          <!-- 站内信箱 -->
          <div class="panel-right-inbox flex-col">
            <div class="panel-subtitle flex-row-between">
              <span>站内信收件箱 (MySQL)</span>
              <button class="btn-read-all" @click="markAllAsRead">全部已读</button>
            </div>
            <div class="filter-row">
              <button :class="{ active: msgFilter === 'all' }" @click="msgFilter = 'all'; loadMessages()">全部</button>
              <button :class="{ active: msgFilter === 'unread' }" @click="msgFilter = 'unread'; loadMessages()">未读</button>
              <button :class="{ active: msgFilter === 'read' }" @click="msgFilter = 'read'; loadMessages()">已读</button>
            </div>

            <div class="messages-list-scroll">
              <div v-for="msg in siteMessages" :key="msg.id" class="message-item-card" :class="{ unread: msg.is_read === 0 }">
                <div class="item-head">
                  <span class="sender-name">发件人: {{ msg.sender }}</span>
                  <span class="send-time">{{ msg.created_at }}</span>
                </div>
                <div class="item-body">{{ msg.content }}</div>
                <div class="item-foot">
                  <button v-if="msg.is_read === 0" class="btn-set-read" @click="markAsRead(msg.id)">标为已读</button>
                  <span v-else class="read-label">已读</span>
                </div>
              </div>
              <div v-if="siteMessages.length === 0" class="no-data">暂无收件记录</div>
            </div>
          </div>
        </section>

        <!-- Tab 3: 滑窗大文件分片上传 -->
        <section v-if="activeTab === 'upload'" class="panel-section upload-panel-layout">
          <!-- 上传操作 -->
          <div class="panel-left-upload flex-col">
            <div class="panel-subtitle">滑动窗口并发上传区域</div>
            
            <div class="upload-dropzone" @click="triggerFileInput" @dragover.prevent @drop.prevent="handleFileDrop">
              <span class="cloud-ico">☁️</span>
              <p>拖拽文件至此区域，或者<strong>点击选择本地文件</strong></p>
              <p class="drop-hint">(4MB分片，窗口数3限制，并发二进制流零拷贝，支持断点续传)</p>
              <input id="fileInputConsole" type="file" style="display:none" @change="handleFileSelect" />
            </div>

            <!-- 上传进度条 -->
            <div v-if="isUploading" class="upload-progress-container glass-panel">
              <div class="progress-meta">
                <span class="file-name truncate">{{ uploadFile?.name }}</span>
                <span class="percent-label">{{ uploadProgress.toFixed(1) }}%</span>
              </div>
              <div class="progress-bar-track">
                <div class="progress-bar-fill" :style="{ width: uploadProgress + '%' }"></div>
              </div>
              <div class="speed-eta-row">
                <span>速度: {{ uploadSpeed }}</span>
                <span>{{ uploadEta }}</span>
                <span>已传: {{ uploadRatio }}</span>
              </div>
              <button class="btn-cancel-upload" @click="abortUpload">取消上传</button>
            </div>
          </div>

          <!-- 已上传列表 -->
          <div class="panel-right-files flex-col">
            <div class="panel-subtitle">已合并文件列表 (uploads/)</div>
            <div class="files-scroll-list">
              <div v-for="f in uploadedFilesList" :key="f.id" class="file-item-card">
                <div class="file-icon">📁</div>
                <div class="file-details truncate">
                  <div class="fname truncate" :title="f.filename">{{ f.filename }}</div>
                  <div class="fmeta">大小: {{ f.file_size_mb }} MB | 时间: {{ f.created_at }}</div>
                </div>
                <button class="btn-delete-file" @click="deleteFile(f.id, f.filename)">×</button>
              </div>
              <div v-if="uploadedFilesList.length === 0" class="no-data">无文件记录</div>
            </div>
          </div>
        </section>

        <!-- Tab 4: 审计日志 -->
        <section v-if="activeTab === 'audit'" class="panel-section audit-panel-layout flex-col">
          <div class="panel-subtitle flex-row-between">
            <span>系统拦截审计日志 (APIRoute & DB 拦截器)</span>
            <div class="filter-controls">
              <input v-model="auditOperator" type="text" placeholder="操作人筛选" @input="loadAuditLogs(1)" />
              <input v-model="auditAction" type="text" placeholder="动作筛选" @input="loadAuditLogs(1)" />
              <select v-model="auditStatus" @change="loadAuditLogs(1)">
                <option value="">执行状态</option>
                <option value="success">success</option>
                <option value="failed">failed</option>
              </select>
            </div>
          </div>

          <div class="table-container">
            <table class="audit-logs-table">
              <thead>
                <tr>
                  <th>时间</th>
                  <th>操作人</th>
                  <th>执行动作</th>
                  <th>资源类型</th>
                  <th>IP</th>
                  <th>状态</th>
                  <th>耗时</th>
                  <th>方法</th>
                  <th>请求参数 (悬浮气泡)</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="log in auditLogs" :key="log.id">
                  <td>{{ log.created_at }}</td>
                  <td class="bold">{{ log.operator }}</td>
                  <td>{{ log.action }}</td>
                  <td>{{ log.resource_type }}</td>
                  <td>{{ log.ip_address }}</td>
                  <td>
                    <span class="status-lbl" :class="log.status">{{ log.status }}</span>
                  </td>
                  <td>{{ log.execution_time ? log.execution_time + 'ms' : '--' }}</td>
                  <td class="bold-method">{{ log.method || 'WS' }}</td>
                  <td class="params-column" @mouseenter="hoverLogId = log.id" @mouseleave="hoverLogId = null">
                    <span class="params-preview truncate">{{ log.request_params ? JSON.stringify(log.request_params) : '--' }}</span>
                    <!-- 浮动 Tooltip JSON 气泡 -->
                    <div v-if="hoverLogId === log.id && log.request_params" class="json-tooltip glass-panel">
                      <pre><code>{{ formatJSON(log.request_params) }}</code></pre>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- 分页器 -->
          <div class="audit-pagination">
            <button :disabled="auditPage === 1" @click="loadAuditLogs(auditPage - 1)">上一页</button>
            <span>第 {{ auditPage }} / {{ Math.ceil(auditTotal / auditLimit) || 1 }} 页</span>
            <button :disabled="auditPage * auditLimit >= auditTotal" @click="loadAuditLogs(auditPage + 1)">下一页</button>
          </div>
        </section>

      </main>
    </div>
  </div>
</template>

<style scoped>
.debug-console-page {
  display: flex;
  flex-direction: column;
  height: 100vh;
  width: 100vw;
  background: radial-gradient(circle at center, #1b305a 0%, #070d1e 100%);
  color: #ffffff;
  padding: 16px;
  box-sizing: border-box;
  font-family: 'Inter', system-ui, sans-serif;
  overflow: hidden;
}

.glass-panel {
  background: rgba(255, 255, 255, 0.05);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 12px;
  box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3);
}

/* Header */
.console-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 24px;
  height: 70px;
  box-sizing: border-box;
  margin-bottom: 16px;
}

.title-logo {
  display: flex;
  align-items: center;
  gap: 10px;
}

.title-logo h2 {
  margin: 0;
  font-size: 1.3rem;
  font-weight: 800;
}

.logo-emoji {
  font-size: 1.6rem;
}

.token-input-field {
  display: flex;
  align-items: center;
  gap: 8px;
  background: rgba(0,0,0,0.3);
  padding: 4px 12px;
  border-radius: 20px;
  border: 1px solid rgba(255,255,255,0.1);
}

.token-input-field label {
  font-size: 0.8rem;
  opacity: 0.8;
}

.token-input-field input {
  background: transparent;
  border: none;
  color: #ffd700;
  outline: none;
  font-size: 0.85rem;
  width: 200px;
}

.header-right {
  display: flex;
  gap: 12px;
  align-items: center;
}

.btn-primary {
  background: linear-gradient(135deg, #ffd54f 0%, #ff8f00 100%);
  color: #3e2723;
  border: none;
  padding: 8px 20px;
  border-radius: 20px;
  font-weight: bold;
  cursor: pointer;
  box-shadow: 0 4px 10px rgba(255, 143, 0, 0.3);
}

.btn-secondary-link {
  color: #81b9fc;
  font-size: 0.9rem;
  text-decoration: underline;
  cursor: pointer;
}

/* Body */
.console-body {
  display: flex;
  gap: 16px;
  flex: 1;
  height: calc(100vh - 120px);
}

/* Side Menu */
.console-menu {
  width: 240px;
  display: flex;
  flex-direction: column;
  padding: 16px 0;
  gap: 8px;
}

.menu-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 20px;
  cursor: pointer;
  transition: all 0.2s;
  border-left: 3px solid transparent;
}

.menu-item span {
  font-weight: bold;
  font-size: 0.95rem;
  opacity: 0.7;
}

.menu-item.active {
  border-left-color: #ff9f1a;
  background: rgba(255, 255, 255, 0.05);
}

.menu-item.active span {
  opacity: 1;
  color: #ff9f1a;
}

.badge {
  background: #f44336;
  color: white;
  font-size: 0.7rem;
  font-weight: bold;
  padding: 2px 6px;
  border-radius: 10px;
}

/* Content Main */
.console-content-main {
  flex: 1;
  padding: 20px;
  overflow: hidden;
  box-sizing: border-box;
}

.panel-section {
  height: 100%;
  width: 100%;
  display: flex;
  gap: 20px;
  box-sizing: border-box;
}

.panel-subtitle {
  font-weight: bold;
  font-size: 1rem;
  color: #ffd700;
  margin-bottom: 12px;
  border-left: 3px solid #ff9800;
  padding-left: 8px;
}

.flex-col {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.flex-row-between {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

/* Tab 1: WS layout */
.ws-panel-layout .panel-left-terminal {
  flex: 1.3;
}

.ws-panel-layout .panel-right-settings {
  flex: 1;
}

.terminal-screen {
  flex: 1;
  background: #020813;
  border-radius: 8px;
  border: 1px solid rgba(255,255,255,0.08);
  padding: 12px;
  font-family: 'Courier New', Courier, monospace;
  font-size: 0.85rem;
  overflow-y: auto;
  margin-bottom: 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.log-entry {
  line-height: 1.4;
  word-break: break-all;
}

.log-system { color: #81c784; }
.log-sent { color: #80d8ff; }
.log-received { color: #ffffff; }
.log-error { color: #e57373; }

.terminal-sender {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}

.terminal-sender input {
  flex: 1;
  background: rgba(0,0,0,0.3);
  border: 1px solid rgba(255,255,255,0.15);
  border-radius: 6px;
  color: #fff;
  padding: 10px 12px;
  outline: none;
}

.private-row {
  margin-bottom: 0;
}

.private-row input {
  max-width: 150px;
}

.btn-orange {
  background: linear-gradient(135deg, #ffa726 0%, #fb8c00 100%);
  color: #fff;
  border: none;
  padding: 10px 20px;
  border-radius: 6px;
  font-weight: bold;
  cursor: pointer;
}

.btn-blue {
  background: linear-gradient(135deg, #29b6f6 0%, #0288d1 100%);
  color: #fff;
  border: none;
  padding: 10px 20px;
  border-radius: 6px;
  font-weight: bold;
  cursor: pointer;
}

/* Right Config Card */
.config-card {
  background: rgba(0,0,0,0.2);
  border: 1px solid rgba(255,255,255,0.1);
  padding: 16px;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 16px;
}

.input-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.input-item label {
  font-size: 0.8rem;
  opacity: 0.8;
}

.input-item input, .input-item textarea {
  background: rgba(0,0,0,0.3);
  border: 1px solid rgba(255,255,255,0.15);
  border-radius: 6px;
  color: #fff;
  padding: 8px 12px;
  outline: none;
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.9rem;
}

.status-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #f44336;
  box-shadow: 0 0 5px #f44336;
}

.status-dot.connected {
  background: #4caf50;
  box-shadow: 0 0 8px #4caf50;
}

.btn-connect {
  background: #4caf50;
  color: white;
  border: none;
  padding: 10px;
  border-radius: 6px;
  font-weight: bold;
  cursor: pointer;
}

.btn-disconnect {
  background: #d32f2f;
  color: white;
  border: none;
  padding: 10px;
  border-radius: 6px;
  font-weight: bold;
  cursor: pointer;
}

.terminal-readme {
  background: rgba(255,255,255,0.03);
  border-radius: 8px;
  padding: 16px;
  font-size: 0.8rem;
}

.terminal-readme h4 {
  margin: 0 0 8px 0;
  color: #ffd700;
}

.terminal-readme p {
  margin: 4px 0;
  line-height: 1.4;
  opacity: 0.7;
}

/* Tab 2: Messages layout */
.msg-panel-layout .panel-left-form {
  flex: 1;
}

.msg-panel-layout .panel-right-inbox {
  flex: 1.2;
}

.msg-form-card {
  background: rgba(0,0,0,0.25);
  border: 1px solid rgba(255,255,255,0.1);
  padding: 16px;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.submit-msg-btn {
  margin-top: 10px;
}

.btn-read-all {
  background: rgba(255,255,255,0.15);
  border: 1px solid rgba(255,255,255,0.25);
  color: #fff;
  font-weight: bold;
  font-size: 0.75rem;
  padding: 4px 12px;
  border-radius: 12px;
  cursor: pointer;
}

.filter-row {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.filter-row button {
  background: rgba(255,255,255,0.1);
  border: none;
  color: #fff;
  padding: 4px 16px;
  font-size: 0.8rem;
  border-radius: 12px;
  cursor: pointer;
}

.filter-row button.active {
  background: #ff9800;
  font-weight: bold;
}

.messages-list-scroll {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.message-item-card {
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.06);
  padding: 12px;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.message-item-card.unread {
  border-left: 3px solid #ff9800;
  background: rgba(255, 152, 0, 0.05);
}

.item-head {
  display: flex;
  justify-content: space-between;
  font-size: 0.75rem;
  opacity: 0.6;
}

.sender-name {
  font-weight: bold;
  color: #ff9800;
}

.item-body {
  font-size: 0.9rem;
  line-height: 1.4;
  word-break: break-all;
}

.item-foot {
  display: flex;
  justify-content: flex-end;
}

.btn-set-read {
  background: rgba(0, 150, 136, 0.2);
  border: 1px solid rgba(0, 150, 136, 0.4);
  color: #009688;
  font-size: 0.75rem;
  font-weight: bold;
  padding: 3px 10px;
  border-radius: 6px;
  cursor: pointer;
}

.read-label {
  font-size: 0.75rem;
  opacity: 0.4;
}

/* Tab 3: Upload Layout */
.upload-panel-layout .panel-left-upload {
  flex: 1.2;
}

.upload-panel-layout .panel-right-files {
  flex: 1;
}

.upload-dropzone {
  border: 2px dashed rgba(255,255,255,0.2);
  background: rgba(255, 255, 255, 0.02);
  border-radius: 12px;
  padding: 40px 20px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
  margin-bottom: 20px;
}

.upload-dropzone:hover {
  background: rgba(255,255,255,0.05);
  border-color: #ffd700;
}

.cloud-ico {
  font-size: 3rem;
  opacity: 0.7;
  display: block;
  margin-bottom: 12px;
}

.drop-hint {
  font-size: 0.75rem;
  opacity: 0.5;
  margin-top: 8px;
}

.upload-progress-container {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.progress-meta {
  display: flex;
  justify-content: space-between;
  font-size: 0.85rem;
  font-weight: bold;
}

.progress-bar-track {
  height: 8px;
  background: rgba(0,0,0,0.4);
  border-radius: 4px;
  overflow: hidden;
}

.progress-bar-fill {
  height: 100%;
  background: linear-gradient(to right, #ffd54f, #ff9800);
}

.speed-eta-row {
  display: flex;
  justify-content: space-between;
  font-size: 0.75rem;
  opacity: 0.8;
}

.btn-cancel-upload {
  background: #f44336;
  color: white;
  border: none;
  padding: 6px 12px;
  font-weight: bold;
  border-radius: 4px;
  cursor: pointer;
  align-self: flex-end;
  font-size: 0.75rem;
}

.files-scroll-list {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.file-item-card {
  display: flex;
  align-items: center;
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.06);
  padding: 8px 12px;
  border-radius: 8px;
  gap: 12px;
}

.file-icon {
  font-size: 1.4rem;
}

.file-details {
  flex: 1;
}

.fname {
  font-weight: bold;
  font-size: 0.85rem;
}

.fmeta {
  font-size: 0.7rem;
  opacity: 0.5;
  margin-top: 3px;
}

.btn-delete-file {
  background: none;
  border: none;
  color: #e57373;
  font-size: 1.5rem;
  cursor: pointer;
  line-height: 1;
}

/* Tab 4: Audit Logs */
.audit-panel-layout {
  height: 100%;
}

.filter-controls {
  display: flex;
  gap: 10px;
}

.filter-controls input, .filter-controls select {
  background: rgba(0,0,0,0.3);
  border: 1px solid rgba(255,255,255,0.15);
  border-radius: 12px;
  color: #fff;
  padding: 4px 12px;
  font-size: 0.8rem;
  outline: none;
}

.table-container {
  flex: 1;
  overflow-y: auto;
  border-radius: 8px;
  border: 1px solid rgba(255,255,255,0.1);
  margin-bottom: 12px;
}

.audit-logs-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
  text-align: left;
}

.audit-logs-table th {
  background: rgba(0,0,0,0.4);
  padding: 12px;
  font-weight: bold;
  opacity: 0.8;
  position: sticky;
  top: 0;
  z-index: 5;
  border-bottom: 1.5px solid rgba(255,255,255,0.1);
}

.audit-logs-table td {
  padding: 10px 12px;
  border-bottom: 1px solid rgba(255,255,255,0.05);
}

.audit-logs-table tbody tr:hover {
  background: rgba(255,255,255,0.02);
}

.bold { font-weight: bold; }
.bold-method { font-weight: bold; color: #81b9fc; }

.status-lbl {
  font-size: 0.75rem;
  font-weight: bold;
  padding: 2px 6px;
  border-radius: 4px;
}

.status-lbl.success {
  background: rgba(76, 175, 80, 0.2);
  color: #81c784;
}

.status-lbl.failed {
  background: rgba(244, 67, 54, 0.2);
  color: #e57373;
}

.params-column {
  position: relative;
  max-width: 180px;
  cursor: pointer;
}

.params-preview {
  display: block;
  font-size: 0.75rem;
  opacity: 0.6;
}

.json-tooltip {
  position: absolute;
  bottom: 100%;
  right: 0;
  width: 280px;
  max-height: 200px;
  overflow-y: auto;
  z-index: 10;
  padding: 10px;
  background: rgba(2, 8, 19, 0.95);
}

.json-tooltip pre {
  margin: 0;
  font-family: monospace;
  font-size: 0.75rem;
  white-space: pre-wrap;
  color: #ffe082;
}

.audit-pagination {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 20px;
  font-size: 0.85rem;
}

.audit-pagination button {
  background: rgba(255,255,255,0.1);
  border: none;
  color: #fff;
  padding: 6px 16px;
  border-radius: 6px;
  cursor: pointer;
}

.audit-pagination button:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.no-data {
  text-align: center;
  padding: 30px;
  opacity: 0.5;
  font-size: 0.85rem;
}

.truncate {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
