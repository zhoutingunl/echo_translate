# Demo 录屏

完整流程走查（用真实 AI 管线，无需麦克风——`record_demo.py` 驱动内置「示例回放」）。解说字幕直接渲染进页面、烧录在画面里；中文画外音由 macOS TTS（Tingting，zh_CN）自动生成。

| 文件 | 说明 |
|---|---|
| [`output/echo_translate_demo.gif`](./output/echo_translate_demo.gif) | README 预览动图（含解说字幕，~2.3MB） |
| [`output/echo_translate_demo_narrated.mp4`](./output/echo_translate_demo_narrated.mp4) | 录屏 + **中文画外音** + 烧录解说字幕 |
| [`output/echo_translate_demo.mp4`](./output/echo_translate_demo.mp4) | 录屏（无旁白，含烧录字幕） |
| [`output/captions.srt`](./output/captions.srt) | 解说字幕轨（sidecar） |
| [`output/storyboard.png`](./output/storyboard.png) | 8 帧分镜一览 |
| `output/shots/` · `output/timeline.json` | 各步骤高清截图 · 字幕时间轴 |

## 走查的步骤（与录屏/旁白一致）

1. **首页** 已连接，提示可「开始聆听」或「示例回放」。
2. **增量字幕** 选「技术分享」回放，英文每句落地即出中文。
3. **自动纠错①** `存储系统` →「修正」→ `分布式存储系统`（ASR 把 storage 修订为 distributed storage）。
4. **自动纠错②** `缓存层` →「修正」→ `分布式缓存层`，旧译文以删除线短暂保留。
5. **术语记忆** 侧栏现场新增术语 `Pulsar`；Kafka/Redis/Kubernetes 全程不被音译。
6. **会议纪要** 回放结束自动生成要点（AI Summarize）。
7. **QoS Dashboard** 字幕延迟、P95、RTF、翻译成功率、术语命中率、纠错次数——逐项对照目标显示 ✅ 达标，并附会话历史与埋点。

> 录屏中所有中文译文与「修正」均为**真实 AI 实时产生**；回放只替换「原文来源」，不是录播。

## 重新生成（录屏 + 字幕 + 配音）

```bash
pip install playwright==1.58.0        # 浏览器二进制若缺：python -m playwright install chromium
PORT=8025 python app.py &             # 启动服务
BASE=http://127.0.0.1:8025 python demo/record_demo.py      # 录屏（字幕烧录进页面）+ timeline.json
python demo/build_narration.py        # 生成 captions.srt + TTS 画外音 + mp4/gif
```
依赖：`ffmpeg`（转码/合成）、macOS `say`（中文 TTS）。`build_narration.py` 不需要 ffmpeg 的字幕滤镜（字幕已烧录在录屏里）。
