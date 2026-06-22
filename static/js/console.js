// 初始化 Lucide 图标
lucide.createIcons();

let ws = null;
let activeTab = 'ws';
let currentFilter = 'all';
let unreadCount = 0;

// 从当前页面 URL 中解析 token，用于安全令牌校验对接
const urlParams = new URLSearchParams(window.location.search);
const token = urlParams.get('token') || '';

// UI 元素
const statusDot = document.getElementById('statusDot');
const statusText = document.getElementById('statusText');
const clientIdInput = document.getElementById('clientIdInput');
const connectBtn = document.getElementById('connectBtn');
const messageInput = document.getElementById('messageInput');
const sendBtn = document.getElementById('sendBtn');
const chatArea = document.getElementById('chatArea');
const msgListArea = document.getElementById('msgListArea');
const unreadBadge = document.getElementById('unreadBadge');

// 生成随机客户端ID
const randomId = 'client_' + Math.random().toString(36).substring(2, 8);
clientIdInput.value = randomId;
document.getElementById('mockReceiver').value = randomId; // 模拟发给自己更方便

// 切换面板
function switchPanel(panelName) {
    activeTab = panelName;
    
    // 改变导航栏状态
    document.querySelectorAll('.menu-item').forEach(item => item.classList.remove('active'));
    const indexMap = { 'ws': 0, 'messages': 1, 'upload': 2, 'audit': 3 };
    document.querySelectorAll('.menu-item')[indexMap[panelName]].classList.add('active');

    // 改变面板显示
    document.querySelectorAll('.panel').forEach(panel => panel.classList.remove('active'));
    const titleMap = {
        'ws': 'WebSocket 调试',
        'messages': '站内信系统',
        'upload': '大文件上传',
        'audit': '审计日志'
    };
    document.getElementById('currentPanelTitle').textContent = titleMap[panelName];

    if (panelName === 'ws') {
        document.getElementById('panelWS').classList.add('active');
    } else if (panelName === 'messages') {
        document.getElementById('panelMessages').classList.add('active');
        loadMessages();
    } else if (panelName === 'upload') {
        document.getElementById('panelUpload').classList.add('active');
        loadUploadedFiles();
    } else if (panelName === 'audit') {
        document.getElementById('panelAudit').classList.add('active');
        loadAuditLogs(1);
    }
}

