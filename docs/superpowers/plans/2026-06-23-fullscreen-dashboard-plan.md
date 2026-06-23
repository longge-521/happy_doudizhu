# 全屏沉浸式控制台实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将控制台页面改造为全屏沉浸式平铺布局，消除大屏幕两侧留白与双重滚动条，实现局部溢出滚动与自适应弹性调试终端。

**Architecture:** 重构 styles.css 的 body 和 .dashboard 属性为 100vw/100vh，重构 sidebar 和 content-area 为独立溢出滚动，并将 terminal 调试组件高度设为弹性 flex。

**Tech Stack:** Vanilla CSS, HTML5, Lucide-Icons

## Global Constraints
- 绝不能修改现有组件的功能和 JS 交互。
- 确保在大屏下与超小屏下都保持合理的自适应能力。

---

### Task 1: 视口全屏化与局部溢出滚动

**Files:**
- Modify: `static/css/styles.css`

- [ ] **Step 1: 修改 body 和 .dashboard 以支持全屏**

修改 `static/css/styles.css:23-49` 处的 `body` 与 `.dashboard` 样式为：
```css
body {
    font-family: var(--font-family);
    background: var(--bg-gradient);
    color: var(--text-main);
    height: 100vh;
    width: 100vw;
    display: flex;
    justify-content: center;
    align-items: stretch;
    padding: 0;
    overflow: hidden;
}

.dashboard {
    width: 100%;
    height: 100%;
    display: grid;
    grid-template-columns: 260px 1fr;
    gap: 0;
    background: var(--card-bg);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border: none;
    border-radius: 0;
    padding: 0;
    box-shadow: none;
}
```

- [ ] **Step 2: 修改 sidebar 和 content-area 支持独立高度和滚动**

修改 `static/css/styles.css:50-57` 处的 `.sidebar`，以及 `static/css/styles.css:133-140` 处的 `.content-area`：
```css
/* 侧边栏 */
.sidebar {
    display: flex;
    flex-direction: column;
    gap: 32px;
    border-right: 1px solid var(--card-border);
    padding: 24px 20px 24px 24px;
    height: 100%;
}
```
并且：
```css
/* 主体内容区 */
.content-area {
    display: flex;
    flex-direction: column;
    gap: 20px;
    height: 100%;
    padding: 24px;
    overflow-y: auto;
}
```

- [ ] **Step 3: 自适应滚动条美化**

在 `static/css/styles.css` 中，为右侧内容区添加更美观的滚动条定义：
```css
.content-area::-webkit-scrollbar {
    width: 8px;
}
.content-area::-webkit-scrollbar-thumb {
    background: rgba(255, 255, 255, 0.08);
    border-radius: 4px;
}
.content-area::-webkit-scrollbar-thumb:hover {
    background: rgba(255, 255, 255, 0.15);
}
```

- [ ] **Step 4: 提交第一阶段布局修改**

```bash
git add static/css/styles.css
git commit -m "style: remove dashboard border and extend to full viewport size"
```

---

### Task 2: 页面弹性伸缩与子卡片布局优化

**Files:**
- Modify: `static/css/styles.css`

- [ ] **Step 1: 将调试面板和控制台面板设为 100% 高度以自适应拉伸**

在 `static/css/styles.css` 的 `.panel` 和 `.terminal` 样式处：
将：
```css
.panel {
    display: none;
    animation: fadeIn 0.3s ease-out forwards;
    flex-direction: column;
    gap: 20px;
}
```
修改为：
```css
.panel {
    display: none;
    animation: fadeIn 0.3s ease-out forwards;
    flex-direction: column;
    gap: 20px;
    height: 100%;
}
```
并且将：
```css
.terminal {
    background: rgba(5, 8, 16, 0.9);
    border: 1px solid var(--card-border);
    border-radius: 16px;
    height: 380px;
    overflow-y: auto;
    padding: 20px;
    font-family: 'Courier New', Courier, monospace;
    display: flex;
    flex-direction: column;
    gap: 10px;
}
```
修改为：
```css
.terminal {
    background: rgba(5, 8, 16, 0.9);
    border: 1px solid var(--card-border);
    border-radius: 16px;
    flex: 1;
    min-height: 400px;
    overflow-y: auto;
    padding: 20px;
    font-family: 'Courier New', Courier, monospace;
    display: flex;
    flex-direction: column;
    gap: 10px;
}
```

- [ ] **Step 2: 优化站内信面板与上传面板的布局适配**

在收件箱 `.msg-list` 的样式中：
```css
.msg-list {
    flex: 1;
    min-height: 350px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding-right: 6px;
}
```
确保在大屏下它能够纵向生长以填充空间。

- [ ] **Step 3: 提交自适应修改**

```bash
git add static/css/styles.css
git commit -m "style: optimize terminal and message list stretch and flexibility"
```

---

### Task 3: 缓存刷新版本号与界面校验

**Files:**
- Modify: `templates/index.html`

- [ ] **Step 1: 修改 index.html 加载 console.js 的 Cache Buster 版本号**

在 `templates/index.html:333` 左右：
将：
```html
    <script src="/static/js/console.js?v=202606230132" defer></script>
```
修改为：
```html
    <script src="/static/js/console.js?v=202606230240" defer></script>
```

- [ ] **Step 2: 在 index.html 中为样式表加上 Cache Buster 版本号**

在 `templates/index.html:12` 左右：
将：
```html
    <link rel="stylesheet" href="/static/css/styles.css">
```
修改为：
```html
    <link rel="stylesheet" href="/static/css/styles.css?v=202606230240">
```

- [ ] **Step 3: 验证修改并提交**

在浏览器中强制刷新缓存（Ctrl + F5），检查 WebSocket 调试、站内信、审计日志、上传文件大面板是否全部全屏展现，滚动条是否美观，大屏自适应正常。
执行提交：
```bash
git add templates/index.html
git commit -m "chore: bump static resource cache buster versions"
```
