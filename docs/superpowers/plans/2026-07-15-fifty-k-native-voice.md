# 510K 原生语音播报 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox syntax.

**Goal:** 为真/假 510K 和梅花 3 首出提供稳定的项目托管原生语音，并消除重复开局播报。

**Architecture:** `useSoundEngine` 负责静态男女声路径和失败降级，`useGameWebSocket` 只在首次 510K `game_start` 触发专用音效。音频由可重复执行的 PowerShell 脚本生成。

**Tech Stack:** Vue 3、TypeScript、Vitest、Web Audio API、PowerShell System.Speech、WAV。

## Global Constraints

- 不使用浏览器 TTS 播放真/假 510K 或梅花 3 首出。
- 不复制腾讯或其他未授权游戏音频。
- 不修改后端协议和 AI 模型，不重新训练。
- 完成后更新根 README，不执行 Git commit。

### Task 1: 红测

- [x] 修改 `frontend/src/composables/__tests__/useSoundEngine.spec.ts`，验证三类专用音频的男女本地 WAV 路径与无 TTS。
- [x] 修改 `frontend/src/composables/__tests__/useGameWebSocket.spec.ts`，验证专用音效、重复 `game_start` 去重、经典开局不播。
- [x] 运行定向 Vitest 并确认因现有 TTS/缺少 SoundName 而失败。

### Task 2: 实现与资产

- [x] 修改 `frontend/src/composables/useSoundEngine.ts`，新增 `club_three_first` 与 WAV 映射、专用失败降级。
- [x] 修改 `frontend/src/composables/useGameWebSocket.ts`，专用播报并按 `room_id` 去重。
- [x] 新增 `frontend/scripts/generate-fifty-k-voice-assets.ps1`，生成 female/male 的 `510k.wav`、`true_510k.wav`、`club_three_first.wav`。
- [x] 运行脚本并确认六个 WAV 非空。
- [x] 运行定向 Vitest 转绿。

### Task 3: 回归与文档

- [x] 更新 `frontend/public/static/audio/fifty_k/README.md` 与根 `README.md`。
- [x] 运行前端类型检查与构建。
- [x] 执行 `git diff --check` 并做最终代码审查。
