"""淘宝商品 Playwright 自动上架模块。"""

__all__ = ['TaobaoPublishClient']


def __getattr__(name: str):
    if name == 'TaobaoPublishClient':
        from .client import TaobaoPublishClient
        return TaobaoPublishClient
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
