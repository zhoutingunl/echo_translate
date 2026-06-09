# EchoTranslate · AI 同声传译助手 🎧

> 实时把单向英语 / 日语 / 韩语音频流翻译成**中文滚动字幕**与**中文语音**，并能**自动纠正**之前识别或翻译的错误。
> 面向看英文技术分享、国际会议、网课、产品发布会、直播的用户——核心目标是**降低认知负荷、让你跟上演讲节奏**，而不是逐字翻译。

完整产品设计见 [`design.md`](./design.md)。

---

## 0. 30 秒看懂

| | |
|---|---|
| **痛点** | 用户不是「听不懂单词」，而是「跟不上语速」。 |
| **做法** | 音频 → 实时识别 → 增量翻译 → **自动纠错（字幕回滚）** → 中文字幕 / 语音。 |
| **亮点** | ① 字幕**回滚修正**（Revision Window，最近 N 秒可纠错）② **术语记忆**（Kubernetes 不译成「库伯内特斯」）③ 演讲 / 会议**双模式** ④ 真实 **QoS Dashboard**（延迟 P95/P99、RTF、纠错率、术语命中率）。 |
| **AI** | 翻译与纠错由 **MiniMax 大模型**驱动（实测单段 ~0.9s）；语音识别 / 播报用**浏览器原生**能力以获得真·零延迟。 |

一键体验：启动后点页面上的 **▶️ 播放示例** —— 用真实 AI 管线复现「storage → distributed storage」「缓存 → 分布式缓存」两处自动纠错。

---

## 1. 快速开始（让人能跑起来）

前置：**Python 3.11**，AI 调用需要一个 MiniMax API Key；**实时聆听**需 **Chrome** 浏览器（Web Speech API）。

```bash
# 1) 依赖
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2) 配置密钥（密钥只放在 .env，已被 .gitignore，绝不进仓库）
cp .env.example .env
#   编辑 .env，填入 MINIMAX_API_KEY=sk-...

# 3) 启动
python app.py
#   打开 http://127.0.0.1:8000          （字幕页）
#   打开 http://127.0.0.1:8000/dashboard （QoS 看板）
```

> **没有麦克风 / 不是 Chrome？** 直接用页面上的「**示例回放**」即可完整演示（含自动纠错、术语、纪要）。回放只替换「原文来源」，**翻译与纠错全部由真实 AI 管线实时产生**，不是录播。

跑测试：

```bash
pytest                 # 64 个用例，覆盖率 ~98%（阈值 85%）
```

---

## 2. 它能做什么

- **实时语音识别（ASR）**：麦克风 / 系统音频 → 增量英文（Chrome Web Speech API，边说边出）。
- **增量翻译**：每个语句一落地立即翻成中文，无需等整段说完。
- **自动纠错 / 字幕回滚**（核心）：最近 `REVISION_WINDOW_SEC`（默认 5s）内的字幕可被**就地更新**，带 `修正` 标记并高亮，旧译文以删除线短暂保留。
- **术语记忆**：术语表里的词（Kubernetes / Kafka / Redis / Hermes …）固定译法、不被音译；可在侧栏增删，新增后会**回溯重渲染**窗口内相关字幕。
- **中文语音播报（TTS）**：浏览器 `SpeechSynthesis`，可开关。
- **演讲 / 会议双模式**：演讲＝完整流畅；会议＝低延迟简洁。
- **会议纪要**：一键把整场译文压缩成要点（AI Summarize）。
- **历史记录 & 埋点**：会话 / 字幕 / 事件落 SQLite。
- **QoS Dashboard**：实时延迟 avg/P95/P99、RTF、翻译成功率、纠错率、术语命中率，并对照 `design.md §12` 目标值标注达标 / 未达标。

---

## 3. 架构

```
浏览器 (Chrome)                         Flask 服务端 (app.py)
┌──────────────────────────┐            ┌─────────────────────────────────────────┐
│ Web Speech API  (ASR) ───┼─ WebSocket ┼─► ASRIngestor ─► TranslationEngine ──┐    │
│ SpeechSynthesis (TTS) ◄──┼─  /ws      │     (segment        (MiniMax 翻译,    │    │
│ 字幕渲染 / 回滚修正 / 术语 │            │      生命周期)        glossary+context) │    │
└──────────────────────────┘            │                                      ▼    │
                                        │   RevisionWindow ◄── 自动纠错 ── AIService │
                                        │   MetricsCollector(QoS)   Store(SQLite)   │
                                        └──────────────┬────────────────────────────┘
                                                       └─► /dashboard (QoS 看板)
```

**模块（关注点分离，均可单测）**

| 文件 | 职责 |
|---|---|
| `ai_service.py` | 统一 AI 后端：`translate / retranslate / summarize`；MiniMax-Text-01 主用，M2 → Hermes 故障转移；剥离 thinking、429/5xx 重试切换；**可注入 completer 以离线测试**。 |
| `asr_engine.py` | 段生命周期：interim/final、窗口内 ASR 修订检测。 |
| `translation_engine.py` | 增量翻译：上下文 + 术语 + 模式策略。 |
| `revision_engine.py` | 纠错策略：窗口判定、术语回溯目标、标记修正。 |
| `glossary.py` | 术语记忆：注入提示 + 命中度量（不做盲替换，避免伪指标）。 |
| `pipeline.py` | 单会话编排：ASR→翻译→纠错→emit，串起度量与持久化。 |
| `metrics.py` | QoS：延迟分位、成功率、纠错率、术语命中率、RTF。 |
| `db.py` | SQLite：sessions / segments / events / glossary / metrics。 |
| `dashboard.py` | 看板蓝图：实时指标 vs 目标值。 |
| `app.py` | Flask 路由 + `/ws` WebSocket + 回放接口。 |
| `replay.py` | 可复现 demo 脚本（驱动真实纠错管线）。 |

