# 安特限时秒杀列表

**脚本（双仓库同名，请先改 webAuto 再复制到 assistantService）**：

| 角色 | 路径 |
|------|------|
| 唯一源 | `webAuto/mcp-server/script/antexiadan-seckill-list.js` |
| assistantService 副本 | `src/spider/antexiadan/scripts/antexiadan-seckill-list.js` |
| CLI 唯一源 | `webAuto/mcp-server/script/antexiadan-seckill-fetch.py` |
| CLI 副本 | `src/spider/antexiadan/scripts/antexiadan-seckill-fetch.py` |

**目标页面**：`https://pc.antexiadan.com/homepage`（须登录）

**assistantService 实现**：

| 模块 | 路径 |
|------|------|
| Flask 路由 | `src/api/routes/antexiadan_routes.py` |
| Playwright 采集 | `src/spider/antexiadan/seckill_sync.py`（读 `scripts/antexiadan-seckill-list.js`） |
| MySQL 存储 | `src/spider/antexiadan/seckill_store.py` |
| DDL | `docs/sql/antexiadan-seckill-db-schema.mysql.sql`（与 webAuto `docs/安特/antexiadan-seckill-db-schema.sql` 对齐） |

---

## HTTP 接口

### POST `/api/antexiadan/seckill-list/sync`

webAuto 扩展桥 / Python CLI 写入。

**请求体**（与 webAuto `rows[]` 一致）：

```json
{
  "fetchedAt": "2026-06-03 18:29",
  "serverTime": "2026-06-03 18:29",
  "serverUnix": 1780482555,
  "apiVersion": "20251218",
  "count": 98,
  "byStatus": { "秒杀中": 37, "预热/待开始": 61 },
  "groups": [{ "title": "秒杀中", "subTitle": "10:00", "count": 1 }],
  "writeSnapshot": true,
  "rows": [
    {
      "seckillId": "34029",
      "goodsId": "242206",
      "title": "【限时抢购】女士轻薄开衫V领防晒空调开衫",
      "priceMin": 69.0,
      "priceMax": 69.0,
      "priceDisplay": "69.00",
      "groupTitle": "秒杀中",
      "slotTime": "10:00",
      "activityStatus": "秒杀中",
      "startTime": "2026-06-03 10:00",
      "endTime": "2026-06-06 10:00",
      "startUnix": 1780442400,
      "endUnix": 1780701600,
      "goodsIsOffline": false,
      "homepageDisplay": true
    }
  ]
}
```

**响应**：

```json
{
  "success": true,
  "ok": true,
  "batchId": 1,
  "upserted": 98,
  "dbPath": "C:\\...\\data\\antexiadan_seckill.sqlite",
  "writeSnapshot": true
}
```

**处理逻辑**：

1. 插入 `antexiadan_seckill_fetch_batch`
2. 按 `seckill_id` UPSERT `antexiadan_seckill_product`
3. `writeSnapshot=true` 时写入 `antexiadan_seckill_product_snapshot`

### GET `/api/antexiadan/seckill-list/products`

查询参数：`activity_status`、`group_title`、`slot_time`、`limit`（默认 500）、`offset`。

### GET `/api/antexiadan/seckill-list/batch/latest`

返回最近一次抓取批次元数据。

---

## Python 一键拉取并入库

```bash
set ANTEXI_API_KEY=<从 Chrome Network seckill-list 复制>
python C:\Users\yao\Desktop\work\webAuto\mcp-server\script\antexiadan-seckill-fetch.py ^
  --sync http://127.0.0.1:8887/api/antexiadan/seckill-list/sync
```

assistantService 须已启动（`main.py` 或打包版，端口 8887）。

---

## Chrome / MCP 注入

```javascript
window.__ANTEXI_SECKILL_RUN_MODE = 'extension'; // 默认
// page_evaluate: return + antexiadan-seckill-list.js 全文
```

| window 变量 | 说明 |
|-------------|------|
| `__ANTEXI_SECKILL_API_KEY` | 可选，覆盖自动解析的 key |
| `__ANTEXI_SECKILL_SYNC_URL` | 默认 `http://127.0.0.1:8887/api/antexiadan/seckill-list/sync` |
| `__ANTEXI_SECKILL_SYNC` | `false` 仅抓取不同步 |

---

## rows[] 字段说明

| 字段 | 类型 | DB 列 |
|------|------|--------|
| seckillId | string | seckill_id（唯一） |
| goodsId | string | goods_id |
| goodsBasicId | string | goods_basic_id |
| title | string | title |
| priceMin / priceMax | number? | price_min / price_max |
| priceDisplay | string | price_display |
| groupTitle | string | group_title |
| slotTime | string | slot_time |
| groupSubTitle | string | group_sub_title |
| activityStatus | string | activity_status |
| startTime / endTime | string | start_time / end_time |
| startUnix / endUnix | number | start_unix / end_unix |
| seckillState | string | seckill_state |
| seckillImage | string | seckill_image |
| goodsUrl | string | goods_url |
| goodsIsOffline | boolean | goods_is_offline |
| homepageDisplay | boolean | homepage_display |
| isFlashTitle | boolean | is_flash_title |

---

## 联动文档

- webAuto：`docs/webAuto-assistantService联动设计.md` §9
- webAuto 契约：`webAuto/docs/安特/antexiadan-seckill-list.md`
