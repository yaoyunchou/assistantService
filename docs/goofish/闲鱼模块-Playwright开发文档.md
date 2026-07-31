# 闲鱼（Goofish）模块 · Playwright 开发文档

目标平台：[闲鱼卖家工作台](https://seller.goofish.com/)（`seller.goofish.com`，Hash 路由 SPA）

配套文档：[闲鱼后台-探测记录.md](闲鱼后台-探测记录.md)（选择器与接口名的唯一取值来源）

---

## 1. 能力概览

| 能力 | 入口 | 状态 |
|------|------|------|
| 本地队列发布 | `/tools/goofish` | 已实现，选择器待登录态校准 |
| 在线商品列表 | `/goofish/items` | 已实现（三级取数） |
| 上架 / 下架 | `/goofish/items` | 已实现 |
| 编辑（改价 / 改描述） | `/goofish/items` | 已实现 |
| 删除（二次确认） | `/goofish/items` | 已实现 |
| 接口探测 | `/goofish/items` → 「探测接口」 | 已实现 |
| 擦亮（刷新曝光） | — | 不做 |

---

## 2. 目录结构

```
src/spider/goofish/
├── config.py              URL / 选择器 / mtop 接口名 / 缺省值（集中配置）
├── client.py              GoofishClient，对外唯一入口
├── mtop_bridge.py         在页面上下文直调 mtop（数据获取主路径）
├── page_guard.py          登录判定、业务 iframe 定位、窗口辅助
├── login_gate.py          ensure_logged_in 登录门禁
├── browser_visible.py     操作前切可见窗口并打开后台
├── api_probe.py           运行时接口探测
├── item_list.py           在线列表（mtop 直调 → 自动识别 → DOM 兜底）
├── step_logger.py         jsonl + 截图（logs/goofish-pw/）
├── test_item_list.py      离线 fixture 测试
├── data/{loader,backfill}.py   Excel 队列与回填
├── flows/{publish_one,manage_items}.py
├── pages/publish_page.py
└── scripts/
    ├── goofish-item-list.js
    ├── goofish-item-action.js
    └── fixtures/{item-list.html,item-list-mtop.json}

src/api/routes/goofish_routes.py
src/tools/goofish_tool.py
src/web/templates/tools/goofish.html      发布 + 本地队列
src/web/templates/goofish_items.html      在线商品管理
```

---

## 3. 三条硬性约束（改代码前必读）

### 3.1 BrowserPool 是「单线程 + 单个长驻 page」

[query_manager.py](../../src/spider/query_manager.py) 的 `_ensure_page()` 复用唯一 `self._page`，
`_executor` 为 `max_workers=1`。因此：

- **不存在「闲鱼专用 tab」**，拼多多 / 淘宝 / 闲鱼共用同一个 page，只靠 `goto` 切 URL
- 每次操作**必须先 `goto` 目标 URL 再校验就绪**，不能假设页面还停在上次位置
- 闲鱼长任务会**独占浏览器线程**，阻塞其它模块

**已采取的应对**：

- 单次 API 只处理一条商品；批量由前端串行发起，可随时中断
- 所有 `pool.execute(timeout=...)` 都设了明确上限
- 前端提示避开 12:00 / 18:00 的 ERP 定时同步

### 3.2 业务页在 iframe 内

shell 的路由表只有 `login / iframe / im / ...`，没有 `seller-item/publish`
（见探测记录第 1 节）。发布页与商品列表都由 `iframe` 路由承载。

因此 DOM 操作必须先取业务 frame：

```python
from spider.goofish.page_guard import find_business_frame

frame = find_business_frame(page) or page.main_frame
frame.locator('textarea').first.fill('...')   # 对 frame 操作，不是 page
```

### 3.3 禁止使用带构建哈希的 class 选择器

后台用 CSS Modules，class 形如 `loginPage--ScuLfa2N`，**每次前端发版都变**。

只允许：稳定 ID（`#ice-container`、`#xy-login-iframe`）、语义属性（`[data-*]`、`role`、`name`、`type`）、
文本匹配（`get_by_text('立即发布')`）、以及基于这些锚点的相对定位。

---

## 4. 登录门禁

判定优先级：**mtop 探针 > URL > DOM**。

```python
from spider.goofish.login_gate import ensure_logged_in

gate = ensure_logged_in(page, wait_login_timeout_sec=180)
if not gate.get('ok'):
    return {'ok': False, 'need_login': gate.get('need_login'), 'message': gate['message']}
```

探针原理（已实测）：调用 `mtop.alibaba.idle.seller.platform.query.login.merchant.info`，
未登录时返回 `ret = ["FAIL_SYS_SESSION_EXPIRED::Session过期"]`。

为什么不用 URL / DOM 作主判据：

- hash 路由跳转不触发 navigation，`page.url` 滞后
- 登录页主 frame 的 `document.body.innerText` 实测为**空**（内容都在 iframe 里）
- class 名带构建哈希，不可靠

探针无法断定时（限流 / 风控），`ensure_logged_in` 返回 `need_login: False` 并如实说明，
**不臆断为未登录**，避免误导用户反复扫码。

---

## 5. 取数策略：三级降级

`item_list.fetch_items()` 按可靠性依次尝试，返回体的 `source` 字段标明实际路径：

| 顺序 | source | 条件 | 说明 |
|------|--------|------|------|
| 1 | `mtop` | `config.ITEM_LIST_API` 已配置 | `lib.mtop.request` 直调，分页可控，最确定 |
| 2 | `capture` | 未配置接口名 | 打开列表页拦截 mtop 响应自动识别，并在 `hint` 里告知应配置的 API 名 |
| 3 | `dom-fallback` | 前两者失败 | 执行 `goofish-item-list.js` 抓 DOM |

前端会在数据来源为 `dom-fallback` 时提示用户去做接口探测。

### 为什么直调 mtop 优于拦截 XHR

`lib-mtop@2.7.3` 全局可用（已实测 `window.lib.mtop.request` 可调），直调能：

- 自己控制分页参数，不必靠点 UI / 滚动去「骗」出请求
- 不受列表页 DOM 与 CSS 改版影响
- 复用页面里的登录态与签名逻辑，不需要自己算 sign

---

## 6. 接口探测（补全登录态才可见的接口）

商品列表 / 发布 / 上下架接口都在 iframe 业务应用里，**未登录时拿不到**。
所以模块内置探测器把这一步变成一键自助：

1. 登录闲鱼后台
2. 打开 `/goofish/items`，点「探测接口」（或 `POST /api/goofish/probe`）
3. 结果落在 `logs/goofish-pw/probe/<时间戳>/`：
   - `apis.json` — 捕获到的接口名、版本、请求参数
   - `sample-<api>.json` — 响应样本（可直接做 fixture）
   - `frames.json` — iframe URL 清单
   - `screenshot.png`
4. 把商品列表接口名写进 `config.ITEM_LIST_API`，取数即切到最可靠的 `mtop` 路径
5. 顺便用 `sample-*.json` 替换 `scripts/fixtures/item-list-mtop.json`，让测试贴合真实结构

探测器只记录结构骨架与截断样本（单接口上限 20000 字符），不落全量业务数据。

---

## 7. Excel 队列约定

数据目录：`C:\Users\yao\Desktop\work\电商数据\闲鱼`，汇总表 `闲鱼商品汇总.xlsx`。

列头：

```
商品标题 | 想卖价 | 原价 | 成色 | 分类 | 是否包邮 | 发货地 | 图片数
本地目录 | 商品URL | 采集时间 | 上架时间 | 上架链接 | 闲鱼商品ID | 状态
```

- **待发布**：`上架链接` 为空，且本地 `images/` 有图
- **已发布**：`上架链接` + `闲鱼商品ID` 已回填
- 单品目录：`{标题}/商品信息.xlsx`（`基本信息` sheet 为键值表）+ `images/`
- 描述也可放 `{标题}/描述.txt`
- 缺列自动回落到 `config.py` 的缺省值（成色默认「全新」、默认包邮），便于表结构逐步补全
- 回填用 openpyxl **只写目标单元格**，不整表重建，避免丢用户的格式与公式

---

## 8. 发布流程

```
校验必填 → 登录门禁 → goto 发布页 → 定位业务 frame
  → 关引导弹层 → 上传图片 → 填标题/描述 → 填价格 → 选成色/分类/包邮/发货地
  → 提交 → 解析商品 ID → 回填 Excel
```

`stop_after` 调试断点：`upload` / `fill` / `submit` / `None`。

### 失败处理原则

- **选择器定位不到** → 抛 `PublishPageError`，错误信息里直接写「怎么补全」（跑探测 + 改 config），
  而不是静默点错位置
- **点了发布但解析不到商品 ID** → 返回 `needs_manual_check: True`，提示人工确认后用
  `POST /api/goofish/mark-uploaded` 回填。**不当作失败**，避免用户重试造成重复铺货
- 非致命属性（成色 / 分类 / 包邮）未命中只记 warning，不中断整单

失败时 `step_logger` 落 jsonl + 截图到 `logs/goofish-pw/YYYY-MM-DD/{slug}/`。

---

## 9. API 一览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/goofish/login-status` | 登录态（mtop 探针） |
| POST | `/api/goofish/open-publish` | 打开发布页（可见窗口） |
| POST | `/api/goofish/open-items` | 打开商品列表页 |
| GET | `/api/goofish/pending` | 本地待发布队列（不需浏览器） |
| POST | `/api/goofish/publish` | 按 `keyword` / `title` 发布单条 |
| POST | `/api/goofish/publish-next` | 发布队列第一条 |
| POST | `/api/goofish/mark-uploaded` | 手动回填上架信息 |
| POST | `/api/goofish/probe` | 探测真实 mtop 接口 |
| GET | `/api/goofish/items` | 在线商品列表 |
| POST | `/api/goofish/items/<id>/online` | 上架 |
| POST | `/api/goofish/items/<id>/offline` | 下架 |
| POST | `/api/goofish/items/<id>/delete` | 删除，**必须 `{"confirm": true}`** |
| POST | `/api/goofish/items/<id>/edit` | 改价 / 改描述 |

统一约定：业务失败返回 **200 + `{ ok: false, need_login?, message }`**，
避免前端把可预期的业务状态当成服务器异常。

---

## 10. 测试

```bat
set PYTHONPATH=src
python -m unittest spider.goofish.test_item_list -v
```

12 个用例，全部离线、可反复跑：

- `MtopParsingTest` — 纯 Python，验证字段命名不统一时的归一化
  （`itemId/id/auctionId`、`price/soldPrice/currentPrice`、中英文状态）
- `DomFallbackTest` — 用本地 fixture HTML 跑真实 JS 脚本

fixture 刻意模拟了后台的真实特征：class 带构建哈希、标题里含数字、混入干扰链接。

> 这个测试已经抓到过一个真实 bug：DOM 脚本把标题「机械键盘 **87**键」里的 87 当成了价格。
> 现在价格解析要求带货币符号，找不到符号时会先剔除标题再找裸数字。

---

## 11. 集成清单（新增功能时别漏）

| 文件 | 改动 | 漏掉的后果 |
|------|------|-----------|
| `main.spec` | `_pack_datas` 含 `spider/goofish/scripts` | 打包后 JS 丢失，运行时 `FileNotFoundError` |
| `src/web/templates/base.html` | 三处工具名元组含 `'goofish'`；`_ec_endpoints` 含 `'goofish_items'` | 闲鱼同时出现在「电商」和「工具」两个分组；管理页无法高亮 |
| `src/notify/__init__.py` | `_SOURCE_DISPLAY` 含 `"goofish": "闲鱼助手"` | 飞书通知显示英文 `goofish` |
| `src/api/routes/__init__.py` | 注册 `goofish_bp` + Swagger tag「闲鱼」 | API 全部 404 |
| `src/app.py` | `init_tools()` 注册 `GoofishTool` | 工具页不可达 |
| `src/web/routes.py` | `/goofish/items` 路由 | 管理页不可达 |

`src/config/modules.py` 未加 `goofish` 条目 —— 与 `taobao` 保持一致（浏览器池已因
`pinduoduo.requires_browser=True` 必然启动，加了还需同步 exe 旁的 `module_config.toml`）。

---

## 12. 已知待办

| 项 | 说明 |
|----|------|
| 发布表单选择器校准 | 当前用语义/文本候选，需登录态实测后写死到 `config.py` |
| `ITEM_LIST_API` | 需探测后填入，填之前走自动识别路径 |
| 价格单位 | 接口返回「元」还是「分」未确认，`_norm_price` **刻意不换算**（会回显到编辑弹窗，猜错就改错价） |
| `ITEM_URL_TEMPLATE` | 后台实际使用的详情域名待确认 |
| 成色 / 分类枚举 | `CONDITION_CHOICES` 为推测值，需对齐真实文案 |
| 编辑换图 | 视 DOM 复杂度决定是否支持 |
| 批量发布 | 目前由前端串行发起单条；如需服务端批量需带节流与断点续跑 |
