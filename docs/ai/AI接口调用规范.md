# AI 接口调用规范

> 适用范围：`assistantService` 项目内所有需要调用大模型（文本问答 / 多模态识图 / 流式生成）的模块。
> 目的：约定统一的调用入口、配置项、请求/响应格式与错误处理，便于新增 AI 接口时按规范实现。

---

## 1. 总体架构

项目存在 **三条 AI 调用路径**，新开发接口请按优先级选择：

| 路径 | 入口 | 适用场景 | 当前状态 |
|------|------|----------|----------|
| **Banana Agent（推荐）** | `from ai import ask / ask_vision / run_agent` | 全项目默认路径；安特滑块识图、库存匹配、问答 | 默认启用，须配置 `BANANA_AI_AK` |
| **OpenAI 兼容直连** | `from ai.client import get_default_client` | Banana 不可用、需自选模型（如 DMXAPI `qwen-flash`） | 保留兼容，`ask()` 已默认走 Banana |
| **Nest 网关（已退役为 AI）** | `nest_client.nest_ai_chat` | 仅 `nest_client` 其他用途保留；AI 不再走此路径 | 配置项保留，AI 调用已迁移 |

> ⚠️ `src/ai/agent.py`（本地 Cursor SDK Agent）已弃用，`run` / `run_stream` 仅转发到 `ai.run_agent`，**不要再新增调用**。

调用链路：业务模块/路由 → `src/ai/__init__.py`（公共 API）→ `ai.banana_client.banana_ask`（`POST /ali-oss/api/v1/agent/ask/`）→ Banana Agent 服务；可选回退到 `ai.client.LLMClient`（OpenAI 兼容 `chat.completions`，如 DMXAPI / OpenAI / 国产兼容网关）。

---

## 2. 配置项（`.env`）

### 2.1 Banana Agent（必配）

| 变量 | 说明 | 示例 |
|------|------|------|
| `BANANA_AI_AK` | **必填**：bananain 管理端生成的 AK，调用时以 `Authorization: Bearer <AK>` 发送 | `ak_xxx` |
| `BANANA_AI_API_BASE` | 可选：API 根路径（含 `/ali-oss/api/v1`），默认 `https://test-sso.bananain.cn/ali-oss/api/v1` | `https://test-sso.bananain.cn/ali-oss/api/v1` |
| `BANANA_AI_TIMEOUT` | 纯文本超时（秒），默认 120 | `120` |
| `BANANA_AI_TIMEOUT_MULTIMODAL` | 多模态超时（秒），默认 300 | `300` |

> 未配置 `BANANA_AI_AK` 时调用会抛 `RuntimeError("BANANA_AI_AK 未配置…")`。

### 2.2 OpenAI 兼容直连（可选回退）

| 变量 | 说明 | 示例 |
|------|------|------|
| `AI_BASE_URL` | OpenAI 兼容根 URL | `https://www.dmxapi.cn/v1` |
| `AI_API_KEY` | API Key | `sk-xxx` |
| `AI_STOCK_LINK_MODEL` | 默认文本模型 | `qwen-flash-2025-07-28` |
| `AI_VISION_MODEL` | 默认视觉模型 | `gpt-4o-mini` |

> `LLMClient` 懒加载，首次调用才初始化；未配置 `AI_API_KEY` 时调用会抛 `RuntimeError`。

### 2.3 Nest CMS REST（保留，非 AI 用途）

| 变量 | 说明 | 示例 |
|------|------|------|
| `NEST_API_BASE` | Nest REST 根路径 | `https://nestapi.xfysj.top/xcx/api/v1` |
| `NEST_DEVICE_KEY` / `NEST_USERNAME` / `NEST_PASSWORD` / `NEST_JWT` | Nest 鉴权（设备密钥/账号密码/JWT） | `keyId.secret` |

> AI 调用已从 Nest `/ai/chat` 迁移至 Banana Agent；上述配置仅为 `nest_client` 其他用途保留。

---

## 3. Python 公共 API（`src/ai/__init__.py`）

业务模块**只允许**通过 `src/ai/__init__.py` 暴露的函数调用 AI，不要直接 `import nest_client` 或 `ai.client`。

### 3.1 `ask(prompt, *, system='', model='', max_tokens=500) -> str`

同步文本问答，等价于 `POST /agent/ask/`。

- `model` 在 Banana Agent 路径下**会被忽略**（由服务端路由），仅写日志
- `max_tokens` 映射为请求超时：`max(60, min(max_tokens // 2, 180))` 秒
- 未配置 `BANANA_AI_AK` → 抛 `RuntimeError("BANANA_AI_AK 未配置…")`

