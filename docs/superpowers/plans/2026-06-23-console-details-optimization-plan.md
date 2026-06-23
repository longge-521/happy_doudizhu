# 控制台细节精致化重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现请求参数悬浮气泡预览（Tooltip），优化表格隔行变色和悬停高亮，并将分页文字替换为 Lucide 方向图标按钮。

**Architecture:** 改造 console.js 渲染审计日志的 `<td>` 以注入 `data-tooltip`，使用纯 CSS attr() 读取属性实现高悬浮 Tooltip 气泡；在 index.html 引入 Lucide 分页图标并在 styles.css 中微调样式。

**Tech Stack:** Vanilla CSS, JavaScript, HTML5, Lucide-Icons

## Global Constraints
- 保证 Tooltip 气泡在极长 JSON 数据下不会撑破屏幕（设定 maxWidth 并自动折行）。
- 分页逻辑与页数跳转方法必须完全保持一致。

---

### Task 1: 气泡 Tooltip 样式与 JS 渲染改造

**Files:**
- Modify: `static/css/styles.css`
- Modify: `static/js/console.js`

- [ ] **Step 1: 编写 Tooltip 与表格行 Hover CSS 样式**

在 `static/css/styles.css` 末尾追加如下气泡和表格美化样式：
```css
/* Tooltip 容器 */
.tooltip-trigger {
    position: relative;
    cursor: help;
}

/* Tooltip 气泡样式 */
.tooltip-trigger::after {
    content: attr(data-tooltip);
    position: absolute;
    bottom: 125%;
    left: 50%;
    transform: translateX(-50%) scale(0.9);
    background: rgba(17, 24, 39, 0.95);
    border: 1px solid var(--card-border);
    color: #34d399; /* 翡翠绿代码色 */
    padding: 10px 14px;
    border-radius: 10px;
    font-size: 11px;
    font-family: monospace;
    white-space: pre-wrap;
    word-break: break-all;
    width: max-content;
    max-width: 320px;
    box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5);
    opacity: 0;
    pointer-events: none;
    transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
    z-index: 999;
}

.tooltip-trigger:hover::after {
    opacity: 1;
    transform: translateX(-50%) scale(1);
}

/* 隔行变色 */
tbody tr:nth-child(even) {
    background: rgba(255, 255, 255, 0.015);
}

/* 悬停高亮过渡 */
tbody tr {
    transition: background-color 0.2s ease;
}
tbody tr:hover {
    background: rgba(255, 255, 255, 0.035) !important;
}
```

- [ ] **Step 2: 改造 console.js 的渲染函数以绑定 data-tooltip 属性**

我们需要找到 `static/js/console.js` 中渲染 `auditLogListBody` 行的逻辑，提取出对 `request_params` 的处理。
（注意：这需要在下一步骤前先用 `view_file` 或 `grep_search` 确认 `console.js` 中渲染请求参数的具体行数与结构，此处暂假定修改其 `request_params` 单元格的渲染）。

- [ ] **Step 3: 提交气泡和表格样式修改**

```bash
git add static/css/styles.css static/js/console.js
git commit -m "style: implement css tooltips for params and table zebra rows"
```

---

### Task 2: 分页器图标化与静态资源刷新

**Files:**
- Modify: `templates/index.html`

- [ ] **Step 1: 将 index.html 中的分页纯文字按钮改造为 Lucide 图标**

在 `templates/index.html` 对应位置：
将上一页和下一页的按钮改为：
```html
<button id="auditPrevPageBtn" onclick="changeAuditPage(-1)" class="btn-secondary" style="padding: 8px 14px; border-radius: 8px;" disabled>
    <i data-lucide="chevron-left" style="width: 16px; height: 16px;"></i>
</button>
<button id="auditNextPageBtn" onclick="changeAuditPage(1)" class="btn-secondary" style="padding: 8px 14px; border-radius: 8px;" disabled>
    <i data-lucide="chevron-right" style="width: 16px; height: 16px;"></i>
</button>
```

- [ ] **Step 2: 在 styles.css 中定义按钮 disabled 的透明度与静止状态**

```css
button:disabled {
    opacity: 0.35;
    cursor: not-allowed;
    pointer-events: none;
    transform: none !important;
    box-shadow: none !important;
}
```

- [ ] **Step 3: 递增 Cache Buster 版本号参数**

将 `templates/index.html` 中 `console.js` 和 `styles.css` 加载链接的版本号后缀变更为 `?v=202606230245`。

- [ ] **Step 4: 运行所有测试并提交**

```bash
git add templates/index.html static/css/styles.css
git commit -m "style: transform pagination buttons to lucide icons and refresh cache versions"
```
