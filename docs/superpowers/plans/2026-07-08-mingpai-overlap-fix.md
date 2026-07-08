# 解决明牌时出牌遮挡 实施计划 (Implementation Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 解决斗地主游戏对局中，机器人/玩家明牌时，其手牌展示区域与出牌区域垂直/水平重叠发生遮挡的问题。

**Architecture:** 修改前端 Vue 页面中出牌区域容器的 CSS 定位。对左侧和右侧的出牌区 `.play-seat-zone.left` 和 `.play-seat-zone.right` 进行对称的水平向内偏移（`left/right: 130px`）和垂直向上提（`top: -20px`），并提升 `z-index: 20`。

**Tech Stack:** Vue 3, CSS (Scoped CSS in Vue Component).

## Global Constraints

- 所有修改只针对 `frontend/src/views/GameRoomView.vue`。
- 修改前后确保其他界面布局元素不受影响。

---

### Task 1: 修改前端出牌区域 CSS 样式

**Files:**
- Modify: `frontend/src/views/GameRoomView.vue`

**Interfaces:**
- Consumes: 无
- Produces: 调整后的左右侧玩家出牌区定位，解决挡牌问题。

- [ ] **Step 1: 定位出牌区 CSS 位置**
  打开并查看 `frontend/src/views/GameRoomView.vue` 文件的 1690-1702 行。
  原代码如下：
  ```css
  .play-seat-zone.left {
    left: 20px;
    top: 15%;
    justify-content: flex-start;
  }

  .play-seat-zone.right {
    right: 20px;
    top: 15%;
    justify-content: flex-end;
  }
  ```

- [ ] **Step 2: 头像缩小、明牌上移与出牌自折行**
  将上述样式替换为：
  在 `PlayerSeat.vue` 中对头像尺寸进行微缩，并对明牌负边距及定位进行调整；同时对 `.played-cards-row` 启用条件换行限制：
  ```css
  .avatar-block {
    width: 80px;
    padding: 10px 4px;
    gap: 6px;
  }
  .avatar-icon-circle {
    width: 42px;
    height: 42px;
  }
  .seat-name {
    font-size: 0.82rem;
    max-width: 72px;
  }
  .player-seat.left .shown-cards-row {
    position: absolute;
    top: -145px;
    left: 0;
  }
  .player-seat.right .shown-cards-row {
    position: absolute;
    top: -145px;
    right: 0;
  }
  .played-cards-row {
    display: flex;
    gap: 3px;
  }
  .played-cards-row.wrap-cards {
    flex-wrap: wrap;
    max-width: 252px;
  }
  .player-seat.right .played-cards-row {
    justify-content: flex-end;
  }
  ```

- [ ] **Step 3: 启动前端开发服务器进行验证**
  在 `frontend` 目录下运行本地开发命令：
  ```bash
  npm run dev
  ```
  在浏览器中打开游戏房间（可通过 `mock=true` 路由进入 mock 测试），观察右侧 AI 玩家出牌以及明牌时卡牌层级及位置。
  确认打出的牌显示在明牌的左上方（右侧玩家）或右上方（左侧玩家），两者在垂直与水平位置上完全错开，无相互遮挡发生。
