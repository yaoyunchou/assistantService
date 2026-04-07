# 如意助手 -- 可组合工作流引擎改造方案

## 一、现状分析与核心问题

### 项目概况

项目是一个基于 Flask + Playwright 的 Windows 桌面助手，包含 **拼多多商家后台自动化**、**途强 IoT 平台自动化**、**1688 订单提取**、**飞书集成**、**定时任务** 等功能模块。代码约 74 个 Python 文件 / 13,700 行。

### 当前架构的核心问题

**1) 业务逻辑整体耦合，无法拆分复用**

以 ERP 订单同步为例，`src/spider/pinduoduo/erp_order_sync.py` 将以下步骤写死在一个函数里：

- 打开浏览器页面 → 检测登录拦截 → 飞书通知 → 注入 JS 脚本抓取 → 解析数据 → 写入飞书表格

如果想"只做抓取不写飞书"或者"抓完先存本地再手动同步"，做不到。

**2) 工具注册硬编码**

`src/app.py` 的 `init_tools()` 函数（第 149-259 行）逐个 import 并注册每个工具，新增工具需修改此文件。

**3) 定时任务 handler 写死**

`src/scheduler/manager.py` 的 `get_task_handlers()` 返回静态字典，新增任务类型需改代码。

**4) 模块间无统一数据传递机制**

各模块直接 import 调用，数据通过函数返回值和局部变量传递，无法做到"步骤 A 的输出自动成为步骤 B 的输入"。

---

## 二、目标架构：原子步骤 + 可组合工作流

```
┌──────────────────────────────────────────────────────┐
│                     配置层                            │
│   workflows.json (工作流定义)   tasks.json (定时任务)  │
└────────────────────┬─────────────────────────────────┘
                     │
┌────────────────────▼─────────────────────────────────┐
│                    引擎层                             │
│  WorkflowEngine (调度引擎)                            │
│  StepRegistry (步骤注册表，自动发现)                    │
│  StepContext (步骤间数据传递上下文)                     │
└────────────────────┬─────────────────────────────────┘
                     │
┌────────────────────▼─────────────────────────────────┐
│                  原子步骤层                            │
│  BrowserStep (浏览器操作基类)                          │
│  FeishuStep (飞书操作基类)                             │
│                                                      │
│  pdd.check_login        feishu.sync_table             │
│  pdd.scrape_erp_orders  feishu.send_message           │
│  pdd.scrape_addresses   feishu.send_webhook           │
│  tu.login               cache.save_json               │
│  tu.scrape_records      cache.load_json               │
│  ali1688.extract_orders                               │
└──────────────────────────────────────────────────────┘
                     │
┌────────────────────▼─────────────────────────────────┐
│                  API / UI 层                          │
│  Flask REST API    Web 管理界面    APScheduler         │
└──────────────────────────────────────────────────────┘
```

---

## 三、核心设计

### 3.1 原子步骤 (Step) 抽象

新建 `src/workflow/step.py`：

```python
class StepContext:
    """工作流上下文：步骤之间的数据传递容器"""
    def __init__(self, initial_data=None):
        self._data = initial_data or {}
        self.errors = []
        self.logs = []

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value

    def merge(self, data: dict):
        self._data.update(data)


class StepResult:
    """步骤执行结果"""
    def __init__(self, success: bool, message: str = "", data: dict = None):
        self.success = success
        self.message = message
        self.data = data or {}


class BaseStep:
    """原子步骤基类"""
    name: str = ""           # 唯一标识，如 "pdd.login"
    display_name: str = ""   # 中文名
    description: str = ""

    # 声明输入/输出 schema（供 UI 展示和校验）
    input_keys: list = []    # 期望从 context 读取的 key
    output_keys: list = []   # 执行后写入 context 的 key

    def execute(self, ctx: StepContext, params: dict = None) -> StepResult:
        """执行步骤，返回结果"""
        raise NotImplementedError

    def validate(self, ctx: StepContext) -> bool:
        """校验前置条件"""
        return True
```

### 3.2 现有功能拆分为原子步骤

| 步骤 name | 来源文件 | 输入 | 输出 |
|-----------|---------|------|------|
| `pdd.check_login` | `client.py` | browser_pool | login_status, page |
| `pdd.show_qrcode` | `client.py` | page | qrcode_base64 |
| `pdd.scrape_erp_orders` | `erp_order_sync.py` | page | erp_rows[] |
| `pdd.scrape_order_addresses` | `order_address_sync.py` | page, order_nos | addresses[] |
| `feishu.sync_table` | `feishutable.py` | rows, table_config | sync_result |
| `feishu.send_message` | `message_sender.py` | text, user_id | send_ok |
| `feishu.send_webhook` | `webhook/notify.py` | card_data, webhook_url | send_ok |
| `tu.login` | `tu/client.py` | browser_pool | login_status |
| `tu.scrape_records` | `tu/client.py` | page | records[] |
| `tu.sync_feishu` | `tu/feishutable.py` | records | sync_result |
| `ali1688.extract_orders` | `order_extract.py` | browser_pool | orders[] |
| `cache.save_json` | 新建 | data, file_path | saved_path |
| `cache.load_json` | 新建 | file_path | data |

### 3.3 工作流引擎

新建 `src/workflow/engine.py`：

