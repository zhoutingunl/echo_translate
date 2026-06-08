# EchoTranslate · AI 同声传译助手

实时把单向英语/日语/韩语音频流翻译成中文，以**滚动字幕**和**中文语音**呈现，并能**自动纠正**之前识别或翻译的错误。

> 详细产品设计见 [`design.md`](./design.md)。本 README 会随功能迭代逐步补全。

## 快速开始

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # 填入 MINIMAX_API_KEY
python app.py               # 打开 http://127.0.0.1:8000
```

更完整的运行说明、架构图与演示脚本将在后续提交补全。
