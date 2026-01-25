"""
飞书API客户端
负责飞书应用认证和API调用
"""
import os
import requests
import time
from typing import Optional, Dict, Any
from utils.logger import get_logger

logger = get_logger('FeishuClient')


class FeishuClient:
    """飞书API客户端"""
    
    # 飞书API基础URL
    BASE_URL = "https://open.feishu.cn/open-apis"
    
    def __init__(self, app_id: Optional[str] = None, app_secret: Optional[str] = None):
        """
        初始化飞书客户端
        
        Args:
            app_id: 飞书应用ID，如果不提供则从环境变量读取
            app_secret: 飞书应用Secret，如果不提供则从环境变量读取
        """
        self.app_id = app_id or os.getenv('FEISHU_APP_ID')
        self.app_secret = app_secret or os.getenv('FEISHU_APP_SECRET')
        
        if not self.app_id or not self.app_secret:
            logger.warning("飞书应用ID或Secret未配置，请在.env文件中配置")
        
        self._access_token = None
        self._token_expire_time = 0
    
    def get_tenant_access_token(self) -> Optional[str]:
        """
        获取tenant_access_token
        实现token缓存，避免频繁请求
        
        Returns:
            access_token，如果获取失败返回None
        """
        # 检查token是否还有效（提前5分钟刷新）
        if self._access_token and time.time() < (self._token_expire_time - 300):
            return self._access_token
        
        # 检查配置
        if not self.app_id or not self.app_secret:
            logger.error("飞书应用ID或Secret未配置")
            return None
        
        try:
            url = f"{self.BASE_URL}/auth/v3/tenant_access_token/internal/"
            headers = {
                "Content-Type": "application/json; charset=utf-8"
            }
            data = {
                "app_id": self.app_id,
                "app_secret": self.app_secret
            }
            
            logger.info("正在获取飞书access_token...")
            response = requests.post(url, json=data, headers=headers, timeout=10)
            result = response.json()
            
            if result.get('code') == 0:
                self._access_token = result.get('tenant_access_token')
                # token有效期通常是2小时（7200秒）
                expire = result.get('expire', 7200)
                self._token_expire_time = time.time() + expire
                logger.info("飞书access_token获取成功")
                return self._access_token
            else:
                logger.error(f"获取飞书access_token失败: {result.get('msg')}")
                return None
        
        except requests.RequestException as e:
            logger.error(f"请求飞书API失败: {e}")
            return None
        except Exception as e:
            logger.error(f"获取飞书access_token时发生错误: {e}", exc_info=True)
            return None
    
    def send_text_message(self, user_id: str, text: str) -> bool:
        """
        发送文本消息给指定用户
        
        Args:
            user_id: 接收消息的用户ID（user_id或open_id）
            text: 消息文本内容
            
        Returns:
            是否发送成功
        """
        access_token = self.get_tenant_access_token()
        if not access_token:
            logger.error("无法获取access_token，消息发送失败")
            return False
        
        try:
            url = f"{self.BASE_URL}/im/v1/messages"
            params = {
                "receive_id_type": "user_id"
            }
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=utf-8"
            }
            data = {
                "receive_id": user_id,
                "msg_type": "text",
                "content": f'{{"text":"{text}"}}'
            }
            
            logger.info(f"正在发送飞书消息给用户: {user_id}")
            response = requests.post(url, params=params, json=data, headers=headers, timeout=10)
            result = response.json()
            
            if result.get('code') == 0:
                logger.info("飞书消息发送成功")
                return True
            else:
                logger.error(f"飞书消息发送失败: {result.get('msg')}")
                return False
        
        except requests.RequestException as e:
            logger.error(f"请求飞书API失败: {e}")
            return False
        except Exception as e:
            logger.error(f"发送飞书消息时发生错误: {e}", exc_info=True)
            return False
    
    def is_configured(self) -> bool:
        """
        检查飞书客户端是否已正确配置
        
        Returns:
            是否已配置
        """
        return bool(self.app_id and self.app_secret)
