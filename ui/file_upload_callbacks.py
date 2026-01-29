"""
文件上传回调函数模块 - 统一处理所有文件上传相关的回调

包含：
1. 文件选择和上传
2. 文件列表显示
3. 算法名输入和确认
4. 上传状态管理
"""

import asyncio
import traceback
import time
from typing import Tuple, Optional
import dash
from dash import html, no_update
from dash import Input, Output, State

from backend.session_manager import SessionManager
from backend.file_upload_service import FileUploadService
from ui.multi_file_upload_handler import MultiFileUploadHandler
from utils.logger import Logger

logger = Logger.get_logger()


# ==================== 辅助函数 ====================

def _create_error_span(message: str, color: str = '#dc3545') -> html.Span:
    """创建统一的错误提示组件"""
    return html.Span(message, style={'color': color})


def _create_success_span(message: str) -> html.Span:
    """创建统一的成功提示组件"""
    return html.Span(message, style={'color': '#28a745', 'fontWeight': 'bold'})


def _validate_backend_and_data(session_manager, session_id: str, store_data: dict) -> Tuple[bool, Optional[html.Span]]:
    """
    验证后端实例和存储数据
    
    Returns:
        Tuple[bool, Optional[html.Span]]: (是否有效, 错误组件)
    """
    # 获取后端实例
    backend = session_manager.get_backend(session_id)
    if not backend:
        return False, _create_error_span("会话无效")
    
    # 验证存储数据
    if not store_data or 'filenames' not in store_data:
        return False, _create_error_span("文件数据无效")
    
    return True, None


# ==================== 回调函数 ====================