// 显示 Toast 提示
function showToast(sender, content) {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.innerHTML = `
        <i data-lucide="bell" class="toast-icon" style="width: 20px; height: 20px;"></i>
        <div class="toast-content">
            <div class="toast-title">新站内信提示</div>
            <div class="toast-body"><strong>${escapeHtml(sender)}</strong>: ${escapeHtml(content)}</div>
        </div>
    `;
    container.appendChild(toast);
    lucide.createIcons();

    // 播放一个系统提示音
    try {
        const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        const oscillator = audioCtx.createOscillator();
        const gainNode = audioCtx.createGain();
        oscillator.connect(gainNode);
        gainNode.connect(audioCtx.destination);
        oscillator.type = 'sine';
        oscillator.frequency.setValueAtTime(587.33, audioCtx.currentTime); // D5
        gainNode.gain.setValueAtTime(0.1, audioCtx.currentTime);
        oscillator.start();
        oscillator.stop(audioCtx.currentTime + 0.15);
    } catch (e) {}

    // 3秒后移除
    setTimeout(() => {
        toast.style.animation = 'slideIn 0.3s reverse forwards';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// 终端打印
function logToTerminal(msg, type = 'system') {
    const div = document.createElement('div');
    div.className = `log-entry log-${type}`;
    const time = new Date().toLocaleTimeString();
    div.textContent = `[${time}] ${msg}`;
    chatArea.appendChild(div);
    chatArea.scrollTop = chatArea.scrollHeight;
}

// WebSocket 连接及重连管理状态
let reconnectAttempts = 0;
const MAX_RECONNECT = 5;
let reconnectTimer = null;
let isUserInitiatedClose = false;

// WebSocket 连接
connectBtn.addEventListener('click', () => {
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
        isUserInitiatedClose = true;
        if (reconnectTimer) {
            clearTimeout(reconnectTimer);
            reconnectTimer = null;
        }
        ws.close();
        return;
    }

    const clientId = clientIdInput.value.trim();
    if (!clientId) {
        showCustomAlert('提示', '客户端 ID 不能为空', 'warning');
        return;
    }

    isUserInitiatedClose = false;
    reconnectAttempts = 0;
    if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const wsUrl = `${protocol}//${host}/ws/${clientId}${token ? `?token=${encodeURIComponent(token)}` : ''}`;

    logToTerminal(`正在尝试连接 ${wsUrl}...`, 'system');
    connectBtn.disabled = true;

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        statusDot.classList.add('connected');
        statusText.textContent = '已连接';
        connectBtn.innerHTML = '<i data-lucide="link-2" style="width:16px;height:16px;"></i><span>断开连接</span>';
        connectBtn.className = 'btn-danger';
        connectBtn.disabled = false;
        messageInput.disabled = false;
        sendBtn.disabled = false;
        clientIdInput.disabled = true;
        logToTerminal('WebSocket 连接成功。', 'system');
        
        // 重连成功后重置计数并清理定时器
        reconnectAttempts = 0;
        if (reconnectTimer) {
            clearTimeout(reconnectTimer);
            reconnectTimer = null;
        }

        // 加载站内信并开启红点提示
        loadMessages();
    };

    ws.onmessage = (event) => {
        try {
            const payload = jsonParse(event.data);
            if (!payload) {
                logToTerminal(event.data, 'received');
                return;
            }
            
            if (payload.type === 'site_message') {
                // 收到站内信推送
                const msgData = payload.data;
                showToast(msgData.sender, msgData.content);
                unreadCount++;
                updateUnreadBadge();
                
                if (activeTab === 'messages') {
                    loadMessages();
                }
            } else if (payload.type === 'upload_start_ack') {
                if (isWsUploading && payload.upload_id === wsUploadId) {
                    if (payload.status === 'success') {
                        // 新上传，先尝试断点续传查询
                        ws.send(JSON.stringify({
                            type: 'upload_resume',
                            upload_id: wsUploadId
                        }));
                    } else {
                        // 拦截到错误，例如同名镜像文件已存在
                        showCustomAlert('文件已存在', payload.message || '该文件已上传，不支持重复上传！', 'warning');
                        resetWsUpload();
                    }
                }
            } else if (payload.type === 'upload_resume_ack') {
                if (isWsUploading && payload.upload_id === wsUploadId && payload.status === 'success') {
                    const completedSet = new Set(payload.completed_chunks || []);
                    
                    // 将已完成的分片计入进度
                    activeUploadsCount = 0;
                    wsUploadedBytes = 0;
                    
                    if (!wsTotalSize) return;
                    
                    for (const idx of completedSet) {
                        const chunkSize = Math.min(wsTotalSize - (idx * WS_CHUNK_SIZE), WS_CHUNK_SIZE);
                        wsUploadedBytes += chunkSize;
                    }
                    
                    if (completedSet.size > 0) {
                        logToTerminal(`断点续传：检测到 ${completedSet.size} 个已完成分片，跳过已传部分`, 'system');
                        const percent = (wsUploadedBytes / wsTotalSize) * 100;
                        progressBarFill.style.width = `${percent.toFixed(1)}%`;
                        uploadPercent.textContent = `${percent.toFixed(1)}%`;
                        const uploadedMb = (wsUploadedBytes / (1024 * 1024)).toFixed(2);
                        const totalMb = (wsTotalSize / (1024 * 1024)).toFixed(2);
                        uploadRatio.textContent = `${uploadedMb} MB / ${totalMb} MB`;
                    }
                    
                    // 构建待发送分片队列（跳过已完成的）
                    const pendingChunks = [];
                    for (let i = 0; i < wsTotalChunks; i++) {
                        if (!completedSet.has(i)) {
                            pendingChunks.push(i);
                        }
                    }
                    
                    if (pendingChunks.length === 0) {
                        // 所有分片均已上传，直接合并
                        ws.send(JSON.stringify({
                            type: 'upload_merge',
                            upload_id: wsUploadId,
                            filename: wsUploadFile ? wsUploadFile.name : '',
                            total_chunks: wsTotalChunks
                        }));
                        return;
                    }
                    
                    // 保存待发送队列，用滑动窗口驱动发送
                    wsPendingQueue = pendingChunks;
                    wsQueueIndex = 0;
                    wsStartTime = Date.now();
                    
                    for (let i = 0; i < CONCURRENCY_LIMIT; i++) {
                        if (wsQueueIndex < wsPendingQueue.length) {
                            sendChunk(wsPendingQueue[wsQueueIndex]);
                            wsQueueIndex++;
                            activeUploadsCount++;
                        }
                    }
                }
            } else if (payload.type === 'upload_chunk_ack') {
                if (isWsUploading && payload.upload_id === wsUploadId && payload.status === 'success') {
                    const ackIndex = payload.chunk_index;
                    
                    if (!wsTotalSize) return;
                    
                    // 更新整体进度数据
                    const currentChunkSize = Math.min(wsTotalSize - (ackIndex * WS_CHUNK_SIZE), WS_CHUNK_SIZE);
                    wsUploadedBytes += currentChunkSize;
                    
                    const percent = (wsUploadedBytes / wsTotalSize) * 100;
                    progressBarFill.style.width = `${percent.toFixed(1)}%`;
                    uploadPercent.textContent = `${percent.toFixed(1)}%`;
                    
                    // 计算上传速度和 ETA (最近 2 秒采样滑动平均)
                    const nowTime = Date.now();
                    speedSamples.push({ time: nowTime, uploaded: wsUploadedBytes });
                    
                    // 仅保留最近 2000ms 的采样样本
                    const cutoff = nowTime - 2000;
                    speedSamples = speedSamples.filter(s => s.time > cutoff);
                    
                    let bytesPerSecond = 0;
                    if (speedSamples.length >= 2) {
                        const firstSample = speedSamples[0];
                        const lastSample = speedSamples[speedSamples.length - 1];
                        const timeDiff = (lastSample.time - firstSample.time) / 1000;
                        const bytesDiff = lastSample.uploaded - firstSample.uploaded;
                        if (timeDiff > 0) {
                            bytesPerSecond = bytesDiff / timeDiff;
                        }
                    } else {
                        // 样本不足 2 个时 fallback 采用从开始计起的平均速度
                        const elapsedSeconds = (nowTime - wsStartTime) / 1000;
                        if (elapsedSeconds > 0) {
                            bytesPerSecond = wsUploadedBytes / elapsedSeconds;
                        }
                    }
                    
                    let speedStr = '';
                    if (bytesPerSecond > 1024 * 1024) {
                        speedStr = `${(bytesPerSecond / (1024 * 1024)).toFixed(2)} MB/s`;
                    } else if (bytesPerSecond > 1024) {
                        speedStr = `${(bytesPerSecond / 1024).toFixed(1)} KB/s`;
                    } else {
                        speedStr = `${bytesPerSecond.toFixed(0)} B/s`;
                    }
                    uploadSpeed.textContent = speedStr;
                    
                    if (bytesPerSecond > 0) {
                        const remainingBytes = wsTotalSize - wsUploadedBytes;
                        const remainingSeconds = remainingBytes / bytesPerSecond;
                        if (remainingSeconds < 60) {
                            uploadEta.textContent = `剩余时间: ${Math.ceil(remainingSeconds)}秒`;
                        } else {
                            const mins = Math.floor(remainingSeconds / 60);
                            const secs = Math.ceil(remainingSeconds % 60);
                            uploadEta.textContent = `剩余时间: ${mins}分${secs}秒`;
                        }
                    } else {
                        uploadEta.textContent = '剩余时间: --';
                    }
                    
                    // 已上传大小比
                    const uploadedMb = (wsUploadedBytes / (1024 * 1024)).toFixed(2);
                    const totalMb = (wsTotalSize / (1024 * 1024)).toFixed(2);
                    uploadRatio.textContent = `${uploadedMb} MB / ${totalMb} MB`;
                    
                    // 扣减在途活跃包数
                    activeUploadsCount--;
                    
                    // 滑动窗口推进：有空余窗口时，立即发出下一个分片
                    if (wsQueueIndex < wsPendingQueue.length) {
                        sendChunk(wsPendingQueue[wsQueueIndex]);
                        wsQueueIndex++;
                        activeUploadsCount++;
                    } else if (activeUploadsCount === 0) {
                        // 所有分片全部上传完成且都收到 Ack
                        uploadSpeed.textContent = '-- KB/s';
                        uploadEta.textContent = '正在合并文件...';
                        uploadPercent.textContent = '99% (正在合并)';
                        
                        ws.send(JSON.stringify({
                            type: 'upload_merge',
                            upload_id: wsUploadId,
                            filename: wsUploadFile ? wsUploadFile.name : '',
                            total_chunks: wsTotalChunks
                        }));
                    }
                }
            } else if (payload.type === 'upload_merge_ack') {
                if (isWsUploading && payload.upload_id === wsUploadId) {
                    if (payload.status === 'success') {
                        progressBarFill.style.width = '100%';
                        uploadPercent.textContent = '100% (已完成)';
                        uploadSpeed.textContent = '-- KB/s';
                        uploadEta.textContent = '上传成功';
                        showCustomAlert('上传成功', `文件 "${wsUploadFile ? wsUploadFile.name : ''}" 通过 WebSocket 上传并合并成功！`, 'success');
                        setTimeout(() => {
                            progressContainer.style.display = 'none';
                        }, 1500);
                        resetWsUpload();
                        loadUploadedFiles();
                    } else {
                        showCustomAlert('合并失败', `请重新上传！原因: ${payload.message || '未知错误'}`, 'danger');
                        resetWsUpload();
                    }
                }
            } else if (payload.type === 'upload_abort_ack') {
                if (payload.status === 'success') {
                    logToTerminal(`服务器确认上传已取消: ${payload.upload_id}`, 'system');
                    // 确保本地状态已重置（abortUpload() 已调用 resetWsUpload）
                }
            } else if (payload.type === 'site_message_ack') {
                if (payload.status === 'success') {
                    logToTerminal(`站内信已发送 (id=${payload.id}): ${payload.message}`, 'system');
                } else {
                    logToTerminal(`站内信发送失败: ${payload.message}`, 'error');
                }
            } else {
                logToTerminal(event.data, 'received');
            }
        } catch (e) {
            logToTerminal(event.data, 'received');
        }
    };

    ws.onclose = (event) => {
        statusDot.classList.remove('connected');
        statusText.textContent = '未连接';
        connectBtn.innerHTML = '<i data-lucide="link" style="width:16px;height:16px;"></i><span>连接服务</span>';
        connectBtn.className = 'btn-primary';
        connectBtn.disabled = false;
        messageInput.disabled = true;
        sendBtn.disabled = true;
        clientIdInput.disabled = false;
        logToTerminal(`连接断开。代码: ${event.code}`, 'system');

        // 在非用户主动断开、且重连次数未达上限时，尝试进行自动重连
        if (!isUserInitiatedClose && reconnectAttempts < MAX_RECONNECT) {
            const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 30000);
            reconnectAttempts++;
            logToTerminal(`连接异常断开，将在 ${delay / 1000} 秒后尝试第 ${reconnectAttempts}/${MAX_RECONNECT} 次自动重连...`, 'system');
            
            reconnectTimer = setTimeout(() => {
                logToTerminal(`正在尝试自动重连...`, 'system');
                connectBtn.click();
            }, delay);
        }
    };

    ws.onerror = (error) => {
        logToTerminal('WebSocket 发生错误，请查看浏览器控制台。', 'error');
        console.error(error);
    };
});

