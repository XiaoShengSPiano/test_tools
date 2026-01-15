"""
异常检测报告页面
"""
import traceback
import json

from dash import html, dcc, callback, Input, Output, State
import dash_bootstrap_components as dbc
from utils.logger import Logger

# 导入评级详情相关函数
from grade_detail_callbacks import get_grade_detail_data

logger = Logger.get_logger()

# 页面元数据（用于动态注册）
page_info = {
    'path': '/',
    'name': '异常检测报告',
    'title': 'SPMID分析 - 异常检测报告'
}


def layout():
    """
    异常检测报告页面布局
    
    显示异常检测报告的核心指标
    （文件管理已移至全局导航栏下方）
    """
    return dbc.Container([
        # 页面标题和快速导航
        dbc.Row([
            dbc.Col([
                html.Div([
                    html.H2([
                        html.I(className="fas fa-file-medical-alt me-2", style={'color': '#1976d2'}),
                        "异常检测报告"
                    ], className="mb-2"),
                    html.P("查看SPMID文件的匹配质量、延时误差和异常统计", 
                           className="text-muted mb-3"),
                ], className="mb-3")
            ], md=8),
            dbc.Col([
                html.Div([
                    html.Label("🔍 快速跳转", className="fw-bold mb-2 d-block"),
                    dbc.ButtonGroup([
                        dbc.Button([
                            html.I(className="fas fa-chart-waterfall me-1"),
                            "瀑布图"
                        ], href="/waterfall", color="info", size="sm", outline=True),
                        dbc.Button([
                            html.I(className="fas fa-chart-scatter me-1"),
                            "散点图"
                        ], href="/scatter", color="success", size="sm", outline=True),
                    ], className="w-100")
                ], className="text-center")
            ], md=4)
        ], className="mb-3"),
        
        html.Hr(className="mb-4"),
        
        # 报告内容区域
        dbc.Card([
            dbc.CardHeader([
                html.H5([
                    html.I(className="fas fa-file-medical-alt me-2"),
                    "异常检测报告"
                ], className="mb-0")
            ]),
            dbc.CardBody([
                # 报告内容容器（动态加载）
                dcc.Loading(
                    id="report-loading",
                    type="default",
                    children=[
                        html.Div(id='report-content-container')
                    ]
                )
            ])
        ], className="shadow-sm"),
        
    ], fluid=True, className="mt-3")


