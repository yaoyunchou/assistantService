"""
飞书消息发送器
提供更高层的消息发送接口和消息模板管理
"""
import os
from typing import Optional
from .feishu_client import FeishuClient
from config import Config
from utils.logger import get_logger

logger = get_logger('FeishuMessageSender')


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
        
        return self.client.send_text_message(target_user, message)
    
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