function jsonParse(str) {
    try {
        return JSON.parse(str);
    } catch (e) {
        return null;
    }
}

// 发送 WS 站内信（接收者默认是自己，方便自测）
function sendWSMessage() {
    const content = messageInput.value.trim();
    if (!content || !ws || ws.readyState !== WebSocket.OPEN) return;

    const target = clientIdInput.value.trim();
    const msg = { type: 'site_message', target: target, content: content };
    ws.send(JSON.stringify(msg));
    logToTerminal(`站内信 → ${target}: ${content}`, 'sent');
    messageInput.value = '';
}

sendBtn.addEventListener('click', sendWSMessage);
messageInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') sendWSMessage();
});

// 站内信功能：拉取消息
function loadMessages() {
    const clientId = clientIdInput.value.trim();
    if (!clientId) return;

    fetch(`/api/messages?receiver=${encodeURIComponent(clientId)}&status=${currentFilter}${token ? `&token=${encodeURIComponent(token)}` : ''}`)
        .then(res => res.json())
        .then(data => {
            msgListArea.innerHTML = '';
            
            // 计算未读数
            if (currentFilter === 'all') {
                unreadCount = data.filter(m => m.is_read === 0).length;
                updateUnreadBadge();
            } else if (currentFilter === 'unread') {
                unreadCount = data.length;
                updateUnreadBadge();
            }

            if (data.length === 0) {
                msgListArea.innerHTML = `<div class="log-entry log-system" style="text-align: center; margin-top: 40px;">暂无相关的站内信记录</div>`;
                return;
            }

            data.forEach(msg => {
                const card = document.createElement('div');
                card.className = `msg-card ${msg.is_read === 0 ? 'unread' : ''}`;
                card.innerHTML = `
                    <div class="msg-header">
                        <span class="msg-sender">${escapeHtml(msg.sender)}</span>
                        <span>${msg.created_at}</span>
                    </div>
                    <div class="msg-body">${escapeHtml(msg.content)}</div>
                    <div class="msg-footer">
                        ${msg.is_read === 0 ? `
                            <button class="btn-secondary" style="padding: 4px 10px; font-size:11px; border-radius:6px;" onclick="markAsRead(${msg.id})">
                                <i data-lucide="check" style="width:12px;height:12px;"></i>
                                <span>设为已读</span>
                            </button>
                        ` : `<span style="font-size:11px; color:var(--text-muted);">已读</span>`}
                    </div>
                `;
                msgListArea.appendChild(card);
            });
            lucide.createIcons();
        })
        .catch(err => {
            console.error(err);
            msgListArea.innerHTML = `<div class="log-entry log-error" style="text-align: center; margin-top: 40px;">拉取消息失败，请检查服务</div>`;
        });
}