def load_report_content(session_id, session_manager):
    """
    根据session-id动态加载报告内容
    
    Args:
        session_id: 会话ID
        session_manager: SessionManager实例（通过参数传入，避免多实例问题）
        
    Returns:
        报告内容组件
    """
    logger.info(f"[DEBUG] load_report_content 被调用, session_id={session_id}")
    
    if not session_id:
        # 无session时显示提示
        logger.warning("[WARN] load_report_content: session_id 为空")
        return _create_no_data_alert()
    
    try:
        # 导入必要的模块
        from ui.components.grade_statistics import create_grade_statistics_card, create_grade_detail_table_placeholder
        from ui.components.data_overview import create_data_overview_card
        from ui.components.error_tables import create_error_statistics_section
        
        # 获取后端实例（不创建新的，避免多实例问题）
        logger.info(f"[DEBUG] pages/report.py - session_manager地址: {id(session_manager)}")
        logger.info(f"[DEBUG] pages/report.py - session_manager.backends: {list(session_manager.backends.keys())}")
        backend = session_manager.get_backend(session_id)
        logger.info(f"[DEBUG] pages/report.py - backend: {backend}")
        
        if not backend:
            # Backend不存在时，等待session初始化
            logger.warning(f"[WARN] Backend尚未初始化 (session={session_id})")
            return dbc.Alert([
                html.H4("⏳ 正在初始化", className="alert-heading"),
                html.P("系统正在初始化，请稍候..."),
                html.Hr(),
                html.Small("如果此消息持续显示，请刷新页面", className="text-muted")
            ], color="info")
        
        # 检查是否有活跃算法
        active_algorithms = backend.get_active_algorithms()
        
        logger.info(f"[DEBUG] active_algorithms: {active_algorithms} (count={len(active_algorithms) if active_algorithms else 0})")
        
        # 添加更详细的调试信息
        logger.info(f"[DEBUG] backend对象: {backend}")
        logger.info(f"[DEBUG] backend.multi_algorithm_manager对象: {backend.multi_algorithm_manager}")
        
        if backend.multi_algorithm_manager:
            all_algorithms = backend.multi_algorithm_manager.get_all_algorithms()
            logger.info(f"[DEBUG] multi_algorithm_manager存在, 所有算法数: {len(all_algorithms)}")
            for alg in all_algorithms:
                logger.info(f"[DEBUG]   - 算法: {alg.metadata.algorithm_name}, is_active={alg.is_active}, has_analyzer={alg.analyzer is not None}")
        else:
            logger.warning("[DEBUG] multi_algorithm_manager不存在")
        
        if not active_algorithms:
            logger.warning(f"[WARN] 没有活跃算法，返回等待数据提示")
            return _create_waiting_data_alert()
        
        # 构建报告内容
        report_components = []
        
        # 为每个活跃算法生成报告
        for algorithm in active_algorithms:
            if not algorithm.analyzer:
                continue
            
            algorithm_name = algorithm.metadata.algorithm_name
            
            # 添加分隔标题
            report_components.append(
                html.H3(f"📊 {algorithm_name}", className="mt-4 mb-3 text-primary")
            )
            
            # 1. 数据概览（统一通过backend获取数据）
            overview_stats = backend.get_data_overview_statistics(algorithm)
            report_components.append(
                create_data_overview_card(overview_stats, algorithm_name)
            )
            
            # 2. 错误统计
            error_sections = create_error_statistics_section(backend, [algorithm])
            report_components.extend(error_sections)
            
            # 3. 评级统计
            try:
                graded_stats = backend.get_graded_error_stats(algorithm)
                if graded_stats and 'error' not in graded_stats:
                    report_components.append(
                        create_grade_statistics_card(graded_stats, algorithm_name)
                    )
                    report_components.append(
                        create_grade_detail_table_placeholder(f"{algorithm_name}_grade")
                    )
            except Exception as e:
                logger.warning(f"获取评级统计失败: {e}")
        
        logger.info(f"[OK] 异常检测报告页面加载成功 (session={session_id})")
        return html.Div(report_components)
        
    except Exception as e:
        logger.error(f"[ERROR] 加载报告内容失败: {e}")
        traceback.print_exc()
        
        return _create_error_alert(str(e))


def _create_no_data_alert():
    """创建无数据提示"""
    return dbc.Alert([
        html.H4("📁 暂无数据", className="alert-heading"),
        html.P("请在上方文件管理区域上传SPMID文件开始分析"),
    ], color="info", className="mt-4")


def _create_waiting_data_alert():
    """创建等待数据提示"""
    return dbc.Alert([
        html.H4("📊 等待数据分析", className="alert-heading"),
        html.P("请在上方上传并分析SPMID文件"),
    ], color="info", className="mt-4")


def _create_error_alert(error_message):
    """创建错误提示"""
    return dbc.Alert([
        html.H4("❌ 加载失败", className="alert-heading"),
        html.P(f"错误信息: {error_message}"),
        html.Hr(),
        html.P("请检查日志文件获取详细信息", className="mb-0 text-muted")
    ], color="danger", className="mt-4")


def _get_grade_detail_data(backend, grade_key: str, algorithm_name: str):
    """
    获取评级统计的详细数据
    
    Args:
        backend: 后端实例
        grade_key: 评级键 ('correct', 'minor', 'moderate', 'large', 'severe')
        algorithm_name: 算法名称
        
    Returns:
        list: 表格行数据列表
    """
    try:
        return get_grade_detail_data(backend, grade_key, algorithm_name)
    except Exception as e:
        logger.error(f"获取评级详细数据失败: {e}")
        traceback.print_exc()
        return []


def _get_invalid_notes_detail_data(backend, algorithm_name: str, data_type: str):
    """
    获取无效音符的详细数据（直接调用algorithm的analyzer）
    
    Args:
        backend: 后端实例
        algorithm_name: 算法名称
        data_type: 数据类型（'record' 或 'replay'）
        
    Returns:
        list: 表格行数据列表
    """
    try:
        # 获取算法对象
        active_algorithms = backend.get_active_algorithms()
        target_algorithm = next(
            (alg for alg in active_algorithms if alg.metadata.algorithm_name == algorithm_name),
            None
        )
        
        if not target_algorithm or not target_algorithm.analyzer:
            return []
        
        invalid_statistics = target_algorithm.analyzer.invalid_statistics
        if not invalid_statistics:
            return []
        
        # 转换数据类型
        data_type_cn = '录制' if data_type == 'record' else '播放'
        
        # 获取详细数据
        detail_data = invalid_statistics.get_detailed_table_data(data_type_cn)
        
        return detail_data
        
    except Exception as e:
        logger.error(f"获取无效音符详细数据失败: {e}")
        traceback.print_exc()
        return []


