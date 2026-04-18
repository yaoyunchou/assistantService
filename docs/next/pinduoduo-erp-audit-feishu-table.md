# 飞书多维表格：拼多多 ERP 审核记录表（设计说明）

在飞书「多维表格」中**新建一张数据表**（或新 Base 中创建），用于接收本应用同步的 **ERP 待审核页** 已审核订单记录。将建表完成后的 `table_id` 配置为环境变量 `PINDUODUO_ERP_AUDIT_FEISHU_TABLE_ID`（与 `PINDUODUO_FEISHU_APP_TOKEN` 对应同一应用）。

## 已建表（Base「夕夕单」）

| 项 | 值 |
|----|-----|
| `app_token` | `ORSHbpajoaANQ4sFg25c917jnTc`（与历史记录中「夕夕单」Base 一致） |
| 数据表名 | 拼多多ERP审核记录 |
| `table_id` | `tblVgYVKU5DbyKdM` |
| 打开链接 | <https://fve8bmmwllf.feishu.cn/base/ORSHbpajoaANQ4sFg25c917jnTc?table=tblVgYVKU5DbyKdM> |
| 建表脚本 | `20260222多维表格运维/create-pdd-erp-audit-table.js`（2026-04-18 已执行） |

环境变量：`PINDUODUO_ERP_AUDIT_FEISHU_TABLE_ID=tblVgYVKU5DbyKdM`。应用侧多维表格一般还需要 Base 的 `app_token`（即上表中的 `ORSHbpajoaANQ4sFg25c917jnTc`），变量名可与项目现有 `PINDUODUO_FEISHU_APP_TOKEN` 等对齐，**勿与表格行 `record` 里的 `token` 类概念混用**。

## 列定义（与代码写入一致）

| 列名 | 类型 | 说明 |
|------|------|------|
| 平台订单号 | 文本 | 主键展示；拼多多平台订单号 |
| 审核完成时间 | 日期时间 | **Unix 毫秒时间戳**（与 ERP 订单表「付款时间」等日期时间列用法一致） |
| 审核日期 | 文本或日期 | 可选；本地日期 `YYYY-MM-DD`，也可用公式由「审核完成时间」推导后删除该列避免双写 |
| 商品摘要 | 多行文本 | 每条 SKU 一行：`标题 规格 ×数量` |
| 标题 | 文本 | 可选；与摘要同行结构对应，便于筛选；多 SKU 时可仅存首行或与摘要二选一 |
| 规格 | 文本 | 可选；SKU 规格文案 |
| 数量 | **数字（整数）** | 可选；件数，Bitable 字段类型为「数字」。多 SKU 时可与「商品摘要」二选一：本列存**首行 SKU 件数**或订单**总件数**，由代码统一约定 |
| 商品图片 | 文本 | 可选；主图或规格图 URL，多条可换行、英文逗号或 JSON 字符串等，与写入代码约定一致 |
| 商品明细JSON | 多行文本 | 可选；`goods` 数组 JSON，便于排查 |
| 来源 | 文本 | 代码固定写入 `ERP审核页` |

若表中未创建某一可选列，请在飞书控制台建同名列后再同步；否则会 `FieldNameNotFound`。首次使用建议先创建上表全部列。

### 拆列与代码约定（标题 / 规格 / 数量 / 商品图片）

- **不影响业务逻辑**：审核 API、SQLite 结构不变；仅飞书 `records.fields` 多写四个字段。
- **标题 / 规格**：取 **`goods[0]`（首行 SKU）** 的 `title`、`spec`，与文档「多 SKU 时仅存首行」一致。
- **数量**：取 **所有 SKU 的 `qty` 整数之和**（订单总件数）；飞书列类型须为「数字」，代码传 **整数**。
- **商品图片**：取各 SKU 的 `imgSrc` 非空值，**英文逗号**拼接（多条 URL）；过长会截断。
- 若你希望「数量」表示首行 SKU 件数而非合计，需在代码中改 `_audit_goods_split_fields`（`feishutable.py`）。

### 开放平台写入格式（节选）

写入 `records[].fields` 时除文本可直接传字符串外，常见类型如下（列名即上表「列名」，须与表中完全一致）：

| 列名 | 写入示例（JSON 片段） |
|------|------------------------|
| 审核完成时间 | `{ "审核完成时间": 1735689600000 }`（Unix **毫秒**，与日期时间字段约定一致） |
| 数量 | `{ "数量": 3 }` 或 `{ "数量": { "number": 3 } }`（以当前多维表格 SDK 为准；语义为**整数件数**） |

## 同步策略

- 应用在向 ERP 提交审核成功并将记录写入本地 SQLite 后，若已配置 `PINDUODUO_ERP_AUDIT_FEISHU_TABLE_ID`，则**追加创建**飞书记录（不做按订单号更新，日志型）。
- 未推送成功的记录可通过 API `POST /api/pinduoduo/erp-audit/sync-feishu` 补传（读取本地未同步标记）。

## 本地存储

- SQLite 路径默认：`get_safe_data_path('data/pdd_erp_audit.sqlite')`，也可用 `PINDUODUO_ERP_AUDIT_DB_PATH` 指定绝对路径。
