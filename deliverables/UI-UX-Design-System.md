# 悦琳英语口语陪练 · UI/UX 设计规范

> 版本: 1.0 · 2026-08-07
> 设计师: UI Designer
> 适用平台: 网页版 (桌面/平板)

---

## 1. 设计原则

### 1.1 核心设计哲学

| 原则 | 定义 | 落地方式 |
|------|------|----------|
| **简洁** | 主任务无摩擦，信息层级一眼可读 | 移除冗余装饰，每个元素都有存在理由 |
| **克制** | 颜色只用于交互和状态，不做装饰 | 主色仅用于按钮/链接/选中态；状态色仅用于发音反馈 |
| **层级** | 通过顺序、间距、字重、对比建立清晰度 | 字号分档、颜色深浅、留白差异 |
| **友好** | 儿童产品要温暖、鼓励、低压力 | 圆角柔和、动画流畅、反馈积极 |

### 1.2 双模式设计区分

| 维度 | 学习模式 (孩子) | 家长模式 (爸爸) |
|------|-----------------|-----------------|
| 进入方式 | 大按钮一键直达 | 小入口 + PIN 验证 |
| 语言 | 练习英文 + 操作中文 | 全中文 |
| 信息形态 | 图形化：大图标、气泡、逐词着色 | 数据化：列表、图表、摘要 |
| 主操作 | 每屏一个：大说话按钮 | 每屏一个：上传/查看/配置 |
| 字号 | **整体放大一档** (18px 基准) | 标准 (16px 基准) |
| 视觉 | 明亮、友好、渐变点缀 | 克制、专业、信息密度高 |

---

## 2. 色彩系统

### 2.1 主色系 (品牌蓝)

```css
--accent: #3D9BFF;        /* 主色：按钮、链接、选中态 */
--accent-2: #9B5CFF;      /* 渐变副色 */
--accent-press: #2E86F0;  /* 按下态 */
--accent-bg: #EAF3FF;     /* 浅色背景 */
--accent-grad: linear-gradient(135deg, #3DB9FF 0%, #8A5CFF 100%);  /* 渐变背景 */
```

### 2.2 状态色 (仅用于发音反馈与评级)

| 状态 | 变量 | 用途 | 色值 |
|------|------|------|------|
| 优秀 | `--good` | 发音正确、A 级 | `#2FA84F` |
| 良好 | `--fair` | 发音一般、B 级 | `#E8890C` |
| 需改进 | `--weak` | 发音错误、C/D 级 | `#E5484D` |

对应背景色：
```css
--good-bg: #E9F7EE;
--fair-bg: #FDF1E0;
--weak-bg: #FDECEA;
```

### 2.3 中性色 (大面积背景与文字)

```css
/* 背景 */
--bg: #F6F7FB;          /* 页面主背景 */
--surface: #FFFFFF;       /* 卡片/浮层 */
--surface-2: #F1F2F6;    /* 悬停态 */
--surface-3: #E8EAEF;    /* 禁用态 */

/* 文字三档 */
--text: #1C1C1E;         /* 主文字 */
--text-2: #6B6B70;       /* 次级文字 */
--text-3: #A8A8AD;       /* 提示/占位 */

/* 边框 */
--border: rgba(0, 0, 0, 0.07);
--border-strong: rgba(0, 0, 0, 0.14);
```

### 2.4 色彩使用规则

1. **检查法**: 去掉全部颜色后界面仍能读懂结构 = 颜色用对了
2. **禁用场景**: 禁止用主色/状态色做背景装饰、大面积色块
3. **对比度**: 文字与背景 WCAG AA (4.5:1)，大文字 3:1

---

## 3. 排版系统

### 3.1 字号阶梯

| 用途 | 变量 | 学习模式 | 家长模式 | 字重 |
|------|------|----------|----------|------|
| 启动页 Hero | `f-display` | 44px | 44px | 700 |
| 大屏 Hero | `f-display-l` | 56px | 56px | 700 |
| 页面标题 | `f-title` | 34px | 34px | 700 |
| 章节标题 | `f-section` | 26px | 26px | 700 |
| 卡片标题 | `f-card` | 20px | 20px | 600 |
| 正文 | `f-body` | 18px | 17px | 400 |
| AI 对话气泡 | `f-bubble` | 22px | 22px | 400 |
| 学生对话气泡 | `f-bubble-student` | 18px | 18px | 400 |
| 说明文字 | `f-caption` | 13px | 13px | 400 |
| 极小提示 | `f-mini` | 11px | 11px | 400 |