def _create_grade_detail_table_content(detail_data, grade_key: str, algorithm_name: str):
    """
    创建评级详情表格内容
    
    Args:
        detail_data: 详细数据列表
        grade_key: 评级键
        algorithm_name: 算法名称
        
    Returns:
        html.Div: 表格容器
    """
    from dash import dash_table
    
    # 创建表格列定义
    if grade_key == 'major':
        # 匹配失败的列定义
        columns = [
            {"name": "算法名称", "id": "algorithm_name"},
            {"name": "类型", "id": "row_type"},
            {"name": "索引", "id": "index"},
            {"name": "键位ID", "id": "key_id"},
            {"name": "按键时间(ms)", "id": "keyon"},
            {"name": "释放时间(ms)", "id": "keyoff"},
            {"name": "锤击时间(ms)", "id": "hammer_time"},
            {"name": "锤速", "id": "hammer_velocity"},
            {"name": "按键时长(ms)", "id": "duration"},
            {"name": "失败原因", "id": "reason"}
        ]
    else:
        # 普通匹配的列定义
        columns = [
            {"name": "算法名称", "id": "algorithm_name"},
            {"name": "类型", "id": "data_type"},
            {"name": "全局索引", "id": "global_index"},
            {"name": "键位ID", "id": "keyId"},
            {"name": "按键时间(ms)", "id": "keyOn"},
            {"name": "释放时间(ms)", "id": "keyOff"},
            {"name": "锤击时间(ms)", "id": "hammer_times"},
            {"name": "锤速", "id": "hammer_velocities"},
            {"name": "按键时长(ms)", "id": "duration"},
            {"name": "匹配状态", "id": "match_status"}
        ]
    
    return html.Div([
        html.H5("详细数据", className="mb-3"),
        dash_table.DataTable(
            id={'type': 'grade-detail-datatable', 'index': algorithm_name},
            columns=columns,
            data=detail_data,
            page_action='none',  # 不分页，显示所有数据
            fixed_rows={'headers': True},  # 固定表头
            active_cell=None,  # 启用active_cell功能
            style_table={
                'maxHeight': '400px',
                'overflowY': 'auto',
                'overflowX': 'auto'
            },
            style_cell={
                'textAlign': 'center',
                'fontSize': '14px',
                'fontFamily': 'Arial, sans-serif',
                'padding': '8px',
                'minWidth': '80px'
            },
            style_header={
                'backgroundColor': '#f8f9fa',
                'fontWeight': 'bold',
                'borderBottom': '2px solid #dee2e6'
            },
            style_data_conditional=[
                # 录制行样式（默认白色背景）
                {
                    'if': {'filter_query': '{row_type} = "record"'},
                    'backgroundColor': '#ffffff',
                    'color': '#000000'
                },
                # 播放行样式（浅蓝色背景）
                {
                    'if': {'filter_query': '{row_type} = "replay"'},
                    'backgroundColor': '#e3f2fd',
                    'color': '#000000'
                },
                # 不同按键之间的分隔（浅灰色边框）
                {
                    'if': {'row_index': 'odd'},
                    'borderBottom': '1px solid #e0e0e0'
                },
                # 悬停样式 - 提供视觉反馈
                {
                    'if': {'state': 'active'},
                    'backgroundColor': 'rgba(0, 116, 217, 0.3)',
                    'border': '1px solid rgb(0, 116, 217)'
                }
            ]
        )
    ])


# ==================== 回调函数实现 ====================