// 更新未读角标
function updateUnreadBadge() {
    if (unreadCount > 0) {
        unreadBadge.textContent = unreadCount;
        unreadBadge.style.display = 'block';
    } else {
        unreadBadge.style.display = 'none';
    }
}

// 标记已读
function markAsRead(id) {
    fetch(`/api/messages/${id}/read${token ? `?token=${encodeURIComponent(token)}` : ''}`, { 
        method: 'POST',
        headers: token ? { 'Authorization': 'Bearer ' + token } : {}
    })
        .then(res => res.json())
        .then(res => {
            if (res.status === 'success') {
                // 刷新消息列表
                loadMessages();
            }
        })
        .catch(err => console.error(err));
}

// 辅助函数：显示自定义提示框（代替 alert）
function showAlertToast(title, body, borderLeftColor = 'var(--danger)', iconName = 'alert-triangle') {
    const container = document.getElementById('toastContainer');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.style.borderLeftColor = borderLeftColor;
    toast.innerHTML = `
        <i data-lucide="${iconName}" class="toast-icon" style="color:${borderLeftColor}; width: 20px; height: 20px;"></i>
        <div class="toast-content">
            <div class="toast-title" style="color:${borderLeftColor};">${escapeHtml(title)}</div>
            <div class="toast-body">${escapeHtml(body)}</div>
        </div>
    `;
    container.appendChild(toast);
    lucide.createIcons();

    setTimeout(() => {
        toast.style.animation = 'slideIn 0.3s reverse forwards';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// 辅助函数：显示自定义警示弹窗（代替 alert）
function showCustomAlert(title, message, type = 'danger') {
    const modal = document.getElementById('customAlertModal');
    const titleEl = document.getElementById('customAlertTitle');
    const msgEl = document.getElementById('customAlertMessage');
    const okBtn = document.getElementById('customAlertOkBtn');
    const iconContainer = document.getElementById('customAlertIconContainer');
    const icon = document.getElementById('customAlertIcon');

    if (!modal || !titleEl || !msgEl || !okBtn || !iconContainer || !icon) {
        alert(message);
        return;
    }

    titleEl.textContent = title;
    msgEl.textContent = message;
    
    if (type === 'danger') {
        iconContainer.style.background = 'rgba(239, 68, 68, 0.15)';
        iconContainer.style.color = 'var(--danger)';
        icon.setAttribute('data-lucide', 'alert-triangle');
    } else if (type === 'warning') {
        iconContainer.style.background = 'rgba(245, 158, 11, 0.15)';
        iconContainer.style.color = '#f59e0b';
        icon.setAttribute('data-lucide', 'alert-circle');
    } else if (type === 'success') {
        iconContainer.style.background = 'rgba(16, 185, 129, 0.15)';
        iconContainer.style.color = 'var(--success)';
        icon.setAttribute('data-lucide', 'check-circle');
    } else {
        iconContainer.style.background = 'rgba(59, 130, 246, 0.15)';
        iconContainer.style.color = 'var(--primary)';
        icon.setAttribute('data-lucide', 'info');
    }

    modal.style.display = 'flex';
    lucide.createIcons();

    const close = () => {
        modal.style.display = 'none';
        okBtn.removeEventListener('click', close);
    };

    okBtn.addEventListener('click', close);
}

// 辅助函数：显示自定义确认弹窗（代替 confirm）
function showCustomConfirm(message, callback) {
    const modal = document.getElementById('customConfirmModal');
    const msgEl = document.getElementById('customConfirmMessage');
    const okBtn = document.getElementById('customConfirmOkBtn');
    const cancelBtn = document.getElementById('customConfirmCancelBtn');
    
    if (!modal || !msgEl || !okBtn || !cancelBtn) return;

    msgEl.textContent = message;
    modal.style.display = 'flex';
    
    lucide.createIcons();

    const close = () => {
        modal.style.display = 'none';
        okBtn.removeEventListener('click', onOk);
        cancelBtn.removeEventListener('click', onCancel);
    };

    const onOk = () => {
        close();
        callback();
    };

    const onCancel = () => {
        close();
    };

    okBtn.addEventListener('click', onOk);
    cancelBtn.addEventListener('click', onCancel);
}

// 一键已读
function markAllAsRead() {
    console.log("markAllAsRead called");
    const clientId = clientIdInput.value.trim();
    if (!clientId) {
        showAlertToast('提示', '请先连接 WebSocket 服务以确定客户端 ID！', 'var(--primary)', 'info');
        return;
    }
    showCustomConfirm('确定要将所有未读消息标记为已读吗？', () => {
        console.log("Sending read-all request for receiver:", clientId);
        fetch(`/api/messages/read-all?receiver=${encodeURIComponent(clientId)}${token ? `&token=${encodeURIComponent(token)}` : ''}`, { 
            method: 'POST',
            headers: token ? { 'Authorization': 'Bearer ' + token } : {}
        })
            .then(res => res.json())
            .then(res => {
                console.log("read-all response:", res);
                if (res.status === 'success') {
                    loadMessages();
                }
            })
            .catch(err => console.error("read-all error:", err));
    });
}

// 模拟发送消息 (往 RabbitMQ 写入)
function sendMockMessage() {
    const sender = document.getElementById('mockSender').value.trim();
    const receiver = document.getElementById('mockReceiver').value.trim();
    const content = document.getElementById('mockContent').value.trim();

    if (!receiver || !content) {
        showCustomAlert('提示', '接收人 ID 和消息内容不能为空', 'warning');
        return;
    }

    fetch(`/api/messages/send${token ? `?token=${encodeURIComponent(token)}` : ''}`, {
        method: 'POST',
        headers: { 
            'Content-Type': 'application/json',
            ...(token ? { 'Authorization': 'Bearer ' + token } : {})
        },
        body: JSON.stringify({ sender, receiver, content })
    })
    .then(res => res.json())
    .then(data => {
        if (data.status === 'success') {
            document.getElementById('mockContent').value = '';
            // 弹窗提示发送成功
            const toast = document.createElement('div');
            toast.className = 'toast';
            toast.style.borderLeftColor = 'var(--primary)';
            toast.innerHTML = `
                <i data-lucide="check-circle" class="toast-icon" style="color:var(--primary); width:20px;height:20px;"></i>
                <div class="toast-content">
                    <div class="toast-title" style="color:var(--primary);">模拟消息投递成功</div>
                    <div class="toast-body">已成功投递到 RabbitMQ，等待消费者写入 MySQL 并派发推送。</div>
                </div>
            `;
            document.getElementById('toastContainer').appendChild(toast);
            lucide.createIcons();
            setTimeout(() => {
                toast.style.animation = 'slideIn 0.3s reverse forwards';
                setTimeout(() => toast.remove(), 300);
            }, 3000);
        } else {
            showCustomAlert('发送失败', '发送失败: ' + data.message, 'danger');
        }
    })
    .catch(err => {
        console.error(err);
        showCustomAlert('发送失败', '发送失败，请确保服务已启动', 'danger');
    });
}

// 消息过滤
function filterMessages(type) {
    currentFilter = type;
    document.getElementById('filterAll').className = type === 'all' ? 'btn-primary' : 'btn-secondary';
    document.getElementById('filterUnread').className = type === 'unread' ? 'btn-primary' : 'btn-secondary';
    document.getElementById('filterRead').className = type === 'read' ? 'btn-primary' : 'btn-secondary';
    loadMessages();
}

function escapeHtml(text) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return text.replace(/[&<>"']/g, function(m) { return map[m]; });
}


// 大文件分片上传功能 (使用纯二进制 WebSocket 零拷贝与滑动窗口并发技术)
const dropzone = document.getElementById('dropzone');
const progressContainer = document.getElementById('progressContainer');
const uploadFileName = document.getElementById('uploadFileName');
const uploadPercent = document.getElementById('uploadPercent');
const progressBarFill = document.getElementById('progressBarFill');
const uploadSpeed = document.getElementById('uploadSpeed');
const uploadEta = document.getElementById('uploadEta');
const uploadRatio = document.getElementById('uploadRatio');

const WS_CHUNK_SIZE = 4 * 1024 * 1024; // 4MB 切片大小
const CONCURRENCY_LIMIT = 3; // 滑动窗口并发限制（允许同时发送 3 个分片）
let wsUploadFile = null;
let wsUploadId = null;
let wsTotalSize = 0;
let wsTotalChunks = 0;
let wsPendingQueue = []; // 待发送的分片索引队列（断点续传时跳过已传分片）
let wsQueueIndex = 0;    // 当前待发送队列的指针
let activeUploadsCount = 0; // 当前在途传输的切片计数
let wsUploadedBytes = 0;
let wsStartTime = 0;
let isWsUploadAborted = false;
let isWsUploading = false;
let speedSamples = [];   // 上传速度计算的时间-大小采样队列

// 拖拽文件样式监听
dropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropzone.classList.add('dragover');
});

dropzone.addEventListener('dragleave', () => {
    dropzone.classList.remove('dragover');
});

dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.classList.remove('dragover');
    if (e.dataTransfer.files.length > 0) {
        uploadFile(e.dataTransfer.files[0]);
    }
});