```python
from ai import ask

reply = ask("把这段商品描述改写成小红书风格：……", system="你是文案编辑", max_tokens=800)
```

### 3.2 `ask_vision(prompt, image, *, system='', model='', max_tokens=200) -> str`

多模态识图，图片转 base64 data URL 放入 `images: [{dataUrl}]` 发送到 `/agent/ask/`。

- `image` 支持三种形式：路径字符串、`Path` 对象、原始 `bytes`
- 自动按扩展名推断 `mime`（png/jpg/jpeg/webp/gif），未识别回落 `image/png`，放入 `images[].dataUrl`
- 也支持传入远程 URL（`http(s)://...`），此时放入 `images[].url`（接口对 `url` 字段只接受 http(s)）
- 超时：`max(60, min(max_tokens * 2, 180))` 秒；若 `BANANA_AI_TIMEOUT_MULTIMODAL` 更大则取其值

```python
from ai import ask_vision
from pathlib import Path

distance = ask_vision(
    "请输出滑块需要拖动的像素距离，仅返回数字",
    Path("captcha/shot.png"),
    max_tokens=50,
)
```

### 3.3 `ask_stream(prompt, *, system='', model='', max_tokens=2000) -> Iterator[str]`

流式问答。**Banana Agent 为一次问答模式（非流式）**，实现为整段返回后一次 `yield`，签名保持兼容。

### 3.4 `run_agent(instruction, *, tools=None, session_name=None, browser_context=None, stream_callback=None) -> str`

原 Cursor Agent 入口，现统一为 Banana Agent `/agent/ask/`。

- `tools`（如 `playwright`）**不会在本地执行**，仅写 warning 日志；浏览器自动化请直接用 Playwright 脚本
- `session_name` 在 Banana Agent 模式下无本地会话恢复，仅记录
- `browser_context` 可携带：
  - `url`：会拼到 instruction 前作为上下文
  - `screenshot` / `screenshot_b64`：作为多模态图片一并发送（支持 `data:` 前缀或纯 base64）

```python
from ai import run_agent

result = run_agent(
    "根据截图判断当前页面是否在登录页",
    browser_context={"url": page.url, "screenshot_b64": b64},
)
```

### 3.5 `run_agent_stream(...) -> Iterator[Dict]`

流式事件兼容层，单次 `text` + `done`；异常时 yield `{'type': 'error', 'message': ...}`。

### 3.6 会话管理（兼容空实现）

- `list_sessions() -> dict`：Banana Agent 模式无本地会话，返回 `{}`
- `delete_session(name)`：兼容无操作，仅 debug 日志

---

## 4. HTTP API（`src/api/routes/ai_routes.py`）

蓝图 `bp = Blueprint('ai', __name__, url_prefix='/api/ai')`，已注册到 `src/api/routes/__init__.py`。

### 4.1 `POST /api/ai/ask`

简单问答。

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `prompt` | string | 是 | 用户问题 |
| `system` | string | 否 | 系统提示词 |
| `model` | string | 否 | Banana Agent 路径下忽略 |
| `max_tokens` | int | 否 | 默认 500 |

**响应**：`{ "success": true, "result": "助手回复文本" }`

**错误**：`prompt` 为空 → 400；`BANANA_AI_AK` 未配置/鉴权失败 → 503；其他异常 → 500。响应体均为 `{"success": false, "error": "..."}`。

### 4.2 `POST /api/ai/run`

同步 Agent 任务（可带截图）。

**请求体（JSON）**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `instruction` | string | 是 | 任务描述 |
| `tools` | list[string] | 否 | 兼容字段，不会本地执行 |
| `session_name` | string | 否 | 兼容字段 |
| `browser_context` | object | 否 | `{url, cookies, screenshot / screenshot_b64}` |

**响应**：同 `/api/ai/ask`。

### 4.3 `POST /api/ai/run-stream`

SSE 流式（Banana Agent 为一次问答，完成后推送 `text` + `done`）。

- `Content-Type: text/event-stream`
- `Cache-Control: no-cache`，`X-Accel-Buffering: no`
- 事件格式：`data: {"type": "text"|"done"|"error", ...}\n\n`
- 队列超时 120s 会推送 `{"type":"error","message":"超时"}`

### 4.4 `GET /api/ai/sessions`

返回 `{"success": true, "sessions": {}}`（Banana Agent 模式无本地会话）。

### 4.5 `DELETE /api/ai/sessions/<session_name>`

兼容删除，返回 `{"success": true, "message": "会话 xxx 已删除"}`。

---