def _handle_grade_detail_click(n_clicks_list, session_id, session_manager):
    """
    处理评级统计按钮点击的业务逻辑
    
    Args:
        n_clicks_list: 所有按钮的点击次数列表
        session_id: 会话ID
        session_manager: SessionManager实例
        
    Returns:
        Tuple: (表格样式列表, 表格内容列表)
    """
    from dash import no_update, callback_context
    import dash
    
    ctx = callback_context
    if not ctx.triggered:
        return [no_update], [no_update]
    
    # 解析触发的按钮ID
    triggered_id = ctx.triggered[0]['prop_id']
    try:
        id_part = triggered_id.split('.')[0]
        button_props = json.loads(id_part)
        button_index = button_props['index']  # 格式：算法名_评级类型
    except (json.JSONDecodeError, KeyError):
        return [no_update], [no_update]
    
    # 获取后端实例
    backend = session_manager.get_backend(session_id)
    if not backend:
        return [no_update], [no_update]
    
    # 获取活跃算法数量
    active_algorithms = backend.get_active_algorithms()
    if not active_algorithms:
        return [no_update], [no_update]
    
    num_outputs = len(active_algorithms)
    
    # 初始化输出值
    styles = [no_update] * num_outputs
    children_list = [no_update] * num_outputs
    
    # 解析button_index: "算法名_评级类型"
    if '_' in button_index:
        algorithm_name, grade_key = button_index.rsplit('_', 1)
    else:
        return [no_update], [no_update]
    
    # 找到对应算法的索引
    target_index = None
    for i, algorithm in enumerate(active_algorithms):
        if algorithm.metadata.algorithm_name == algorithm_name:
            target_index = i
            break
    
    if target_index is None:
        return [no_update], [no_update]
    
    # 获取详细数据
    detail_data = _get_grade_detail_data(backend, grade_key, algorithm_name)
    
    if not detail_data:
        # 没有数据，隐藏表格
        styles[target_index] = {'display': 'none'}
        children_list[target_index] = no_update
    else:
        # 有数据，显示表格
        styles[target_index] = {'display': 'block', 'marginTop': '20px'}
        children_list[target_index] = _create_grade_detail_table_content(
            detail_data, grade_key, algorithm_name
        )
    
    return styles, children_list


def _handle_hammer_error_click(btn_clicks_list, clear_clicks_list, current_children_list, session_id, session_manager):
    """
    处理锤击错误按钮点击和清除按钮点击的业务逻辑
    支持同时显示丢锤和多锤的错误表格（累积显示），以及清除功能

    Args:
        btn_clicks_list: 显示按钮的点击次数列表
        clear_clicks_list: 清除按钮的点击次数列表
        current_children_list: 当前表格内容列表
        session_id: 会话ID
        session_manager: SessionManager实例

    Returns:
        Tuple: (表格容器样式列表, 表格内容列表, 清除按钮容器样式列表)
    """
    from dash import no_update, callback_context
    from ui.components.error_tables import _create_hammer_error_detail_table
    import json

    ctx = callback_context
    if not ctx.triggered:
        return [no_update], [no_update], [no_update]

    # 解析触发的按钮ID
    triggered_id = ctx.triggered[0]['prop_id']
    try:
        id_part = triggered_id.split('.')[0]
        button_props = json.loads(id_part)
        button_type = button_props['type']
        button_index = button_props['index']
    except (json.JSONDecodeError, KeyError):
        return [no_update], [no_update], [no_update]

    # 获取后端实例
    backend = session_manager.get_backend(session_id)
    if not backend:
        return [no_update], [no_update], [no_update]

    # 获取活跃算法数量
    active_algorithms = backend.get_active_algorithms()
    if not active_algorithms:
        return [no_update], [no_update], [no_update]

    num_outputs = len(active_algorithms)

    # 初始化输出值
    styles = [no_update] * num_outputs
    children_list = [no_update] * num_outputs
    clear_btn_styles = [no_update] * num_outputs

    # 处理清除按钮点击
    if button_type == 'hammer-error-clear-btn':
        algorithm_name = button_index

        # 找到对应算法的索引
        target_index = None
        for i, algorithm in enumerate(active_algorithms):
            if algorithm.metadata.algorithm_name == algorithm_name:
                target_index = i
                break

        if target_index is not None:
            # 隐藏表格和清除按钮
            styles[target_index] = {'display': 'none'}
            children_list[target_index] = []
            clear_btn_styles[target_index] = {'display': 'none'}

        return styles, children_list, clear_btn_styles

    # 处理显示按钮点击
    if button_type == 'hammer-error-btn':
        # 解析button_index: "算法名_drop" 或 "算法名_multi"
        if '_' in button_index:
            algorithm_name, error_type = button_index.rsplit('_', 1)  # error_type: 'drop' or 'multi'
        else:
            return [no_update], [no_update], [no_update]

        # 找到对应算法的索引
        target_index = None
        for i, algorithm in enumerate(active_algorithms):
            if algorithm.metadata.algorithm_name == algorithm_name:
                target_index = i
                break

        if target_index is None:
            return [no_update], [no_update], [no_update]

        # 获取新点击的数据
        if error_type == 'drop':
            new_data = backend.get_drop_hammers_detail_table_data(algorithm_name)
        elif error_type == 'multi':
            new_data = backend.get_multi_hammers_detail_table_data(algorithm_name)
        else:
            return [no_update], [no_update], [no_update]

        # 即使没有数据也要更新UI状态，显示空表格或提示信息
        if not new_data:
            # 创建一个显示"无数据"的空表格
            new_table = _create_hammer_error_detail_table([], algorithm_name, error_type)
        else:
            new_table = _create_hammer_error_detail_table(new_data, algorithm_name, error_type)

        # 获取当前已有的内容
        new_table = _create_hammer_error_detail_table(new_data, algorithm_name, error_type)

        # 获取当前已有的内容
        current_content = current_children_list[target_index] if target_index < len(current_children_list) else None

        # 如果已有内容，将新表格添加到现有内容
        if current_content and isinstance(current_content, list) and len(current_content) > 0:
            # 已有表格，追加新表格
            combined_children = current_content + [new_table]
        else:
            # 首次添加
            combined_children = [new_table]

        # 更新目标算法的显示
        styles[target_index] = {'display': 'block'}
        children_list[target_index] = combined_children
        clear_btn_styles[target_index] = {'display': 'block'}  # 显示清除按钮

    return styles, children_list, clear_btn_styles


