"""
Flask路由处理模块
"""
from flask import request, jsonify
from spider.query_manager import query_with_retry, batch_query_waybill_numbers
from config import Config
from utils.startup import is_startup_enabled, get_exe_path, add_to_startup, remove_from_startup
from utils.logger import get_logger

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
