"""
钢琴数据分析工具 - 主应用入口
"""
import os
import warnings
from typing import Optional

import dash
import dash_bootstrap_components as dbc

# 本地模块导入
from backend.history_manager import HistoryManager
from backend.session_manager import SessionManager
from ui.callbacks import register_callbacks
from ui.layout_components import create_main_layout
from utils.logger import Logger

# 常量定义
HOST = '0.0.0.0'
PORT = 9999
DEBUG = True

# 抑制来自 dash 及其依赖库的日期解析弃用警告
warnings.filterwarnings('ignore', category=DeprecationWarning, message='.*Parsing dates.*')


class ApplicationManager:
    """应用管理器 - 使用单例模式管理核心组件"""

    _instance: Optional['ApplicationManager'] = None
    _history_manager: Optional[HistoryManager] = None
    _session_manager: Optional[SessionManager] = None
    _app: Optional[dash.Dash] = None

    def __new__(cls) -> 'ApplicationManager':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @property
    def history_manager(self) -> HistoryManager:
        """获取历史管理器单例"""
        if self._history_manager is None:
            self._history_manager = HistoryManager()
        return self._history_manager

    @property
    def session_manager(self) -> SessionManager:
        """获取会话管理器单例"""
        if self._session_manager is None:
            self._session_manager = SessionManager(self.history_manager)
        return self._session_manager

    @property
    def app(self) -> dash.Dash:
        """获取Dash应用单例"""
        if self._app is None:
            self._app = self._create_app()
        return self._app

    def _create_app(self) -> dash.Dash:
        """创建并配置Dash应用"""
        app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
        app.config.suppress_callback_exceptions = True
        # 创建主界面布局
        app.layout = create_main_layout()
        register_callbacks(app, self.session_manager, self.history_manager)
        return app

    def run(self) -> None:
        """运行应用"""
        logger = Logger.get_logger()

        # 只在主进程中记录启动信息，避免Flask debug模式下的重复日志
        if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
            logger.info("✅ SPMID模块加载成功")
            logger.info(f"📁 数据库路径: {self.history_manager.db_path}")
            logger.info("✅ 数据库初始化完成")
            logger.info(f"🌐 访问地址: http://{HOST}:{PORT}")

        self.app.run(debug=DEBUG, host=HOST, port=PORT)


# 创建应用管理器实例
app_manager = ApplicationManager()

# 导出常用对象以保持向后兼容
app = app_manager.app
history_manager = app_manager.history_manager
session_manager = app_manager.session_manager

if __name__ == '__main__':
    app_manager.run()