```python
class WorkflowEngine:
    """工作流执行引擎"""

    def __init__(self, registry: StepRegistry):
        self.registry = registry

    def run(self, workflow_def: dict, initial_data: dict = None) -> WorkflowResult:
        ctx = StepContext(initial_data)

        for step_def in workflow_def["steps"]:
            step = self.registry.get(step_def["step"])
            params = step_def.get("params", {})

            # 条件执行
            if not self._check_condition(step_def.get("condition"), ctx):
                continue

            result = step.execute(ctx, params)

            if not result.success:
                error_strategy = step_def.get("on_error", "abort")
                if error_strategy == "skip":
                    continue
                elif error_strategy == "goto":
                    # 跳转到指定步骤（按 label 查找）
                    ...
                else:
                    return WorkflowResult(success=False, context=ctx)

        return WorkflowResult(success=True, data=ctx._data)
```

### 3.4 工作流配置示例

新建 `workflows/pdd_erp_full_sync.json`：

```json
{
  "id": "pdd_erp_full_sync",
  "name": "拼多多 ERP 订单全量同步",
  "description": "登录检查 -> 抓取 ERP 订单 -> 同步飞书 -> 通知",
  "steps": [
    {
      "step": "pdd.check_login",
      "params": { "target_url": "erp/order/all" },
      "on_error": "abort"
    },
    {
      "step": "pdd.scrape_erp_orders",
      "params": { "scroll_max_steps": 50 },
      "condition": { "key": "login_status", "equals": true }
    },
    {
      "step": "feishu.sync_table",
      "params": {
        "input_key": "erp_rows",
        "table_id": "tblyAX9t4DJK2wuJ",
        "match_field": "平台订单号"
      }
    },
    {
      "step": "feishu.send_message",
      "params": {
        "template": "erp_sync_summary",
        "input_key": "sync_result"
      },
      "on_error": "skip"
    }
  ]
}
```

### 3.5 定时任务与工作流的融合

改造 `scheduler/manager.py`，定时任务触发工作流而非硬编码 handler：

```json
{
  "id": "pdd_erp_noon",
  "name": "拼多多 ERP 午间同步",
  "workflow": "pdd_erp_full_sync",
  "params": { "scroll_max_steps": 100 },
  "cron": "0 12 * * *"
}
```

### 3.6 步骤自动注册（插件发现）

新建 `src/workflow/registry.py`，自动扫描 `src/workflow/steps/` 目录下的所有步骤类并注册：

```python
class StepRegistry:
    _steps = {}

    def register(self, step_cls):
        self._steps[step_cls.name] = step_cls

    def get(self, name: str) -> BaseStep:
        cls = self._steps.get(name)
        if cls is None:
            raise ValueError(f"未知步骤: {name}")
        return cls()

    def auto_discover(self, package="workflow.steps"):
        """自动发现并注册所有 BaseStep 子类"""
        import importlib
        import pkgutil
        pkg = importlib.import_module(package)
        for _, module_name, _ in pkgutil.iter_modules(pkg.__path__):
            mod = importlib.import_module(f"{package}.{module_name}")
            for attr in dir(mod):
                cls = getattr(mod, attr)
                if isinstance(cls, type) and issubclass(cls, BaseStep) and cls is not BaseStep:
                    if cls.name:
                        self.register(cls)

    def list_steps(self) -> list:
        return [{"name": s.name, "display_name": s.display_name, "description": s.description}
                for s in self._steps.values()]
```

---

## 四、目录结构改造

```
src/
  workflow/                    # 新增：工作流引擎核心
    __init__.py
    step.py                    # BaseStep, StepContext, StepResult
    engine.py                  # WorkflowEngine
    registry.py                # StepRegistry 自动发现
    steps/                     # 原子步骤实现
      __init__.py
      pdd_steps.py             # pdd.check_login, pdd.scrape_erp_orders, ...
      tu_steps.py              # tu.login, tu.scrape_records
      feishu_steps.py          # feishu.sync_table, feishu.send_message, ...
      ali1688_steps.py         # ali1688.extract_orders
      cache_steps.py           # cache.save_json, cache.load_json

  workflows/                   # 新增：工作流定义（JSON）
    pdd_erp_full_sync.json
    pdd_address_sync.json
    tu_full_sync.json
    ...

  api/routes/
    workflow_routes.py         # 新增：工作流 CRUD + 执行 API
```

---

## 五、改造策略：渐进式迁移

为了不影响现有功能的稳定运行，建议**渐进式迁移**，分三个阶段：

### 阶段一：搭建工作流引擎框架（不改现有代码）

- 新建 `workflow/` 目录，实现 `BaseStep`、`StepContext`、`WorkflowEngine`、`StepRegistry`
- 新建第一批步骤（从现有代码提取逻辑，但保留原有代码不变）
- 新建工作流 API (`workflow_routes.py`)
- 工作流管理页面

### 阶段二：逐模块迁移

- 将 PDD ERP 同步迁移为工作流（最复杂的场景先做）
- 将途强同步迁移为工作流
- 将 1688 订单提取迁移为工作流
- 定时任务改为触发工作流

### 阶段三：清理与增强

- 移除旧的硬编码调用链
- 工具自动发现替代 `app.py` 硬编码注册
- 增加工作流可视化编排 UI（拖拽式）
- 增加工作流执行历史和日志

---

## 六、额外优化建议

### 6.1 代码质量

- `app.py` 中大量 `print()` 应替换为 `logger`（已有 logger 模块但 app.py 未使用）
- `erp_order_sync.py` 和 `order_address_sync.py` 各 270/560 行，职责混杂，拆分后可大幅精简

### 6.2 配置管理

- 飞书 table_id、app_token 等散落在 `Config`、环境变量、前端传参多处，应统一到工作流参数

### 6.3 错误处理

- 当前登录拦截的处理逻辑在多处重复（ERP 同步、地址同步），可抽取为 `pdd.check_login` 步骤统一处理

### 6.4 测试

- 步骤化后每个 Step 可独立单元测试（mock StepContext），比测试整条业务链路容易得多
