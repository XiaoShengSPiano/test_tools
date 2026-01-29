"""
会话和初始化管理回调函数模块
包含会话初始化、多算法模式启用等相关的回调逻辑
"""

import uuid

from dash import no_update
from dash import Input, Output, State

from backend.session_manager import SessionManager
from utils.logger import Logger

logger = Logger.get_logger()


def register_session_callbacks(app, session_manager: SessionManager, history_manager):
    """注册会话和初始化管理相关的回调函数"""

    @app.callback(
        Output('session-id', 'data'),
        Input('session-id', 'data'),
        prevent_initial_call=False
    )
    def init_session_and_enable_multi_algorithm(session_data):
        """初始化会话ID并自动启用多算法模式"""
        if session_data is None:
            session_id = str(uuid.uuid4())
        else:
            session_id = session_data

        # 多算法模式始终启用
        session_id, backend = session_manager.get_or_create_backend(session_id)
        if backend:
            # multi_algorithm_manager 在初始化时已创建
            logger.info("[OK] 多算法模式已就绪")

        return session_id
