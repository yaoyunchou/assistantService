"""
脚本执行工具
"""
import subprocess
import sys
import io
import contextlib
import traceback
from typing import Dict, Any, Optional
from .base import BaseTool


class ScriptTool(BaseTool):
    """Python脚本执行工具"""
    
    def __init__(self):
        super().__init__(
            name="script_executor",
            display_name="脚本执行",
            description="执行Python脚本，支持参数传递和结果返回"
        )
        self._execution_history = []
        self._max_history = 100
    
    def get_info(self):
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "icon": "🐍"
        }
    
    def initialize(self, **kwargs):
        """初始化工具"""
        return True
    
    def cleanup(self):
        """清理资源"""
        pass
    
    def execute_script(
        self,
        code: str,
        timeout: int = 30,
        args: Optional[Dict[str, Any]] = None,
        sandbox: bool = True
    ) -> Dict[str, Any]:
        """
        执行Python脚本
        
        Args:
            code: Python代码
            timeout: 执行超时时间（秒）
            args: 脚本参数（作为全局变量注入）
            sandbox: 是否使用沙箱模式（限制危险操作）
            
        Returns:
            执行结果字典
        """
        if sandbox:
            # 沙箱模式：限制危险操作
            code = self._wrap_in_sandbox(code)
        
        # 准备执行环境
        exec_globals = {
            '__builtins__': __builtins__,
            '__name__': '__main__',
            '__file__': '<script>',
        }
        
        # 注入参数
        if args:
            exec_globals.update(args)
        
        # 捕获输出
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()
        
        import time
        start_time = time.time()
        error = None
        output = ""
        result = None
        
        try:
            with contextlib.redirect_stdout(stdout_capture), \
                 contextlib.redirect_stderr(stderr_capture):
                # 执行代码
                exec(compile(code, '<script>', 'exec'), exec_globals)
                
                # 尝试获取返回值（如果代码定义了result变量）
                if 'result' in exec_globals:
                    result = exec_globals['result']
        
        except Exception as e:
            error = {
                'type': type(e).__name__,
                'message': str(e),
                'traceback': traceback.format_exc()
            }
        
        elapsed_time = time.time() - start_time
        
        # 获取输出
        output = stdout_capture.getvalue()
        error_output = stderr_capture.getvalue()
        
        if error_output:
            if error:
                error['stderr'] = error_output
            else:
                output += f"\n[STDERR]\n{error_output}"
        
        # 检查超时
        if elapsed_time > timeout:
            error = {
                'type': 'TimeoutError',
                'message': f'脚本执行超时（>{timeout}秒）',
            }
        
        # 记录执行历史
        execution_record = {
            'timestamp': time.time(),
            'code': code[:200] + '...' if len(code) > 200 else code,  # 只保存前200字符
            'success': error is None,
            'elapsed_time': elapsed_time,
            'output_length': len(output),
            'has_result': result is not None
        }
        self._execution_history.append(execution_record)
        
        # 限制历史记录数量
        if len(self._execution_history) > self._max_history:
            self._execution_history = self._execution_history[-self._max_history:]
        
        return {
            'success': error is None,
            'output': output,
            'result': result,
            'error': error,
            'elapsed_time': elapsed_time
        }
    
    def _wrap_in_sandbox(self, code: str) -> str:
        """
        将代码包装在沙箱环境中
        
        Args:
            code: 原始代码
            
        Returns:
            包装后的代码
        """
        # 禁止的危险操作
        dangerous_patterns = [
            'import os',
            'import sys',
            'import subprocess',
            '__import__',
            'eval(',
            'exec(',
            'compile(',
            'open(',
            'file(',
            'input(',
            'raw_input(',
        ]
        
        # 检查是否包含危险操作
        code_lower = code.lower()
        for pattern in dangerous_patterns:
            if pattern.lower() in code_lower:
                # 不执行，直接返回错误
                raise SecurityError(f"沙箱模式禁止使用: {pattern}")
        
        return code
    
    def get_execution_history(self, limit: int = 20) -> list:
        """
        获取执行历史
        
        Args:
            limit: 返回记录数量限制
            
        Returns:
            执行历史列表
        """
        return self._execution_history[-limit:]


class SecurityError(Exception):
    """安全错误"""
    pass
