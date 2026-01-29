"""
钢琴数据分析工具 - 主应用入口
"""
import warnings

from application_manager import ApplicationManager

# 抑制 dash 及其依赖的日期解析弃用警告
warnings.filterwarnings('ignore', category=DeprecationWarning, message='.*Parsing dates.*')

# 单例应用管理器（延迟创建 app / history / session）
app_manager = ApplicationManager()

# 向后兼容：导出常用对象
app = app_manager.app
history_manager = app_manager.history_manager
session_manager = app_manager.session_manager

if __name__ == '__main__':
    app_manager.run()
