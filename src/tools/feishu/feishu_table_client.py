"""
飞书多维表格客户端
提供飞书多维表格的完整操作功能，包括创建、更新、删除、查询等
"""
import json
import requests
from typing import Optional, Dict, Any, List, Tuple
from .feishu_client import FeishuClient
from utils.logger import get_logger

logger = get_logger('FeishuTableClient')


def _feishu_fields_debug_str(fields: Optional[Dict[str, Any]], max_items: int = 45, max_total: int = 2400) -> str:
    """记录写入失败时打印字段名、Python 类型与截断后的值，便于排查 Number/Datetime 转换问题。"""
    if not fields:
        return '{}'
    parts: List[str] = []
    for i, (k, v) in enumerate(fields.items()):
        if i >= max_items:
            parts.append(f'...(+{len(fields) - max_items} more keys)')
            break
        tname = type(v).__name__
        if v is None:
            rep = 'None'
        elif isinstance(v, (int, float, bool)):
            rep = repr(v)
        else:
            rep = repr(v)
            if len(rep) > 140:
                rep = rep[:137] + '...'
        parts.append(f'{k}<{tname}>={rep}')
    s = ' | '.join(parts)
    if len(s) > max_total:
        return s[: max_total - 3] + '...'
    return s


class FeishuTableClient:
    """飞书多维表格客户端"""
    
    # 飞书API基础URL
    BASE_URL = "https://open.feishu.cn/open-apis"
    
    def __init__(self, app_token: Optional[str] = None, table_id: Optional[str] = None, client: Optional[FeishuClient] = None):
        """
        初始化飞书多维表格客户端
        
        Args:
            app_token: 多维表格的唯一标识符，如果提供则后续方法调用可省略此参数
            table_id: 数据表的唯一标识符，如果提供则后续方法调用可省略此参数
            client: 飞书客户端实例，如果不提供则创建新实例
        """
        self.client = client or FeishuClient()
        self.app_token = app_token
        self.table_id = table_id
    
    def _get_access_token(self) -> Optional[str]:
        """
        获取访问令牌
        
        Returns:
            access_token，如果获取失败返回None
        """
        return self.client.get_tenant_access_token()
    
    def _get_app_token_and_table_id(self, app_token: Optional[str] = None, table_id: Optional[str] = None) -> Tuple[str, str]:
        """
        获取app_token和table_id，优先使用方法参数，否则使用实例属性
        
        Args:
            app_token: 方法参数中的app_token
            table_id: 方法参数中的table_id
            
        Returns:
            (app_token, table_id) 元组
            
        Raises:
            ValueError: 如果app_token或table_id未提供
        """
        final_app_token = app_token or self.app_token
        final_table_id = table_id or self.table_id
        
        if not final_app_token:
            raise ValueError("app_token未提供，请在创建实例时传入或在方法调用时传入")
        if not final_table_id:
            raise ValueError("table_id未提供，请在创建实例时传入或在方法调用时传入")
        
        return final_app_token, final_table_id
    
    def _make_request(self, method: str, url: str, data: Optional[Dict] = None, params: Optional[Dict] = None) -> Optional[Dict[str, Any]]:
        """
        发送HTTP请求
        
        Args:
            method: HTTP方法（GET, POST, PUT, DELETE）
            url: 请求URL
            data: 请求体数据
            params: URL参数
            
        Returns:
            响应数据字典，如果失败返回None
        """
        access_token = self._get_access_token()
        if not access_token:
            logger.error("无法获取access_token，请求失败")
            return None
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        
        try:
            response = requests.request(
                method=method,
                url=url,
                json=data,
                params=params,
                headers=headers,
                timeout=30
            )
            try:
                result = response.json()
            except Exception as json_err:
                logger.error(
                    '飞书API响应非JSON method=%s url_suffix=%s status=%s err=%s body_prefix=%r',
                    method,
                    url.split('/open-apis', 1)[-1][:120] if '/open-apis' in url else url[-120:],
                    response.status_code,
                    json_err,
                    (response.text or '')[:500],
                )
                return None

            if result.get('code') == 0:
                return result.get('data')

            # 失败时打出完整业务体（常含字段级原因）；避免单行过长用截断
            try:
                full = json.dumps(result, ensure_ascii=False)
            except Exception:
                full = str(result)
            if len(full) > 4000:
                full = full[:3997] + '...'
            logger.error(
                '飞书API请求失败 method=%s http_status=%s code=%s msg=%s body=%s',
                method,
                response.status_code,
                result.get('code'),
                result.get('msg'),
                full,
            )
            return None
        
        except requests.RequestException as e:
            logger.error(f"请求飞书API失败: {e}")
            return None
        except Exception as e:
            logger.error(f"请求飞书API时发生错误: {e}", exc_info=True)
            return None
    
    def create_record(self, fields: Dict[str, Any], app_token: Optional[str] = None, table_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        创建单条记录
        
        Args:
            fields: 记录字段数据，格式：{"字段名": "字段值"}
            app_token: 多维表格的唯一标识符，如果不提供则使用创建实例时传入的值
            table_id: 数据表的唯一标识符，如果不提供则使用创建实例时传入的值
            
        Returns:
            创建的记录信息（包含record_id），如果失败返回None
            
        示例:
            >>> # 方式1：在创建实例时传入app_token和table_id
            >>> client = FeishuTableClient(
            ...     app_token="bascnCMII2O1qg4W1O4w",
            ...     table_id="tblxxxxxxxxxxxx"
            ... )
            >>> result = client.create_record(fields={"姓名": "张三", "年龄": 25})
            >>> 
            >>> # 方式2：在方法调用时传入（会覆盖实例属性）
            >>> client = FeishuTableClient()
            >>> result = client.create_record(
            ...     fields={"姓名": "张三", "年龄": 25},
            ...     app_token="bascnCMII2O1qg4W1O4w",
            ...     table_id="tblxxxxxxxxxxxx"
            ... )
        """
        app_token, table_id = self._get_app_token_and_table_id(app_token, table_id)
        url = f"{self.BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/records"
        data = {"fields": fields}
        
        logger.info(f"正在创建记录到表格: {table_id}")
        result = self._make_request("POST", url, data=data)
        
        if result:
            logger.info(f"记录创建成功，record_id: {result.get('record', {}).get('record_id')}")
            return result.get('record')
        logger.error(
            '记录创建失败 table_id=%s fields=%s',
            table_id,
            _feishu_fields_debug_str(fields),
        )
        return None
    
    def batch_create_records(self, records: List[Dict[str, Any]], app_token: Optional[str] = None, table_id: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
        """
        批量创建记录
        
        Args:
            records: 记录列表，每个记录包含fields字段，格式：[{"fields": {...}}, {"fields": {...}}]
            app_token: 多维表格的唯一标识符，如果不提供则使用创建实例时传入的值
            table_id: 数据表的唯一标识符，如果不提供则使用创建实例时传入的值
            
        Returns:
            创建的记录列表，如果失败返回None
            
        示例:
            >>> # 方式1：在创建实例时传入app_token和table_id
            >>> client = FeishuTableClient(
            ...     app_token="bascnCMII2O1qg4W1O4w",
            ...     table_id="tblxxxxxxxxxxxx"
            ... )
            >>> result = client.batch_create_records([
            ...     {"fields": {"姓名": "张三", "年龄": 25}},
            ...     {"fields": {"姓名": "李四", "年龄": 30}}
            ... ])
        """
        app_token, table_id = self._get_app_token_and_table_id(app_token, table_id)
        url = f"{self.BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_create"
        data = {"records": records}
        
        logger.info(f"正在批量创建 {len(records)} 条记录到表格: {table_id}")
        result = self._make_request("POST", url, data=data)
        
        if result:
            created_records = result.get('records', [])
            logger.info(f"批量创建成功，共创建 {len(created_records)} 条记录")
            return created_records
        first_fields = records[0].get('fields') if records else None
        logger.error(
            '批量创建记录失败 table_id=%s batch_size=%s first_fields=%s',
            table_id,
            len(records),
            _feishu_fields_debug_str(first_fields),
        )
        return None
    
    def update_record(self, record_id: str, fields: Dict[str, Any], app_token: Optional[str] = None, table_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        更新单条记录
        
        Args:
            record_id: 记录的唯一标识符
            fields: 要更新的字段数据，格式：{"字段名": "字段值"}
            app_token: 多维表格的唯一标识符，如果不提供则使用创建实例时传入的值
            table_id: 数据表的唯一标识符，如果不提供则使用创建实例时传入的值
            
        Returns:
            更新后的记录信息，如果失败返回None
            
        示例:
            >>> # 方式1：在创建实例时传入app_token和table_id
            >>> client = FeishuTableClient(
            ...     app_token="bascnCMII2O1qg4W1O4w",
            ...     table_id="tblxxxxxxxxxxxx"
            ... )
            >>> result = client.update_record(
            ...     record_id="recxxxxxxxxxxxx",
            ...     fields={"年龄": 26}
            ... )
        """
        app_token, table_id = self._get_app_token_and_table_id(app_token, table_id)
        url = f"{self.BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}"
        data = {"fields": fields}
        
        logger.info(f"正在更新记录: {record_id}")
        result = self._make_request("PUT", url, data=data)
        
        if result is not None:
            logger.info(f"记录更新成功: {record_id}")
            rec = result.get('record')
            # 飞书偶发 code=0 但 data 无 record 或为空对象，仍视为更新成功
            return rec if rec is not None else {}
        logger.error(
            '记录更新失败 record_id=%s table_id=%s fields=%s',
            record_id,
            table_id,
            _feishu_fields_debug_str(fields),
        )
        return None
    
    def batch_update_records(self, records: List[Dict[str, Any]], app_token: Optional[str] = None, table_id: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
        """
        批量更新记录
        
        Args:
            records: 记录列表，每个记录必须包含record_id和fields，格式：
                    [{"record_id": "xxx", "fields": {...}}, {"record_id": "yyy", "fields": {...}}]
            app_token: 多维表格的唯一标识符，如果不提供则使用创建实例时传入的值
            table_id: 数据表的唯一标识符，如果不提供则使用创建实例时传入的值
            
        Returns:
            更新后的记录列表，如果失败返回None
            
        示例:
            >>> # 方式1：在创建实例时传入app_token和table_id
            >>> client = FeishuTableClient(
            ...     app_token="bascnCMII2O1qg4W1O4w",
            ...     table_id="tblxxxxxxxxxxxx"
            ... )
            >>> result = client.batch_update_records([
            ...     {"record_id": "recxxxxx", "fields": {"年龄": 26}},
            ...     {"record_id": "recyyyyy", "fields": {"年龄": 31}}
            ... ])
        """
        app_token, table_id = self._get_app_token_and_table_id(app_token, table_id)
        url = f"{self.BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_update"
        data = {"records": records}
        
        logger.info(f"正在批量更新 {len(records)} 条记录")
        result = self._make_request("POST", url, data=data)
        
        if result:
            updated_records = result.get('records', [])
            logger.info(f"批量更新成功，共更新 {len(updated_records)} 条记录")
            return updated_records
        first = records[0] if records else {}
        logger.error(
            '批量更新记录失败 table_id=%s batch_size=%s first_record_id=%s first_fields=%s',
            table_id,
            len(records),
            first.get('record_id'),
            _feishu_fields_debug_str(first.get('fields')),
        )
        return None
    
    def delete_record(self, record_id: str, app_token: Optional[str] = None, table_id: Optional[str] = None) -> bool:
        """
        删除单条记录
        
        Args:
            record_id: 记录的唯一标识符
            app_token: 多维表格的唯一标识符，如果不提供则使用创建实例时传入的值
            table_id: 数据表的唯一标识符，如果不提供则使用创建实例时传入的值
            
        Returns:
            是否删除成功
            
        示例:
            >>> # 方式1：在创建实例时传入app_token和table_id
            >>> client = FeishuTableClient(
            ...     app_token="bascnCMII2O1qg4W1O4w",
            ...     table_id="tblxxxxxxxxxxxx"
            ... )
            >>> success = client.delete_record(record_id="recxxxxxxxxxxxx")
        """
        app_token, table_id = self._get_app_token_and_table_id(app_token, table_id)
        url = f"{self.BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}"
        
        logger.info(f"正在删除记录: {record_id}")
        result = self._make_request("DELETE", url)
        
        if result is not None:
            logger.info(f"记录删除成功: {record_id}")
            return True
        else:
            logger.error(f"记录删除失败: {record_id}")
            return False
    
    def batch_delete_records(self, record_ids: List[str], app_token: Optional[str] = None, table_id: Optional[str] = None) -> bool:
        """
        批量删除记录
        
        Args:
            record_ids: 要删除的记录ID列表
            app_token: 多维表格的唯一标识符，如果不提供则使用创建实例时传入的值
            table_id: 数据表的唯一标识符，如果不提供则使用创建实例时传入的值
            
        Returns:
            是否删除成功
            
        示例:
            >>> # 方式1：在创建实例时传入app_token和table_id
            >>> client = FeishuTableClient(
            ...     app_token="bascnCMII2O1qg4W1O4w",
            ...     table_id="tblxxxxxxxxxxxx"
            ... )
            >>> success = client.batch_delete_records(record_ids=["recxxxxx", "recyyyyy"])
        """
        app_token, table_id = self._get_app_token_and_table_id(app_token, table_id)
        url = f"{self.BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_delete"
        data = {"records": record_ids}
        
        logger.info(f"正在批量删除 {len(record_ids)} 条记录")
        result = self._make_request("POST", url, data=data)
        
        if result is not None:
            logger.info(f"批量删除成功，共删除 {len(record_ids)} 条记录")
            return True
        else:
            logger.error("批量删除记录失败")
            return False
    
    def get_record(self, record_id: str, app_token: Optional[str] = None, table_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        获取单条记录
        
        Args:
            record_id: 记录的唯一标识符
            app_token: 多维表格的唯一标识符，如果不提供则使用创建实例时传入的值
            table_id: 数据表的唯一标识符，如果不提供则使用创建实例时传入的值
            
        Returns:
            记录信息，如果失败返回None
            
        示例:
            >>> # 方式1：在创建实例时传入app_token和table_id
            >>> client = FeishuTableClient(
            ...     app_token="bascnCMII2O1qg4W1O4w",
            ...     table_id="tblxxxxxxxxxxxx"
            ... )
            >>> record = client.get_record(record_id="recxxxxxxxxxxxx")
        """
        app_token, table_id = self._get_app_token_and_table_id(app_token, table_id)
        url = f"{self.BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}"
        
        logger.info(f"正在获取记录: {record_id}")
        result = self._make_request("GET", url)
        
        if result:
            logger.info(f"记录获取成功: {record_id}")
            return result.get('record')
        else:
            logger.error(f"记录获取失败: {record_id}")
            return None
    
    def list_records(
        self,
        page_size: int = 100,
        page_token: Optional[str] = None,
        filter: Optional[str] = None,
        sort: Optional[List[Dict[str, Any]]] = None,
        view_id: Optional[str] = None,
        app_token: Optional[str] = None,
        table_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        获取记录列表
        
        Args:
            page_size: 分页大小，默认100，最大500
            page_token: 分页标记，用于获取下一页数据
            filter: 筛选条件（可选）
            sort: 排序条件（可选），格式：[{"field_name": "字段名", "desc": True/False}]
            view_id: 视图 ID（与网页 URL 中 view= 一致）；不传时接口行为可能与当前表格视图不一致
            app_token: 多维表格的唯一标识符，如果不提供则使用创建实例时传入的值
            table_id: 数据表的唯一标识符，如果不提供则使用创建实例时传入的值
            
        Returns:
            包含records列表和has_more、page_token的字典，如果失败返回None
            
        示例:
            >>> # 方式1：在创建实例时传入app_token和table_id
            >>> client = FeishuTableClient(
            ...     app_token="bascnCMII2O1qg4W1O4w",
            ...     table_id="tblxxxxxxxxxxxx"
            ... )
            >>> result = client.list_records(page_size=50)
            >>> records = result.get('items', [])
        """
        app_token, table_id = self._get_app_token_and_table_id(app_token, table_id)
        url = f"{self.BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/records"
        
        params = {
            "page_size": min(page_size, 500)  # 最大500
        }
        
        if page_token:
            params["page_token"] = page_token

        if view_id:
            params["view_id"] = view_id
        
        if filter:
            params["filter"] = filter
        
        if sort:
            # 将排序条件转换为字符串格式
            params["sort"] = json.dumps(sort)
        
        logger.info(f"正在获取记录列表，page_size: {params['page_size']}")
        result = self._make_request("GET", url, params=params)
        
        if result:
            items = result.get('items') or []  # 确保 items 不会是 None
            logger.info(f"记录列表获取成功，共 {len(items)} 条记录")
            return result
        else:
            logger.error("记录列表获取失败")
            return None
    
    def get_all_records(
        self,
        filter: Optional[str] = None,
        sort: Optional[List[Dict[str, Any]]] = None,
        view_id: Optional[str] = None,
        app_token: Optional[str] = None,
        table_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        获取所有记录（自动处理分页）
        
        Args:
            filter: 筛选条件（可选）
            sort: 排序条件（可选）
            app_token: 多维表格的唯一标识符，如果不提供则使用创建实例时传入的值
            table_id: 数据表的唯一标识符，如果不提供则使用创建实例时传入的值
            
        Returns:
            所有记录的列表
            
        示例:
            >>> # 方式1：在创建实例时传入app_token和table_id
            >>> client = FeishuTableClient(
            ...     app_token="bascnCMII2O1qg4W1O4w",
            ...     table_id="tblxxxxxxxxxxxx"
            ... )
            >>> all_records = client.get_all_records()
        """
        app_token, table_id = self._get_app_token_and_table_id(app_token, table_id)
        all_records = []
        page_token = None
        
        while True:
            result = self.list_records(
                page_size=500,  # 使用最大分页大小
                page_token=page_token,
                filter=filter,
                sort=sort,
                view_id=view_id,
                app_token=app_token,
                table_id=table_id
            )
            
            if not result:
                break
            
            items = result.get('items') or []  # 确保 items 不会是 None
            all_records.extend(items)
            
            has_more = result.get('has_more', False)
            if not has_more:
                break
            
            page_token = result.get('page_token')
            if not page_token:
                break
        
        logger.info(f"共获取 {len(all_records)} 条记录")
        return all_records
    
    def get_app_info(self, app_token: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        获取多维表格应用信息
        
        Args:
            app_token: 多维表格的唯一标识符，如果不提供则使用创建实例时传入的值
            
        Returns:
            应用信息字典，如果失败返回None
            
        示例:
            >>> client = FeishuTableClient(app_token="bascnCMII2O1qg4W1O4w")
            >>> app_info = client.get_app_info()
            >>> print(app_info.get('name'))  # 应用名称
        """
        app_token = app_token or self.app_token
        if not app_token:
            raise ValueError("app_token未提供，请在创建实例时传入或在方法调用时传入")
        
        url = f"{self.BASE_URL}/bitable/v1/apps/{app_token}"
        
        logger.info(f"正在获取应用信息: {app_token}")
        result = self._make_request("GET", url)
        
        if result:
            logger.info(f"应用信息获取成功: {app_token}")
            return result.get('app')
        else:
            logger.error(f"应用信息获取失败: {app_token}")
            return None
    
    def list_tables(self, app_token: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
        """
        获取多维表格中的所有数据表列表
        
        Args:
            app_token: 多维表格的唯一标识符，如果不提供则使用创建实例时传入的值
            
        Returns:
            数据表列表，如果失败返回None
            
        示例:
            >>> client = FeishuTableClient(app_token="bascnCMII2O1qg4W1O4w")
            >>> tables = client.list_tables()
            >>> for table in tables:
            ...     print(f"表名: {table.get('name')}, ID: {table.get('table_id')}")
        """
        app_token = app_token or self.app_token
        if not app_token:
            raise ValueError("app_token未提供，请在创建实例时传入或在方法调用时传入")
        
        url = f"{self.BASE_URL}/bitable/v1/apps/{app_token}/tables"
        
        logger.info(f"正在获取数据表列表: {app_token}")
        result = self._make_request("GET", url)
        
        if result:
            tables = result.get('items', [])
            logger.info(f"数据表列表获取成功，共 {len(tables)} 个表")
            return tables
        else:
            logger.error("数据表列表获取失败")
            return None
    
    def get_table_info(self, app_token: Optional[str] = None, table_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        获取数据表信息
        
        Args:
            app_token: 多维表格的唯一标识符，如果不提供则使用创建实例时传入的值
            table_id: 数据表的唯一标识符，如果不提供则使用创建实例时传入的值
            
        Returns:
            数据表信息字典，如果失败返回None
            
        示例:
            >>> client = FeishuTableClient(
            ...     app_token="bascnCMII2O1qg4W1O4w",
            ...     table_id="tblxxxxxxxxxxxx"
            ... )
            >>> table_info = client.get_table_info()
            >>> print(f"表名: {table_info.get('name')}")
        """
        app_token, table_id = self._get_app_token_and_table_id(app_token, table_id)
        url = f"{self.BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}"
        
        logger.info(f"正在获取数据表信息: {table_id}")
        result = self._make_request("GET", url)
        
        if result:
            logger.info(f"数据表信息获取成功: {table_id}")
            return result.get('table')
        else:
            logger.error(f"数据表信息获取失败: {table_id}")
            return None
    
    def list_fields(self, app_token: Optional[str] = None, table_id: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
        """
        获取数据表的字段列表（表结构）
        
        Args:
            app_token: 多维表格的唯一标识符，如果不提供则使用创建实例时传入的值
            table_id: 数据表的唯一标识符，如果不提供则使用创建实例时传入的值
            
        Returns:
            字段列表，每个字段包含字段名、字段类型等信息，如果失败返回None
            
        示例:
            >>> client = FeishuTableClient(
            ...     app_token="bascnCMII2O1qg4W1O4w",
            ...     table_id="tblxxxxxxxxxxxx"
            ... )
            >>> fields = client.list_fields()
            >>> for field in fields:
            ...     print(f"字段名: {field.get('field_name')}, 类型: {field.get('type')}")
        """
        app_token, table_id = self._get_app_token_and_table_id(app_token, table_id)
        
        # 验证 table_id 格式（通常以 tbl 开头）
        if table_id and not table_id.startswith('tbl'):
            logger.warning(f"table_id '{table_id}' 格式可能不正确，通常 table_id 应该以 'tbl' 开头")
            logger.info(f"提示：可以使用 list_tables() 方法获取正确的 table_id")
        
        url = f"{self.BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/fields"
        
        logger.info(f"正在获取字段列表: {table_id}")
        result = self._make_request("GET", url)
        
        if result:
            fields = result.get('items', [])
            logger.info(f"字段列表获取成功，共 {len(fields)} 个字段")
            return fields
        else:
            # 检查是否是 table_id 错误
            logger.error(f"字段列表获取失败，table_id: {table_id}")
            logger.error(f"提示：如果 table_id 不正确，请使用 list_tables() 方法获取正确的 table_id")
            logger.error(f"示例：tables = client.list_tables(); print(tables)")
            return None
    
    def get_table_schema(self, app_token: Optional[str] = None, table_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        获取数据表的完整结构信息（表信息 + 字段列表）
        这个方法会同时获取表信息和字段列表，方便了解表格的完整结构
        
        Args:
            app_token: 多维表格的唯一标识符，如果不提供则使用创建实例时传入的值
            table_id: 数据表的唯一标识符，如果不提供则使用创建实例时传入的值
            
        Returns:
            包含表信息和字段列表的字典，格式：
            {
                "table": {...},  # 表信息
                "fields": [...]  # 字段列表
            }
            如果失败返回None
            
        示例:
            >>> client = FeishuTableClient(
            ...     app_token="bascnCMII2O1qg4W1O4w",
            ...     table_id="tblxxxxxxxxxxxx"
            ... )
            >>> schema = client.get_table_schema()
            >>> print(f"表名: {schema['table']['name']}")
            >>> print(f"字段数: {len(schema['fields'])}")
            >>> for field in schema['fields']:
            ...     print(f"  - {field['field_name']} ({field['type']})")
        """
        app_token, table_id = self._get_app_token_and_table_id(app_token, table_id)
        
        # 获取表信息
        table_info = self.get_table_info(app_token, table_id)
        if not table_info:
            return None
        
        # 获取字段列表
        fields = self.list_fields(app_token, table_id)
        if fields is None:
            return None
        
        return {
            "table": table_info,
            "fields": fields
        }
    
    def print_table_schema(self, app_token: Optional[str] = None, table_id: Optional[str] = None) -> None:
        """
        打印数据表结构信息（用于调试和开发）
        
        Args:
            app_token: 多维表格的唯一标识符，如果不提供则使用创建实例时传入的值
            table_id: 数据表的唯一标识符，如果不提供则使用创建实例时传入的值
            
        示例:
            >>> client = FeishuTableClient(
            ...     app_token="bascnCMII2O1qg4W1O4w",
            ...     table_id="tblxxxxxxxxxxxx"
            ... )
            >>> client.print_table_schema()
            # 输出：
            # ========== 数据表结构 ==========
            # 表名: 订单表
            # 表ID: tblxxxxxxxxxxxx
            # 
            # 字段列表:
            # 1. 订单号 (text) - field_id: fldxxxxx
            # 2. 金额 (number) - field_id: fldyyyyy
            # ...
        """
        schema = self.get_table_schema(app_token, table_id)
        if not schema:
            print("❌ 获取表格结构失败")
            return
        
        table = schema.get('table', {})
        fields = schema.get('fields', [])
        
        print("=" * 50)
        print("数据表结构")
        print("=" * 50)
        print(f"表名: {table.get('name', 'N/A')}")
        print(f"表ID: {table.get('table_id', 'N/A')}")
        print(f"修订版本: {table.get('revision', 'N/A')}")
        print()
        
        if not fields:
            print("⚠️  该表没有字段")
            return
        
        print(f"字段列表 (共 {len(fields)} 个):")
        print("-" * 50)
        
        # 字段类型映射（中文显示）
        type_map = {
            1: "多行文本",
            2: "数字",
            3: "单选",
            4: "多选",
            5: "日期",
            7: "复选框",
            11: "人员",
            13: "电话号码",
            15: "超链接",
            17: "附件",
            18: "关联",
            19: "公式",
            20: "双向关联",
            21: "地理位置",
            22: "群组",
            23: "创建时间",
            24: "最后更新时间",
            25: "创建人",
            26: "修改人",
            1001: "自动编号",
            1002: "条码",
            1003: "进度",
            1004: "按钮",
        }
        
        for idx, field in enumerate(fields, 1):
            field_name = field.get('field_name', 'N/A')
            field_type = field.get('type', 0)
            field_id = field.get('field_id', 'N/A')
            type_name = type_map.get(field_type, f"未知类型({field_type})")
            
            # 获取字段属性（如果有）
            property_info = field.get('property', {})
            required = field.get('is_primary', False) or property_info.get('required', False)
            required_text = " [必填]" if required else ""
            
            print(f"{idx}. {field_name} ({type_name}){required_text}")
            print(f"   field_id: {field_id}")
            
            # 如果是选项类型，显示选项
            if field_type in [3, 4]:  # 单选或多选
                options = property_info.get('options', [])
                if options:
                    option_names = [opt.get('name', '') for opt in options]
                    print(f"   选项: {', '.join(option_names)}")
            
            print()
        
        print("=" * 50)
        print("\n💡 提示：插入数据时，使用字段名作为 key，例如：")
        print("   fields = {")
        for field in fields[:3]:  # 只显示前3个字段作为示例
            field_name = field.get('field_name', '')
            print(f"       '{field_name}': '值',")
        if len(fields) > 3:
            print("       ...")
        print("   }")
        print()
    
    def is_configured(self) -> bool:
        """
        检查飞书表格客户端是否已正确配置
        
        Returns:
            是否已配置
        """
        return self.client.is_configured()


# 全局单例
_feishu_table_client = None

def get_feishu_table_client() -> FeishuTableClient:
    """
    获取全局飞书表格客户端实例
    
    Returns:
        FeishuTableClient实例
    """
    global _feishu_table_client
    if _feishu_table_client is None:
        _feishu_table_client = FeishuTableClient()
    return _feishu_table_client
