# 安特 Playwright 登录门禁设计

日期：2026-07-09

## 目标

所有依赖 Playwright 浏览器会话的安特逻辑，在执行前必须通过登录门禁：

1. 已登录 → 直接继续后续脚本
2. 未登录（被重定向到登录页）→ 用 `.env` 账号密码自动登录 → 成功后再继续
3. 自动登录失败 → 返回明确错误，不执行后续脚本

## 环境变量（本地 `.env` 配置）

| 字段名 | 说明 | 示例 |
|--------|------|------|
| `ANTEXIADAN_USERNAME` | 安特 PC 商城登录账号 | `your_account` |
| `ANTEXIADAN_PASSWORD` | 安特 PC 商城登录密码 | `your_password` |
| `ANTEXIADAN_CAPTCHA_MAX_ATTEMPTS` | Agent 滑块尝试次数 | `5` |
| `FEISHU_WEBHOOK_ANTEXIADAN` | 失败通知 Webhook | 可选，回退通用 |
| `CURSOR_API_KEY` | Agent 识别所需 | 必填（自动过滑块时） |

对应 `Config`：

- `Config.ANTEXIADAN_USERNAME`
- `Config.ANTEXIADAN_PASSWORD`

## 作用范围

### 挂门禁（浏览器入口）

- `POST /api/antexiadan/seckill-list/fetch-browser`
- `goods_search.capture_pcapi_credentials` / `ensure_goods_search` / `ensure_goods_search_batch`

### 不挂门禁

- `POST /seckill-list/fetch`（直连 pcapi + key）
- `POST /seckill-list/sync`、查询类 GET 接口

## 模块

新增 `src/spider/antexiadan/login.py`：

| 函数 | 职责 |
|------|------|
| `is_login_page(page)` | URL / 表单判断是否在登录页 |
| `is_logged_in(page)` | 打开 homepage，若不在登录页则视为已登录 |
| `do_login(page)` | 在登录页填入账号密码并提交 |
| `ensure_logged_in(page)` | 检查 → 未登录则自动登录 → `{ok, loggedIn, error?}` |

## 流程

```
pool.execute(page => {
  r = ensure_logged_in(page)
  if not r.ok: return error
  // 原有逻辑：拦截 key / 搜索 / 采集
})
```

未登录时站点会把访问拦截到登录页；`ensure_logged_in` 检测到登录页后自动填表登录，再回到 homepage 确认。

## 登录判定

- 打开 `https://pc.antexiadan.com/homepage`，若被重定向到 `/login` 或出现「请输入手机号」→ 未登录
- 能停留在 homepage（非 login URL）→ 已登录

### 自动登录步骤（真实页面）

1. 点击 Tab「密码登录」（默认是验证码登录）
2. 填写 `请输入手机号` / `请输入密码`
3. 点击「登 录」/「登录」
4. 若出现 `#t_mask` /「安全验证」滑块 → **Cursor Agent 看截图估距离，本页拖动，最多 5 次**
5. 仍失败 → 发飞书 Webhook（`source=antexiadan`），返回错误
6. 等待离开 `/login`，再确认能进入 homepage

选择器：

- Tab：`get_by_role('tab', name='密码登录')`
- 手机号：`get_by_placeholder('请输入手机号')`
- 密码：`get_by_placeholder('请输入密码')`
- 按钮：`get_by_role('button', name='登 录')` 或 `登录`
- 滑块遮罩：`#t_mask` / `.t-mask` / 文案「安全验证」「拖动下方滑块」

### 滑块自动破解（Agent）

1. 本页 `screenshot` 存到 `data/antexiadan/captcha/`
2. `run_agent`（无 Playwright MCP）读取图片，回复 `{"distancePx": N}`
3. 本页定位滑块按钮，拟人化 `mouse` 拖动
4. 检查 `#t_mask` 是否消失；失败则刷新拼图再试
5. 满 N 次失败 → `notify` Webhook

## 错误返回约定

```json
{
  "ok": false,
  "success": false,
  "needLogin": true,
  "error": "安特未登录且自动登录失败：缺少 ANTEXIADAN_USERNAME / ANTEXIADAN_PASSWORD"
}
```

或登录提交后仍停在登录页时的具体错误信息。
