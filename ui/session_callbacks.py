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
        logger.info(f"[DEBUG] session_callbacks - session_manager地址: {id(session_manager)}")
        session_id, backend = session_manager.get_or_create_backend(session_id)
        logger.info(f"[DEBUG] session_callbacks - 创建的backend: {backend}")
        logger.info(f"[DEBUG] session_callbacks - session_manager.backends: {list(session_manager.backends.keys())}")
        if backend:
            # multi_algorithm_manager 在初始化时已创建
            logger.info("[OK] 多算法模式已就绪")

        return session_id

    # 添加时间滑块初始化回调 - 当数据加载完成后自动设置合理的时间范围
    @app.callback(
        [Output('time-filter-slider', 'min', allow_duplicate=True),
         Output('time-filter-slider', 'max', allow_duplicate=True),
         Output('time-filter-slider', 'value', allow_duplicate=True),
         Output('time-filter-slider', 'marks', allow_duplicate=True)],
        Input('report-content', 'children'),
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def initialize_time_slider_on_data_load(report_content, session_id):
        """当数据加载完成后初始化时间滑块"""
        backend = session_manager.get_backend(session_id)
        if not backend:
            return no_update, no_update, no_update, no_update

        # 只有当有分析数据时才更新滑块
        if not hasattr(backend, 'all_error_notes') or not backend.all_error_notes:
            return no_update, no_update, no_update, no_update

        try:
            # 获取实际的时间范围
            filter_info = backend.get_filter_info()
            time_range = filter_info['time_range']
            time_min, time_max = time_range

            # 确保时间范围是有效的
            if not isinstance(time_min, (int, float)) or not isinstance(time_max, (int, float)):
                return no_update, no_update, no_update, no_update

            if time_min >= time_max:
                return no_update, no_update, no_update, no_update

            # 转换为整数，避免滑块精度问题
            time_min, time_max = int(time_min), int(time_max)

            # 创建合理的标记点
            range_size = time_max - time_min
            if range_size <= 1000:
                step = max(1, range_size // 5)
            elif range_size <= 10000:
                step = max(10, range_size // 10)
            else:
                step = max(100, range_size // 20)

            marks = {}
            for i in range(time_min, time_max + 1, step):
                if i == time_min or i == time_max or (i - time_min) % (step * 2) == 0:
                    marks[i] = str(i)

            logger.info(f"⏰ 初始化时间滑块: min={time_min}, max={time_max}, 范围={range_size}")

            return time_min, time_max, [time_min, time_max], marks

        except Exception as e:
            logger.warning(f"[WARNING] 初始化时间滑块失败: {e}")
            return no_update, no_update, no_update, no_update

    # 添加初始化历史记录下拉菜单的回调 - 只在应用启动时初始化一次
    @app.callback(
        [Output('history-dropdown', 'options', allow_duplicate=True),
         Output('history-dropdown', 'value', allow_duplicate=True)],
        Input('session-id', 'data'),
        prevent_initial_call='initial_duplicate'  # 修复：使用 initial_duplicate 允许初始调用和重复输出
    )
    def initialize_history_dropdown(session_id):
        """初始化历史记录下拉框选项 - 只在会话初始化时调用一次"""
        # 检查是否已经初始化过
        if hasattr(initialize_history_dropdown, '_initialized'):
            return no_update, no_update

        try:
            # 检查数据库功能是否已禁用
            if hasattr(history_manager, 'disable_database') and history_manager.disable_database:
                disabled_option = {
                    'label': '⚠️ 数据库功能已禁用',
                    'value': 'disabled',
                    'disabled': True
                }
                initialize_history_dropdown._initialized = True
                return [disabled_option], None

            # 获取历史记录列表
            history_list = history_manager.get_history_list(limit=100)

            if not history_list:
                initialize_history_dropdown._initialized = True
                return [], None

            # 转换为下拉框选项格式
            options = []
            for record in history_list:
                label = f"{record['filename']} ({record['timestamp'][:19] if record['timestamp'] else '未知时间'}) - 多锤:{record['multi_hammers']} 丢锤:{record['drop_hammers']}"
                options.append({
                    'label': label,
                    'value': record['id']
                })

            logger.info(f"[OK] 初始化历史记录下拉菜单，找到 {len(options)} 条记录")
            initialize_history_dropdown._initialized = True
            return options, None  # 返回选项列表，但不预选任何项

        except Exception as e:
            logger.error(f"[ERROR] 初始化历史记录下拉框失败: {e}")
            initialize_history_dropdown._initialized = True
            return [], None

    @app.callback(
        Output('history-dropdown', 'options', allow_duplicate=True),
        [Input('history-search', 'value'),
         Input('session-id', 'data')],
        prevent_initial_call=True  # 修改为True，防止初始化时重复调用
    )
    def update_history_dropdown_search(search_value, session_id):
        """更新历史记录下拉框选项 - 仅搜索触发"""
        try:
            # 检查数据库功能是否已禁用
            if hasattr(history_manager, 'disable_database') and history_manager.disable_database:
                return [{
                    'label': '⚠️ 数据库功能已禁用',
                    'value': 'disabled',
                    'disabled': True
                }]

            # 获取历史记录列表
            history_list = history_manager.get_history_list(limit=100)

            if not history_list:
                return []

            # 转换为下拉框选项格式
            options = []
            for record in history_list:
                label = f"{record['filename']} ({record['timestamp'][:19] if record['timestamp'] else '未知时间'}) - 多锤:{record['multi_hammers']} 丢锤:{record['drop_hammers']}"

                # 如果有搜索值，则过滤选项
                if search_value and search_value.lower() not in label.lower():
                    continue

                options.append({
                    'label': label,
                    'value': record['id']
                })

            return options

        except Exception as e:
            logger.error(f"[ERROR] 更新历史记录下拉框失败: {e}")
            return []
