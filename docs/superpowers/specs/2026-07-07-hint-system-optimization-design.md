# 出牌提示系统全面优化设计

## 背景

当前出牌提示功能完全在前端实现，核心入口为 `cardUtils.ts` 中的 `findSuggestedPlay()` 函数。该函数只返回一个推荐方案，不支持多方案循环切换。同时自由出牌时的提示范围有限（只涵盖单张、对子、三条、炸弹、火箭），缺少顺子、连对、飞机等组合型牌的提示。

### 现有问题

1. **单一提示**：`findSuggestedPlay()` 只返回第一个合法牌型，用户无法浏览其他出牌方案。
2. **自由出牌组合不全**：`findOpeningPlay()` 不提示顺子、连对、三带一、三带二、飞机等组合牌型。
3. **带牌策略粗糙**：三带一/三带二的副牌选择过于简单（取最小 rank 的牌），未考虑避免拆炸弹、保留对子等策略。
4. **缺少循环指示器**：用户无法知道当前提示是第几个/共几个。

## 变更目标

- 支持多方案循环提示，每次点击"提示"按钮切换下一个可行方案。
- 提示按钮上显示"提示 1/5"这样的索引指示器。
- 补全自由出牌时的所有牌型提示（顺子、连对、三带一、三带二、飞机带单、飞机带对）。
- 优化副牌选择策略，避免拆炸弹。

## 涉及文件

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `frontend/src/utils/cardUtils.ts` | 新增函数 | 新增 `findAllPlayableHints()` |
| `frontend/src/views/GameRoomView.vue` | 修改 | 循环提示状态管理 + 按钮文案 + 索引指示器 |

## 详细设计

### 1. `cardUtils.ts` — 新增 `findAllPlayableHints()`

#### 函数签名

```typescript
export function findAllPlayableHints(
  hand: number[],
  lastCards: number[]
): number[][]
```

返回值：按推荐优先级排序的多组可出牌方案。每组是一个 `number[]`（牌 ID 数组）。

#### 自由出牌模式（lastCards 为空）

按以下优先级依次枚举所有可出组合，同类型内从小到大：

1. **单张**：手中每个不同 rank 出一张最小的牌
2. **对子**：手中每个 ≥2 张的 rank 出一对
3. **顺子**：枚举所有长度 ≥5、rank ≤ A（即 rank < 12）的连续单张序列
4. **连对**：枚举所有长度 ≥3 对、rank ≤ A 的连续对子序列
5. **三条**：手中每个 ≥3 张的 rank 出三条
6. **三带一**：每个三条 + 最佳副牌（一张）
7. **三带二**：每个三条 + 最佳副牌（一对）
8. **飞机（不带）**：枚举所有 ≥2 个连续三条
9. **飞机带单**：连续三条 + 等量单张副牌
10. **飞机带对**：连续三条 + 等量对子副牌
11. **炸弹**：手中每个 4 张的 rank
12. **火箭**：大小王

#### 跟牌模式（lastCards 非空）

根据上家牌型，枚举所有能压过的同类型组合（从小到大），末尾追加炸弹和火箭：

- **single**：所有 rank > lastMainRank 的单张
- **pair**：所有 rank > lastMainRank 且 count ≥ 2 的对子
- **triple**：所有 rank > lastMainRank 且 count ≥ 3 的三条
- **triple_one**：所有 rank > lastMainRank 的三条 + 最佳单张副牌
- **triple_two**：所有 rank > lastMainRank 的三条 + 最佳对子副牌
- **straight**：同长度、mainRank 更大的所有顺子
- **double_straight**：同长度、mainRank 更大的所有连对
- **airplane / airplane_single / airplane_pair**：同长度、mainRank 更大的所有飞机组合 + 副牌
- **four_two_single**：所有 rank > lastMainRank 的四张 + 2 张最佳副牌
- **four_two_pair**：所有 rank > lastMainRank 的四张 + 2 对最佳副牌
- **bomb**：所有 rank > lastMainRank 的炸弹
- **rocket**：无需比较，火箭最大

非炸弹/火箭牌型末尾统一追加：
1. 所有炸弹（从小到大）
2. 火箭（如果有大小王）

#### 副牌选择策略优化

`pickSingleSideCards` 和 `pickPairSideCards` 的选择逻辑调整：

- **避免拆炸弹**：如果某个 rank 恰好有 4 张，跳过该 rank 的牌
- 优先选择手中数量最少的 rank 的牌（先出零散牌）
- 仍然按 rank 从小到大排序

### 2. `GameRoomView.vue` — 循环提示交互

#### 状态管理

新增 `hintState` reactive ref：

```typescript
const hintState = ref<{
  allHints: number[][]
  currentIndex: number
} | null>(null)
```

#### 提示按钮文案

```typescript
const hintButtonText = computed(() => {
  if (!hintState.value || hintState.value.allHints.length === 0) {
    return '提示'
  }
  return `提示 ${hintState.value.currentIndex + 1}/${hintState.value.allHints.length}`
})
```

#### 点击提示逻辑

```typescript
function applySuggestion() {
  if (gameStore.gamePhase !== 'PLAYING' || !gameStore.isMyTurn) return

  const lastCards = lastCardsToBeat.value

  if (!hintState.value) {
    // 首次点击：计算所有提示
    const allHints = findAllPlayableHints(gameStore.myHand, lastCards)
    if (allHints.length === 0) return  // 要不起，按钮已禁用
    hintState.value = { allHints, currentIndex: 0 }
  } else {
    // 再次点击：切换下一个
    hintState.value.currentIndex =
      (hintState.value.currentIndex + 1) % hintState.value.allHints.length
  }

  // 选中当前提示方案的牌
  gameStore.selectCards(hintState.value.allHints[hintState.value.currentIndex])
}
```

#### 重置时机

- `currentTurn` 变化时重置 `hintState = null`
- `myHand` 变化时重置 `hintState = null`
- `gamePhase` 变化时重置 `hintState = null`

#### 提示按钮禁用条件

当 `playSuggestion?.canPlay` 为 false 时（即 `findSuggestedPlay` 返回空），按钮禁用并显示"要不起"。

#### 超时自动出牌

保持现有行为不变：超时时使用 `suggestedCards`（即 `findSuggestedPlay` 的第一个结果）自动出牌。

#### hinted 高亮

`suggestedCards`（传给 `HandCards` 的 `:hinted-cards`）保持使用 `findSuggestedPlay` 的结果，始终高亮默认推荐方案。当用户点击提示循环后，选中状态（selected）会覆盖高亮状态。

## 不变更的部分

- 后端无变更，出牌提示完全在前端计算。
- `findSuggestedPlay()` 保留，继续用于超时自动出牌和默认高亮。
- `HandCards.vue`、`PokerCard.vue`、`gameStore.ts` 无变更。
- 牌型检测 `detectCardPlay()` 和压制判断 `canBeatCardPlay()` 无变更。

## 验证计划

### 手动验证

1. **自由出牌**：验证所有牌型（单张、对子、顺子、连对、三带一/二、飞机、炸弹、火箭）均出现在提示列表中。
2. **跟牌模式**：验证各种上家牌型下，提示列表仅包含能压过的组合。
3. **循环切换**：多次点击"提示"按钮，确认索引正确递增并循环。
4. **按钮文案**：确认显示"提示 1/5"格式的文字。
5. **重置行为**：轮次变化后，提示状态正确重置。
6. **副牌优化**：三带一不会拆炸弹去带牌。
7. **超时自动出牌**：超时时仍然使用第一个推荐方案自动出牌。
8. **要不起场景**：确认按钮禁用且无法点击。
