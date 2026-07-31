"""闲鱼（Goofish）卖家工作台自动化模块。

分层：
    config.py        URL / 选择器 / mtop 接口名 / 缺省值（集中配置，改版单点修正）
    mtop_bridge.py   在页面上下文直调 mtop（数据获取主路径）
    page_guard.py    登录判定、业务 iframe 定位、窗口辅助
    login_gate.py    ensure_logged_in 登录门禁
    browser_visible.py  操作前切可见窗口并打开后台
    api_probe.py     运行时接口探测（补全登录后才可见的接口）
    item_list.py     在线商品列表（mtop 直调 + DOM 兜底）
    data/            Excel 队列加载与回填
    flows/           发布与管理编排
    pages/           Page Object

对外统一从 client.GoofishClient 调用。
"""
from __future__ import annotations

__all__ = ['GoofishClient']


def __getattr__(name: str):
    # 懒加载，避免导入本包就拉起 playwright / openpyxl
    if name == 'GoofishClient':
        from spider.goofish.client import GoofishClient
        return GoofishClient
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
