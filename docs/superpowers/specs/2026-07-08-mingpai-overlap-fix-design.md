# 解决明牌时出牌遮挡的设计规格说明书 (Design Spec)

本文档记录如何解决斗地主游戏对局中，机器人或玩家选择“明牌”后，其明牌手牌与打出的牌（出牌区）重叠或遮挡的视觉布局问题。

## 1. 问题背景

在当前的版本中，当右侧（或左侧）机器人/玩家选择“明牌”后，其手牌列表会以明牌状态并排展开展示。
* 右侧玩家的手牌从右向左展开，左侧玩家的手牌从左向右展开。
* 同时，左右两侧玩家的出牌区（即打出的一组牌展示区）也定位于各自头像的内侧。
* 由于明牌手牌的横向展开宽度较长（多张牌时可达 `300px` 以上），且出牌区垂直高度与手牌高度基本一致（重合在 `top: 30%` ~ `35%` 区域），导致当明牌玩家打出卡牌时，打出的牌会与明牌手牌堆严重重合遮挡，导致玩家无法辨清打出的牌或明牌内容。

## 2. 腾讯斗地主方案参考

腾讯斗地主通过以下方式解决此类冲突：
1. **水平内移**：打出的牌（出牌区）比手牌区更加靠近屏幕中心，腾出外侧的空间给手牌/明牌显示。
2. **垂直错位**：出牌区整体比手牌/明牌区偏上（通常处于头像的左上或右上角），手牌区在下方展示。
3. **层级保障**：出牌区拥有更高的 `z-index`。

## 3. 具体设计与修改方案

我们将对前端房间主页面 `frontend/src/views/GameRoomView.vue` 内的出牌区定位样式进行如下修改：

### 3.1 `play-seat-zone.right` (右侧玩家出牌区样式)
* **原样式**：
  ```css
  .play-seat-zone.right {
    right: 20px;
    top: 15%;
    justify-content: flex-end;
  }
  ```
* **重构优化为如下三层联合方案**：

#### 3.1.1 头像层 (缩小 20%)
将左右两侧 AI 头像面板的宽度与内边距缩减，圆形头像从 `50px` 缩至 `42px`：
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
```

#### 3.1.2 明牌层 (悬浮置顶 + 可读间距)
将明牌手牌容器定位到头像上方 `145px` 的无遮挡空档区，且将扑克牌重叠负左边距设为 `-34px`，确保数值花色清晰可见：
```css
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
```

#### 3.1.3 出牌层 (双行折行 + 宽度限制)
保留父级容器 `.play-seat-zone` 样式在原本的 `left/right: 20px; top: 15%;` 处（使加倍等动作提示文字不偏位），同时在 `.played-cards-row` 上限制最大宽度为 `252px`（最多并排 4 张牌）并支持 `flex-wrap: wrap` 折行展示：
```css
.played-cards-row {
  display: flex;
  flex-wrap: wrap;
  max-width: 252px;
  gap: 3px;
}
/* 右侧玩家折行出牌靠右对齐 */
.player-seat.right .played-cards-row {
  justify-content: flex-end;
}
```

---

## 4. 验证方案

### 4.1 手动验证
1. 运行前端与后端，进入斗地主对局大厅，开启匹配或与 AI 机器人对局。
2. 触发明牌事件（例如地主确认明牌，或者玩家自己明牌）。
3. 检查明牌展示时手牌是否完整显示。
4. 观察该明牌玩家出牌时，打出的牌（出牌）是否规整地显示在明牌的上方 and 内侧，且无任何重叠遮挡。