function handleFileSelect(e) {
    if (e.target.files.length > 0) {
        uploadFile(e.target.files[0]);
    }
}

async function uploadFile(file) {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
        showCustomAlert('提示', '请先连接 WebSocket 服务！', 'warning');
        return;
    }
    if (isWsUploading) {
        showCustomAlert('提示', '当前已有正在上传的任务', 'warning');
        return;
    }

    isWsUploadAborted = false;
    isWsUploading = true;
    wsUploadFile = file;
    // 使用确定性 upload_id（基于清洗后的文件名+大小），断线重连后可恢复上传且安全防范非法字符
    const cleanName = file.name.replace(/[^\w\-]/g, '_');
    wsUploadId = cleanName + '_' + file.size;
    wsTotalSize = file.size;
    wsTotalChunks = Math.ceil(wsTotalSize / WS_CHUNK_SIZE);
    wsPendingQueue = [];
    wsQueueIndex = 0;
    activeUploadsCount = 0;
    wsUploadedBytes = 0;
    wsStartTime = Date.now();

    uploadFileName.textContent = file.name;
    progressContainer.style.display = 'flex';
    progressBarFill.style.width = '0%';
    uploadPercent.textContent = '0%';
    uploadSpeed.textContent = '0 KB/s';
    uploadEta.textContent = '计算中...';
    uploadRatio.textContent = `0 MB / ${(wsTotalSize / (1024 * 1024)).toFixed(2)} MB`;

    // 发送上传开始信号
    ws.send(JSON.stringify({
        type: 'upload_start',
        upload_id: wsUploadId,
        filename: file.name
    }));
}