## 5. Banana Agent `/agent/ask/` 协议（底层）

公共 API 最终落到 `ai.banana_client.banana_ask`，规范如下。

### 5.1 鉴权

- 请求头：`Authorization: Bearer <BANANA_AI_AK>`
- AK 在 bananain 管理端生成（形如 `ak_xxx`），直接放在 `.env` 的 `BANANA_AI_AK`
- **无需登录换取 token**，比 Nest 简单：每次请求直接带 AK
- 未配置 AK → `RuntimeError("BANANA_AI_AK 未配置…")`

### 5.2 请求

- 方法：`POST`
- URL：`{BANANA_AI_API_BASE}/agent/ask/`（默认 `https://test-sso.bananain.cn/ali-oss/api/v1/agent/ask/`）
- Headers：`Content-Type: application/json; charset=utf-8`、`Authorization: Bearer <AK>`

**请求体（纯文本）**

```json
{
  "prompt": "用户文本",
  "system": "可选系统提示"
}
```

**请求体（多模态）**：增加 `images` 数组，每个元素支持三种字段（接口实测）：

- `url`：远程 http(s) URL
- `dataUrl`：`data:{mime};base64,...`（本地图片转 data URL，带 mime，推荐）
- `base64`：纯 base64（无前缀）

```json
{
  "prompt": "描述这张图中的主要内容",
  "system": "用中文简洁回答",
  "images": [
    {"url": "https://example.com/a.jpg"},
    {"dataUrl": "data:image/png;base64,xxxx"}
  ]
}
```

> 本地图片（如安特滑块截图）由 `banana_client._image_to_data_url` 转成 `data:image/...;base64,...`，放入 `images[].dataUrl`（按扩展名自动推断 mime：png/jpg/jpeg/webp/gif）。远程 http(s) URL 放入 `images[].url`。**注意：`images[].url` 只接受 http(s)，不接受 data URL**（实测返回 `images[0].url 须为 http(s) 地址`）。

### 5.3 响应解析（`banana_client._extract_text`）

响应示例：

```json
{
  "success": true,
  "result": "助手回复文本"
}
```

按以下顺序提取文本（兼容多种字段名与嵌套，避免接口小变动即报错）：

1. 顶层是字符串 → 直接返回
2. `success` 为 `false` → 抛 `RuntimeError(f"Banana AI 调用失败: {error/message}")`
3. 依次取 `result` / `content` / `reply` / `text` / `answer` / `output` / `message` / `msg`
4. 顶层 `choices`（OpenAI 风格兜底）→ `choices[0].message.content`
5. `data` 是字符串/对象 → 递归提取
6. 都没有 → 抛 `RuntimeError(f"Banana AI 响应无文本内容: {payload}")`

### 5.4 错误约定

- HTTP 非 2xx / 空响应 / 非 JSON → 包装为 `{"success": false, "error": "..."}`
- `success: false` → `RuntimeError(f"Banana AI 调用失败: ...")`
- 文本为空 → `RuntimeError(f"Banana AI 响应无文本内容: ...")`
- 上层 HTTP 路由捕获 `RuntimeError` 返回 503，其他异常返回 500

### 5.5 实测要点与避坑指南（2026-08-04 探测确认）

以下结论来自探测脚本对 `/agent/ask/` 的实际请求验证，**后续 AI 调用务必遵守**：

#### 5.5.1 `images` 数组三种字段

接口对 `images` 数组每个元素支持三种字段（接口错误信息原文：`images[0] 须包含 url、base64 或 dataUrl`）：

| 字段 | 接受内容 | 实测结果 | 用途 |
|------|----------|----------|------|
| `url` | **仅 http(s) 远程地址** | data URL → 400 `images[0].url 须为 http(s) 地址` | 远程已上传的图片 |
| `dataUrl` | `data:{mime};base64,...`（带 mime 前缀） | ✅ 200 | **本地图片推荐**（带 mime，接口能识别 png/jpg/webp/gif） |
| `base64` | 纯 base64（无前缀） | ✅ 200 | 本地图片（无 mime，接口按默认处理） |

**决策规则**（已在 `banana_client.banana_ask` 实现）：

- 远程 http(s) URL → `{"url": http_url}`
- 本地图片（bytes/文件路径）→ 先转 data URL → `{"dataUrl": "data:image/png;base64,..."}`
- 已是结构化 dict → 原样透传

#### 5.5.2 不被接受的传法（避坑）

