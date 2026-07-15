# 510K 语音升级：Edge TTS 神经网络语音替换

## 背景

当前 510K 三条专属语音（"梅花3先出"、"五十K"、"真五十K"）由 Windows `System.Speech` + `Microsoft Huihui Desktop` 声线合成，音质机械、缺乏游戏感。需要用 Edge TTS 神经网络语音替换，使播报更接近真人配音。

## 变更范围

仅替换 510K 三条专属语音的生成方式和音频资产。前端播放逻辑、音频路径、文件格式保持不变。经典斗地主 CDN 语音不在本次范围。

## 声线选型

| 角色 | 声线 ID | 说明 |
|---|---|---|
| 女声 | `zh-CN-XiaoxiaoNeural` | 微软小晓，活泼自然，Edge TTS 中最成熟的中文女声 |
| 男声 | `zh-CN-YunxiNeural` | 微软云希，干练有力，适合游戏播报 |

使用 SSML `<prosody>` 标签调参，目标是短促有力的斗地主播报节奏：
- `rate="+15%"`：加速 15%，避免拖沓
- `pitch="+5%"`（女声）/ `pitch="-5%"`（男声）：微调音高区分性别

## 生成的音频文件

共 6 个文件，与现有文件路径完全一致：

| 路径 | 播报内容 |
|---|---|
| `fifty_k/female/510k.wav` | "五十K" |
| `fifty_k/female/true_510k.wav` | "真五十K" |
| `fifty_k/female/club_three_first.wav` | "梅花三先出" |
| `fifty_k/male/510k.wav` | "五十K" |
| `fifty_k/male/true_510k.wav` | "真五十K" |
| `fifty_k/male/club_three_first.wav` | "梅花三先出" |

每个文件同步写入 `frontend/public/static/audio/fifty_k/` 和 `backend/static/audio/fifty_k/` 两个目录。

## 实现细节

### 生成脚本

用 `frontend/scripts/generate-fifty-k-voice-assets.py` 替换现有 `generate-fifty-k-voice-assets.ps1`：

- 依赖：`edge-tts`（纯 Python，无需 ffmpeg）
- edge-tts 直接输出 MP3；脚本内部用 Python 标准库 `wave` + `audioop`（或 `io.BytesIO` 解码）将其转为 WAV，保持与现有前端 `fetchAndDecodeAudio()` 的兼容
- 脚本验证：检查每个输出文件存在、大小 > 44 字节、RIFF/WAVE 文件头
- 保留命令行参数以允许自定义输出目录和声线

### 旧脚本处理

删除 `frontend/scripts/generate-fifty-k-voice-assets.ps1`，不再保留。

### 前端代码

**零改动**。音频路径、SoundName 类型、playSound 调用链路、降级逻辑全部保持不变。

### 文档更新

- 更新 `frontend/public/static/audio/fifty_k/README.md`：反映新的 Edge TTS 生成方式
- 更新项目 `README.md`：在相关功能描述中注明语音升级

## 验收标准

1. 6 个 WAV 文件实际存在且非空，具有 RIFF/WAVE 文件头
2. 播放效果：小晓女声和云希男声，短促有力，自然流畅
3. 前端 `playSound('club_three_first')` / `playSound('fifty_k_true')` / `playSound('fifty_k_false')` 正常播放新音频
4. 前端 Vitest 测试、TypeScript 类型检查、构建通过（前端代码无变更，应自然通过）
5. 生成脚本 `python generate-fifty-k-voice-assets.py` 可重复执行
