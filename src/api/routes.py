"""
Flask路由处理模块
"""
from flask import request, jsonify
from config import Config
from utils.startup import is_startup_enabled, get_exe_path, add_to_startup, remove_from_startup
from utils.logger import get_logger
from utils.script_manager import get_script_manager
from tools.script_tool import ScriptTool
from utils.config_manager import get_config_manager
import uuid
import threading
import time

# 获取logger
routes_logger = get_logger('Routes')

# 全局浏览器池引用（从main模块导入）
_browser_pool_ref = None


def register_routes(app, browser_pool):
    """
    注册Flask路由
    
    Args:
        app: Flask应用实例
        browser_pool: 浏览器池实例（可能为 None，会在需要时懒加载创建）
    """
    global _browser_pool_ref
    _browser_pool_ref = browser_pool
    
    if browser_pool:
        routes_logger.info(f"注册路由时，browser_pool对象ID: {id(browser_pool)}")
        routes_logger.info(f"注册路由时，browser_pool._initialized: {getattr(browser_pool, '_initialized', 'N/A')}")
        routes_logger.info(f"注册路由时，browser_pool对象类型: {type(browser_pool)}")
        
        # 同时更新所有工具的浏览器池引用
        try:
            from tools.manager import get_tool_manager
            tool_manager = get_tool_manager()
            for tool in tool_manager.get_all_tools():
                if hasattr(tool, 'browser_pool'):
                    tool.browser_pool = browser_pool
                    routes_logger.info(f"已设置工具 {tool.name} 的浏览器池引用")
        except Exception as e:
            routes_logger.warning(f"更新工具浏览器池引用失败: {e}")
    else:
        routes_logger.info("注册路由时，browser_pool 为 None（将在需要时懒加载创建）")
    
    @app.route('/health', methods=['GET'])
    def health_check():
        """健康检查接口"""
        return jsonify({
            'status': 'ok',
            'service': Config.APP_NAME,
            'startup_enabled': is_startup_enabled()
        }), 200
    
    @app.route('/startup', methods=['GET', 'POST', 'DELETE'])
    def manage_startup():
        """管理开机自启动
        
        GET: 查询当前自启动状态
        POST: 启用自启动
        DELETE: 禁用自启动
        """
        try:
            if request.method == 'GET':
                # 查询状态
                enabled = is_startup_enabled()
                return jsonify({
                    'success': True,
                    'startup_enabled': enabled,
                    'exe_path': get_exe_path()
                }), 200
            
            elif request.method == 'POST':
                # 启用自启动
                if add_to_startup():
                    return jsonify({
                        'success': True,
                        'message': '已启用开机自启动',
                        'startup_enabled': True
                    }), 200
                else:
                    return jsonify({
                        'success': False,
                        'error': '启用开机自启动失败'
                    }), 500
            
            elif request.method == 'DELETE':
                # 禁用自启动
                if remove_from_startup():
                    return jsonify({
                        'success': True,
                        'message': '已禁用开机自启动',
                        'startup_enabled': False
                    }), 200
                else:
                    return jsonify({
                        'success': False,
                        'error': '禁用开机自启动失败'
                    }), 500
        
        except Exception as e:
            routes_logger.error(f"管理启动项异常: {e}", exc_info=True)
            return jsonify({
                'success': False,
                'error': f'服务器内部错误: {str(e)}'
            }), 500
    
    @app.errorhandler(404)
    def not_found(error):
        """404错误处理"""
        return jsonify({
            'success': False,
            'error': '接口不存在'
        }), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        """500错误处理"""
        return jsonify({
            'success': False,
            'error': '服务器内部错误'
        }), 500
    
    # 脚本执行相关API
    script_tool = ScriptTool()
    script_manager = get_script_manager()
    
    @app.route('/api/script/execute', methods=['POST'])
    def execute_script():
        """执行Python脚本
        
        请求体格式:
        {
            "code": "print('Hello, World!')",
            "timeout": 30,
            "args": {"x": 1, "y": 2},
            "sandbox": true
        }
        """
        try:
            data = request.get_json()
            if not data:
                return jsonify({
                    'success': False,
                    'error': '请求体不能为空'
                }), 400
            
            code = data.get('code', '')
            if not code:
                return jsonify({
                    'success': False,
                    'error': '缺少必需参数: code'
                }), 400
            
            timeout = data.get('timeout', 30)
            args = data.get('args', {})
            sandbox = data.get('sandbox', True)
            script_id = data.get('script_id')  # 可选，如果提供则记录历史
            
            # 执行脚本
            result = script_tool.execute_script(
                code=code,
                timeout=timeout,
                args=args,
                sandbox=sandbox
            )
            
            # 记录执行历史
            if script_id:
                script_manager.add_execution_history(
                    script_id=script_id,
                    success=result['success'],
                    output=result.get('output', ''),
                    error=str(result.get('error', {}).get('message', '')) if result.get('error') else None,
                    elapsed_time=result.get('elapsed_time', 0)
                )
            
            return jsonify({
                'success': True,
                'data': result
            }), 200
            
        except Exception as e:
            routes_logger.error(f"执行脚本异常: {e}", exc_info=True)
            return jsonify({
                'success': False,
                'error': f'服务器内部错误: {str(e)}'
            }), 500
    
    @app.route('/api/script/list', methods=['GET'])
    def list_scripts():
        """获取脚本列表
        
        查询参数:
        - category: 分类过滤（可选）
        """
        try:
            category = request.args.get('category')
            scripts = script_manager.list_scripts(category=category)
            return jsonify({
                'success': True,
                'data': scripts
            }), 200
        except Exception as e:
            routes_logger.error(f"获取脚本列表异常: {e}", exc_info=True)
            return jsonify({
                'success': False,
                'error': f'服务器内部错误: {str(e)}'
            }), 500
    
    @app.route('/api/script/save', methods=['POST'])
    def save_script():
        """保存脚本
        
        请求体格式:
        {
            "script_id": "script_123" (可选，不提供则自动生成),
            "code": "print('Hello')",
            "name": "测试脚本",
            "category": "test",
            "description": "这是一个测试脚本"
        }
        """
        try:
            data = request.get_json()
            if not data:
                return jsonify({
                    'success': False,
                    'error': '请求体不能为空'
                }), 400
            
            code = data.get('code', '')
            if not code:
                return jsonify({
                    'success': False,
                    'error': '缺少必需参数: code'
                }), 400
            
            script_id = data.get('script_id') or str(uuid.uuid4())
            name = data.get('name', script_id)
            category = data.get('category', 'default')
            description = data.get('description', '')
            
            if script_manager.save_script(
                script_id=script_id,
                code=code,
                name=name,
                category=category,
                description=description
            ):
                return jsonify({
                    'success': True,
                    'data': {
                        'script_id': script_id,
                        'name': name
                    }
                }), 200
            else:
                return jsonify({
                    'success': False,
                    'error': '保存脚本失败'
                }), 500
                
        except Exception as e:
            routes_logger.error(f"保存脚本异常: {e}", exc_info=True)
            return jsonify({
                'success': False,
                'error': f'服务器内部错误: {str(e)}'
            }), 500
    
    @app.route('/api/script/<script_id>', methods=['GET', 'DELETE'])
    def manage_script(script_id):
        """管理脚本
        
        GET: 获取脚本代码和信息
        DELETE: 删除脚本
        """
        try:
            if request.method == 'GET':
                # 获取脚本代码
                code = script_manager.load_script(script_id)
                if code is None:
                    return jsonify({
                        'success': False,
                        'error': '脚本不存在'
                    }), 404
                
                # 获取脚本信息
                info = script_manager.get_script_info(script_id)
                
                return jsonify({
                    'success': True,
                    'data': {
                        'script_id': script_id,
                        'code': code,
                        'info': info
                    }
                }), 200
            
            elif request.method == 'DELETE':
                # 删除脚本
                if script_manager.delete_script(script_id):
                    return jsonify({
                        'success': True,
                        'message': '脚本已删除'
                    }), 200
                else:
                    return jsonify({
                        'success': False,
                        'error': '删除脚本失败'
                    }), 500
                    
        except Exception as e:
            routes_logger.error(f"管理脚本异常: {e}", exc_info=True)
            return jsonify({
                'success': False,
                'error': f'服务器内部错误: {str(e)}'
            }), 500
    
    @app.route('/api/script/<script_id>/history', methods=['GET'])
    def get_script_history(script_id):
        """获取脚本执行历史
        
        查询参数:
        - limit: 返回记录数量限制（默认20）
        """
        try:
            limit = int(request.args.get('limit', 20))
            history = script_manager.get_execution_history(script_id, limit=limit)
            return jsonify({
                'success': True,
                'data': history
            }), 200
        except Exception as e:
            routes_logger.error(f"获取执行历史异常: {e}", exc_info=True)
            return jsonify({
                'success': False,
                'error': f'服务器内部错误: {str(e)}'
            }), 500
    
    @app.route('/api/script/categories', methods=['GET'])
    def get_script_categories():
        """获取所有脚本分类"""
        try:
            categories = script_manager.get_categories()
            return jsonify({
                'success': True,
                'data': categories
            }), 200
        except Exception as e:
            routes_logger.error(f"获取分类异常: {e}", exc_info=True)
            return jsonify({
                'success': False,
                'error': f'服务器内部错误: {str(e)}'
            }), 500
    
    # 配置管理相关API
    @app.route('/api/settings/modules', methods=['GET', 'POST'])
    def manage_module_config():
        """管理模块配置
        
        GET: 获取模块配置
        POST: 保存模块配置
        """
        try:
            from utils.module_manager import get_module_manager
            from config import save_module_config
            
            module_manager = get_module_manager()
            
            if request.method == 'GET':
                # 获取模块配置
                config = module_manager.get_config()
                return jsonify({
                    'success': True,
                    'data': config
                }), 200
            
            elif request.method == 'POST':
                # 保存模块配置
                data = request.get_json()
                if not data:
                    return jsonify({
                        'success': False,
                        'error': '请求体不能为空'
                    }), 400
                
                # 验证配置格式
                from config.modules import validate_module_config
                for module_name, module_config in data.items():
                    if not validate_module_config(module_config):
                        return jsonify({
                            'success': False,
                            'error': f'模块 {module_name} 的配置格式无效'
                        }), 400
                
                # 保存配置
                if save_module_config(data):
                    # 重新加载配置
                    module_manager.reload_config()
                    return jsonify({
                        'success': True,
                        'message': '模块配置已保存'
                    }), 200
                else:
                    return jsonify({
                        'success': False,
                        'error': '保存模块配置失败'
                    }), 500
                    
        except Exception as e:
            routes_logger.error(f"管理模块配置异常: {e}", exc_info=True)
            return jsonify({
                'success': False,
                'error': f'服务器内部错误: {str(e)}'
            }), 500
    
    @app.route('/api/settings/reset', methods=['POST'])
    def reset_settings():
        """重置配置为默认值"""
        try:
            from config.modules import get_default_module_config
            from config import save_module_config
            from utils.module_manager import get_module_manager
            
            # 获取默认配置
            default_config = get_default_module_config()
            
            # 保存默认配置
            if save_module_config(default_config):
                # 重新加载配置
                module_manager = get_module_manager()
                module_manager.reload_config()
                
                return jsonify({
                    'success': True,
                    'message': '配置已重置为默认值'
                }), 200
            else:
                return jsonify({
                    'success': False,
                    'error': '重置配置失败'
                }), 500
                
        except Exception as e:
            routes_logger.error(f"重置配置异常: {e}", exc_info=True)
            return jsonify({
                'success': False,
                'error': f'服务器内部错误: {str(e)}'
            }), 500
    
    # 应用配置管理API
    config_manager = get_config_manager()
    
    @app.route('/api/settings/app', methods=['GET', 'POST'])
    def manage_app_config():
        """管理应用配置
        
        GET: 获取当前配置
        POST: 保存和应用配置
        """
        try:
            if request.method == 'GET':
                # 获取当前配置
                config = config_manager.get_config()
                return jsonify({
                    'success': True,
                    'data': config
                }), 200
            
            elif request.method == 'POST':
                # 保存和应用配置
                data = request.get_json()
                if not data:
                    return jsonify({
                        'success': False,
                        'error': '请求体不能为空'
                    }), 400
                
                # 验证端口号
                if 'port' in data:
                    port = int(data['port'])
                    if port < 1024 or port > 65535:
                        return jsonify({
                            'success': False,
                            'error': f'端口号必须在1024-65535之间，当前值: {port}'
                        }), 400
                
                # 保存配置到文件
                if not config_manager.save_config(data):
                    return jsonify({
                        'success': False,
                        'error': '保存配置失败'
                    }), 500
                
                # 尝试应用配置（热重载）
                result = config_manager.apply_config(data)
                
                response_data = {
                    'success': True,
                    'message': '配置已保存',
                    'applied': result['applied'],
                    'need_restart': result['need_restart'],
                    'require_restart': result['require_restart']
                }
                
                if result['require_restart']:
                    response_data['message'] = '配置已保存，但需要重启应用才能生效（端口或主机配置已更改）'
                else:
                    response_data['message'] = '配置已保存并应用（无需重启）'
                
                return jsonify(response_data), 200
                
        except ValueError as e:
            return jsonify({
                'success': False,
                'error': f'配置验证失败: {str(e)}'
            }), 400
        except Exception as e:
            routes_logger.error(f"管理应用配置异常: {e}", exc_info=True)
            return jsonify({
                'success': False,
                'error': f'服务器内部错误: {str(e)}'
            }), 500
    
    @app.route('/api/settings/reload', methods=['POST'])
    def reload_config():
        """重新加载配置文件"""
        try:
            # 重新加载模块配置
            from utils.module_manager import get_module_manager
            module_manager = get_module_manager()
            module_reload_success = module_manager.reload_config()
            
            # 重新加载应用配置
            app_reload_success = config_manager.reload_from_file()
            
            return jsonify({
                'success': module_reload_success or app_reload_success,
                'module_reloaded': module_reload_success,
                'app_reloaded': app_reload_success,
                'message': '配置已重新加载'
            }), 200
        except Exception as e:
            routes_logger.error(f"重新加载配置异常: {e}", exc_info=True)
            return jsonify({
                'success': False,
                'error': f'服务器内部错误: {str(e)}'
            }), 500
    
    # ==================== 浏览器池管理API ====================
    
    @app.route('/api/browser/pool/status', methods=['GET'])
    def browser_pool_status():
        """获取浏览器池状态信息"""
        try:
            pool = _browser_pool_ref
            if not pool:
                return jsonify({
                    'success': True,
                    'data': {
                        'status': 'not_initialized',
                        'message': '浏览器池未初始化'
                    }
                }), 200
            
            status = pool.get_pool_status()
            return jsonify({
                'success': True,
                'data': {
                    'status': 'active',
                    **status
                }
            }), 200
        
        except Exception as e:
            routes_logger.error(f"获取浏览器池状态异常: {e}", exc_info=True)
            return jsonify({
                'success': False,
                'error': f'服务器内部错误: {str(e)}'
            }), 500
    
    # ==================== 拼多多API接口 ====================
    
    @app.route('/api/pinduoduo/status', methods=['GET'])
    def pinduoduo_get_status():
        """获取拼多多最后执行状态"""
        try:
            # 检查浏览器池是否存在
            if not _browser_pool_ref:
                return jsonify({
                    'success': False,
                    'error': '浏览器池未初始化'
                }), 500
            
            # 直接使用浏览器池和客户端
            from spider.pinduoduo.client import PinduoduoClient
            
            with _browser_pool_ref.get_page(timeout=30) as page:
                client = PinduoduoClient(page=page)
                status_data = client.get_last_execution_status()
                
                return jsonify({
                    'success': True,
                    **status_data
                }), 200
        
        except Exception as e:
            routes_logger.error(f"获取拼多多状态异常: {e}", exc_info=True)
            return jsonify({
                'success': False,
                'error': f'服务器内部错误: {str(e)}'
            }), 500
    
    @app.route('/api/pinduoduo/login', methods=['POST'])
    def pinduoduo_start_login():
        """启动拼多多登录流程，返回二维码"""
        try:
            routes_logger.info("[PinduoduoLogin] 开始处理登录请求")
            
            # 检查浏览器池是否存在
            if not _browser_pool_ref:
                routes_logger.error("[PinduoduoLogin] 浏览器池未初始化")
                return jsonify({
                    'success': False,
                    'error': '浏览器池未初始化'
                }), 500
            
            # 直接使用浏览器池和客户端，不需要通过工具层
            from spider.pinduoduo.client import PinduoduoClient
            
            routes_logger.info("[PinduoduoLogin] 获取浏览器页面...")
            with _browser_pool_ref.get_page(timeout=60) as page:
                routes_logger.info("[PinduoduoLogin] 创建拼多多客户端...")
                client = PinduoduoClient(page=page)
                
                routes_logger.info("[PinduoduoLogin] 检查登录状态并获取二维码...")
                qrcode_data = client.show_login_qrcode()
                
                if qrcode_data == "ALREADY_LOGGED_IN":
                    # 已经登录，不需要二维码
                    routes_logger.info("[PinduoduoLogin] 已经登录，无需扫码")
                    return jsonify({
                        'success': True,
                        'already_logged_in': True,
                        'message': '已经登录，无需扫码'
                    }), 200
                
                if not qrcode_data:
                    routes_logger.error("[PinduoduoLogin] 获取二维码失败")
                    return jsonify({
                        'success': False,
                        'error': '获取二维码失败，请检查网络连接或页面加载'
                    }), 500
                
                routes_logger.info("[PinduoduoLogin] 二维码获取成功，需要扫码登录")
                return jsonify({
                    'success': True,
                    'already_logged_in': False,
                    'qrcode': qrcode_data,
                    'message': '请使用拼多多APP扫描二维码'
                }), 200
        
        except Exception as e:
            error_msg = str(e)
            error_type = type(e).__name__
            routes_logger.error(f"[PinduoduoLogin] 启动拼多多登录异常: {error_type}: {error_msg}", exc_info=True)
            return jsonify({
                'success': False,
                'error': f'服务器内部错误: {error_type}: {error_msg}'
            }), 500
    
    @app.route('/api/pinduoduo/check_login_complete', methods=['GET'])
    def pinduoduo_check_login():
        """检查拼多多登录是否完成"""
        try:
            # 检查浏览器池是否存在
            if not _browser_pool_ref:
                return jsonify({
                    'success': False,
                    'error': '浏览器池未初始化'
                }), 500
            
            # 直接使用浏览器池和客户端
            from spider.pinduoduo.client import PinduoduoClient
            
            with _browser_pool_ref.get_page(timeout=30) as page:
                client = PinduoduoClient(page=page)
                logged_in = client.check_login_complete(timeout=0)
                routes_logger.info(f"[PinduoduoCheckLogin] 登录状态检查结果: {logged_in}")
                
                return jsonify({
                    'success': True,
                    'logged_in': logged_in,
                    'message': '登录成功' if logged_in else '等待扫码'
                }), 200
        
        except Exception as e:
            routes_logger.error(f"检查拼多多登录状态异常: {e}", exc_info=True)
            return jsonify({
                'success': False,
                'error': f'服务器内部错误: {str(e)}'
            }), 500
    
    @app.route('/api/pinduoduo/logout', methods=['POST'])
    def pinduoduo_logout():
        """清除拼多多登录状态和Cookie"""
        try:
            # 检查浏览器池是否存在
            if not _browser_pool_ref:
                return jsonify({
                    'success': False,
                    'error': '浏览器池未初始化'
                }), 500
            
            # 直接使用浏览器池和客户端
            from spider.pinduoduo.client import PinduoduoClient
            
            with _browser_pool_ref.get_page(timeout=30) as page:
                client = PinduoduoClient(page=page)
                success = client.clear_cookies()
                
                if success:
                    return jsonify({
                        'success': True,
                        'message': '已清除登录状态和Cookie'
                    }), 200
                else:
                    return jsonify({
                        'success': False,
                        'error': '清除Cookie失败'
                    }), 500
        
        except Exception as e:
            routes_logger.error(f"清除拼多多登录状态异常: {e}", exc_info=True)
            return jsonify({
                'success': False,
                'error': f'服务器内部错误: {str(e)}'
            }), 500
    
    @app.route('/api/pinduoduo/execute', methods=['POST'])
    def pinduoduo_execute():
        """执行拼多多自动化操作（TODO预留）"""
        try:
            routes_logger.info("[PinduoduoExecute] 开始处理执行请求")
            
            # 检查浏览器池是否存在
            if not _browser_pool_ref:
                routes_logger.error("[PinduoduoExecute] 浏览器池未初始化")
                return jsonify({
                    'success': False,
                    'error': '浏览器池未初始化'
                }), 500
            
            # 直接使用浏览器池和客户端
            from spider.pinduoduo.client import PinduoduoClient
            
            routes_logger.info("[PinduoduoExecute] 获取浏览器页面...")
            with _browser_pool_ref.get_page(timeout=120) as page:
                routes_logger.info("[PinduoduoExecute] 创建拼多多客户端...")
                client = PinduoduoClient(page=page)
                
                routes_logger.info("[PinduoduoExecute] 执行自动化操作...")
                result = client.execute_automation()
                
                return jsonify(result), 200
        
        except Exception as e:
            routes_logger.error(f"执行拼多多自动化异常: {e}", exc_info=True)
            return jsonify({
                'success': False,
                'error': f'服务器内部错误: {str(e)}'
            }), 500