| 错误传法 | 接口返回 | 原因 |
|----------|----------|------|
| `images: [{"url": "data:image/png;base64,..."}]` | 400 `images[0].url 须为 http(s) 地址` | `url` 字段只接受 http(s)，data URL 必须改用 `dataUrl` 字段 |
| `message: [{type:text}, {type:image_url, image_url:{url:data_url}}]` + `systemPrompt`（Nest OpenAI 风格） | 400 `prompt / message / instruction 不能为空` | 接口不认 OpenAI chat 风格的 `message` 数组，只认 `prompt` 字符串 + `images` 数组 |
| `images: [{"data": "data:image/png;base64,..."}]` | 400 `images[0] 须包含 url、base64 或 dataUrl` | 字段名是 `dataUrl` 不是 `data` |

#### 5.5.3 请求体字段名对照（Nest → Banana Agent）

迁移时字段名有变化，**不要照搬 Nest 的字段名**：

| 用途 | Nest `/ai/chat`（旧） | Banana `/agent/ask/`（新） |
|------|----------------------|---------------------------|
| 用户输入（纯文本） | `message`（字符串） | `prompt`（字符串） |
| 系统提示 | `systemPrompt` | `system` |
| 多模态图片 | `message` 数组 + `image_url` | `images` 数组 + `url`/`dataUrl`/`base64` |
| 模型 | `model` | 忽略（服务端路由） |

#### 5.5.4 接口探测方法

当接口行为不明确时，用探测脚本快速验证（参考已删除的 `_probe_banana_vision.py`）：

```python
import base64, json, http.client
from urllib.parse import urlparse
from config import Config

AK = Config.BANANA_AI_AK
URL = f"{(Config.BANANA_AI_API_BASE or 'https://test-sso.bananain.cn/ali-oss/api/v1').rstrip('/')}/agent/ask/"
PNG_B64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=='

def post(body):
    data = json.dumps(body, ensure_ascii=False).encode('utf-8')
    p = urlparse(URL)
    c = http.client.HTTPSConnection(p.hostname, p.port or 443, timeout=60)
    c.request('POST', p.path, body=data, headers={
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {AK}',
    })
    r = c.getresponse(); raw = r.read().decode('utf-8', 'replace'); c.close()
    return r.status, raw

# 试不同字段组合，看接口接受哪种
for name, body in [
    ('images[{url:data_url}]', {'prompt': '回复红色', 'images': [{'url': f'data:image/png;base64,{PNG_B64}'}]}),
    ('images[{dataUrl:data_url}]', {'prompt': '回复红色', 'images': [{'dataUrl': f'data:image/png;base64,{PNG_B64}'}]}),
    ('images[{base64:b64}]', {'prompt': '回复红色', 'images': [{'base64': PNG_B64}]}),
]:
    st, raw = post(body)
    print(f'{name} -> HTTP {st}: {raw[:120]}')
```

> 探测脚本用完即删，不要提交到仓库。结论确认后回填到本节。

---

## 6. OpenAI 兼容直连（`src/ai/client.py`）

仅当 Banana Agent 不可用或需自选模型时使用。

### 6.1 `LLMClient` 方法

| 方法 | 说明 | 关键参数 |
|------|------|----------|
| `complete(prompt, *, system, model, max_tokens=500, temperature=0.0)` | 同步文本补全 | 默认模型 `AI_STOCK_LINK_MODEL` 或 `gpt-3.5-turbo` |
| `complete_vision(prompt, image, *, system, model, max_tokens=200, temperature=0.0, mime_type='image/png')` | 多模态识图 | 默认模型 `AI_VISION_MODEL` 或 `gpt-4o-mini` |
| `complete_stream(prompt, *, system, model, max_tokens=2000)` | 流式补全，`yield` 文本块 | `stream=True` |

### 6.2 单例

```python
from ai.client import get_default_client

client = get_default_client()  # 从 Config 读取 AI_API_KEY / AI_BASE_URL / 模型
text = client.complete("你好")
```

---

## 7. 新增 AI 接口的开发规范

当你需要新增一个 AI 能力（如商品标题生成、图片分类、客服回复），请按以下步骤：

### 7.1 选择实现层

| 需求 | 实现位置 |
|------|----------|
| 纯文本/多模态问答，无业务逻辑 | 直接用 `ai.ask` / `ai.ask_vision`，**无需新增代码** |
| 需要特定 prompt 模板、参数封装、结果解析 | 在业务模块内新增函数，内部调用 `ai.ask*` |
| 需要暴露给前端/外部 | 在 `src/api/routes/` 新增路由，调用 `ai.*` 或业务函数 |
| Banana Agent 后端新增了独立端点 | 在 `ai/banana_client.py` 新增封装函数，再在 `ai/__init__.py` 暴露 |

