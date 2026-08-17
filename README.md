# 悦琳英语口语陪练 · 网页版

给女儿(悦琳)做的 AI 英语口语陪练网站。爸爸上传教案 → AI 理解本轮是在回答、按角色提问、临时提问、求助还是跟读 → 按教案任务推进 → 自动生成练习记录。

**技术路线**:Azure Speech(双语 STT / 明确跟读评分 / TTS)+ DeepSeek V4 Flash(自然对话 / 意图理解 / 渐进纠错)
**设计**:Apple 风格,双模式(学习 / 家长),详见 `英语口语陪练网站-设计规划.md`

## 工程边界

本仓库只负责英语口语学习网站工程：后端、前端、语音与 AI 服务、
课程运行状态和学习记录。语文、数学、英语预习复习资料以及英语口语
教案的源文件都属于独立的“悦琳学习库”，不复制到本仓库维护。

两个工程只通过校验后的 `schema_version: "2.0"`、`*.lesson.json` 文件
交接。网站不导入学习库代码，也不读取学习库的绝对路径。完整规则见
[`docs/project-boundary.md`](docs/project-boundary.md)。

## 运行

```bash
pip install -r requirements.txt
python server.py          # → http://localhost:8000
```

无任何 API Key 时全链路 mock 可跑:教案解析(规则引擎)、教师对话(按任务推进)、跟读模拟评分、TTS(浏览器朗读)。

### 测试

```bash
python -m unittest discover -v
```

回归用例覆盖开放回答、自由聊天、连续插话、中英文提问、求助提示、明确跟读评分、A/B/C/D、历史顺序和服务降级。

### 接入真实服务

1. 复制 `.env.example` 为 `.env`,填入 Key(也可以在网页「家长模式 → 设置」里填):
   ```
   DEEPSEEK_API_KEY=sk-...
   DEEPSEEK_MODEL=deepseek-v4-flash
   AZURE_SPEECH_KEY=...
   AZURE_SPEECH_REGION=eastasia
   AZURE_TTS_VOICE_EN=en-US-AvaMultilingualNeural
   ```
2. 重启服务生效。

## 使用流程

| 谁 | 做什么 |
|---|---|
| 爸爸 | 家长模式 → 教案库 → 优先上传 lesson-v2 JSON（兼容 TXT/MD/DOCX/DOC/PDF/图片）→ 确认入库 |
| 悦琳 | 学习模式 → 选课程 → 自然回答/提问/求助 → 仅在明确跟读时获得简洁发音反馈 |
| 爸爸 | 家长模式 → 会话记录 → 查看评级 / 易错点 / 第 1·3·7 天复习计划 |

## 目录结构

```
server.py            # FastAPI 主程序(全部 API)
app/parser.py        # 教案解析(TXT / MD / DOCX / DOC / PDF / 图片)
app/lesson_contract.py # lesson-v2 JSON 校验 / 跨项目稳定契约
app/lesson_engine.py # 教案 activity / pending task / 确定性推进
app/turn_manager.py  # DeepSeek V4 Flash 结构化意图、自然回应与渐进纠错
app/turn_analyzer.py # 旧模块兼容入口
app/dialogue_manager.py # 插话恢复、历史、提示/示范与会话编排
app/scoring.py       # 任务 A/B/C/D(与发音分独立)
app/llm.py           # DeepSeek JSON Output / 总结
app/azure_speech.py  # 双语 ASR / scripted 跟读评估 / TTS
app/storage.py       # 本地 JSON 存储(课程/会话/设置/用量)
static/              # 前端(单页应用,hash 路由)
data/                # 运行时数据(courses / sessions / uploads)
config.json          # 学员信息 / 家长 PIN(默认 1234)
docs/                # 产品、架构、业务规则、教案契约和 Agent 上下文
AGENTS.md            # 跨 Agent 长期工作规则
```

## AI 原生项目上下文

长期规则见 `AGENTS.md`，核心项目摘要见 `docs/ai-context.md`。网站与教案库是两个独立项目，只通过 `schema_version: "2.0"` 的 lesson JSON 连接。新教案上传前可运行：

```bash
python scripts/validate_lessons.py <lesson文件或目录>
```

## 家长 PIN

默认 `1234`,改 `config.json` 的 `pin` 或 `.env` 的 `PARENT_PIN`。

## 当前状态

- [x] P0:双模式框架 / 教案上传解析(TXT+DOCX+图片)/ 课程库 / 学习会话
- [x] P1:Azure 双语 ASR + TTS;仅 repeat 音频做 scripted 发音评估
- [x] P2:DeepSeek V4 Flash Turn Manager / 插话恢复 / 渐进纠错 / 跟读记录
- [ ] P3:局域网部署 / README 完善 / Unit01·02 实测

## 其他电脑部署清单

1. `git clone` + `cd` 进入目录
2. 创建虚拟环境: `python -m venv venv && venv\Scripts\activate` (或 `source venv/bin/activate`)
3. 安装依赖: `pip install -r requirements.txt`
4. 复制 API Key: `cp .env.example .env`, 编辑填入 DeepSeek + Azure Key
5. (可选, Windows 专用) 解析 .doc 需要本机安装 Word 或 WPS, 否则只支持 .txt/.md/.docx/.pdf
6. 启动: `python server.py`
