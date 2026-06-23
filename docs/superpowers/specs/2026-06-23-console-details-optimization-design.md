# 控制台细节精致化优化设计规格说明书

为了提升“全屏控制台”的用户交互与视觉感受（WOW 效果），我们需要对审计日志页面的请求参数展示、表格行交互以及底部组件进行精雕细琢。

## 设计目标
1. 鼠标悬停在截断的请求参数单元格上时，通过纯 CSS 气泡（Tooltip）显示格式化的完整参数。
2. 为表格引入淡雅的隔行背景交替以及行 hover 平滑亮底反馈，增强视觉聚拢。
3. 引入 Lucide 方向小图标改造分页按钮，以更加国际化和简约的风格统一整站按钮视觉语言。

## 具体代码改动设计

### 1. CSS 气泡预览 (static/css/styles.css)
通过纯 CSS 伪元素 `::after` 在悬浮时投射 `attr(data-tooltip)`：
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
```

### 2. JS 模板更新以支撑 Tooltip 数据 (static/js/console.js)
在 [console.js](file:///d:/Project_2023/hmp_ws_service/static/js/console.js) 渲染审计日志 `<tr>` 行时：
- 对请求参数所在的 `<td>` 进行处理。
- 增加 `class="tooltip-trigger"`，如果参数超过 30 字符则截断显示并在 `data-tooltip` 中绑定完整的原始数据（若为空则不绑定）。

### 3. 表格行样式美化 (static/css/styles.css)
- 双数行添加细微背景色：`tbody tr:nth-child(even) { background: rgba(255, 255, 255, 0.015); }`。
- 添加 Hover 高亮过渡：
  ```css
  tbody tr {
      transition: background-color 0.2s ease;
  }
  tbody tr:hover {
      background: rgba(255, 255, 255, 0.035) !important;
  }
  ```

### 4. 按钮 Disabled 状态视觉优化 (static/css/styles.css)
```css
button:disabled {
    opacity: 0.35;
    cursor: not-allowed;
    pointer-events: none;
    transform: none !important;
    box-shadow: none !important;
}
```

### 5. 分页器 Lucide 图标改造 (templates/index.html)
将原本“上一页/下一页”纯文字替换为 Lucide 图标：
- 上一页：`<i data-lucide="chevron-left" style="width: 16px; height: 16px;"></i>`
- 下一页：`<i data-lucide="chevron-right" style="width: 16px; height: 16px;"></i>`
