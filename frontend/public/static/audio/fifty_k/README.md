# 510K 专属语音开发资产

本目录实际托管以下六个 MP3 文件：

- `female/510k.mp3`：假 510K，播报"五十K"。
- `female/true_510k.mp3`：真 510K，播报"真五十K"。
- `female/club_three_first.mp3`：开局播报"梅花3先出"。
- `male/510k.mp3`：假 510K，播报"五十K"。
- `male/true_510k.mp3`：真 510K，播报"真五十K"。
- `male/club_three_first.mp3`：开局播报"梅花3先出"。

运行时前端请求路径是 `/static/audio/fifty_k/...`。在本项目中，Vite 开发服务器会把 `/static` 代理到后端，后端生产托管也会优先挂载 `backend/static`，因此同一批 MP3 必须同时存在于：

- `frontend/public/static/audio/fifty_k/`
- `backend/static/audio/fifty_k/`

当前文件使用 Edge TTS 神经网络语音引擎生成。`female` 目录使用 `zh-CN-XiaoxiaoNeural`（微软小晓，活泼自然），`male` 目录使用 `zh-CN-YunxiNeural`（微软云希，干练有力），通过 SSML `<prosody>` 标签调整语速和音高以适配短促的斗地主播报节奏。

## 重新生成

生成前需满足以下条件：

- 已安装 Python 3.9+。
- 已安装 `edge-tts` 依赖：`pip install edge-tts`。
- 需要网络连接（Edge TTS 在生成时调用微软在线服务）。

在项目根目录执行默认生成命令：

```bash
python frontend/scripts/generate-fifty-k-voice-assets.py
```

默认脚本会同时写入前端 public 目录与后端 static 目录；如只需要指定单独目录，可传入 `--output-root` 或 `--backend-output-root` 覆盖。

也可以通过参数指定其他 Edge TTS 声线：

```bash
python frontend/scripts/generate-fifty-k-voice-assets.py --female-voice zh-CN-XiaoyiNeural --male-voice zh-CN-YunjianNeural
```

脚本生成后会逐一验证所有文件存在、大小超过 100 字节，并具有有效的 MP3 帧头或 ID3 标签头；验证失败时脚本会直接报错退出。脚本还会自动清理同目录下的旧 `.wav` 文件。

## 许可与替换要求

Edge TTS 使用微软在线语音服务，生成的音频仅作为项目开发资产使用。正式发布或商用前，项目方必须自行核验 Edge TTS 服务条款是否允许当前使用和分发方式；如无法确认，应替换为原创录音或具有明确发布、商用授权的录音。

禁止从腾讯斗地主或其他第三方游戏复制语音音频。运行时若本地文件加载失败，前端只回退到普通出牌提示音，不会改播炸弹音效，也不会调用浏览器 `speechSynthesis`。
