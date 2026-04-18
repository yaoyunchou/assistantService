# PyInstaller 打包规则（如意助手）

本项目使用 PyInstaller 6 **onedir** 模式打包。以下是开发和打包中必须遵守的规则，避免踩坑。

---

## 核心概念：`_internal` 目录

PyInstaller 6 onedir 模式下，`main.spec` 中 `datas` 声明的文件会被放到 `dist/如意助手/_internal/<目标路径>/`，**不是** `dist/如意助手/<目标路径>/`。

```
dist/如意助手/
├── 如意助手.exe            ← sys.executable
├── _internal/              ← PyInstaller 内嵌资源根目录
│   ├── config/
│   │   └── inventory_product_mapping.json   ← datas 目标 'config'
│   ├── scheduler/
│   │   └── tasks.toml                        ← datas 目标 'scheduler'
│   ├── spider/pinduoduo/scripts/
│   │   ├── pdd-erp-order-all-table.js        ← datas 目标 'spider/pinduoduo/scripts'
│   │   └── pdd-order-search-receiver.js
│   ├── web/templates/                        ← datas 目标 'web/templates'
│   ├── static/                               ← datas 目标 'static'
│   ├── config.py                             ← datas 目标 '.'
│   └── module_config.toml                    ← datas 目标 '.'
├── .env                    ← 打包后由 spec 脚本从项目根复制（不进 _internal）
└── playwright_drivers/     ← 打包后由 spec 脚本复制
```

---

## 规则 1：新增非 Python 资源文件必须加入 `main.spec` 的 `datas`

当代码中引用了非 `.py` 的文件（JS 脚本、JSON 配置、模板、图片等），必须在 `main.spec` 的 `Analysis.datas` 中声明，否则打包后找不到文件。

**检查方法**：搜索代码中所有通过 `Path(__file__)` 或硬编码路径引用的非 Python 文件，确认它们都在 `datas` 列表中。

**反面案例**：`erp_order_sync.py` 通过 `Path(__file__).parent / 'scripts' / 'pdd-erp-order-all-table.js'` 引用 JS 脚本，但 `datas` 中遗漏了 `scripts/` 目录，打包后报 `FileNotFoundError`。

---

## 规则 2：读取「只读内嵌资源」用 `get_bundled_data_root()`，不是 `get_project_root()`

| 函数 | frozen 返回值 | 用途 |
|------|--------------|------|
| `get_project_root()` | `exe_dir/` | 读写 exe 同目录的用户可编辑文件 |
| `get_bundled_data_root()` | `exe_dir/_internal/`（优先） | 读取打包内嵌的只读默认文件 |
| `get_safe_data_path(rel)` | `exe_dir/rel`（有写权限时） | 获取可写数据路径 |

**错误做法**：
```python
# ✗ 打包后找 exe_dir/config/xxx.json，实际在 _internal/config/
default = get_project_root() / 'config' / 'xxx.json'
```

**正确做法**：
```python
# ✓ 打包后找 _internal/config/xxx.json
from utils.path_helper import get_bundled_data_root
default = get_bundled_data_root() / 'config' / 'xxx.json'
```

**什么时候用哪个**：
- 读取打包自带的**默认/种子**文件 → `get_bundled_data_root()`
- 读写用户运行时**可修改**的文件 → `get_safe_data_path()` 或 `get_project_root()`
- 通过 `Path(__file__)` 引用同包资源（如 JS 脚本） → 自动正确，因为 `__file__` 在 `_internal` 下

---

## 规则 3：`.env` 不进 bundle，需额外处理

`.env` 含敏感密钥，**不**放入 `datas`；而是在 `main.spec` 末尾的 `copy_dotenv_to_dist()` 中，打包完成后从项目根复制到 `dist/如意助手/`。

**注意事项**：
- 项目根必须有 `.env` 文件，打包时才会自动复制
- Inno Setup `setup.iss` 当前**未**把 `.env` 打入安装包，安装后用户需自行配置
- 运行时 `config.py` 按顺序搜索：`exe_dir/.env` → `cwd/.env`

---

## 规则 4：新增代码引用外部文件的自查清单

每次新增或修改「代码引用非 Python 文件」的场景时，按以下清单逐项检查：

- [ ] 文件是否已加入 `main.spec` 的 `datas`？
- [ ] `datas` 的目标路径是否与代码中的引用路径一致？
- [ ] 若通过 `get_project_root()` 读取，是否应改为 `get_bundled_data_root()`？
- [ ] 开发环境（`sys.frozen=False`）和打包环境（`sys.frozen=True`）是否都能正确找到文件？
- [ ] 如果文件需要用户编辑，是否有「只读默认 + 可写覆盖」的合并逻辑？

---

## 规则 5：`build.bat` 打包后务必验证

打包完成后，至少检查以下内容是否存在于 `dist/如意助手/_internal/` 下：

```
_internal/config/inventory_product_mapping.json
_internal/scheduler/tasks.toml
_internal/spider/pinduoduo/scripts/pdd-erp-order-all-table.js
_internal/spider/pinduoduo/scripts/pdd-order-search-receiver.js
_internal/web/templates/
_internal/static/
_internal/module_config.toml
_internal/config.py
```

以及 `dist/如意助手/` 根目录下：
```
.env（若项目根有）
playwright_drivers/
```
