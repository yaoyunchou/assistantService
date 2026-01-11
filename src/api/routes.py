"""
Flask路由处理模块
"""
from flask import request, jsonify
from spider.query_manager import query_with_retry, batch_query_waybill_numbers
from config import Config
from utils.startup import is_startup_enabled, get_exe_path, add_to_startup, remove_from_startup
from utils.logger import get_logger
from utils.script_manager import get_script_manager
from tools.script_tool import ScriptTool
from utils.config_manager import get_config_manager
import uuid

# 获取logger
routes_logger = get_logger('Routes')

# 全局浏览器池引用（从main模块导入）
_browser_pool_ref = None

def register_routes(app, browser_pool):
    """
    注册Flask路由
    
    Args:
        app: Flask应用实例
        browser_pool: 浏览器池实例
    """
    global _browser_pool_ref
    _browser_pool_ref = browser_pool
    routes_logger.info(f"注册路由时，browser_pool对象ID: {id(browser_pool)}")
    routes_logger.info(f"注册路由时，browser_pool._initialized: {getattr(browser_pool, '_initialized', 'N/A')}")
    routes_logger.info(f"注册路由时，browser_pool对象类型: {type(browser_pool)}")
    
    @app.route('/health', methods=['GET'])
    def health_check():
        """健康检查接口"""
        # 使用全局引用获取最新的browser_pool对象
        pool = _browser_pool_ref
        # 安全地检查浏览器池是否已初始化
        pool_initialized = False
        if pool is not None:
            routes_logger.info(f"[Health] browser_pool对象ID: {id(pool)}")
            if hasattr(pool, '_initialized'):
                pool_initialized = pool._initialized
                routes_logger.info(f"[Health] browser_pool._initialized: {pool_initialized}")
            else:
                routes_logger.warning("[Health] browser_pool没有_initialized属性")
        else:
            routes_logger.warning("[Health] browser_pool为None")
        
        return jsonify({
            'status': 'ok',
            'service': 'JNSpider',
            'browser_pool_initialized': pool_initialized,
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
    
    @app.route('/query', methods=['GET'])
    def query_single():
        """单个快递单号查询接口
        
        请求格式:
        GET /query?waybill=JD1234567890
        
        响应格式:
        {
            "success": true,
            "waybill": "JD1234567890",
            "data": {
                "success": true,
                "company": "京东快递",
                "state": "3",
                "data": [...]
            }
        }
        """
        try:
            # 从URL参数获取运单号
            waybill = request.args.get('waybill')
            
            # 验证参数
            if not waybill:
                return jsonify({
                    'success': False,
                    'error': '缺少必需参数: waybill'
                }), 400
            
            if not isinstance(waybill, str) or not waybill.strip():
                return jsonify({
                    'success': False,
                    'error': 'waybill参数必须是非空字符串'
                }), 400
            
            waybill = waybill.strip()
            
            # 使用全局引用获取最新的browser_pool对象
            pool = _browser_pool_ref
            
            # 添加详细的调试日志
            routes_logger.info(f"[Query] 查询单号: {waybill}")
            routes_logger.info(f"[Query] _browser_pool_ref对象ID: {id(pool) if pool else 'None'}")
            routes_logger.info(f"[Query] _browser_pool_ref是否为None: {pool is None}")
            
            # 浏览器池已在服务启动时初始化，这里只需要检查
            if pool is None:
                routes_logger.error("[Query] browser_pool为None，返回错误")
                return jsonify({
                    'success': False,
                    'error': '浏览器池未初始化，请检查服务状态'
                }), 500
            
            # 检查浏览器池是否已初始化（使用hasattr避免AttributeError）
            has_initialized_attr = hasattr(pool, '_initialized')
            routes_logger.info(f"[Query] pool是否有_initialized属性: {has_initialized_attr}")
            if has_initialized_attr:
                initialized_value = pool._initialized
                routes_logger.info(f"[Query] pool._initialized的值: {initialized_value}")
            else:
                routes_logger.warning("[Query] pool没有_initialized属性")
            
            if not has_initialized_attr or not pool._initialized:
                routes_logger.error(f"[Query] 浏览器池未初始化，has_initialized_attr={has_initialized_attr}, _initialized={getattr(pool, '_initialized', 'N/A')}")
                return jsonify({
                    'success': False,
                    'error': '浏览器池未初始化，请检查服务状态'
                }), 500
            
            # 查询物流信息
            routes_logger.info(f"正在查询单号: {waybill}")
            result = query_with_retry(
                waybill_number=waybill,
                browser_pool=pool,
                max_retry=Config.MAX_RETRY
            )
            
            if result is None:
                result = {
                    'success': False,
                    'error': '查询失败，未返回结果'
                }
            
            # 返回结果
            return jsonify({
                'success': True,
                'waybill': waybill,
                'data': result
            }), 200
            
        except Exception as e:
            routes_logger.error(f"查询异常: {e}", exc_info=True)
            return jsonify({
                'success': False,
                'error': f'服务器内部错误: {str(e)}'
            }), 500
    
    @app.route('/batch', methods=['POST'])
    def query_batch():
        """快递单号列表批量查询接口
        
        请求体格式:
        {
            "waybills": ["JD1234567890", "SF9876543210"]
        }
        
        响应格式:
        {
            "success": true,
            "data": {
                "JD1234567890": {
                    "success": true,
                    "company": "京东快递",
                    "state": "3",
                    "data": [...]
                },
                "SF9876543210": {
                    "success": true,
                    "company": "顺丰快递",
                    "state": "0",
                    "data": []
                }
            }
        }
        """
        try:
            # 获取请求数据
            data = request.get_json()
            if not data:
                return jsonify({
                    'success': False,
                    'error': '请求体不能为空，请提供JSON格式数据'
                }), 400
            
            # 验证参数
            waybills = data.get('waybills')
            if not waybills:
                return jsonify({
                    'success': False,
                    'error': '缺少必需参数: waybills'
                }), 400
            
            if not isinstance(waybills, list):
                return jsonify({
                    'success': False,
                    'error': 'waybills参数必须是数组'
                }), 400
            
            if len(waybills) == 0:
                return jsonify({
                    'success': False,
                    'error': 'waybills数组不能为空'
                }), 400
            
            # 验证数组中的每个元素
            valid_waybills = []
            for waybill in waybills:
                if isinstance(waybill, str) and waybill.strip():
                    valid_waybills.append(waybill.strip())
            
            if len(valid_waybills) == 0:
                return jsonify({
                    'success': False,
                    'error': 'waybills数组中必须包含至少一个有效的单号'
                }), 400
            
            # 使用全局引用获取最新的browser_pool对象
            pool = _browser_pool_ref
            
            # 添加详细的调试日志
            routes_logger.info(f"[Batch] 批量查询 {len(valid_waybills)} 个单号")
            routes_logger.info(f"[Batch] _browser_pool_ref对象ID: {id(pool) if pool else 'None'}")
            routes_logger.info(f"[Batch] _browser_pool_ref是否为None: {pool is None}")
            
            # 浏览器池已在服务启动时初始化，这里只需要检查
            if pool is None:
                routes_logger.error("[Batch] browser_pool为None，返回错误")
                return jsonify({
                    'success': False,
                    'error': '浏览器池未初始化，请检查服务状态'
                }), 500
            
            # 检查浏览器池是否已初始化（使用hasattr避免AttributeError）
            has_initialized_attr = hasattr(pool, '_initialized')
            routes_logger.info(f"[Batch] pool是否有_initialized属性: {has_initialized_attr}")
            if has_initialized_attr:
                initialized_value = pool._initialized
                routes_logger.info(f"[Batch] pool._initialized的值: {initialized_value}")
            else:
                routes_logger.warning("[Batch] pool没有_initialized属性")
            
            if not has_initialized_attr or not pool._initialized:
                routes_logger.error(f"[Batch] 浏览器池未初始化，has_initialized_attr={has_initialized_attr}, _initialized={getattr(pool, '_initialized', 'N/A')}")
                return jsonify({
                    'success': False,
                    'error': '浏览器池未初始化，请检查服务状态'
                }), 500
            
            # 批量查询物流信息
            routes_logger.info(f"正在批量查询 {len(valid_waybills)} 个单号...")
            results = batch_query_waybill_numbers(
                waybill_numbers=valid_waybills,
                browser_pool=pool,
                max_retry=Config.MAX_RETRY
            )
            
            # 返回结果
            return jsonify({
                'success': True,
                'data': results
            }), 200
            
        except Exception as e:
            routes_logger.error(f"批量查询异常: {e}", exc_info=True)
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