> ⚠️ 涉及多模态（传图片）时，**务必先阅读 [§5.5 实测要点与避坑指南](#55-实测要点与避坑指南2026-08-04-探测确认)**：`images[].url` 只接受 http(s)，本地 base64 必须用 `dataUrl` 字段，不要用 Nest 的 `message` 数组风格。

### 7.2 命名与签名约定

- 公共 API 一律在 `src/ai/__init__.py` 暴露，**不要让外部直接 `import banana_client` 或 `nest_client`**
- 函数签名保持 `(prompt/instruction, *, system, model, max_tokens, ...)` 顺序，便于兼容
- 返回纯字符串；需要结构化结果时由调用方解析（或新增 `parse_*` 辅助函数）
- 异常一律抛 `RuntimeError`，由 HTTP 路由统一转 503/500

### 7.3 HTTP 路由规范

- 蓝图统一挂在 `/api/ai/*`，新增端点在 `ai_routes.py` 内追加
- 业务失败返回 `200 + {"success": false, "error": "..."}`（避免前端误判 500），鉴权失败可返回 503
- 请求体校验：必填字段缺失返回 400
- 流式接口用 `text/event-stream`，事件用 `{"type": "...", ...}` JSON

### 7.4 配置项

- 新增模型/超时等配置项加到 `Config` 类（`src/config.py`）并写入 `.env.example`
- 命名前缀：Banana Agent 相关用 `BANANA_AI_`，直连 OpenAI 兼容用 `AI_`，Nest 其他用途用 `NEST_`
- 提供默认值，避免必填项破坏现有部署

### 7.5 日志与可观测

- 使用 `utils.logger.get_logger('ai.xxx')` 或 `logging.getLogger('ai.xxx')`
- 关键节点打 INFO：请求字节数、模型名、超时；失败打 ERROR + `exc_info=True`
- 多模态请求记录 `image_bytes` 大小、`mime`、`user_chars`、`system_chars`

### 7.6 测试

- 至少写一个**不依赖网络**的单元测试：mock `banana_ask` 或用 fixture
- 多模态解析逻辑参考 `src/spider/goofish/test_item_list.py` 的 fixture 模式
- 鉴权失败、空响应、`success: false` 等边界必须覆盖

### 7.7 文档同步

新增接口后必须更新：

- 本文档（`docs/ai/AI接口调用规范.md`）：新增端点、配置项、示例
- `docs/log.md`：记录变更摘要、原因、影响范围
- `README.md`：若涉及对外能力变化，同步功能说明

---

## 8. 完整调用示例

### 8.1 业务模块调用问答

```python
from ai import ask

def generate_item_title(raw: str) -> str:
    system = "你是电商文案编辑，输出 30 字以内的商品标题"
    return ask(f"原文：{raw}\n请改写为小红书风格标题", system=system, max_tokens=200)
```

### 8.2 多模态识图（滑块距离）

```python
from pathlib import Path
from ai import ask_vision

def solve_captcha_distance(shot_path: Path) -> int:
    text = ask_vision(
        "请输出滑块需要拖动的像素距离，仅返回纯数字",
        shot_path,
        max_tokens=50,
    )
    return int(text.strip())
```

### 8.3 HTTP 路由新增示例

```python
# src/api/routes/ai_routes.py 内追加
@bp.route('/generate-title', methods=['POST'])
def generate_title():
    body = request.get_json(silent=True) or {}
    raw = (body.get('raw') or '').strip()
    if not raw:
        return jsonify({'success': False, 'error': 'raw 不能为空'}), 400
    try:
        from ai import ask
        title = ask(
            f"原文：{raw}\n请改写为小红书风格标题",
            system="你是电商文案编辑，输出 30 字以内的商品标题",
            max_tokens=200,
        )
        return jsonify({'success': True, 'result': title})
    except RuntimeError as e:
        return jsonify({'success': False, 'error': str(e)}), 503
    except Exception as e:
        logger.error('generate-title 失败: %s', e, exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500
```

### 8.4 前端调用示例

```javascript
// 简单问答
const resp = await fetch('/api/ai/ask', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    prompt: '帮我把这段描述改写成小红书风格',
    system: '你是电商文案编辑',
    max_tokens: 500,
  }),
});
const data = await resp.json();
if (data.success) {
  console.log(data.result);
}

// SSE 流式
const evt = new EventSource('/api/ai/run-stream');
evt.onmessage = (e) => {
  const payload = JSON.parse(e.data);
  if (payload.type === 'text') console.log(payload.content);
  if (payload.type === 'done') evt.close();
};
```
