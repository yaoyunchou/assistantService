# 拼多多 ERP 已发货数据补录（刷历史数据）—— 操作手册

**结论先说：以后补录任何一天的已发货数据，只需要 2 条命令，几分钟内完成。** 本文记录 2026-07-15 那次补录为什么花了很久，以及下次应该怎么做才能不重复踩坑。

---

## 1. TL;DR：下次直接这么做

```bash
# 1) 抓数据（会弹出可见浏览器，若已登录会自动继续；若未登录用拼多多 APP 扫码）
python scripts/run_delivered_sync_standalone.py --date-shortcut 昨天

# 2) 把抓到的数据直接写进 Nest 库（按 orderNo upsert，不再依赖助手/浏览器）
python scripts/push_erp_delivered_to_nest.py --file data/erp_delivered_<日期>.json --jwt "<token>"
```

- 想抓「今天」就把 `--date-shortcut 昨天` 换成 `今天`，或直接 `--ship-date 2026-07-20` 之类的具体日期（仅影响输出文件名，实际筛选仍靠 `--date-shortcut`）。
- `--jwt` 每次登录 CMS 后从浏览器 `localStorage` 复制 `access_token`，大约 24 小时过期；长期使用建议改用 `--device-key`（见第 4 节）。
- 第 2 步前可以先加 `--dry-run` 看一眼第一条 DTO，确认字段没问题再真跑。
- 跑完用下面的命令核对数量是否对得上（把 token、日期换掉）：

```bash
curl -s "https://nestapi.xfysj.top/xcx/api/v1/assistant/pinduoduo/erp-delivered/today-printed-records?page=1&pageSize=1&shippingDateStart=2026-07-15&shippingDateEnd=2026-07-15" \
  -H "Authorization: Bearer <token>" | python -m json.tool
```

看返回里 `data.total` 是否等于当天实际发货单数。

---

## 2. 这次为什么弄了很久（复盘）

补数本身应该是「重复剧本」，但这次因为好几个**互相独立的坑叠在一起**，导致排查链路拉得很长：

| # | 卡点 | 现象 | 根因 |
|---|------|------|------|
| 1 | 抓取逻辑本身有 bug | 待发货列表只抓到 12/50 条 | 表格是**虚拟滚动**，只读当前视口 DOM，没有滚动+去重逻辑 |
| 2 | 已发货数据也漏（35/50） | 库里数据比实际少 | 默认筛选「已打印快递单」会漏掉未打印的单；且滚动 3 步无新增就提前停 |
| 3 | 通过助手 API 补数一直超时 | `Page.goto` 120s 超时 | **助手当时跑的是打包好的 EXE，不是仓库里改过的 `src/` 代码**——调 HTTP 接口等于在测旧版本；同时浏览器实例/登录态本身也可能卡死 |
| 4 | 本地起 Flask dev 环境一堆坑 | `ModuleNotFoundError: flask`、`UnicodeDecodeError: gbk`、`UnicodeEncodeError` | 系统 Python 没装依赖；Windows 终端默认 GBK 编码，装依赖/打印中文都炸 |
| 5 | 换成独立 Playwright 脚本后，数据终于抓对了，但**不知道怎么落库** | 抓到了完整 50 条，卡在“怎么写进数据库” | 一开始以为只能走助手已有的同步接口（还是得过浏览器那条脆弱链路），没意识到 Nest 侧还有别的口子 |
| 6 | 找到 Nest 直写接口后，第一次调用全部 404 | POST 直写接口返回 nginx 404 | **Base path 少了 `/xcx` 前缀**——Swagger JSON 里 `paths` 字段（如 `/api/v1/...`）只是 Nest 内部路径，真实外部网关地址是 `https://nestapi.xfysj.top/xcx/api/v1/...`；Swagger UI 的挂载路径往往就是真实前缀，没有单独验证就假设两者一致 |

**核心教训**：这次的大部分时间不是花在「写代码」上，而是花在**环境/链路排查**上——搞清楚「助手到底跑的是哪份代码」「Nest 真实网关路径是什么」这类一次性、可文档化的事实。这些事实一旦确认并写下来，以后就不用再排查第二次。

