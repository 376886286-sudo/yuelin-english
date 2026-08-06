# 悦琳英语口语陪练 · 网页版

给女儿(悦琳)做的 AI 英语口语陪练网站。爸爸上传教案 → AI 按教案带读 → 自动生成跟读记录。

**技术路线**:国际版 Azure(识别 / 合成 / 发音评估)+ DeepSeek(教案解析 / 教师对话 / 记录 / 规划)
**设计**:Apple 风格,双模式(学习 / 家长),详见 `英语口语陪练网站-设计规划.md`

## 运行

```bash
pip install -r requirements.txt
python server.py          # → http://localhost:8000
```

无任何 API Key 时全链路 mock 可跑:教案解析(规则引擎)、教师对话(按教案推进)、发音评估(随机评分)、TTS(浏览器朗读)。

### 接入真实服务

1. 复制 `.env.example` 为 `.env`,填入 Key(也可以在网页「家长模式 → 设置」里填):
   ```
   DEEPSEEK_API_KEY=sk-...
   AZURE_SPEECH_KEY=...
   AZURE_SPEECH_REGION=eastasia
   ```
2. 重启服务生效。

## 使用流程

| 谁 | 做什么 |
|---|---|
| 爸爸 | 家长模式 → 教案库 → 上传 TXT/MD/DOCX/DOC/PDF/图片 → 确认入库 |
| 悦琳 | 学习模式 → 选课程 → 按 AI 提示开口说(按住说话)→ 逐词发音反馈 → 环节评级 A/B/C/D |
| 爸爸 | 家长模式 → 会话记录 → 查看评级 / 易错点 / 第 1·3·7 天复习计划 |

## 目录结构

```
server.py            # FastAPI 主程序(全部 API)
app/parser.py        # 教案解析(TXT / MD / DOCX / DOC / PDF / 图片)
app/llm.py           # DeepSeek(有 Key 走真实,无 Key mock)
app/azure_speech.py  # Azure 语音(识别/评估/合成,无 Key mock)
app/storage.py       # 本地 JSON 存储(课程/会话/设置/用量)
static/              # 前端(单页应用,hash 路由)
data/                # 运行时数据(courses / sessions / uploads)
config.json          # 学员信息 / 家长 PIN(默认 1234)
```

## 家长 PIN

默认 `1234`,改 `config.json` 的 `pin` 或 `.env` 的 `PARENT_PIN`。

## 当前状态

- [x] P0:双模式框架 / 教案上传解析(TXT+DOCX+图片)/ 课程库 / 学习会话(mock 链路)
- [ ] P1:Azure 真实 Key 接入(ASR / TTS / 发音评估逐词)
- [ ] P2:DeepSeek 真实记录 / 与 AI 调整教案 / 复习计划详情
- [ ] P3:局域网部署 / 用量核对 / README 完善 / Unit01·02 实测
