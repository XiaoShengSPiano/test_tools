"""
文件上传和历史记录管理回调函数模块
包含文件上传、多算法文件处理等相关的回调逻辑
"""

from dash import html, no_update
from dash import Input, Output, State

from backend.session_manager import SessionManager
from ui.multi_file_upload_handler import MultiFileUploadHandler
from utils.logger import Logger

logger = Logger.get_logger()


def register_upload_history_callbacks(app, session_manager: SessionManager):
    """注册文件上传和历史记录管理相关的回调函数"""

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

        # 确保多算法模式已启用
        # 确保multi_algorithm_manager已初始化
        if not backend.multi_algorithm_manager:
            backend._ensure_multi_algorithm_manager()

        # 确保上传区域和管理区域始终显示
        upload_style = {'display': 'block'}
        management_style = {'display': 'block'}

        # 使用MultiFileUploadHandler处理文件上传
        upload_handler = MultiFileUploadHandler()
        file_list, status_text, new_store_data = upload_handler.process_uploaded_files(contents_list, filename_list, store_data, backend)

        return upload_style, management_style, file_list, status_text, new_store_data