---

## 3. 关键事实（记牢，别再排查第二次）

1. **抓数据不用等于写库**。这两件事是独立的：
   - 抓数据：`scripts/run_delivered_sync_standalone.py`（独立 Playwright，绕开 Flask/浏览器池，用独立的浏览器 profile `browser_data_standalone`，不会跟正在跑的助手/EXE 抢登录态）。
   - 写库：不用非得走助手的「同步接口」（那条链路要过浏览器，脆弱）。Nest 侧本身就有**直接写库**的 CRUD 接口（`POST/PUT/DELETE .../erp-delivered/today-printed-records`），按 `orderNo` upsert，装好数据直接怼进去最快最稳。
2. **Nest 网关真实前缀是 `/xcx/api/v1`**，不是 Swagger JSON `paths` 里裸露的 `/api/v1`。以后对接任何 Nest 接口，先拿一条已知会返回非 404（哪怕是 400/401）的请求验证一次 base path，不要直接假设。
   - 验证方法：`curl -X POST https://nestapi.xfysj.top/xcx/api/v1/auth/login -d '{}' -H 'Content-Type: application/json'` → 返回 400（字段校验错误）说明路径对；如果是 nginx 404 页面说明 base path 错了。
3. **Nest 鉴权三种方式**（`/api/v1/auth/*`，实际带 `/xcx` 前缀）：
   - `POST /auth/login`：`{username, password}`
   - `POST /auth/login-with-device-key`：`{device_key: "keyId.secret"}`（**推荐用于自动化脚本**，管理员后台生成一次，不用每天复制过期 JWT）
   - `POST /auth/wechat/login`：小程序场景，本手册不涉及
   - 三者都返回 `access_token`（约 24h 有效）+ `refresh_token`。
4. **`erpDeliveredTodayPrintedDto` 的默认筛选是「已打印快递单」**——如果要补全部发货单（含未打印的），线上同步接口要传 `filter_print_status: "__ALL__"`（空串或不传则用页面默认，可能漏未打印的）。`run_delivered_sync_standalone.py` 默认已经是抓全部，除非加 `--printed-only`。
5. **助手可能跑的是打包 EXE，不是 `src/` 源码**。调助手自身 HTTP 接口排查 bug 之前，先确认「当前跑着的是不是刚改的这份代码」，否则会对着旧版本反复排查，白费功夫。判断方法：看进程是 `dist\如意助手\如意助手.exe` 还是 `python dev.py`；改了 `src/` 代码想验证，优先用独立脚本直接测，不要绕经可能是旧版本的服务。
6. **两个数据脚本落盘格式不同但都兼容**：`run_delivered_sync_standalone.py` 落盘是助手原始返回 `{ok, rows, ...}`；`backfill_erp_delivered.py` 落盘是包装过的 `{result: {rows, ...}}`。`push_erp_delivered_to_nest.py` 两种都认。

---

## 4. 涉及文件

| 文件 | 作用 |
|------|------|
| `scripts/run_delivered_sync_standalone.py` | 独立 Playwright 脚本，抓「已发货页」任意一天数据（改 `--date-shortcut`），不依赖 Flask/浏览器池，独立浏览器 profile 避免和正在跑的助手抢登录态 |
| `scripts/push_erp_delivered_to_nest.py` | 把抓到的 JSON 直接 POST 进 Nest 库（按 `orderNo` upsert），支持 `--jwt` / `--device-key` / `--username`+`--password` 三种鉴权 |
| `scripts/backfill_erp_delivered.py` | 老的补数脚本，走「助手 HTTP 接口 → 浏览器」链路，依赖助手在线且浏览器可用；链路更长，仅在助手确认健康时用 |
| `src/spider/pinduoduo/scripts/pdd-erp-order-delivered-query.js` | 已发货页抓取逻辑（滚动去重 + 翻页 + 页脚总数校验），被上面两个 Python 脚本共用 |

相关变更记录见 `docs/log.md`（搜索「2026-07-16」）。