// 读取指定分片并发送 (零拷贝组合 Blob 直接发送)
function sendChunk(chunkIndex) {
    if (isWsUploadAborted) return;

    const start = chunkIndex * WS_CHUNK_SIZE;
    const end = Math.min(start + WS_CHUNK_SIZE, wsTotalSize);
    const blobChunk = wsUploadFile.slice(start, end);

    // 构造 4 字节的序号 Header (Int32, 大端序)
    const headerBuffer = new ArrayBuffer(4);
    const view = new DataView(headerBuffer);
    view.setUint32(0, chunkIndex, false); // false = big-endian

    // 零拷贝拼接头 Blob 与数据 Blob，直接通过 WebSocket 发送二进制数据帧
    const headerBlob = new Blob([headerBuffer]);
    const combinedBlob = new Blob([headerBlob, blobChunk]);

    ws.send(combinedBlob);
}

// 重载上传状态
function resetWsUpload() {
    isWsUploading = false;
    wsUploadFile = null;
    wsUploadId = null;
    wsPendingQueue = [];
    wsQueueIndex = 0;
    activeUploadsCount = 0;
    progressContainer.style.display = 'none';
    speedSamples = []; // 重置采样
    
    // 重置文件输入框的值，以确保同名文件被取消/上传成功后，再次选择时能正确触发 change 事件
    const fileInput = document.getElementById('fileInput');
    if (fileInput) {
        fileInput.value = '';
    }
}

