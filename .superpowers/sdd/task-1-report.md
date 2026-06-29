# Task 1 执行报告: 前端开发 - 出牌错误气泡、重新洗牌提示与底牌 3D 翻面

## 1. 任务概述
本任务完成了 Landlord 斗地主游戏房间界面的三项关键视觉和交互增强功能：
1. **底牌 3D 翻转动效**：底牌展示升级为 3D 翻转包裹层，获得底牌数据时，底牌将以流畅的 3D 翻转动画亮出，并附带时间差过渡（每张牌延迟 0.1 秒）。
2. **出牌错误气泡**：当用户非法出牌或牌力不足被后端拦截返回错误时，将展示具有弹性抖动动画（`shake-toast`）的红色警告气泡，并在 2.5 秒后自动淡出。
3. **重新洗牌横幅提示**：在连续无人叫牌导致重新洗牌时，界面中央将展示具有毛玻璃背景的重新洗牌横幅，带有旋转的 🔄 图标，维持 1.8 秒后自动淡出。

---

## 2. 修改文件及具体实现

### 修改的文件
- [GameRoomView.vue](file:///d:/Project_2023/hmp_ws_service/frontend/src/views/GameRoomView.vue)

### 具体实现详情

1. **HTML 模板改造**:
   - 在底牌展示区 `top-right-hud` 中，引入了 `.bottom-card-flip-container` 等包裹层，分离了正面 `.bottom-card-front` 与背面 `.bottom-card-back`。
   - 在个人操作栏倒计时区上方，新增了 `<transition name="fade">` 气泡层，绑定 `gameStore.errorMsg`。
   - 在容器最底端增加了重新洗牌横幅，绑定本地状态 `showRedealNotice`。

2. **JavaScript 脚本扩展**:
   - 定义了 `showRedealNotice` ref 变量。
   - 监听 `gameStore.errorMsg`，一旦有值，则在 2.5 秒后将其置空以触发淡出动画。
   - 监听 `gameStore.gamePhase`。当其从 `CALLING` 切换为 `DEALING` 时，即代表触发了重新洗牌（`redeal`）逻辑，将 `showRedealNotice.value` 设为 `true`，并在 1.8 秒后恢复为 `false`。

3. **CSS 动画与样式支持**:
   - 为底牌 3D 翻转容器设置了 `perspective: 600px`，内部容器设置了 `transform-style: preserve-3d` 与 `backface-visibility: hidden`。
   - 实现气泡警告的 `shake-toast` 帧动画以及洗牌指示器的 `spin-redeal` 无限旋转动画。

---

## 3. 测试与验证
- 执行了 `npm run type-check` 进行 TypeScript 强类型校验。
- 在校验过程中，排查并修复了 `GameRoomView.vue` 中原先遗留的几处模板语法类型警告（包括 `@click` 回调缺少显式括号导致传递 `PointerEvent` 与参数 `isAuto: boolean` 冲突的问题，以及 `playerPlayedCards` 数据读取时的严格非空与可选链校验），确保了修改后的 `GameRoomView.vue` 文件本身实现了完全编译通过且无 TS 类型报错。
