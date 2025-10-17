"""
钢琴数据分析工具 - 主应用入口
"""
import dash
import dash_bootstrap_components as dbc
from utils.logger import Logger
import os

# 导入模块化组件
from backend.history_manager import HistoryManager
from ui.layout_components import create_main_layout
from ui.callbacks import register_callbacks

# 全局变量
backends = {}  # 存储不同会话的后端实例
history_manager = HistoryManager()

# 初始化Dash应用
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])

# 设置suppress_callback_exceptions=True以支持动态组件
app.config.suppress_callback_exceptions = True

# 设置主界面布局
app.layout = create_main_layout()

# 注册回调函数
register_callbacks(app, backends, history_manager)

logger = Logger.get_logger()

if __name__ == '__main__':
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        logger.info("✅ SPMID模块加载成功 (utils)")
        logger.info(f"📁 数据库路径: {history_manager.db_path}")
        logger.info("✅ 数据库初始化完成")
        logger.info("🌐 访问地址: http://localhost:9090")
    app.run(debug=True, host='0.0.0.0', port=9090)