### 3.2 字体栈

```css
font-family: -apple-system, BlinkMacSystemFont,
  "SF Pro Display", "SF Pro Text",
  "PingFang SC", "Microsoft YaHei", sans-serif;
```

**优先级**: 系统原生字体 → Apple SF → 苹方 → 微软雅黑

### 3.3 字重规范

- **标题**: 600-700 (加粗)
- **正文**: 400 (常规)
- **禁止**: 避免 300/500 中间值，层级靠字号区分

---

## 4. 间距系统 (8pt 网格)

### 4.1 基础间距

```css
--s-1: 8px;   /* 紧凑元素 */
--s-2: 16px;  /* 组件内间距 */
--s-3: 24px;  /* 区块间距 */
--s-4: 32px;  /* 区块间距 */
--s-5: 48px;  /* 大区块 */
```

### 4.2 页面布局间距

| 场景 | 水平 padding | 垂直 padding |
|------|--------------|--------------|
| 页面边缘 | 24px (平板) / 32px (桌面) | — |
| 导航栏 | 16px | 56px 高 |
| 卡片内边距 | 16px-24px | — |
| 列表行 | 16px | 44-48px 行高 |
| 底部操作栏 | — | 100px 高 |

---

## 5. 组件规范

### 5.1 按钮

#### 主按钮 (Primary)

```css
.btn-primary {
  background: var(--accent-grad);
  color: #fff;
  box-shadow: var(--shadow-accent);  /* 0 8px 24px rgba(79,124,255,0.32) */
  border: none;
  border-radius: 980px;  /* 药丸形 */
  font-size: 17px;
  font-weight: 600;
  padding: 12px 28px;
  min-height: 44px;
  cursor: pointer;
  transition: all 0.15s var(--ease);
}
.btn-primary:hover {
  filter: brightness(1.05);
  box-shadow: var(--shadow-lg);
}
.btn-primary:active {
  transform: scale(0.96);
}
.btn-primary:disabled {
  opacity: 0.4;
  cursor: not-allowed;
  box-shadow: none;
}
```

#### 次按钮 (Secondary)

```css
.btn-secondary {
  background: var(--surface);
  color: var(--accent);
  border: 0.5px solid var(--border-strong);
  box-shadow: var(--shadow-sm);
  border-radius: 980px;
  font-size: 17px;
  font-weight: 600;
  padding: 12px 28px;
  min-height: 44px;
}
.btn-secondary:hover {
  background: var(--accent-bg);
  border-color: var(--accent);
}
```

#### 幽灵按钮 (Ghost)

```css
.btn-ghost {
  background: transparent;
  color: var(--accent);
  border: none;
  border-radius: 980px;
  font-size: 15px;
  font-weight: 500;
  padding: 8px 12px;
}
.btn-ghost:hover {
  background: var(--accent-bg);
}
```

#### 按钮尺寸

| 尺寸 | 高度 | 字号 | 用途 |
|------|------|------|------|
| SM | 36px | 15px | 次要操作 |
| MD (默认) | 44px | 17px | 标准按钮 |
| LG | 52px | 17px | 重要操作 |
| **XL (主操作)** | 60px | 18px | 学习模式主说话按钮 |

### 5.2 卡片

#### 课程卡片

```css
.course-card {
  background: var(--surface);
  border: 0.5px solid var(--border);
  border-radius: var(--radius-lg);  /* 18px */
  box-shadow: var(--shadow-sm);
  padding: var(--s-3);  /* 24px */
  cursor: pointer;
  transition: transform 0.18s var(--ease), box-shadow 0.18s var(--ease);
}
.course-card:hover {
  transform: translateY(-3px);
  box-shadow: var(--shadow-md);
}
.course-card:active {
  transform: translateY(-1px) scale(0.99);
}
.course-card.selected {
  border-color: var(--accent);
  background: var(--accent-bg);
  box-shadow: 0 0 0 3px rgba(61,155,255,0.25), var(--shadow-md);
}
```

