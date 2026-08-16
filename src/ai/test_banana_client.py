"""
Banana Agent AI 接口测试用例

运行方式：
    cd src
    python -m ai.test_banana_client            # pytest 风格（若装了 pytest）
    python ai/test_banana_client.py            # 直接运行（无需 pytest）

测试分层：
- 离线测试（不依赖网络/AK）：响应解析、图片转 data URL
- 在线测试（依赖 BANANA_AI_AK + 网络）：纯文本问答、多模态识图、流式、run_agent
  未配置 AK 时在线测试自动跳过（标记 SKIP），不会报错。
"""
from __future__ import annotations

import base64
import os
import sys
import tempfile
import unittest
from pathlib import Path

# 确保能 import src 下的包
_SRC_DIR = Path(__file__).resolve().parent.parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))


# 1x1 红色 PNG（base64），用于多模态测试，避免依赖外部图片文件
_TINY_RED_PNG_B64 = (
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=='
)


def _ak_configured() -> bool:
    """检查 BANANA_AI_AK 是否已配置（从 Config 读取，与生产路径一致）。"""
    try:
        from config import Config  # noqa: PLC0415
        return bool((getattr(Config, 'BANANA_AI_AK', '') or '').strip())
    except Exception:
        return bool((os.getenv('BANANA_AI_AK') or '').strip())


# ─────────────────────────────────────────────────────────────
# 离线测试：响应解析
# ─────────────────────────────────────────────────────────────
class ExtractTextTest(unittest.TestCase):
    """`banana_client._extract_text` 解析逻辑（不依赖网络）。"""

    def test_plain_result(self):
        from ai.banana_client import _extract_text
        self.assertEqual(_extract_text({'success': True, 'result': 'hello'}), 'hello')

    def test_string_top(self):
        from ai.banana_client import _extract_text
        self.assertEqual(_extract_text('直接是字符串'), '直接是字符串')

    def test_data_string(self):
        from ai.banana_client import _extract_text
        self.assertEqual(_extract_text({'success': True, 'data': 'world'}), 'world')

    def test_data_nested_object(self):
        from ai.banana_client import _extract_text
        self.assertEqual(
            _extract_text({'success': True, 'data': {'content': 'nested'}}),
            'nested',
        )

    def test_openai_choices_fallback(self):
        from ai.banana_client import _extract_text
        payload = {'choices': [{'message': {'content': 'openai-style'}}]}
        self.assertEqual(_extract_text(payload), 'openai-style')

    def test_success_false_raises(self):
        from ai.banana_client import _extract_text
        with self.assertRaises(RuntimeError) as ctx:
            _extract_text({'success': False, 'error': '鉴权失败'})
        self.assertIn('鉴权失败', str(ctx.exception))

    def test_empty_payload_returns_empty(self):
        """`_extract_text` 对无文本字段返回空串（由 `banana_ask` 层抛 RuntimeError）。"""
        from ai.banana_client import _extract_text
        self.assertEqual(_extract_text({'success': True, 'unrelated': 'x'}), '')

    def test_banana_ask_raises_on_empty_response(self):
        """`banana_ask` 在响应无文本时抛 RuntimeError（mock AK + HTTP）。"""
        from ai import banana_client
        from ai.banana_client import banana_ask

        original_ak = banana_client._resolve_ak
        original_post = banana_client._http_post_json
        banana_client._resolve_ak = lambda: 'ak_fake_test'
        banana_client._http_post_json = lambda url, body, *, headers, timeout: {'success': True, 'unrelated': 'x'}
        try:
            with self.assertRaises(RuntimeError) as ctx:
                banana_ask('hi', timeout=5)
            self.assertIn('无文本内容', str(ctx.exception))
        finally:
            banana_client._resolve_ak = original_ak
            banana_client._http_post_json = original_post

    def test_banana_ask_success_false_raises(self):
        """`banana_ask` 在 success=false 时抛 RuntimeError（mock AK + HTTP）。"""
        from ai import banana_client
        from ai.banana_client import banana_ask

        original_ak = banana_client._resolve_ak
        original_post = banana_client._http_post_json
        banana_client._resolve_ak = lambda: 'ak_fake_test'
        banana_client._http_post_json = lambda url, body, *, headers, timeout: {'success': False, 'error': '鉴权失败'}
        try:
            with self.assertRaises(RuntimeError) as ctx:
                banana_ask('hi', timeout=5)
            self.assertIn('鉴权失败', str(ctx.exception))
        finally:
            banana_client._resolve_ak = original_ak
            banana_client._http_post_json = original_post

    def test_banana_ask_builds_body_with_images(self):
        """`banana_ask` 多模态请求体用 images[{dataUrl}]（mock AK + HTTP 捕获 body）。"""
        from ai import banana_client
        from ai.banana_client import banana_ask

        captured = {}
        original_ak = banana_client._resolve_ak
        original_post = banana_client._http_post_json
        banana_client._resolve_ak = lambda: 'ak_fake_test'

        def _capture(url, body, *, headers, timeout):
            captured['body'] = body
            captured['headers'] = headers
            return {'success': True, 'result': 'ok'}

        banana_client._http_post_json = _capture
        try:
            raw = base64.b64decode(_TINY_RED_PNG_B64)
            banana_ask('描述图片', system='你是助手', images=[raw], timeout=5)
            # 多模态走 prompt + system + images[{dataUrl}]
            self.assertEqual(captured['body']['prompt'], '描述图片')
            self.assertEqual(captured['body']['system'], '你是助手')
            self.assertIn('images', captured['body'])
            self.assertEqual(len(captured['body']['images']), 1)
            self.assertTrue(captured['body']['images'][0]['dataUrl'].startswith('data:image/png;base64,'))
            self.assertNotIn('message', captured['body'])
            self.assertEqual(captured['headers']['Authorization'], 'Bearer ak_fake_test')
        finally:
            banana_client._resolve_ak = original_ak
            banana_client._http_post_json = original_post

    def test_banana_ask_remote_url_uses_url_field(self):
        """远程 http(s) URL 用 url 字段，非 dataUrl 字段。"""
        from ai import banana_client
        from ai.banana_client import banana_ask

        captured = {}
        original_ak = banana_client._resolve_ak
        original_post = banana_client._http_post_json
        banana_client._resolve_ak = lambda: 'ak_fake_test'
        banana_client._http_post_json = lambda url, body, *, headers, timeout: (
            captured.update({'body': body}) or {'success': True, 'result': 'ok'}
        )
        try:
            banana_ask('看图', images=['https://example.com/a.jpg'], timeout=5)
            self.assertEqual(captured['body']['images'][0], {'url': 'https://example.com/a.jpg'})
        finally:
            banana_client._resolve_ak = original_ak
            banana_client._http_post_json = original_post

    def test_banana_ask_text_uses_prompt_system(self):
        """`banana_ask` 纯文本请求体用 prompt / system 简单格式（mock AK + HTTP）。"""
        from ai import banana_client
        from ai.banana_client import banana_ask

        captured = {}
        original_ak = banana_client._resolve_ak
        original_post = banana_client._http_post_json
        banana_client._resolve_ak = lambda: 'ak_fake_test'
        banana_client._http_post_json = lambda url, body, *, headers, timeout: (
            captured.update({'body': body}) or {'success': True, 'result': 'ok'}
        )
        try:
            banana_ask('你好', system='是助手', timeout=5)
            self.assertEqual(captured['body'], {'prompt': '你好', 'system': '是助手'})
            self.assertNotIn('message', captured['body'])
            self.assertNotIn('images', captured['body'])
        finally:
            banana_client._resolve_ak = original_ak
            banana_client._http_post_json = original_post

    def test_field_priority_result_over_message(self):
        """result 优先于 message/msg。"""
        from ai.banana_client import _extract_text
        payload = {'success': True, 'result': '优先取这个', 'message': '不取这个'}
        self.assertEqual(_extract_text(payload), '优先取这个')


