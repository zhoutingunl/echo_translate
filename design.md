# EchoTranslate（AI同声传译助手）

Version: 1.0

Runtime: Python 3.11

Framework: Flask + gevent

Database: SQLite

AI Platform: Hermes

---

# 1. 项目简介

EchoTranslate 是一款实时 AI 同声传译助手。

用户观看：

* 技术分享
* 国际会议
* 英文课程
* 产品发布会
* YouTube视频
* 在线直播

时，可以实时获得中文字幕或中文语音翻译。

系统支持：

* 实时ASR
* 增量翻译
* 自动纠错
* 字幕回滚修正
* 语音播报
* QoS监控

---

# 2. 用户洞察

用户真正的问题不是：

```text
听不懂单词
```

而是：

```text
跟不上语速
```

例如：

演讲者说：

"I'm going to discuss the architecture of our distributed storage system..."

用户可能认识每个词。

但来不及处理。

因此核心目标：

```text
降低认知负荷
```

而不是追求逐字翻译。

---

# 3. 产品定位

不是翻译软件。

不是字幕生成器。

定位：

实时跨语言信息获取助手

目标：

让用户持续跟上演讲节奏。

---

# 4. 产品目标

实现：

音频

↓

实时识别

↓

实时翻译

↓

自动修正

↓

字幕/语音输出

整体延迟控制在可接受范围。

---

# 5. 核心功能

## 实时语音识别（ASR）

输入：

* 麦克风
* 系统音频
* 视频流

输出：

增量文本。

实现采用双后端：

* Chrome / Edge：浏览器 Web Speech API（零延迟，首选）
* Safari / Firefox：服务端百炼 `paraformer-realtime-v2`，浏览器以 16kHz PCM 经 WebSocket 流式上送

两后端产出统一的 interim / final，下游翻译与纠错管线完全复用。

---

## 实时翻译

支持：

* English → 中文
* Japanese → 中文
* Korean → 中文

架构支持扩展更多语言。

---

## 增量字幕

边说边翻译。

无需等待完整句子。

---

## 自动纠错

ASR修正：

```text
Storage
↓
Distributed Storage
```

自动同步更新字幕。

---

翻译修正：

```text
缓存
↓
分布式缓存
```

自动替换。

---

## 中文字幕

支持：

实时滚动字幕

---

## 中文语音播报

支持：

TTS播报。

---

## 历史记录

保存：

原文

译文

时间轴

---

# 6. 创新点

## 字幕回滚机制

传统方案：

字幕错误后无法修正。

---

本系统：

支持：

Revision Window

例如：

最近5秒字幕允许回滚更新。

---

效果：

减少ASR误识别影响。

---

## 术语记忆

例如：

```text
Kafka
Redis
Kubernetes
Hermes
```

建立术语表。

避免反复翻译错误。

---

## 演讲模式

偏向：

完整表达

---

## 会议模式

偏向：

低延迟

---

用户可切换策略。

---

# 7. 技术架构

```text
Audio Source

      |

      v

Streaming ASR

      |

      v

Incremental Buffer

      |

      v

Translation Engine

      |

      +------------+

      |            |

      v            v

Subtitle      TTS

      |

      v

Web UI
```

---

# 8. AI架构

统一通过 Hermes。

封装：

AIService

---

能力：

ASR

Translate

Summarize

TTS

---

# 9. 核心链路

## Step1

接收音频流

---

## Step2

ASR增量识别

例如：

```text
We are building

We are building a

We are building a distributed
```

---

## Step3

翻译引擎

增量翻译。

---

## Step4

字幕更新

支持回滚。

---

## Step5

TTS播报

可选开启。

---

# 10. 自动纠错设计

这是核心功能。

---

ASR通常：

```text
Storage
```

后续变成：

```text
Distributed Storage
```

---

系统维护：

Revision Window

默认：

5秒

---

如果上游结果更新：

同步修改字幕。

---

用户看到：

```text
[修正]
存储
↓
分布式存储
```

---

# 11. 术语系统

维护：

Glossary

---

例如：

```text
Kubernetes
```

固定翻译：

```text
Kubernetes
```

而非：

```text
库伯内特斯
```

---

支持：

用户导入术语表。

---

# 12. QoS设计

重点。

---

## End-to-End Latency

定义：

音频输入

↓

字幕出现

目标：

<2秒

---

## P95 Latency

目标：

<3秒

---

## ASR实时率

Real-Time Factor

目标：

<1

---

## 翻译成功率

目标：

> 95%

---

## 修正率

统计：

被回滚修正字幕比例。

---

# 13. Dashboard

地址：

/dashboard

---

展示：

实时延迟

P95

P99

ASR耗时

翻译耗时

TTS耗时

---

统计：

累计翻译时长

翻译字数

术语命中率

修正次数

---

# 14. Evaluation Framework

避免伪指标。

---

## 字幕延迟

测量：

字幕出现时间

*

音频时间

---

## Correction Rate

测量：

字幕修正比例

---

## User Catch-up Rate

用户是否跟得上演讲。

通过用户反馈统计。

---

## Glossary Hit Rate

术语正确命中率。

---

## Session Success Rate

完整会话比例。

---

# 15. A/B Test

## 翻译策略

A：

完整句翻译

B：

增量翻译

比较：

用户满意度

延迟

---

## Revision Window

3秒

VS

5秒

VS

8秒

---

评估：

阅读体验

修正次数

---

# 16. 埋点设计

track(event)

---

audio_start

audio_stop

---

subtitle_render

subtitle_corrected

---

translation_success

translation_error

---

tts_start

tts_finish

---

dashboard_open

---

# 17. 数据模型

Session

Transcript

Translation

Glossary

Metrics

EventLog

---

# 18. 项目结构

echo_translate/

app.py

config.py

db.py

ai_service.py

asr_engine.py

translation_engine.py

revision_engine.py

tts_engine.py

metrics.py

dashboard.py

templates/

static/

tests/

README.md

design.md

---

# 19. 测试设计

pytest

pytest-cov

---

覆盖：

ASR Engine

Translation Engine

Revision Engine

Dashboard

Store

AIService

---

目标：

代码覆盖率 >85%

---

# 20. Demo设计

演示：

技术演讲视频

↓

实时字幕

↓

自动修正

↓

TTS播报

↓

Dashboard

---

时长：

5分钟

---

# 21. 商业化思考

个人版：

会议翻译

课程翻译

---

专业版：

企业会议

国际会议

线上直播

---

API版：

提供实时翻译能力。

---

# 22. 安全设计

禁止提交：

API_KEY

AccessToken

Cookie

Hermes认证信息

---

统一放入：

.env

config.json

---

# 23. Git协作原则

遵循自然迭代。

每个PR对应：

一个可独立Review功能。

例如：

PR1：

实时ASR

---

PR2：

翻译引擎

---

PR3：

字幕修正

---

PR4：

TTS

---

PR5：

Dashboard

---

避免：

一次性提交全部代码。

---

# 24. AI辅助开发声明

允许使用AI辅助开发。

必须保证：

代码可运行

测试通过

README与实现一致

---

# 25. Definition Of Done

满足：

* 实时ASR完成
* 实时翻译完成
* 自动纠错完成
* 字幕回滚完成
* TTS完成
* Dashboard完成
* QoS指标可展示
* 单元测试覆盖率 >85%
* README完整
* Demo完整
* design.md完整

项目方可标记完成。


