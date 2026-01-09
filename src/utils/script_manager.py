"""
脚本管理器
负责脚本文件的保存、读取、删除和管理
"""
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
import sys


class ScriptManager:
    """脚本管理器"""
    
    def __init__(self, scripts_dir: Optional[str] = None):
        """
        初始化脚本管理器
        
        Args:
            scripts_dir: 脚本文件目录，None则使用默认目录
        """
        if scripts_dir:
            self.scripts_dir = Path(scripts_dir)
        else:
            # 默认目录：项目根目录或exe同目录下的scripts文件夹
            if getattr(sys, 'frozen', False):
                exe_dir = Path(sys.executable).parent
                self.scripts_dir = exe_dir / 'scripts'
            else:
                current_dir = Path(__file__).parent.parent.parent
                self.scripts_dir = current_dir / 'scripts'
        
        # 确保目录存在
        self.scripts_dir.mkdir(parents=True, exist_ok=True)
        
        # 脚本元数据文件
        self.metadata_file = self.scripts_dir / 'metadata.json'
        self._metadata = self._load_metadata()
    
    def _load_metadata(self) -> Dict[str, Any]:
        """加载脚本元数据"""
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"[ScriptManager] 加载元数据失败: {e}")
                return {}
        return {}
    
    def _save_metadata(self):
        """保存脚本元数据"""
        try:
            with open(self.metadata_file, 'w', encoding='utf-8') as f:
                json.dump(self._metadata, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[ScriptManager] 保存元数据失败: {e}")
    
    def save_script(
        self,
        script_id: str,
        code: str,
        name: Optional[str] = None,
        category: Optional[str] = None,
        description: Optional[str] = None
    ) -> bool:
        """
        保存脚本
        
        Args:
            script_id: 脚本ID
            code: 脚本代码
            name: 脚本名称
            category: 脚本分类
            description: 脚本描述
            
        Returns:
            是否成功
        """
        try:
            # 保存脚本文件
            script_file = self.scripts_dir / f"{script_id}.py"
            with open(script_file, 'w', encoding='utf-8') as f:
                f.write(code)
            
            # 更新元数据
            if script_id not in self._metadata:
                self._metadata[script_id] = {}
            
            self._metadata[script_id].update({
                'name': name or script_id,
                'category': category or 'default',
                'description': description or '',
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat(),
                'file': str(script_file)
            })
            
            self._save_metadata()
            return True
        except Exception as e:
            print(f"[ScriptManager] 保存脚本失败: {e}")
            return False
    
    def load_script(self, script_id: str) -> Optional[str]:
        """
        加载脚本代码
        
        Args:
            script_id: 脚本ID
            
        Returns:
            脚本代码，如果不存在返回None
        """
        script_file = self.scripts_dir / f"{script_id}.py"
        if not script_file.exists():
            return None
        
        try:
            with open(script_file, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            print(f"[ScriptManager] 加载脚本失败: {e}")
            return None
    
    def delete_script(self, script_id: str) -> bool:
        """
        删除脚本
        
        Args:
            script_id: 脚本ID
            
        Returns:
            是否成功
        """
        try:
            # 删除脚本文件
            script_file = self.scripts_dir / f"{script_id}.py"
            if script_file.exists():
                script_file.unlink()
            
            # 删除元数据
            if script_id in self._metadata:
                del self._metadata[script_id]
                self._save_metadata()
            
            return True
        except Exception as e:
            print(f"[ScriptManager] 删除脚本失败: {e}")
            return False
    
    def list_scripts(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        列出所有脚本
        
        Args:
            category: 分类过滤（可选）
            
        Returns:
            脚本列表
        """
        scripts = []
        for script_id, metadata in self._metadata.items():
            if category and metadata.get('category') != category:
                continue
            
            script_info = {
                'id': script_id,
                'name': metadata.get('name', script_id),
                'category': metadata.get('category', 'default'),
                'description': metadata.get('description', ''),
                'created_at': metadata.get('created_at', ''),
                'updated_at': metadata.get('updated_at', ''),
                'file_exists': (self.scripts_dir / f"{script_id}.py").exists()
            }
            scripts.append(script_info)
        
        return scripts
    
    def get_script_info(self, script_id: str) -> Optional[Dict[str, Any]]:
        """
        获取脚本信息
        
        Args:
            script_id: 脚本ID
            
        Returns:
            脚本信息字典，如果不存在返回None
        """
        if script_id not in self._metadata:
            return None
        
        metadata = self._metadata[script_id].copy()
        metadata['id'] = script_id
        metadata['file_exists'] = (self.scripts_dir / f"{script_id}.py").exists()
        return metadata
    
    def get_categories(self) -> List[str]:
        """
        获取所有分类
        
        Returns:
            分类列表
        """
        categories = set()
        for metadata in self._metadata.values():
            category = metadata.get('category', 'default')
            categories.add(category)
        return sorted(list(categories))
    
    def add_execution_history(
        self,
        script_id: Optional[str],
        success: bool,
        output: str,
        error: Optional[str] = None,
        elapsed_time: float = 0
    ):
        """
        添加执行历史记录
        
        Args:
            script_id: 脚本ID（如果是临时脚本则为None）
            success: 是否成功
            output: 输出内容
            error: 错误信息（可选）
            elapsed_time: 执行时间（秒）
        """
        if script_id and script_id in self._metadata:
            if 'execution_history' not in self._metadata[script_id]:
                self._metadata[script_id]['execution_history'] = []
            
            history = self._metadata[script_id]['execution_history']
            history.append({
                'timestamp': datetime.now().isoformat(),
                'success': success,
                'output_length': len(output),
                'error': error,
                'elapsed_time': elapsed_time
            })
            
            # 限制历史记录数量
            max_history = 50
            if len(history) > max_history:
                self._metadata[script_id]['execution_history'] = history[-max_history:]
            
            self._save_metadata()
    
    def get_execution_history(self, script_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        获取脚本执行历史
        
        Args:
            script_id: 脚本ID
            limit: 返回记录数量限制
            
        Returns:
            执行历史列表
        """
        if script_id not in self._metadata:
            return []
        
        history = self._metadata[script_id].get('execution_history', [])
        return history[-limit:]


# 全局脚本管理器实例
_script_manager: Optional[ScriptManager] = None


def get_script_manager() -> ScriptManager:
    """
    获取全局脚本管理器实例
    
    Returns:
        脚本管理器实例
    """
    global _script_manager
    if _script_manager is None:
        _script_manager = ScriptManager()
    return _script_manager
