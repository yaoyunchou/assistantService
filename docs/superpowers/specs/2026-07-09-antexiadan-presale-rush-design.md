# 安特预售抢购控制台设计

日期：2026-07-09

## 目标

在安特模块新增「预售抢购」页面：从「正在预售/预热」商品选品，按开售时间建定时任务：

1. **开售前 20 分钟**：Playwright 登录 → 逐个进详情 → 设数量 → **加入购物车**
2. **开售时刻**：打开购物车 → 勾选本批商品 → **去结算/提交订单**；若跳出第三方支付页则停住并飞书通知，人工完成付款

## 默认约定（已锁定）

| 项 | 约定 |
|----|------|
| 选品池 | `activity_status=预热/待开始` + `group_title=预热中` + 未下架 |
| 任务合并 | 同一 `start_unix` / `start_time` → 一个抢购计划 |
| 数量 | 能对上拼多多预售单则用订单 `qty`，否则 1；页面可改 |
| 加购时机 | 开售前 20 分钟（`ANTEXIADAN_PRESALE_CART_ADVANCE_MIN`，默认 20） |
| 支付时机 | 开售时刻准时触发 |
| 支付深度 | 自动点到提交订单；第三方收银台停住 + 通知 |
| 调度 | 复用 APScheduler；扩展一次性 `run_at`（DateTrigger） |

## 页面

- 路径：`/antexiadan/presale-rush`
- 模板：`antexiadan_presale_rush.html`
- 导航：安特分组下「预售抢购」

区块：

1. **候选商品**：勾选 + 改数量 + 按开售时间分组预览
2. **创建计划**：一键按选中商品生成「加购任务 + 结算任务」
3. **计划列表**：状态、下次执行、立即试跑（加购/结算）、取消

## 任务模型

每个开售时间点创建一个 **计划**（逻辑组），落地为两条 Scheduler 任务：

### A. `antexiadan_presale_cart`

- `run_at` = `start_unix - 20*60`
- `data`：
  ```json
  {
    "phase": "cart",
    "startUnix": 1783572000,
    "startTime": "2026-07-09 16:00",
    "planId": "uuid",
    "items": [
      {"seckillId": "...", "goodsId": "...", "title": "...", "goodsUrl": "...", "qty": 2}
    ]
  }
  ```

### B. `antexiadan_presale_checkout`

- `run_at` = `start_unix`
- `data`：同上，`phase: "checkout"`，`items` 与加购一致

任务名示例：

- `安特预售加购 · 2026-07-09 16:00（3件）`
- `安特预售结算 · 2026-07-09 16:00（3件）`

若「现在距开售不足 20 分钟」：加购任务立即执行（或 `run_at=now+5s`），结算仍按开售时刻。

## Playwright 流程

### 加购（phase=cart）

1. `ensure_logged_in(page)`
2. 对每个 item：`goto(goodsUrl)` → 设置数量 → 点击「加入购物车」
3. 遇滑块走现有 `handle_captcha`
4. 汇总成功/失败；失败发安特 Webhook

### 结算（phase=checkout）

1. `ensure_logged_in(page)`
2. 打开购物车页
3. 尽量勾选本批商品（按标题/goodsId 匹配）
4. 点击去结算 / 提交订单
5. 若 URL/页面进入支付收银台：截图 + 飞书通知「请手动完成支付」
6. **不**尝试破解第三方支付

> 选择器首版按常见文案定位（加入购物车 / 去结算 / 提交订单），真机跑通后可再固化。

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/antexiadan/presale-rush/candidates` | 候选商品 + 建议 qty |
| POST | `/api/antexiadan/presale-rush/plans` | body: `{ items: [...] }` 按 start 建计划 |
| GET | `/api/antexiadan/presale-rush/plans` | 列出相关 scheduler 任务 |
| POST | `/api/antexiadan/presale-rush/tasks/<id>/run` | 立即执行该任务 |
| DELETE | `/api/antexiadan/presale-rush/plans/<planId>` | 取消同 plan 的加购+结算任务 |

## Scheduler 扩展

- `task_config` / `add_task` 支持可选字段 `run_at`（ISO 本地时间或 unix）
- 有 `run_at` 时用 `DateTrigger`，无则沿用 cron
- 一次性任务执行后保留配置记录，便于页面回看

## 模块文件

- `src/spider/antexiadan/presale_rush.py` — 加购/结算编排
- `src/web/templates/antexiadan_presale_rush.html`
- `src/api/routes/antexiadan_routes.py` — 上述 API
- `src/web/routes.py` + `base.html` — 页面与导航
- `src/scheduler/manager.py` — 新 handler + DateTrigger

## 支付与标记

- 到点结算：购物车勾选 → 去结算/提交订单
- 进入第三方支付页：停住 + 飞书通知，人工付款
- **下单/结算成功后**：按 `presellOrderNo` 将 `erp_order_presell.purchased` 标为 `1`
- 可手动补标：`POST /api/antexiadan/presale-rush/mark-presell` body `{ "orderNos": ["..."] }`

## 非目标（本期不做）

- 自动完成微信/支付宝等第三方付款
- 多账号并发抢购
- 库存监控轮询