#### 圆角规范

```css
--radius-md: 12px;   /* 输入框、小卡片 */
--radius-lg: 18px;   /* 卡片、浮层 */
--radius-xl: 24px;   /* 大面积容器 */
--radius-pill: 980px; /* 按钮、胶囊 */
```

### 5.3 列表

```css
.list {
  background: var(--surface);
  border-radius: var(--radius-lg);
  border: 0.5px solid var(--border);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
}
.row {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  padding: 14px var(--s-3);
  cursor: pointer;
  transition: background 0.12s;
  border-bottom: 0.5px solid var(--border);
}
.row:last-child { border-bottom: none; }
.row:hover { background: var(--surface-2); }
```

### 5.4 对话气泡

```css
.msg { display: flex; gap: 10px; max-width: 580px; }
.msg.ai { align-self: flex-start; }
.msg.student { align-self: flex-end; flex-direction: row-reverse; }

.bubble {
  background: var(--surface);
  border: 0.5px solid var(--border);
  border-radius: 20px;
  padding: 12px 16px;
  font-size: 18px;
  line-height: 1.55;
  box-shadow: var(--shadow-sm);
}
.msg.student .bubble {
  background: var(--accent-grad);
  color: #fff;
  border: none;
  border-top-right-radius: 8px;
  box-shadow: var(--shadow-accent);
}
.msg.ai .bubble { border-top-left-radius: 8px; }
```

### 5.5 输入框

```css
input[type="text"],
input[type="password"],
select,
textarea {
  width: 100%;
  padding: 12px 14px;
  border: 0.5px solid var(--border-strong);
  border-radius: var(--radius-md);
  font-size: 16px;
  font-family: inherit;
  background: var(--surface);
  color: var(--text);
  outline: none;
  transition: border-color 0.15s, box-shadow 0.15s;
}
input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 4px rgba(79,124,255,0.15);
}
```

### 5.6 徽章/评级

```css
.badge {
  display: inline-block;
  min-width: 26px;
  text-align: center;
  padding: 2px 8px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 700;
}
.badge.A { background: var(--good-bg); color: var(--good); }
.badge.B { background: var(--accent-bg); color: var(--accent); }
.badge.C { background: var(--fair-bg); color: var(--fair); }
.badge.D { background: var(--weak-bg); color: var(--weak); }
```

---

## 6. 阴影系统

```css
--shadow-sm: 0 1px 2px rgba(0,0,0,0.04), 0 2px 8px rgba(0,0,0,0.04);
--shadow-md: 0 4px 12px rgba(0,0,0,0.06), 0 12px 32px rgba(0,0,0,0.06);
--shadow-lg: 0 8px 24px rgba(0,0,0,0.10), 0 24px 56px rgba(0,0,0,0.10);
--shadow-accent: 0 8px 24px rgba(79,124,255,0.32);
```

**使用原则**:
- 卡片悬停: `shadow-sm` → `shadow-md`
- 主按钮/图标: 始终带 accent 阴影
- 毛玻璃元素: 极轻阴影或无阴影

---

## 7. 动效系统

### 7.1 缓动函数

```css
--ease: cubic-bezier(0.32, 0.72, 0, 1);        /* 弹性进入 */
--ease-out: cubic-bezier(0.16, 1, 0.3, 1);     /* 柔和退出 */
```

### 7.2 时长规范

| 场景 | 变量 | 时长 |
|------|------|------|
| 快速反馈 | `anim-fast` | 0.12s |
| 标准交互 | `anim-med` | 0.2s |
| 页面切换 | `anim-slow` | 0.4s |

### 7.3 关键动效

#### 页面进入
```css
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: none; }
}
.view { animation: fadeIn 0.3s var(--ease); }
```

#### 启动页 Logo 浮动
```css
@keyframes float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-8px); }
}
.logo { animation: float 3s ease-in-out infinite; }
```

#### 录音脉冲
```css
@keyframes ringPulse {
  0% { transform: scale(1); opacity: 0.5; }
  100% { transform: scale(2); opacity: 0; }
}
.stage-pulse { animation: ringPulse 1.4s ease-out infinite; }
```

#### 按钮按压
```css
.btn:active { transform: scale(0.96); }
.big-mic-btn:active { transform: scale(0.94); }
```

