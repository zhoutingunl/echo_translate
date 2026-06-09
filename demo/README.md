# Demo 录屏

完整流程走查（用真实 AI 管线，无需麦克风——`record_demo.py` 驱动内置「示例回放」）。

| 文件 | 说明 |
|---|---|
| [`output/echo_translate_demo.mp4`](./output/echo_translate_demo.mp4) | 端到端录屏（~23s）：实时字幕 → 自动纠错 → 术语 → 纪要 → QoS 看板 |
| [`output/storyboard.png`](./output/storyboard.png) | 8 帧分镜一览 |
| `output/shots/` | 各步骤高清截图 |

## 走查的步骤（与录屏一致）

1. **首页** 已连接，提示可「开始聆听」或「示例回放」。
2. **增量字幕** 选「技术分享」回放，英文每句落地即出中文。
3. **自动纠错①** `存储系统` →「修正」→ `分布式存储系统`（ASR 把 storage 修订为 distributed storage）。
4. **自动纠错②** `缓存层` →「修正」→ `分布式缓存层`，旧译文以删除线短暂保留。
5. **术语记忆** 侧栏现场新增术语 `Pulsar`；Kafka/Redis/Kubernetes 全程不被音译。
6. **会议纪要** 回放结束自动生成要点（AI Summarize）。
7. **QoS Dashboard** 字幕延迟 avg 1077ms、P95 1375ms、RTF 0.683、翻译成功率/术语命中率 100%、纠错 2/6——逐项对照目标显示 ✅ 达标，并附会话历史与埋点。

> 录屏中所有中文译文与「修正」均为**真实 AI 实时产生**；回放只替换「原文来源」，不是录播。

## 重新生成

```bash
pip install playwright==1.58.0        # 浏览器二进制若缺：python -m playwright install chromium
PORT=8023 python app.py &             # 启动服务
BASE=http://127.0.0.1:8023 python demo/record_demo.py
```