// 取消上传
function abortUpload() {
    isWsUploadAborted = true;
    if (ws && ws.readyState === WebSocket.OPEN && wsUploadId) {
        ws.send(JSON.stringify({
            type: 'upload_abort',
            upload_id: wsUploadId
        }));
    }
    showCustomAlert('提示', '上传已被取消', 'info');
    resetWsUpload();
}

// 拉取并渲染已上传文件列表
function loadUploadedFiles() {
    fetch(`/api/uploads${token ? `?token=${encodeURIComponent(token)}` : ''}`, {
        headers: token ? { 'Authorization': 'Bearer ' + token } : {}
    })
    .then(res => res.json())
    .then(data => {
        const tbody = document.getElementById('fileListBody');
        if (!tbody) return;
        
        tbody.innerHTML = '';
        if (data.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="5" style="text-align: center; padding: 20px; color: var(--text-muted);">
                        暂无上传文件记录
                    </td>
                </tr>
            `;
            return;
        }
        
        data.forEach(file => {
            const tr = document.createElement('tr');
            tr.style.borderBottom = '1px solid var(--card-border)';
            tr.innerHTML = `
                <td style="padding: 12px 8px; font-weight: 500; color: var(--text-main);">${escapeHtml(file.filename)}</td>
                <td style="padding: 12px 8px; color: var(--text-muted);">${file.file_size_mb} MB</td>
                <td style="padding: 12px 8px; color: var(--text-muted); font-family: monospace; font-size: 11px;">${escapeHtml(file.file_path)}</td>
                <td style="padding: 12px 8px; color: var(--text-muted);">${file.created_at}</td>
                <td style="padding: 12px 8px;">
                    <button class="btn-danger" style="padding: 4px 10px; font-size: 11px; border-radius: 6px; display: inline-flex; align-items: center; gap: 4px;" onclick="deleteUploadedFile(${file.id}, '${escapeHtml(file.filename)}')">
                        <i data-lucide="trash-2" style="width: 12px; height: 12px;"></i>
                        <span>删除</span>
                    </button>
                </td>
            `;
            tbody.appendChild(tr);
        });
        lucide.createIcons();
    })
    .catch(err => {
        console.error("加载文件列表失败:", err);
        const tbody = document.getElementById('fileListBody');
        if (tbody) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="5" style="text-align: center; padding: 20px; color: var(--danger);">
                        加载文件列表失败，请检查服务连接
                    </td>
                </tr>
            `;
        }
    });
}

// 删除已上传文件
function deleteUploadedFile(fileId, filename) {
    showCustomConfirm(`确定要永久删除文件 "${filename}" 及其数据库记录吗？`, () => {
        fetch(`/api/uploads/${fileId}${token ? `?token=${encodeURIComponent(token)}` : ''}`, {
            method: 'DELETE',
            headers: token ? { 'Authorization': 'Bearer ' + token } : {}
        })
        .then(res => res.json())
        .then(res => {
            if (res.status === 'success') {
                showAlertToast('提示', `文件 "${filename}" 已成功删除！`, 'var(--primary)', 'check-circle');
                loadUploadedFiles(); // 刷新列表
            } else {
                showAlertToast('错误', `删除失败: ${res.message || '未知错误'}`, 'var(--danger)', 'alert-triangle');
            }
        })
        .catch(err => {
            console.error("删除文件出错:", err);
            showAlertToast('错误', '删除请求失败，请确保服务已启动', 'var(--danger)', 'alert-triangle');
        });
    });
}


// 审计日志全局状态
let currentAuditPage = 1;
const auditPageLimit = 10;

