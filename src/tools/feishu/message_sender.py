"""
飞书消息发送器
提供更高层的消息发送接口和消息模板管理
"""
import os
from typing import Optional, Dict, Any, Union
from .feishu_client import FeishuClient
from config import Config
from utils.logger import get_logger

logger = get_logger('FeishuMessageSender')


def _is_valid_feishu_user_id(user_id: Optional[str]) -> bool:
    """
    飞书 user_id/open_id 格式：open_id 通常为 ou_ 开头且较长，user_id 为较长数字串。
    过短或纯短数字（如工号 1848）会被 API 拒绝。
    """
    if not user_id or not isinstance(user_id, str):
        return False
    s = user_id.strip()
    if len(s) < 10:
        return False
    if s.startswith("ou_"):
        return True
    if s.isdigit() and len(s) < 15:
        return False
    return True


class FeishuMessageSender:
    """飞书消息发送器"""
    
    def __init__(self, client: Optional[FeishuClient] = None):
        """
        初始化消息发送器
        
        Args:
            client: 飞书客户端实例，如果不提供则创建新实例
        """
        self.client = client or FeishuClient()
        self.default_user_id = os.getenv('FEISHU_USER_ID')
        
        if not self.default_user_id:
            logger.warning("未配置默认接收用户ID，请在.env文件中配置FEISHU_USER_ID")
    
    def send_pinduoduo_login_alert(self, user_id: Optional[str] = None) -> bool:
        """
        发送拼多多需要重新登录的通知
        
        Args:
            user_id: 接收消息的用户ID，如果不提供则使用默认用户ID
            
        Returns:
            是否发送成功
        """
        if not Config.FEISHU_ENABLED:
            logger.info("飞书通知已禁用，跳过发送")
            return False
        
        if not self.client.is_configured():
            logger.warning("飞书客户端未配置，无法发送通知")
            return False
        
        target_user = user_id or self.default_user_id
        if not target_user:
            logger.error("未指定接收用户ID，无法发送通知")
            return False
        if not _is_valid_feishu_user_id(target_user):
            logger.error(
                "接收用户ID格式无效（飞书要求 open_id 如 ou_xxx 或较长用户ID），请勿使用工号等短数字。当前值: %s",
                target_user[:20] if len(target_user) > 20 else target_user,
            )
            return False
        
        message = "【拼多多助手】检测到拼多多商家后台需要重新登录，请及时处理。"
        
        return self.client.send_text_message(target_user, message)
    
    def send_custom_message(self, message: str, user_id: Optional[str] = None) -> bool:
        """
        发送自定义消息
        
        Args:
            message: 消息内容
            user_id: 接收消息的用户ID，如果不提供则使用默认用户ID
            
        Returns:
            是否发送成功
        """
        if not Config.FEISHU_ENABLED:
            logger.info("飞书通知已禁用，跳过发送")
            return False
        
        if not self.client.is_configured():
            logger.warning("飞书客户端未配置，无法发送通知")
            return False
        
        target_user = user_id or self.default_user_id
        if not target_user:
            logger.error("未指定接收用户ID，无法发送通知")
            return False
        if not _is_valid_feishu_user_id(target_user):
            logger.error(
                "接收用户ID格式无效（飞书要求 open_id 如 ou_xxx 或较长用户ID），"
                "请勿使用工号等短数字。当前值: %s", target_user[:20] if len(target_user) > 20 else target_user
            )
            return False
        
        return self.client.send_text_message(target_user, message)

    def send_card_message(
        self,
        card: Union[Dict[str, Any], str],
        user_id: Optional[str] = None
    ) -> bool:
        """
        发送卡片消息。

        卡片内容可以是：
        - dict：完整卡片结构（config/header/elements）或模板结构，会序列化为 JSON
        - str：已是 JSON 字符串的卡片内容

        配置与文本消息相同，使用 FEISHU_APP_ID、FEISHU_APP_SECRET、FEISHU_USER_ID，
        无需额外配置。详见 README 飞书配置说明。

        Args:
            card: 卡片内容（dict 或 JSON 字符串）
            user_id: 接收用户ID，不传则使用默认 FEISHU_USER_ID

        Returns:
            是否发送成功
        """
        if not Config.FEISHU_ENABLED:
            logger.info("飞书通知已禁用，跳过发送")
            return False

        if not self.client.is_configured():
            logger.warning("飞书客户端未配置，无法发送卡片")
            return False

        raw_user = user_id or self.default_user_id
        if not raw_user:
            logger.error("未指定接收用户ID，无法发送卡片")
            return False
        if not _is_valid_feishu_user_id(raw_user):
            if user_id and self.default_user_id and _is_valid_feishu_user_id(self.default_user_id):
                logger.warning(
                    "提供的接收用户ID格式无效，已改用默认用户。飞书要求 open_id（ou_xxx）或较长用户ID，勿填工号。无效值: %s",
                    raw_user[:20] if len(raw_user) > 20 else raw_user,
                )
                raw_user = self.default_user_id
            else:
                logger.error(
                    "接收用户ID格式无效（飞书要求 open_id 如 ou_xxx 或较长用户ID），请勿使用工号等短数字。当前值: %s",
                    raw_user[:20] if len(raw_user) > 20 else raw_user,
                )
                return False
        target_user = raw_user

        return self.client.send_card_message(target_user, card)
    
    def is_available(self) -> bool:
        """
        检查消息发送器是否可用
        
        Returns:
            是否可用
        """
        return (
            Config.FEISHU_ENABLED and
            self.client.is_configured() and
            bool(self.default_user_id)
        )


# 全局单例
_message_sender = None

def get_message_sender() -> FeishuMessageSender:
    """
    获取全局消息发送器实例
    
    Returns:
        FeishuMessageSender实例
    """
    global _message_sender
    if _message_sender is None:
        _message_sender = FeishuMessageSender()
    return _message_sender