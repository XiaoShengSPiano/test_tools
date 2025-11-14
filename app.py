"""
钢琴数据分析工具 - 主应用入口
"""
import warnings
# 抑制来自 dash 及其依赖库的日期解析弃用警告
warnings.filterwarnings('ignore', category=DeprecationWarning, message='.*Parsing dates.*')
import dash
import dash_bootstrap_components as dbc
from utils.logger import Logger
import os

# 导入模块化组件
from backend.history_manager import HistoryManager
from backend.session_manager import SessionManager
from ui.layout_components import create_main_layout
from ui.callbacks import register_callbacks

# 全局变量（使用单例模式，避免在debug模式下重复初始化）
# 注意：在Flask debug模式下，模块会被重新加载，但单例模式可以确保只初始化一次
_history_manager = None
_session_manager = None

def get_history_manager():
    """获取HistoryManager单例"""
    global _history_manager
    if _history_manager is None:
        _history_manager = HistoryManager()
    return _history_manager

def get_session_manager():
    """获取SessionManager单例"""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager(get_history_manager())
    return _session_manager

# 初始化单例
history_manager = get_history_manager()
session_manager = get_session_manager()

# 初始化Dash应用
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])

# 设置suppress_callback_exceptions=True以支持动态组件
app.config.suppress_callback_exceptions = True

# 设置主界面布局
app.layout = create_main_layout()

# 注册回调函数
print("=" * 100)
print("🔧 开始注册回调函数...")
print("=" * 100)
register_callbacks(app, session_manager, history_manager)
print("=" * 100)
print("✅ 回调函数注册完成！")
print("=" * 100)

logger = Logger.get_logger()

if __name__ == '__main__':
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        logger.info("✅ SPMID模块加载成功 (utils)")
        logger.info(f"📁 数据库路径: {history_manager.db_path}")
        logger.info("✅ 数据库初始化完成")
        logger.info("🌐 访问地址: http://localhost:9090")
    app.run(debug=True, host='0.0.0.0', port=9090)