def register_file_upload_callbacks(app, session_manager: SessionManager):
    """注册文件上传相关的所有回调函数"""

    @app.callback(
        [Output('upload-multi-algorithm-data', 'contents', allow_duplicate=True),
         Output('upload-multi-algorithm-data', 'filename', allow_duplicate=True),
         Output('multi-algorithm-file-list', 'children', allow_duplicate=True),
         Output('multi-algorithm-upload-status', 'children', allow_duplicate=True)],
        [Input('reset-multi-algorithm-upload', 'n_clicks')],
        prevent_initial_call=True
    )
    def reset_multi_algorithm_upload(n_clicks):
        """重置多算法上传区域，清除上传状态"""
        if not n_clicks:
            return no_update, no_update, no_update, no_update

        # 重置上传组件和状态
        return None, None, html.Div(), html.Span("上传区域已重置，可以重新选择文件", style={'color': '#17a2b8'})

    @app.callback(
        [Output('multi-algorithm-upload-area', 'style', allow_duplicate=True),
         Output('multi-algorithm-management-area', 'style', allow_duplicate=True),
         Output('multi-algorithm-file-list', 'children', allow_duplicate=True),
         Output('multi-algorithm-upload-status', 'children', allow_duplicate=True),
         Output('multi-algorithm-files-store', 'data', allow_duplicate=True)],
        [Input('upload-multi-algorithm-data', 'contents')],
        [State('upload-multi-algorithm-data', 'filename'),
         State('session-id', 'data'),
         State('multi-algorithm-files-store', 'data')],
        prevent_initial_call=True
    )
    def handle_multi_file_upload(contents_list, filename_list, session_id, store_data):
        """处理多文件上传，显示文件列表供用户输入算法名称"""
        # 获取后端实例
        backend = session_manager.get_backend(session_id)
        if not backend:
            return no_update, no_update, no_update, no_update, no_update

        # 确保上传区域和管理区域始终显示
        upload_style = {'display': 'block'}
        management_style = {'display': 'block'}

        # 使用MultiFileUploadHandler处理文件上传
        upload_handler = MultiFileUploadHandler()
        file_list, status_text, new_store_data = upload_handler.process_uploaded_files(contents_list, filename_list, store_data, backend)

        return upload_style, management_style, file_list, status_text, new_store_data

    @app.callback(
        Output({'type': 'algorithm-status', 'index': dash.dependencies.MATCH}, 'children'),
        [Input({'type': 'confirm-algorithm-btn', 'index': dash.dependencies.MATCH}, 'n_clicks')],
        [State({'type': 'algorithm-name-input', 'index': dash.dependencies.MATCH}, 'value'),
         State({'type': 'confirm-algorithm-btn', 'index': dash.dependencies.MATCH}, 'id'),
         State('multi-algorithm-files-store', 'data'),
         State('session-id', 'data')],
        prevent_initial_call=True
    )
    def confirm_add_algorithm(n_clicks, algorithm_name, button_id, store_data, session_id):
        """
        确认添加算法（文件上传流程的最后一步）
        
        用户上传文件并输入算法名后，点击确认按钮触发此回调。
        """
        
        # 验证输入参数
        if not n_clicks or not algorithm_name or not algorithm_name.strip():
            return _create_error_span("请输入算法名称", '#ffc107')

        # 验证后端和数据
        is_valid, error_span = _validate_backend_and_data(session_manager, session_id, store_data)
        if not is_valid:
            return error_span

        logger.info(f"[DEBUG] file_upload_callbacks - session_manager地址: {id(session_manager)}")
        logger.info(f"[DEBUG] file_upload_callbacks - session_manager.backends: {list(session_manager.backends.keys())}")
        backend = session_manager.get_backend(session_id)
        
        logger.info(f"[DEBUG] 文件上传使用的backend: {backend}")
        if backend:
            logger.info(f"[DEBUG] backend.multi_algorithm_manager: {backend.multi_algorithm_manager}")
            logger.info(f"[DEBUG] backend.file_upload_service: {backend.file_upload_service}")
            logger.info(f"[DEBUG] backend.file_upload_service.multi_algorithm_manager: {backend.file_upload_service.multi_algorithm_manager}")

        try:
            upload_handler = MultiFileUploadHandler()
            file_id = button_id['index']
            
            # 从 store_data 中查找文件名（store 现在只存元数据，不存大内容）
            upload_handler = MultiFileUploadHandler()
            file_data = upload_handler.get_file_data_by_id(file_id, store_data)
            if not file_data:
                return _create_error_span("找不到文件信息")
            
            _, filename = file_data # 注意：store 中的 content 现在可能是 None
            algorithm_name = algorithm_name.strip()

            # [优化] 优先从后端缓存中获取二进制数据
            decoded_bytes = backend.get_cached_temp_file(file_id)
            
            if decoded_bytes:
                logger.info(f"[OK] 从后端缓存获取到文件数据 (ID: {file_id}), 大小: {len(decoded_bytes)} 字节")
            else:
                # 如果缓存中没有，尝试从 Store 中获取（兼容模式）
                logger.warning(f"[WARN] 后端缓存未命中 (ID: {file_id})，尝试从 Store 获取")
                content, _ = file_data
                if not content:
                    return _create_error_span("缓存已失效且 Store 中无内容，请重新上传")
                
                decoded_bytes = FileUploadService.decode_base64_file_content(content)
                if decoded_bytes is None:
                    return _create_error_span("文件解码失败")

            # ============ 步骤3: 添加算法（后端处理：SPMID 解析 + 分析） ============
            t0 = time.perf_counter()
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            success, error_msg = loop.run_until_complete(
                backend.file_upload_service.add_file_as_algorithm(
                    decoded_bytes, filename, algorithm_name
                )
            )
            loop.close()
            if success:
                logger.info(f"[OK] 算法 '{algorithm_name}' 添加成功")
                return _create_success_span("[OK] 添加成功")
            else:
                return _create_error_span(f"[ERROR] {error_msg}")

        except Exception as e:
            logger.error(f"[ERROR] 添加算法失败: {e}")
            logger.error(traceback.format_exc())
            return _create_error_span(f"添加失败: {str(e)}")
    
    # 独立的回调：监听algorithm-status变化，触发报告刷新
    @app.callback(
        Output('algorithm-management-trigger', 'data', allow_duplicate=True),
        Input({'type': 'algorithm-status', 'index': dash.dependencies.ALL}, 'children'),
        prevent_initial_call=True
    )
    def trigger_report_on_upload_success(status_children):
        """
        当有算法上传成功时，触发报告页面刷新
        
        这个回调监听所有 algorithm-status 的变化，
        当检测到成功状态时，更新 trigger 以通知报告页面
        """
        # 检查是否有成功状态
        if status_children:
            for status in status_children:
                if status and isinstance(status, dict):
                    # 检查是否包含成功标记
                    if 'props' in status and 'children' in status['props']:
                        children_text = str(status['props']['children'])
                        if 'OK' in children_text or '添加成功' in children_text:
                            logger.info(f"[TRIGGER] 检测到算法上传成功，触发报告刷新")
                            return time.time()
        
        return no_update