def _handle_invalid_notes_click(btn_clicks_list, clear_clicks_list, current_children_list, session_id, session_manager):
    """
    处理无效音符按钮点击和清除按钮点击的业务逻辑
    支持同时显示录制和播放的无效音符表格（累积显示），以及清除功能
    
    Args:
        btn_clicks_list: 显示按钮的点击次数列表
        clear_clicks_list: 清除按钮的点击次数列表
        current_children_list: 当前表格内容列表
        session_id: 会话ID
        session_manager: SessionManager实例
        
    Returns:
        Tuple: (表格容器样式列表, 表格内容列表, 清除按钮容器样式列表)
    """
    from dash import no_update, callback_context
    from ui.components.error_tables import _create_invalid_detail_table
    
    
    ctx = callback_context
    if not ctx.triggered:
        return [no_update], [no_update], [no_update]
    
    # 解析触发的按钮ID
    triggered_id = ctx.triggered[0]['prop_id']
    try:
        id_part = triggered_id.split('.')[0]
        button_props = json.loads(id_part)
        button_type = button_props['type']
        button_index = button_props['index']
    except (json.JSONDecodeError, KeyError):
        return [no_update], [no_update], [no_update]
    
    # 获取后端实例
    backend = session_manager.get_backend(session_id)
    if not backend:
        return [no_update], [no_update], [no_update]
    
    # 获取活跃算法数量
    active_algorithms = backend.get_active_algorithms()
    if not active_algorithms:
        return [no_update], [no_update], [no_update]
    
    num_outputs = len(active_algorithms)
    
    # 初始化输出值
    styles = [no_update] * num_outputs
    children_list = [no_update] * num_outputs
    clear_btn_styles = [no_update] * num_outputs
    
    # 处理清除按钮点击
    if button_type == 'invalid-notes-clear-btn':
        algorithm_name = button_index
        
        # 找到对应算法的索引
        target_index = None
        for i, algorithm in enumerate(active_algorithms):
            if algorithm.metadata.algorithm_name == algorithm_name:
                target_index = i
                break
        
        if target_index is not None:
            # 隐藏表格和清除按钮
            styles[target_index] = {'display': 'none'}
            children_list[target_index] = []
            clear_btn_styles[target_index] = {'display': 'none'}
        
        return styles, children_list, clear_btn_styles
    
    # 处理显示按钮点击
    if button_type == 'invalid-notes-btn':
        # 解析button_index: "算法名_record" 或 "算法名_replay"
        if '_' in button_index:
            algorithm_name, data_type = button_index.rsplit('_', 1)  # data_type: 'record' or 'replay'
        else:
            return [no_update], [no_update], [no_update]
        
        # 找到对应算法的索引
        target_index = None
        for i, algorithm in enumerate(active_algorithms):
            if algorithm.metadata.algorithm_name == algorithm_name:
                target_index = i
                break
        
        if target_index is None:
            return [no_update], [no_update], [no_update]
        
        # 获取新点击的数据
        new_data = _get_invalid_notes_detail_data(backend, algorithm_name, data_type)
        
        if not new_data:
            return [no_update], [no_update], [no_update]
        
        # 复用原来的表格创建函数
        new_table = _create_invalid_detail_table(new_data, algorithm_name, data_type)
        
        # 获取当前已有的内容
        current_content = current_children_list[target_index] if target_index < len(current_children_list) else None
        
        # 如果已有内容，将新表格添加到现有内容
        if current_content and isinstance(current_content, list) and len(current_content) > 0:
            # 已有表格，追加新表格
            combined_children = current_content + [new_table]
        else:
            # 首次添加
            combined_children = [new_table]
        
        # 更新目标算法的显示
        styles[target_index] = {'display': 'block'}
        children_list[target_index] = combined_children
        clear_btn_styles[target_index] = {'display': 'block'}  # 显示清除按钮
    
    return styles, children_list, clear_btn_styles


