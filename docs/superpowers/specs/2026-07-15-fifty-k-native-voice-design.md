# 510K 原生语音播报设计

## 目标

- 普通单张 5、10、K 继续复用现有经典斗地主男女声牌点语音。
- 假 510K 播放“五十K”，真 510K 播放“真五十K”，不得误播“炸弹”。
- 510K 开局由持有梅花 3 的首出玩家音色播报“梅花三先出”。
- 三类 510K 专用语音全部使用项目托管的静态音频，不调用浏览器 `speechSynthesis`。

## 实现

新增 `club_three_first` 音效名，与 `fifty_k_true`、`fifty_k_false` 一起映射到 `/static/audio/fifty_k/{female|male}/` 下的 WAV 文件。静态音频使用本机 Windows 中文语音生成并随项目托管，男女版本使用同一中文声线的不同 SSML 音高与语速，保持短促的斗地主播报节奏；生成脚本保留在仓库中以便重新生成。

前端在 510K `game_start` 上直接调用 `playSound('club_three_first', current_turn)`。以 `room_id` 记录最近已经播报的房间，重复 `game_start` 不重复播放；`reconnected` 与周期状态同步不触发播报。经典与不洗牌开局不播放该音频。

音频加载失败时只保留现有普通提示/出牌音，不降级到浏览器 TTS。

## 验收

- 男女声设置分别请求正确的本地 510K 和梅花 3 WAV 路径。
- 真/假 510K 不请求 `bomb.ogg`，不调用 `speechSynthesis`。
- 510K 首次 `game_start` 播放一次 `club_three_first`；重复事件、重连、经典开局均不播放。
- 六个 WAV 资产实际存在且非空。
- 前端定向 Vitest、类型检查与构建通过。