---

## 4. 关键设计取舍（为什么做 A 不做 B）

- **ASR / TTS 用浏览器原生，而非服务端 AI 语音。**
  实测当前可用的 MiniMax Anthropic 端点**不接受音频输入**（`unsupported content type 'audio'`），且所给 key 无法调用 MiniMax 原生 ASR/TTS（需 Bearer-JWT + GroupId）。
  与其堆一个跑不通的「服务端 AI 语音」，不如把 AI 预算集中在**真正高价值、且能跑通**的环节——**翻译 + 智能纠错**；ASR/TTS 交给浏览器换取**真·零延迟**与离线可用。这是有意识的减法。
- **翻译模型选 `MiniMax-Text-01`。** 实测对比：Text-01 ≈0.9s 且无 thinking 块；M2 ≈1.7–2.0s 且需剥离 thinking；M3 ≈3.3s。实时场景延迟优先，故 Text-01 主用，M2/Hermes 仅作故障转移。
- **纠错只保留「会真正改变输出」的路径**（ASR 修订 + 术语回溯）。曾实现「用后文上下文回译前句」，但实测对完整句几乎不改变译文，是伪功能，故删去——**只统计真实发生的纠错，不做伪指标**。
- **回放模式是诚实的演示**：只替换「原文来源」，翻译/纠错全部实时由 AI 产生，并在 UI/README 明确标注，避免「造假演示」。

---

## 5. QoS 指标（design.md §12-13）

`/dashboard` 实时展示并对照目标：

| 指标 | 目标 | 说明 |
|---|---|---|
| 字幕延迟 avg | < 2s | 识别提交 → 字幕就绪（服务端单时钟，无时钟漂移） |
| P95 延迟 | < 3s | |
| RTF 实时率 | < 1 | 处理耗时 / 墙钟，<1 表示跟得上 |
| 翻译成功率 | > 95% | |
| 术语命中率 | > 95% | 出现的术语中保持固定译法的比例 |
| 纠错率 | 统计量 | 被回滚修正的字幕比例 |

> 延迟口径诚实说明：服务端度量「识别提交→字幕」这一段（主要是 AI 翻译耗时，实测 P95 ≈1.1s）。浏览器端 ASR 还会再增加约 0.3–1s，UI 另行展示。

---

## 6. 配置项（`.env`）

见 [`.env.example`](./.env.example)。常用：`MINIMAX_API_KEY`、`MINIMAX_MODEL`、`REVISION_WINDOW_SEC`、`CONTEXT_SEGMENTS`、`PORT`、`HERMES_ENABLED`（公司 VPN 内可作故障转移后端）。**密钥只在 `.env`，已被 `.gitignore`。**

---

## 7. 项目结构

```
echo_translate/
├── app.py            ├── ai_service.py      ├── templates/  index.html · dashboard.html
├── config.py         ├── asr_engine.py      ├── static/     app.js · app.css · dashboard.js
├── db.py             ├── translation_engine.py ├── tests/    （13 个测试模块，~98%）
├── pipeline.py       ├── revision_engine.py ├── requirements.txt · pytest.ini · .coveragerc
├── metrics.py        ├── glossary.py        ├── .env.example · .gitignore
├── dashboard.py      ├── replay.py          └── README.md · design.md · DEMO.md
```

---

## 8. AI 辅助开发声明（design.md §24）

本项目在开发中使用了 AI 辅助。所提交代码均**可运行、测试通过（pytest 64 项 ~98% 覆盖）、README 与实现一致**；架构取舍（模型选型、ASR/TTS 方案、删去伪纠错功能等）均经实测验证，理由见 §4。

## 9. 演示

端到端走查（实时字幕 → 自动纠错 → 术语 → 纪要 → QoS 看板，**字幕为真实 AI 实时产生**）：

![demo](./demo/output/echo_translate_demo.gif)

- **带中文画外音的录屏**（推荐）：[`demo/output/echo_translate_demo_narrated.mp4`](./demo/output/echo_translate_demo_narrated.mp4) —— 烧录解说字幕 + 中文 TTS 旁白。
- **无旁白录屏**：[`demo/output/echo_translate_demo.mp4`](./demo/output/echo_translate_demo.mp4)；分镜一览 [`demo/output/storyboard.png`](./demo/output/storyboard.png)；解说字幕轨 [`demo/output/captions.srt`](./demo/output/captions.srt)。
- **讲解脚本**：[`DEMO.md`](./DEMO.md)（5 分钟分镜）。
- **一键复现录屏 + 配音**：见 [`demo/README.md`](./demo/README.md)（Playwright 驱动真实 UI 与 AI 管线，无需麦克风）。