# ─────────────────────────────────────────────────────────────
# 离线测试：图片转 data URL
# ─────────────────────────────────────────────────────────────
class ImageToDataUrlTest(unittest.TestCase):
    """`banana_client._image_to_data_url`（不依赖网络）。"""

    def test_bytes_to_data_url(self):
        from ai.banana_client import _image_to_data_url
        raw = base64.b64decode(_TINY_RED_PNG_B64)
        url = _image_to_data_url(raw)
        self.assertTrue(url.startswith('data:image/png;base64,'))
        self.assertIn(_TINY_RED_PNG_B64, url)

    def test_remote_url_passthrough(self):
        from ai.banana_client import _image_to_data_url
        self.assertEqual(
            _image_to_data_url('https://example.com/a.jpg'),
            'https://example.com/a.jpg',
        )

    def test_data_url_passthrough(self):
        from ai.banana_client import _image_to_data_url
        src = 'data:image/png;base64,xxxx'
        self.assertEqual(_image_to_data_url(src), src)

    def test_local_file_png(self):
        from ai.banana_client import _image_to_data_url
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'shot.png'
            p.write_bytes(base64.b64decode(_TINY_RED_PNG_B64))
            url = _image_to_data_url(p)
            self.assertTrue(url.startswith('data:image/png;base64,'))

    def test_local_file_jpg_mime(self):
        from ai.banana_client import _image_to_data_url
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'pic.jpg'
            p.write_bytes(b'\xff\xd8\xff\xe0')  # 假 jpg 头
            url = _image_to_data_url(p)
            self.assertTrue(url.startswith('data:image/jpeg;base64,'))