### 7.4 动效禁用 (无障碍)

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
  .logo { animation: none; }
}
```

---

## 8. 响应式规则

### 8.1 断点定义

| 断点 | 宽度 | 设备 |
|------|------|------|
| Mobile | < 640px | 手机竖屏 |
| Tablet | 640px - 1023px | iPad 竖屏 / 小平板 |
| **Base (基准)** | 1024px - 1366px | iPad 横屏 / 笔记本 |
| Desktop | ≥ 1367px | 大屏桌面 |

### 8.2 平板适配 (max-width: 1024px)

```css
@media (max-width: 1024px) {
  .nav { height: 52px; }
  .content { padding-bottom: calc(120px + var(--safe-bottom)); }
  .cta-bar { height: 88px; padding-bottom: var(--safe-bottom); }
  .launch .hero h1 { font-size: 36px; }
  .course-grid { grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); }
  .metric-grid { grid-template-columns: repeat(3, 1fr); }
}
```

### 8.3 小平板/竖屏 (max-width: 820px)

```css
@media (max-width: 820px) {
  .launch .hero h1 { font-size: 30px; }
  .nav .title { font-size: 15px; }
  .metric-grid { grid-template-columns: 1fr 1fr; }
  .course-grid { grid-template-columns: repeat(2, 1fr); }
}
```

### 8.4 大屏桌面 (min-width: 1367px)

```css
@media (min-width: 1367px) {
  .launch .hero h1 { font-size: 56px; }
  .content { max-width: 1200px; margin: 0 auto; }
  .metric-grid { grid-template-columns: repeat(4, 1fr); }
}
```

### 8.5 安全区适配

```css
--safe-top: env(safe-area-inset-top, 0px);
--safe-bottom: env(safe-area-inset-bottom, 0px);
```

---

## 9. 可访问性 (Accessibility)

### 9.1 焦点管理

```css
*:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);  /* 0 0 0 4px rgba(61,185,255,0.35) */
  border-radius: var(--radius-md);
}
```

### 9.2 触控目标

```css
--tap-min: 44px;   /* iOS HIG 最小 */
--tap-good: 56px;  /* 9岁孩子推荐 */
```

**规范**: 所有可点击元素最小 44px，重要按钮至少 56px

### 9.3 色彩对比

- 常规文字: 4.5:1 (WCAG AA)
- 大文字 (18px+ 粗体或 24px+): 3:1
- 组件边界: 3:1

---

## 10. 毛玻璃材质

仅用于需要强调"悬浮感"的组件：

```css
.glass {
  background: rgba(255, 255, 255, 0.78);
  backdrop-filter: saturate(180%) blur(20px);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
  border-bottom: 0.5px solid var(--border);
}
```

**应用场景**:
- 导航栏
- 底部操作条
- 浮动说话按钮容器

---

## 11. 页面布局规范

### 11.1 启动页

```
┌─────────────────────────────┐
│                             │
│         🗣️ (浮动动画)       │
│                             │
│      悦琳英语口语           │
│    开口就有反馈 · 每天进步  │
│                             │
│  ┌───────────────────────┐  │
│  │ 📖 开始练习            │  │
│  └───────────────────────┘  │
│                             │
│       [家长模式]            │
│                             │
└─────────────────────────────┘
```

- 居中对齐
- 背景: 浅灰 + 微妙渐变光晕
- 主按钮: 渐变背景 + 阴影
- 家长入口: 幽灵按钮

### 11.2 学习模式 · 课程选择

```
┌─────────────────────────────┐
│ ← 返回      选择课程         │
├─────────────────────────────┤
│                             │
│  ┌─────────┐ ┌─────────┐   │
│  │ 📖 Unit │ │ 📖 Unit │   │
│  │  01     │ │  02     │   │
│  │ 见面问候 │ │ 数字年龄 │   │
│  └─────────┘ └─────────┘   │
│                             │
│  ┌─────────┐                │
│  │ 📖 Unit │                │
│  │  03     │                │
│  │ 礼貌借用 │                │
│  └─────────┘                │
│                             │
├─────────────────────────────┤
│                             │
│      [ 开始练习 ] (XL 按钮)  │
│                             │
└─────────────────────────────┘
```

- 网格布局 (auto-fill, minmax 230px)
- 卡片悬停上浮
- 底部栏固定主操作

### 11.3 学习模式 · 会话页

```
┌─────────────────────────────┐
│ ← 返回    Unit 01  ●●○    │  ← 环节进度
├─────────────────────────────┤
│                             │
│  AI: Hello! I'm Baobao.    │
│  What's your name?         │
│                             │
│  悦琳: My name is Mike     │
│  🟢🟢🟢🟢🟡🟢              │  ← 逐词反馈
│                             │
│  AI: Great! Nice to meet   │
│  you. How do you feel?     │
│                             │
├─────────────────────────────┤
│                             │
│      🎤  按住说话           │  ← 毛玻璃底部
│                             │
└─────────────────────────────┘
```

### 11.4 家长模式 · 仪表盘

```
┌─────────────────────────────┐
│ 仪表盘    [学员: 悦琳]      │
├─────────────────────────────┤
│  本周学习                    │
│  ┌──────┐ ┌──────┐ ┌────┐ │
│  │ 45分钟│ │ 3次   │ │ 85分│ │
│  │ 练习时长│ │练习次数│ │平均分│ │
│  └──────┘ └──────┘ └────┘ │
│                             │
│  [课程库] [会话记录] [复习]  │ ← 胶囊导航
│                             │
│  最近练习                    │
│  ┌──────────────────────┐  │
│  │ Unit 01 · 08-06     │  │
│  │ MEET A · FEEL B     │  │
│  └──────────────────────┘  │
└─────────────────────────────┘
```

---

## 12. 组件状态清单

| 组件 | Default | Hover | Active | Disabled | Focus |
|------|---------|-------|--------|----------|-------|
| 主按钮 | 渐变 bg | brightness 1.05 | scale 0.96 | opacity 0.4 | focus-ring |
| 次按钮 | surface bg | accent-bg | scale 0.96 | opacity 0.4 | focus-ring |
| 卡片 | shadow-sm | translateY -3px + shadow-md | scale 0.99 | — | — |
| 输入框 | border-strong | — | accent border | surface-3 bg | accent shadow |
| 列表行 | surface bg | surface-2 bg | — | — | focus-ring |

---

## 13. 设计检查清单

### 13.1 上线前必检

- [ ] 去掉颜色后界面结构仍清晰
- [ ] 主操作每屏只有一个
- [ ] 所有触控目标 ≥ 44px
- [ ] 文字对比度 ≥ 4.5:1
- [ ] 动效可被 `prefers-reduced-motion` 禁用
- [ ] 焦点可见 (focus-ring)
- [ ] 学习模式字号 ≥ 家长模式
- [ ] 状态色仅用于发音反馈和评级

### 13.2 儿童产品特检

- [ ] 无复杂文字说明 (用图标/动画替代)
- [ ] 鼓励性反馈优先
- [ ] 错误不惩罚，提供重试机会
- [ ] 操作可逆 (取消/返回)
- [ ] 无广告/无内购入口

---

## 附录: 变量速查表

```css
/* 颜色 */
--accent, --accent-2, --accent-press, --accent-bg, --accent-grad
--good, --fair, --weak, --good-bg, --fair-bg, --weak-bg
--bg, --surface, --surface-2, --surface-3
--text, --text-2, --text-3, --border, --border-strong

/* 尺寸 */
--radius-md, --radius-lg, --radius-xl, --radius-pill
--btn-h-sm, --btn-h, --btn-h-lg, --btn-h-xl
--tap-min, --tap-good

/* 字号 */
--f-display, --f-display-l, --f-title, --f-section
--f-card, --f-body, --f-bubble, --f-bubble-student
--f-caption, --f-mini

/* 间距 */
--s-1, --s-2, --s-3, --s-4, --s-5

/* 阴影 */
--shadow-sm, --shadow-md, --shadow-lg, --shadow-accent

/* 动画 */
--ease, --ease-out, --anim-fast, --anim-med, --anim-slow

/* 其他 */
--focus-ring, --safe-top, --safe-bottom
```

---

**文档状态**: 准备开发
**后续**: 可导出为 Figma Tokens 或直接用于 CSS 开发
