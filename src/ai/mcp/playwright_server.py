"""
AI 大脑 — Playwright MCP stdio 服务器
实现 MCP（Model Context Protocol）stdio 传输协议，暴露 7 个 Playwright 浏览器工具。
由 cursor_sdk.Agent 通过 StdioMcpServerConfig 以子进程方式启动。

支持功能：
  - 启动时从 AI_COOKIES_DIR 加载业务 Cookie（共享登录态）
  - 支持爬虫移交协议（AI_BROWSER_CONTEXT_FILE 指定的上下文文件）
  - 通过 CHROME_EXECUTABLE_PATH 使用项目统一的浏览器驱动

工具列表：
  navigate    导航到 URL（可选加载 Cookie profile）
  screenshot  截图，返回 base64 PNG
  click       点击元素
  fill        填写表单字段
  evaluate    执行 JavaScript 并返回结果
  get_text    获取元素文本内容
  wait_for    等待元素出现
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger('ai.mcp.playwright')

# ─────────────────────────────────────────────────────────────
# MCP 工具定义
# ─────────────────────────────────────────────────────────────
TOOLS = [
    {
        'name': 'navigate',
        'description': '导航到指定 URL。可选指定 cookie_profile（如 pinduoduo）自动加载该业务的登录 Cookie。',
        'inputSchema': {
            'type': 'object',
            'properties': {
                'url': {'type': 'string', 'description': '目标 URL'},
                'cookie_profile': {
                    'type': 'string',
                    'description': '可选，加载指定业务 Cookie（如 pinduoduo / tu）',
                },
            },
            'required': ['url'],
        },
    },
    {
        'name': 'screenshot',
        'description': '对当前页面截图，返回 base64 编码的 PNG 图片。',
        'inputSchema': {
            'type': 'object',
            'properties': {
                'full_page': {
                    'type': 'boolean',
                    'description': '是否截取完整页面（默认 false，仅视窗）',
                },
            },
        },
    },
    {
        'name': 'click',
        'description': '点击页面上的元素。',
        'inputSchema': {
            'type': 'object',
            'properties': {
                'selector': {'type': 'string', 'description': 'CSS 选择器或 XPath'},
            },
            'required': ['selector'],
        },
    },
    {
        'name': 'fill',
        'description': '在表单字段或可编辑元素中填写文本。',
        'inputSchema': {
            'type': 'object',
            'properties': {
                'selector': {'type': 'string', 'description': 'CSS 选择器'},
                'value': {'type': 'string', 'description': '要填写的文本'},
            },
            'required': ['selector', 'value'],
        },
    },
    {
        'name': 'evaluate',
        'description': '在页面中执行 JavaScript 代码，返回执行结果（JSON 序列化）。',
        'inputSchema': {
            'type': 'object',
            'properties': {
                'script': {'type': 'string', 'description': 'JavaScript 代码'},
            },
            'required': ['script'],
        },
    },
    {
        'name': 'get_text',
        'description': '获取元素的文本内容。',
        'inputSchema': {
            'type': 'object',
            'properties': {
                'selector': {'type': 'string', 'description': 'CSS 选择器'},
            },
            'required': ['selector'],
        },
    },
    {
        'name': 'wait_for',
        'description': '等待选择器匹配的元素出现在页面上。',
        'inputSchema': {
            'type': 'object',
            'properties': {
                'selector': {'type': 'string', 'description': 'CSS 选择器'},
                'timeout': {
                    'type': 'number',
                    'description': '超时毫秒数（默认 30000）',
                },
            },
            'required': ['selector'],
        },
    },
]


# ─────────────────────────────────────────────────────────────
# 浏览器状态（模块级单例）
# ─────────────────────────────────────────────────────────────
_playwright = None
_browser = None
_context = None
_page = None


async def _ensure_browser() -> None:
    """确保浏览器已启动（懒加载）"""
    global _playwright, _browser, _context, _page

    if _page is not None:
        return

    from playwright.async_api import async_playwright

    chrome_path = os.environ.get('CHROME_EXECUTABLE_PATH', '') or None
    _playwright = await async_playwright().start()

    launch_kwargs: Dict[str, Any] = {
        'headless': True,
        'args': ['--no-sandbox', '--disable-dev-shm-usage'],
    }
    if chrome_path:
        launch_kwargs['executable_path'] = chrome_path

    _browser = await _playwright.chromium.launch(**launch_kwargs)
    _context = await _browser.new_context(
        viewport={'width': 1280, 'height': 800},
        user_agent=(
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/120.0.0.0 Safari/537.36'
        ),
    )

    # 加载爬虫移交协议的 cookies（优先）
    ctx_file = os.environ.get('AI_BROWSER_CONTEXT_FILE', '')
    if ctx_file and Path(ctx_file).exists():
        try:
            ctx_data = json.loads(Path(ctx_file).read_text(encoding='utf-8'))
            if ctx_data.get('cookies'):
                await _context.add_cookies(ctx_data['cookies'])
                logger.info('已加载移交协议 cookies（%d 条）', len(ctx_data['cookies']))
        except Exception as e:
            logger.warning('加载移交协议 cookies 失败: %s', e)

    _page = await _context.new_page()
    logger.info('Playwright 浏览器已启动')


def _find_cookie_file(profile: str) -> Optional[Path]:
    """在 AI_COOKIES_DIR 下查找指定 profile 的 cookie 文件"""
    cookies_dir = os.environ.get('AI_COOKIES_DIR', '')
    if not cookies_dir:
        return None
    base = Path(cookies_dir)
    candidates = [
        base / profile / 'cookies.json',
        base / f'{profile}_cookies.json',
        base / f'{profile}.cookies.json',
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


async def _load_profile_cookies(profile: str) -> int:
    """加载指定业务的 Cookie，返回加载条数"""
    global _context
    if _context is None:
        return 0
    f = _find_cookie_file(profile)
    if not f:
        logger.warning('未找到 %s 的 Cookie 文件', profile)
        return 0
    try:
        raw = json.loads(f.read_text(encoding='utf-8'))
        # 兼容不同格式：直接列表 or {"cookies": [...]}
        cookies = raw if isinstance(raw, list) else raw.get('cookies', [])
        if cookies:
            await _context.add_cookies(cookies)
            logger.info('已加载 %s cookies（%d 条）', profile, len(cookies))
            return len(cookies)
    except Exception as e:
        logger.warning('加载 %s cookies 失败: %s', profile, e)
    return 0


# ─────────────────────────────────────────────────────────────
# 工具实现
# ─────────────────────────────────────────────────────────────

async def _tool_navigate(url: str, cookie_profile: str = '') -> str:
    await _ensure_browser()
    if cookie_profile:
        await _load_profile_cookies(cookie_profile)
    await _page.goto(url, wait_until='domcontentloaded', timeout=30000)
    title = await _page.title()
    return f'已导航到: {url}\n页面标题: {title}'


async def _tool_screenshot(full_page: bool = False) -> str:
    await _ensure_browser()
    png_bytes = await _page.screenshot(full_page=full_page)
    b64 = base64.b64encode(png_bytes).decode()
    return f'data:image/png;base64,{b64}'


async def _tool_click(selector: str) -> str:
    await _ensure_browser()
    await _page.click(selector, timeout=10000)
    return f'已点击: {selector}'


async def _tool_fill(selector: str, value: str) -> str:
    await _ensure_browser()
    await _page.fill(selector, value)
    return f'已填写 {selector}: {value[:50]}{"..." if len(value) > 50 else ""}'


async def _tool_evaluate(script: str) -> str:
    await _ensure_browser()
    result = await _page.evaluate(script)
    return json.dumps(result, ensure_ascii=False, default=str)


async def _tool_get_text(selector: str) -> str:
    await _ensure_browser()
    text = await _page.text_content(selector, timeout=10000)
    return text or ''


async def _tool_wait_for(selector: str, timeout: float = 30000) -> str:
    await _ensure_browser()
    await _page.wait_for_selector(selector, timeout=timeout)
    return f'元素已出现: {selector}'


async def _dispatch_tool(name: str, arguments: Dict) -> str:
    """分发工具调用"""
    try:
        if name == 'navigate':
            return await _tool_navigate(
                arguments['url'],
                arguments.get('cookie_profile', ''),
            )
        elif name == 'screenshot':
            return await _tool_screenshot(arguments.get('full_page', False))
        elif name == 'click':
            return await _tool_click(arguments['selector'])
        elif name == 'fill':
            return await _tool_fill(arguments['selector'], arguments['value'])
        elif name == 'evaluate':
            return await _tool_evaluate(arguments['script'])
        elif name == 'get_text':
            return await _tool_get_text(arguments['selector'])
        elif name == 'wait_for':
            return await _tool_wait_for(
                arguments['selector'],
                arguments.get('timeout', 30000),
            )
        else:
            return f'未知工具: {name}'
    except Exception as e:
        logger.error('工具 %s 执行失败: %s', name, e, exc_info=True)
        return f'工具执行失败: {e}'


# ─────────────────────────────────────────────────────────────
# MCP stdio 协议处理
# ─────────────────────────────────────────────────────────────

async def _send(obj: Dict) -> None:
    """向 stdout 发送 JSON-RPC 响应"""
    line = json.dumps(obj, ensure_ascii=False)
    sys.stdout.write(line + '\n')
    sys.stdout.flush()


async def _handle_request(req: Dict) -> None:
    method = req.get('method', '')
    req_id = req.get('id')
    params = req.get('params', {})

    if method == 'initialize':
        await _send({
            'jsonrpc': '2.0',
            'id': req_id,
            'result': {
                'protocolVersion': '2024-11-05',
                'capabilities': {'tools': {}},
                'serverInfo': {'name': 'playwright', 'version': '1.0.0'},
            },
        })

    elif method == 'notifications/initialized':
        pass  # 无需回复

    elif method == 'tools/list':
        await _send({
            'jsonrpc': '2.0',
            'id': req_id,
            'result': {'tools': TOOLS},
        })

    elif method == 'tools/call':
        tool_name = params.get('name', '')
        arguments = params.get('arguments', {})
        result_text = await _dispatch_tool(tool_name, arguments)

        # screenshot 工具返回图片内容
        if tool_name == 'screenshot' and result_text.startswith('data:image'):
            b64_data = result_text.split(',', 1)[1] if ',' in result_text else result_text
            content = [
                {'type': 'image', 'data': b64_data, 'mimeType': 'image/png'},
            ]
        else:
            content = [{'type': 'text', 'text': result_text}]

        await _send({
            'jsonrpc': '2.0',
            'id': req_id,
            'result': {'content': content},
        })

    else:
        if req_id is not None:
            await _send({
                'jsonrpc': '2.0',
                'id': req_id,
                'error': {'code': -32601, 'message': f'未知方法: {method}'},
            })


async def _main() -> None:
    """主循环：从 stdin 读取 JSON-RPC 请求，处理后写回 stdout"""
    logger.info('Playwright MCP 服务器启动')
    loop = asyncio.get_event_loop()

    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)

    while True:
        try:
            line_bytes = await reader.readline()
            if not line_bytes:
                break
            line = line_bytes.decode('utf-8').strip()
            if not line:
                continue
            req = json.loads(line)
            await _handle_request(req)
        except json.JSONDecodeError as e:
            logger.warning('JSON 解析失败: %s', e)
        except Exception as e:
            logger.error('请求处理异常: %s', e, exc_info=True)

    # 清理
    global _playwright, _browser
    if _browser:
        await _browser.close()
    if _playwright:
        await _playwright.stop()
    logger.info('Playwright MCP 服务器关闭')


if __name__ == '__main__':
    asyncio.run(_main())