# ─────────────────────────────────────────────────────────────
# 离线测试：AK / API base 解析
# ─────────────────────────────────────────────────────────────
class ConfigResolveTest(unittest.TestCase):
    """`_resolve_api_base` 默认值（不依赖网络）。"""

    def test_default_api_base(self):
        from ai.banana_client import _resolve_api_base, DEFAULT_API_BASE
        # 若 .env 未配 BANANA_AI_API_BASE，应回落默认
        try:
            from config import Config  # noqa: PLC0415
            if getattr(Config, 'BANANA_AI_API_BASE', '').strip():
                self.assertEqual(_resolve_api_base(), Config.BANANA_AI_API_BASE.strip().rstrip('/'))
            else:
                self.assertEqual(_resolve_api_base(), DEFAULT_API_BASE)
        except Exception:
            self.assertEqual(_resolve_api_base(), DEFAULT_API_BASE)

    def test_ask_path_constant(self):
        from ai.banana_client import ASK_PATH
        self.assertEqual(ASK_PATH, '/agent/ask/')


# ─────────────────────────────────────────────────────────────
# 在线测试：实际调用 Banana Agent（依赖 BANANA_AI_AK + 网络）
# ─────────────────────────────────────────────────────────────
class OnlineBananaTest(unittest.TestCase):
    """在线集成测试。未配置 AK 时整组跳过。"""

    def setUp(self):
        if not _ak_configured():
            self.skipTest('BANANA_AI_AK 未配置，跳过在线测试')

    def test_ask_text(self):
        """纯文本问答：让模型回答一个确定性问题。"""
        from ai import ask
        reply = ask('请只回复两个字：你好', max_tokens=20)
        self.assertIsInstance(reply, str)
        self.assertTrue(len(reply) > 0)
        print(f'\n[ask 文本] 回复: {reply!r}')

    def test_ask_with_system(self):
        """带 system 提示词的问答。"""
        from ai import ask
        reply = ask(
            '1+1=?',
            system='你是一个只输出数字的助手，禁止任何解释',
            max_tokens=10,
        )
        self.assertIsInstance(reply, str)
        self.assertTrue(len(reply) > 0)
        print(f'\n[ask+system] 回复: {reply!r}')

    def test_ask_vision_local_bytes(self):
        """多模态识图：传 bytes（1x1 红点 PNG）。"""
        from ai import ask_vision
        raw = base64.b64decode(_TINY_RED_PNG_B64)
        reply = ask_vision(
            '这张图片的主色调是什么？用中文一句话回答',
            raw,
            max_tokens=50,
        )
        self.assertIsInstance(reply, str)
        self.assertTrue(len(reply) > 0)
        print(f'\n[ask_vision bytes] 回复: {reply!r}')

    def test_ask_vision_local_file(self):
        """多模态识图：传本地文件路径。"""
        from ai import ask_vision
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'shot.png'
            p.write_bytes(base64.b64decode(_TINY_RED_PNG_B64))
            reply = ask_vision(
                '请用中文一句话描述这张图',
                p,
                max_tokens=50,
            )
            self.assertIsInstance(reply, str)
            self.assertTrue(len(reply) > 0)
            print(f'\n[ask_vision file] 回复: {reply!r}')

    def test_ask_stream(self):
        """流式（一次 yield）。"""
        from ai import ask_stream
        chunks = list(ask_stream('请只回复两个字：测试', max_tokens=20))
        self.assertGreater(len(chunks), 0)
        joined = ''.join(chunks)
        self.assertTrue(len(joined) > 0)
        print(f'\n[ask_stream] 共 {len(chunks)} 段, 合并: {joined!r}')

    def test_run_agent_plain(self):
        """run_agent 纯文本。"""
        from ai import run_agent
        result = run_agent('请只回复四个字：智能助手', tools=[])
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)
        print(f'\n[run_agent] 回复: {result!r}')

    def test_run_agent_with_browser_context_url(self):
        """run_agent 带 browser_context.url（拼到 instruction 前）。"""
        from ai import run_agent
        result = run_agent(
            '请只回复：已收到URL',
            browser_context={'url': 'https://example.com/demo'},
        )
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)
        print(f'\n[run_agent+url] 回复: {result!r}')

    def test_run_agent_with_screenshot_b64(self):
        """run_agent 带 screenshot_b64（多模态）。"""
        from ai import run_agent
        result = run_agent(
            '请用中文一句话描述这张截图',
            browser_context={'screenshot_b64': f'data:image/png;base64,{_TINY_RED_PNG_B64}'},
        )
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)
        print(f'\n[run_agent+screenshot] 回复: {result!r}')

    def test_ak_not_leaked_in_error(self):
        """AK 不应出现在正常返回或异常文本里。"""
        from ai import ask
        from config import Config  # noqa: PLC0415
        ak = (getattr(Config, 'BANANA_AI_AK', '') or '').strip()
        if not ak:
            self.skipTest('AK 未配置')
        reply = ask('请回复：OK', max_tokens=10)
        self.assertNotIn(ak, reply)


if __name__ == '__main__':
    unittest.main(verbosity=2)