// 加载审计日志列表数据
function loadAuditLogs(page = 1) {
    currentAuditPage = page;
    const operator = document.getElementById('auditOperatorFilter').value.trim();
    const action = document.getElementById('auditActionFilter').value;
    const status = document.getElementById('auditStatusFilter').value;
    
    let query = `?page=${page}&limit=${auditPageLimit}`;
    if (operator) query += `&operator=${encodeURIComponent(operator)}`;
    if (action) query += `&action=${encodeURIComponent(action)}`;
    if (status) query += `&status=${encodeURIComponent(status)}`;
    if (token) query += `&token=${encodeURIComponent(token)}`;
    
    const tbody = document.getElementById('auditLogListBody');
    if (!tbody) return;
    
    tbody.innerHTML = `<tr><td colspan="12" style="text-align: center; padding: 20px;">正在加载中...</td></tr>`;
    
    fetch(`/api/audit-logs${query}`, {
        headers: token ? { 'Authorization': 'Bearer ' + token } : {}
    })
    .then(res => {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
    })
    .then(res => {
        tbody.innerHTML = '';
        const data = res.data || [];
        const total = res.total || 0;
        
        if (data.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="12" style="text-align: center; padding: 20px; color: var(--text-muted);">
                        暂无符合条件的审计日志
                    </td>
                </tr>
            `;
            document.getElementById('auditPaginationInfo').textContent = `共 0 条记录，当前第 1/1 页`;
            document.getElementById('auditPrevPageBtn').disabled = true;
            document.getElementById('auditNextPageBtn').disabled = true;
            return;
        }
        
        data.forEach(log => {
            const tr = document.createElement('tr');
            tr.style.borderBottom = '1px solid var(--card-border)';
            
            const statusStyle = log.status === 'success' 
                ? 'color: var(--success); font-weight: 500;' 
                : 'color: var(--danger); font-weight: 500;';
                
            let methodStyle = 'background: rgba(16, 185, 129, 0.15); color: var(--success);';
            if (log.method === 'POST') methodStyle = 'background: rgba(59, 130, 246, 0.15); color: var(--primary);';
            if (log.method === 'DELETE') methodStyle = 'background: rgba(239, 68, 68, 0.15); color: var(--danger);';
            if (log.method === 'PUT' || log.method === 'PATCH') methodStyle = 'background: rgba(245, 158, 11, 0.15); color: #f59e0b;';

            tr.innerHTML = `
                <td style="padding: 10px 8px; color: var(--text-muted);">${log.id}</td>
                <td style="padding: 10px 8px; color: var(--text-muted);">${log.created_at}</td>
                <td style="padding: 10px 8px; font-weight: 500; color: var(--text-main);">${escapeHtml(log.operator || '--')}</td>
                <td style="padding: 10px 8px;"><span style="padding: 4px 8px; border-radius: 6px; font-size: 11px; font-weight: 600; ${methodStyle}">${log.method || '--'}</span></td>
                <td style="padding: 10px 8px; font-family: monospace; font-size:12px; color: #60a5fa;">${log.action}</td>
                <td style="padding: 10px 8px; color: var(--text-muted);">${log.resource_type || '--'}</td>
                <td style="padding: 10px 8px; color: var(--text-muted);">${log.resource_id || '--'}</td>
                <td style="padding: 10px 8px; color: var(--text-muted); max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${escapeHtml(JSON.stringify(log.request_params || {}))}">${escapeHtml(log.request_params ? JSON.stringify(log.request_params).substring(0, 25) + '...' : '--')}</td>
                <td style="padding: 10px 8px; color: var(--text-muted);">${log.ip_address || '--'}</td>
                <td style="padding: 10px 8px; color: #34d399; font-weight: 500;">${log.execution_time != null ? log.execution_time + ' ms' : '--'}</td>
                <td style="padding: 10px 8px; ${statusStyle}">${log.status}</td>
                <td style="padding: 10px 8px;">
                    <button class="btn-secondary" style="padding: 4px 10px; font-size: 11px; border-radius: 6px; display: inline-flex; align-items: center; gap: 4px;" onclick="showAuditDetail('${escapeHtml(log.details || '{}')}')">
                        <i data-lucide="eye" style="width: 12px; height: 12px;"></i>
                        <span>详情</span>
                    </button>
                </td>
            `;
            tbody.appendChild(tr);
        });
        
        // 分页控制
        const totalPages = Math.ceil(total / auditPageLimit) || 1;
        document.getElementById('auditPaginationInfo').textContent = `共 ${total} 条记录，当前第 ${currentAuditPage}/${totalPages} 页`;
        document.getElementById('auditPrevPageBtn').disabled = currentAuditPage <= 1;
        document.getElementById('auditNextPageBtn').disabled = currentAuditPage >= totalPages;
        
        lucide.createIcons();
    })
    .catch(err => {
        console.error("加载审计日志失败:", err);
        tbody.innerHTML = `
            <tr>
                <td colspan="12" style="text-align: center; padding: 20px; color: var(--danger);">
                    加载审计日志失败，请检查服务连接或 API Token
                </td>
            </tr>
        `;
    });
}

function resetAuditFilters() {
    document.getElementById('auditOperatorFilter').value = '';
    document.getElementById('auditActionFilter').value = '';
    document.getElementById('auditStatusFilter').value = '';
    loadAuditLogs(1);
}

function changeAuditPage(direction) {
    loadAuditLogs(currentAuditPage + direction);
}

function showAuditDetail(detailsStr) {
    const modal = document.getElementById('auditDetailModal');
    const pre = document.getElementById('auditDetailPre');
    if (!modal || !pre) return;
    
    try {
        const parsed = JSON.parse(detailsStr);
        pre.textContent = JSON.stringify(parsed, null, 2);
    } catch (e) {
        pre.textContent = detailsStr;
    }
    modal.style.display = 'flex';
    lucide.createIcons();
}

function closeAuditDetailModal() {
    const modal = document.getElementById('auditDetailModal');
    if (modal) modal.style.display = 'none';
}

// 页面加载完成后自动触发一次 WebSocket 连接
window.addEventListener('DOMContentLoaded', () => {
    if (clientIdInput && clientIdInput.value.trim() && connectBtn) {
        connectBtn.click();
    }
});
