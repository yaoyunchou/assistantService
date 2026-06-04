# docs/next — 下一阶段规划总览

> **整理日期**: 2026-06-04  
> **状态**: 规划阶段，尚未实施  
> **背景**: 基于对现有架构的梳理，结合 AI 模块引入后的扩展需求，本目录记录下一阶段的改造方向与具体设计。

---

## 目录

1. [核心问题与改造动机](#1-核心问题与改造动机)
2. [目标架构：模块边界划分](#2-目标架构模块边界划分)
3. [各模块职责与边界规则](#3-各模块职责与边界规则)
4. [AI 模块融入方案](#4-ai-模块融入方案)
5. [本目录文件索引](#5-本目录文件索引)
6. [渐进迁移路线图](#6-渐进迁移路线图)

---

## 1. 核心问题与改造动机

### 1.1 当前耦合问题

**问题一：spider/ 同时承担三件事**

以 `erp_order_sync.py` 为典型，一个函数里混合了：
- 「怎么操作浏览器」（自动化执行）
- 「数据写到哪」（飞书表格同步）
- 「失败了怎么通知」（消息推送）

导致：想单独复用其中任意一个环节都做不到，任意一个逻辑改动都要动整个函数。

**问题二：飞书能力散落在多处**

```
tools/feishu/feishu_client.py         ← 基础 API 客户端
tools/feishu/feishu_table_client.py   ← 多维表格 CRUD
tools/feishu/message_sender.py        ← 消息发送
tools/feishu/webhook/notify.py        ← Webhook 通知
spider/pinduoduo/feishutable.py       ← 拼多多数据同步（在 spider 里！）
spider/tu/feishutable.py              ← 途强数据同步
```

飞书的「基础能力」和「业务同步逻辑」混杂，且横跨 `tools/` 和 `spider/` 两个目录。

**问题三：通知无统一入口**

任何模块都可以直接 import `FeishuMessageSender` 发消息，无法在中间插入 AI 分析过滤层。

**问题四：工具注册硬编码**

`app.py::init_tools()` 逐个 import 并注册每个工具，新增工具必须修改该文件。

**问题五：定时任务 handler 写死**

`scheduler/manager.py::get_task_handlers()` 返回静态字典，新增任务类型需改代码。

---

## 2. 目标架构：模块边界划分

```
src/
│
├── automation/          # 「会做什么」—— 只管操作外部系统，不关心数据去哪
│   ├── browser/         # 浏览器池（BrowserPool，从 spider/query_manager 迁移）
│   ├── pinduoduo/       # PDD client：登录、抓数据、操作页面（去除 feishutable）
│   ├── tu/              # TuClient：纯爬虫逻辑
│   └── ali1688/         # 1688 client：纯爬虫逻辑
│
├── workflow/            # 「做什么、按什么顺序」—— 编排原子能力
│   ├── step.py          # BaseStep, StepContext, StepResult
│   ├── engine.py        # WorkflowEngine
│   ├── registry.py      # StepRegistry 自动发现
│   ├── steps/           # 原子步骤实现
│   │   ├── automation_steps.py   # 调用 automation/ 的步骤
│   │   ├── storage_steps.py      # 调用 storage/ 的步骤
│   │   ├── notify_steps.py       # 调用 notify/ 的步骤
│   │   └── ai_steps.py           # 调用 ai/ 的步骤 ← AI 融入工作流
│   └── workflows/       # JSON 工作流配置文件
│
├── storage/             # 「数据存在哪」—— 纯数据读写，无业务逻辑
│   ├── feishu/          # FeishuTableClient（从 tools/feishu/ 迁移）
│   ├── local/           # JSON cache（从各模块 cache/ 统一）
│   └── dataset/         # 【预留】结构化历史数据、知识库 ← 数据集模块
│
├── notify/              # 「通知谁、用什么渠道」—— 统一通知出口
│   ├── __init__.py      # 对外只暴露 notify(event, context) 单一接口
│   ├── channels/
│   │   ├── feishu.py    # 飞书私聊/卡片渠道
│   │   └── webhook.py   # Webhook 渠道
│   └── filter.py        # AI 过滤层：分析是否值得通知 ← 小场景快速落地点
│
├── ai/                  # 「思考」—— 已建立，保持不变
│   ├── agent.py         # Cursor SDK Agent，含会话持久化
│   └── client.py        # OpenAI-compatible LLM client
│
├── scheduler/           # 「什么时候触发」—— 只触发 workflow，不写业务逻辑
├── api/                 # 「HTTP 接口」—— 薄层，参数校验 + 调用 workflow
├── web/                 # 「页面模板」
└── utils/               # 「工具函数」—— 纯工具，无业务依赖
```

---

## 3. 各模块职责与边界规则

| 模块 | 核心职责 | 只能调用 | 不能调用 |
|------|---------|---------|---------|
| `automation/` | 操作外部系统（浏览器/API） | `utils/`, `storage/local/` | `notify/`, `ai/`, `workflow/` |
| `storage/` | 数据读写（飞书表格/本地缓存） | `utils/` | `automation/`, `ai/`, `notify/` |
| `notify/` | 统一消息发送出口 | `ai/`, `storage/`, `utils/` | `automation/`, `workflow/` |
| `ai/` | AI 推理与 Agent 执行 | `utils/` | 任何业务模块（保持解耦） |
| `workflow/` | 编排所有模块，组合业务流程 | 所有模块 | — |
| `api/routes/` | HTTP 接口层 | `workflow/`, `scheduler/` | 不直接调 `automation/` |
| `scheduler/` | 定时触发 | `workflow/` | 不直接调 `automation/` |

**核心约束：**
- `automation/` 不主动触发通知，只返回结果给调用方（workflow）
- `api/` 和 `scheduler/` 不直接调爬虫，统一通过 `workflow/` 调度
- `notify/` 是系统中**唯一可以发消息**的出口

---

## 4. AI 模块融入方案

### 4.1 小场景：AI 过滤通知（快速落地，改动最小）

在 `notify/filter.py` 中，利用 `ai/` 模块对执行结果进行分析，决定是否值得通知：

```
任务执行完成
    ↓
notify.notify(event)         ← 统一入口
    ↓
filter.should_notify(event)  ← 调用 ai.ask() 分析
    ↓
True  → channel.send()       ← 发送通知
False → 记录日志，静默
```

适用场景：任务偶发性失败不需要每次都报警，由 AI 判断是否是真正需要关注的问题。

### 4.2 深度融入：AI 作为工作流步骤

在 `workflow/steps/ai_steps.py` 中定义 AI 分析步骤，可嵌入任意工作流：

```json
{
  "steps": [
    { "step": "pdd.scrape_erp_orders" },
    { "step": "ai.analyze_result", "params": { "prompt": "分析以下订单数据是否有异常" } },
    { "step": "feishu.sync_table", "condition": { "key": "ai_verdict", "equals": "normal" } },
    { "step": "notify.alert", "condition": { "key": "ai_verdict", "equals": "anomaly" } }
  ]
}
```

适用场景：AI 参与决策工作流走向，根据分析结果选择不同的后续步骤。

### 4.3 爬虫遇障接管（已实现）

当爬虫遇到验证码、页面变化等无法自动处理的情况，可以将当前浏览器状态（URL、cookies、截图）传给 AI Agent，由 Agent 接管后续操作：

```python
from ai import run_agent
result = run_agent(
    instruction="当前页面出现验证码，请帮我完成验证并继续订单抓取",
    browser_context={ "url": page.url, "cookies": cookies, "screenshot": screenshot_base64 }
)
```

---

## 5. 本目录文件索引

| 文件 | 内容 | 状态 |
|------|------|------|
| `README.md` | 本文件：下一阶段总体规划 | 规划中 |
| `workflow-engine-plan.md` | 工作流引擎详细设计方案（BaseStep/WorkflowEngine/StepRegistry 完整代码） | 详细设计完成，待实施 |
| `pinduoduo-erp-audit-feishu-table.md` | 飞书多维表格「ERP 审核记录表」字段定义与同步策略 | 已建表（`tblVgYVKU5DbyKdM`），待代码对接 |

---

## 6. 渐进迁移路线图

按影响范围从小到大，每步独立可验证：

### 第一步：统一通知入口（改动最小）
- 新建 `notify/` 模块，对外暴露单一 `notify()` 接口
- 将现有所有 `FeishuMessageSender`、`webhook/notify` 调用点替换为 `notify.notify()`
- 验证：所有通知功能不受影响
- **为 AI 过滤层预留接入点**

### 第二步：拆分 storage 层
- 将 `spider/pinduoduo/feishutable.py`、`spider/tu/feishutable.py` 迁移到 `storage/feishu/`
- `automation/` 层不再直接写飞书，只返回数据
- 验证：ERP 同步、途强同步功能不受影响

### 第三步：建立 workflow 骨架
- 参照 `workflow-engine-plan.md` 实现 `BaseStep`、`StepContext`、`WorkflowEngine`
- 将一个完整场景（建议选 ERP 订单同步，最复杂）迁移为工作流验证设计
- 定时任务改为触发 workflow，而非直接调 handler

### 第四步：AI 融入通知（完成小场景）
- 在 `notify/filter.py` 接入 `ai.ask()`，实现智能过滤
- 在 `workflow/steps/ai_steps.py` 中实现 `AIAnalysisStep`

### 第五步：dataset 模块（未来）
- 在 `storage/dataset/` 建立结构化执行历史存储
- 为 AI 提供历史上下文，提升分析质量
- 错误模式库、业务规则知识库