# ==================== 页面回调注册 ====================

def register_callbacks(app, session_manager):
    """
    注册报告页面的回调
    
    Args:
        app: Dash应用实例
        session_manager: SessionManager实例
    """
    import dash
    
    # 1. 报告内容更新回调
    @app.callback(
        Output('report-content-container', 'children'),
        [
            Input('session-id', 'data'),
            Input('algorithm-management-trigger', 'data'),
        ]
    )
    def update_report_content(session_id, algorithm_trigger):
        """当session-id或算法状态变化时，自动加载报告内容"""
        return load_report_content(session_id, session_manager)
    
    # 2. 评级详情表格回调
    @app.callback(
        Output({'type': 'grade-detail-table', 'index': dash.dependencies.ALL}, 'style'),
        Output({'type': 'grade-detail-table', 'index': dash.dependencies.ALL}, 'children'),
        Input({'type': 'grade-detail-btn', 'index': dash.dependencies.ALL}, 'n_clicks'),
        State('session-id', 'data'),
        prevent_initial_call=True
    )
    def show_grade_detail(n_clicks_list, session_id):
        """处理评级统计按钮点击，显示详细数据表格"""
        return _handle_grade_detail_click(n_clicks_list, session_id, session_manager)
    
    # 3. 锤击错误详情表格回调
    @app.callback(
        Output({'type': 'hammer-error-details', 'index': dash.ALL}, 'style'),
        Output({'type': 'hammer-error-details', 'index': dash.ALL}, 'children'),
        Output({'type': 'hammer-error-clear-container', 'index': dash.ALL}, 'style'),
        Input({'type': 'hammer-error-btn', 'index': dash.ALL}, 'n_clicks'),
        Input({'type': 'hammer-error-clear-btn', 'index': dash.ALL}, 'n_clicks'),
        State({'type': 'hammer-error-details', 'index': dash.ALL}, 'children'),
        State('session-id', 'data'),
        prevent_initial_call=True
    )
    def show_hammer_error_detail(btn_clicks_list, clear_clicks_list, current_children_list, session_id):
        """处理锤击错误按钮点击和清除按钮点击"""
        return _handle_hammer_error_click(
            btn_clicks_list, clear_clicks_list, current_children_list,
            session_id, session_manager
        )

    # 4. 无效音符详情表格回调
    @app.callback(
        Output({'type': 'invalid-notes-details', 'index': dash.ALL}, 'style'),
        Output({'type': 'invalid-notes-details', 'index': dash.ALL}, 'children'),
        Output({'type': 'invalid-notes-clear-container', 'index': dash.ALL}, 'style'),
        Input({'type': 'invalid-notes-btn', 'index': dash.ALL}, 'n_clicks'),
        Input({'type': 'invalid-notes-clear-btn', 'index': dash.ALL}, 'n_clicks'),
        State({'type': 'invalid-notes-details', 'index': dash.ALL}, 'children'),
        State('session-id', 'data'),
        prevent_initial_call=True
    )
    def show_invalid_notes_detail(btn_clicks_list, clear_clicks_list, current_children_list, session_id):
        """处理无效音符按钮点击和清除按钮点击"""
        return _handle_invalid_notes_click(
            btn_clicks_list, clear_clicks_list, current_children_list,
            session_id, session_manager
        )


