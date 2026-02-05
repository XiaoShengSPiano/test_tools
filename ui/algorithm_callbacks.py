"""
算法管理回调函数模块
包含算法添加、删除、更新等管理相关的回调逻辑
"""

import asyncio
import time
import traceback
import warnings

# Suppress dash_table deprecation warning
warnings.filterwarnings('ignore', message='.*dash_table package is deprecated.*', category=UserWarning)

from typing import Optional, Tuple, List, Any, Union, Dict

import dash
import dash_bootstrap_components as dbc
from dash import html, dcc, no_update, dash_table
from dash import Input, Output, State
from dash._callback_context import callback_context

from backend.session_manager import SessionManager
from ui.multi_file_upload_handler import MultiFileUploadHandler
from utils.logger import Logger
from utils.ui_helpers import create_empty_figure
from plotly.graph_objects import Figure
import plotly.graph_objects as go

logger = Logger.get_logger()



def _create_error_span(message: str, color: str = '#dc3545') -> html.Span:
    """创建统一的错误提示组件"""
    return html.Span(message, style={'color': color})


def _create_success_span(message: str) -> html.Span:
    """创建统一的成功提示组件"""
    return html.Span(message, style={'color': '#28a745', 'fontWeight': 'bold'})


def _validate_backend_and_data(session_manager: SessionManager, session_id: str, store_data: dict) -> Tuple[bool, Optional[html.Span]]:
    """
    验证后端实例和存储数据

    Returns:
        Tuple[bool, Optional[html.Span]]: (是否有效, 错误组件)
    """
    # 获取后端实例
    backend = session_manager.get_backend(session_id)
    if not backend:
        return False, _create_error_span("会话无效")

    # multi_algorithm_manager 在初始化时已创建

    # 验证存储数据
    if not store_data or 'contents' not in store_data or 'filenames' not in store_data:
        return False, _create_error_span("文件数据丢失，请重新上传")

    return True, None


def _handle_plot_update_error(error: Exception, backend) -> Tuple[Figure, html.Div]:
    """
    处理图表更新错误，返回错误图表和错误报告

    Args:
        error: 发生的异常
        backend: 后端实例

    Returns:
        Tuple[Figure, html.Div]: (错误图表, 错误报告)
    """
    logger.error(f"[ERROR] 更新多算法瀑布图失败: {str(error)}")
    logger.error(traceback.format_exc())

    error_fig = create_empty_figure(f"更新失败: {str(error)}")

    # 返回包含必需组件的错误布局或占位符
    empty_fig = {}
    error_report = html.Div([
        html.H4("更新失败", className="text-center text-danger"),
        html.P(f"错误信息: {str(error)}", className="text-center"),
        # 包含所有必需的图表组件（隐藏），确保回调函数不会报错
        dcc.Graph(id='key-delay-scatter-plot', figure=empty_fig, style={'display': 'none'}),
        dcc.Graph(id='key-delay-zscore-scatter-plot', figure=empty_fig, style={'display': 'none'}),
        dcc.Graph(id='hammer-velocity-delay-scatter-plot', figure=empty_fig, style={'display': 'none'}),
        # key-hammer-velocity-scatter-plot 已删除（功能与按键-力度交互效应图重复）
        html.Div(id='offset-alignment-plot', style={'display': 'none'}),
        html.Div([
            dash_table.DataTable(
                id='offset-alignment-table',
                data=[],
                columns=[]
            )
        ], style={'display': 'none'})
    ])

    return error_fig, error_report


def _ensure_algorithm_active(backend, alg_name: str, display_name: str) -> bool:
    """
    确保算法激活状态

    Args:
        backend: 后端实例
        alg_name: 算法内部名称
        display_name: 算法显示名称

    Returns:
        bool: 是否激活
    """
    is_active = True
    algorithm = backend.multi_algorithm_manager.get_algorithm(alg_name) if hasattr(backend, 'multi_algorithm_manager') else None
    if algorithm:
        algorithm.is_active = True
        logger.info(f"[OK] 确保算法 '{display_name}' 默认显示: is_active={is_active}")
    return is_active


def _create_status_display(status: str, is_ready: bool) -> Tuple[html.I, str]:
    """
    创建状态显示组件

    Args:
        status: 状态字符串
        is_ready: 是否就绪

    Returns:
        Tuple[html.I, str]: (状态图标, 状态文本)
    """
    status_configs = {
        ('ready', True): ("fas fa-check-circle", "#28a745", "就绪"),
        ('loading', None): ("fas fa-spinner fa-spin", "#17a2b8", "加载中"),
        ('error', None): ("fas fa-exclamation-circle", "#dc3545", "错误"),
    }

    # 默认状态
    icon_class, color, text = "fas fa-clock", "#ffc107", "等待中"

    # 查找匹配的状态配置
    for (s, r), (cls, col, txt) in status_configs.items():
        if s == status and (r is None or r == is_ready):
            icon_class, color, text = cls, col, txt
            break

    status_icon = html.I(className=icon_class, style={'color': color, 'marginRight': '5px'})
    return status_icon, text


def _create_algorithm_card(alg_info: dict) -> dbc.Card:
    """
    创建算法卡片组件

    Args:
        alg_info: 算法信息字典

    Returns:
        dbc.Card: 算法卡片组件
    """
    alg_name = alg_info['algorithm_name']
    display_name = alg_info.get('display_name', alg_name)
    filename = alg_info['filename']
    color = alg_info['color']
    is_active = alg_info.get('is_active', True)

    # 创建状态显示
    status_icon, status_text = _create_status_display(alg_info['status'], alg_info['is_ready'])

    # 创建开关
    toggle_switch = dbc.Switch(
        id={'type': 'algorithm-toggle', 'index': alg_name},
        label='显示',
        value=is_active,
        style={'fontSize': '12px'}
    )

    # 创建删除按钮
    delete_button = dbc.Button(
        "删除",
        id={'type': 'algorithm-delete-btn', 'index': alg_name},
        color='danger',
        size='sm',
        n_clicks=0,
        style={'marginTop': '5px', 'width': '100%'}
    )

    return dbc.Card([
        dbc.CardBody([
            html.Div([
                html.Div([
                    html.Span(display_name, style={'fontWeight': 'bold', 'fontSize': '14px', 'color': color}),
                    html.Br(),
                    html.Small(filename, style={'color': '#6c757d', 'fontSize': '11px'}),
                    html.Br(),
                    html.Small([status_icon, status_text], style={'fontSize': '11px'})
                ], style={'flex': '1'}),
                html.Div([toggle_switch, delete_button], style={'marginLeft': '10px'})
            ], style={'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'center'})
        ])
    ], className='mb-2', style={'border': f'2px solid {color}', 'borderRadius': '5px'})


def _generate_plot_and_report(backend, active_algorithms: List[str]) -> Tuple[Figure, html.Div]:
    """
    生成图表和报告

    Args:
        backend: 后端实例
        active_algorithms: 激活的算法列表

    Returns:
        Tuple[Figure, html.Div]: (图表, 报告内容)
    """
    logger.info(f"[PROCESS] 更新多算法瀑布图，共 {len(active_algorithms)} 个激活算法")

    # 生成多算法瀑布图
    fig = backend.generate_waterfall_plot()

    # 报告内容已迁移至 pages/report.py，这里仅返回一个占位符以触发相关逻辑
    report_content = html.Div("报告正在加载...", style={'display': 'none'})

    logger.info("[OK] 多算法瀑布图和报告更新完成")
    return fig, report_content


def _parse_trigger_id(trigger_id: str) -> Optional[str]:
    """
    解析触发器ID，提取算法名称

    Args:
        trigger_id: 触发器ID字符串

    Returns:
        Optional[str]: 算法名称，解析失败返回None
    """
    import json
    trigger_prop_id = trigger_id.split('.')[0]
    try:
        trigger_data = json.loads(trigger_prop_id)
        return trigger_data.get('index', '')
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"[ERROR] 无法解析 trigger_id: {trigger_id}, error: {e}")
        return None


def _handle_toggle_action(
    backend,
    algorithm_name: str,
    toggle_values: List[Optional[bool]],
    toggle_ids: List[Optional[Dict[str, str]]]
) -> None:
    """
    处理开关切换操作

    Args:
        backend: 后端实例
        algorithm_name: 算法名称
        toggle_values: 开关值列表
        toggle_ids: 开关ID列表
    """
    if toggle_values and toggle_ids:
        for i, toggle_id in enumerate(toggle_ids):
            if toggle_id and toggle_id.get('index') == algorithm_name:
                new_value = toggle_values[i] if i < len(toggle_values) else None
                if new_value is not None:
                    algorithm = backend.multi_algorithm_manager.get_algorithm(algorithm_name) if hasattr(backend, 'multi_algorithm_manager') else None
                    if algorithm:
                        if algorithm.is_active != new_value:
                            algorithm.is_active = new_value
                            logger.info(f"[OK] 算法 '{algorithm_name}' 显示状态设置为: {'显示' if new_value else '隐藏'}")
                        else:
                            logger.debug(f"[INFO] 算法 '{algorithm_name}' 显示状态未变化: {new_value}")
                break
    else:
        # 向后兼容
        backend.toggle_algorithm(algorithm_name)


def _handle_delete_action_simple(backend, algorithm_name: str) -> Optional[str]:
    """
    处理删除操作

    Args:
        backend: 后端实例
        algorithm_name: 算法名称

    Returns:
        Optional[str]: 删除的算法文件名，如果未删除返回None
    """
    # 获取算法信息用于文件列表更新
    algorithms_before = backend.get_all_algorithms()

    deleted_filename = None
    for alg_info in algorithms_before:
        if alg_info['algorithm_name'] == algorithm_name:
            deleted_filename = alg_info.get('filename', '')
            break

    success = backend.remove_algorithm(algorithm_name)

    if success:
        logger.info(f"[OK] 算法 '{algorithm_name}' 已删除")
        return deleted_filename
    else:
        logger.error(f"[ERROR] 删除算法 '{algorithm_name}' 失败")
        return None


def _update_file_list_after_algorithm_change(
    backend,
    algorithms: List[Dict[str, Any]],
    algorithm_deleted: bool,
    store_data: Optional[Dict[str, Any]]
) -> Tuple[Union[html.Div, Any], Union[html.Span, Any], Union[Dict[str, Any], Any]]:
    """
    更新算法变更后的文件列表

    Args:
        backend: 后端实例
        algorithms: 当前算法列表
        algorithm_deleted: 是否删除了算法
        store_data: 存储的数据

    Returns:
        Tuple[Union[html.Div, Any], Union[html.Span, Any], Union[Dict[str, Any], Any]]:
        (文件列表组件, 状态文本, 更新后的存储数据)
    """
    # 获取已添加算法的文件名
    added_filenames = {alg_info.get('filename', '') for alg_info in algorithms}

    # 初始化返回值
    file_list_children = no_update
    upload_status_text = no_update
    updated_store_data = no_update

    # 需要更新文件列表的条件：有算法存在且有store_data时就更新
    need_update = len(algorithms) > 0 and store_data and 'filenames' in store_data

    if need_update and store_data and 'contents' in store_data and 'filenames' in store_data:
        contents_list = store_data.get('contents', [])
        filenames_list = store_data.get('filenames', [])
        file_ids = store_data.get('file_ids', [])
        history_hints = store_data.get('history_hints', [])

        # 过滤出未添加的文件
        filtered_contents = []
        filtered_filenames = []
        filtered_file_ids = []
        filtered_history_hints = []

        for i, filename in enumerate(filenames_list):
            if filename not in added_filenames:
                if i < len(contents_list):
                    filtered_contents.append(contents_list[i])
                filtered_filenames.append(filename)
                if i < len(file_ids):
                    filtered_file_ids.append(file_ids[i])
                if i < len(history_hints):
                    filtered_history_hints.append(history_hints[i])
                else:
                    filtered_history_hints.append(None)

        # 更新存储数据
        updated_store_data = {
            'contents': filtered_contents,
            'filenames': filtered_filenames,
            'file_ids': filtered_file_ids,
            'history_hints': filtered_history_hints
        }

        # 生成文件列表UI
        upload_handler = MultiFileUploadHandler()
        file_items = []
        for content, filename, file_id, history_hint in zip(filtered_contents, filtered_filenames, filtered_file_ids, filtered_history_hints):
            if filename not in added_filenames:
                file_card = upload_handler.create_file_card(file_id, filename, existing_record=history_hint)
                file_items.append(file_card)

        file_list_children = html.Div(file_items) if file_items else []

        # 生成状态文本
        total_files = len(filtered_filenames)
        if total_files > 0:
            upload_status_text = html.Span(
                f"共 {total_files} 个文件，请为每个文件输入算法名称",
                style={'color': '#17a2b8', 'fontWeight': 'bold'}
            )
        else:
            upload_status_text = html.Span("", style={'color': '#6c757d'})
    elif algorithm_deleted:
        # 删除了算法但没有store_data
        file_list_children = []
        upload_status_text = html.Span("", style={'color': '#6c757d'})
        updated_store_data = {'contents': [], 'filenames': [], 'file_ids': []}

    return file_list_children, upload_status_text, updated_store_data


def _generate_upload_status_text(
    updated_store_data: Optional[Dict[str, Any]],
    store_data: Optional[Dict[str, Any]],
    algorithms: List[Dict[str, Any]]
) -> html.Span:
    """
    生成上传状态文本

    Args:
        updated_store_data: 更新后的存储数据
        store_data: 原始存储数据
        algorithms: 当前算法列表

    Returns:
        html.Span: 状态文本组件
    """
    if updated_store_data and isinstance(updated_store_data, dict):
        total_files = len(updated_store_data.get('filenames', []))
        if total_files > 0:
            return html.Span(
                f"共 {total_files} 个文件，请为每个文件输入算法名称",
                style={'color': '#17a2b8', 'fontWeight': 'bold'}
            )
    elif store_data and isinstance(store_data, dict):
        total_files = len(store_data.get('filenames', []))
        added_filenames = {alg_info.get('filename', '') for alg_info in algorithms}
        filtered_count = sum(1 for f in store_data.get('filenames', []) if f not in added_filenames)
        if filtered_count > 0:
            return html.Span(
                f"共 {filtered_count} 个文件，请为每个文件输入算法名称",
                style={'color': '#17a2b8', 'fontWeight': 'bold'}
            )

    return html.Span("", style={'color': '#6c757d'})

def register_algorithm_callbacks(app, session_manager: SessionManager):
    """注册算法管理相关的回调函数"""

    @app.callback(
        [Output('multi-algorithm-file-list', 'children', allow_duplicate=True),
         Output('multi-algorithm-upload-status', 'children', allow_duplicate=True),
         Output('multi-algorithm-files-store', 'data', allow_duplicate=True)],
        Input('algorithm-management-trigger', 'data'),
        State('session-id', 'data'),
        State('multi-algorithm-files-store', 'data'),
        prevent_initial_call=True
    )
    def update_file_list_after_algorithm_add(management_trigger, session_id, store_data):
        """算法添加成功后更新文件列表"""
        backend = session_manager.get_backend(session_id)
        if not backend:
            return no_update, no_update, no_update

        algorithms = backend.get_all_algorithms()
        logger.info(f"[PROCESS] 算法添加成功，更新文件列表")

        file_list_children, upload_status_text, updated_store_data = _update_file_list_after_algorithm_change(
            backend, algorithms, False, store_data
        )

        return file_list_children, upload_status_text, updated_store_data

    @app.callback(
        Output('algorithm-list-trigger', 'data', allow_duplicate=True),
        [Input({'type': 'algorithm-upload-success', 'index': dash.dependencies.ALL}, 'data')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def trigger_algorithm_list_update(upload_success_data, session_id):
        """当新的算法上传成功时触发列表更新"""
        trigger_value = time.time()
        logger.info(f"[PROCESS] 收到算法上传成功信号，触发列表更新")
        return trigger_value
    
    # 新架构：算法变化时触发报告内容更新
    @app.callback(
        Output('algorithm-management-trigger', 'data', allow_duplicate=True),
        [Input('algorithm-list-trigger', 'data'),
         Input({'type': 'algorithm-toggle', 'index': dash.dependencies.ALL}, 'value')],
        prevent_initial_call=True
    )
    def trigger_report_update_on_algorithm_change(trigger_data, toggle_values):
        """
        当算法添加/删除/切换时，触发报告更新
        
        新架构：通过更新 algorithm-management-trigger 来通知报告页面刷新
        """
        return time.time()

    @app.callback(
        [Output('algorithm-list', 'children', allow_duplicate=True),
         Output('algorithm-management-status', 'children', allow_duplicate=True),
         Output('active-algo-count-badge', 'children')],
        [Input('algorithm-list-trigger', 'data')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def update_algorithm_list(trigger_data: Any, session_id: str) -> Tuple[List[dbc.Card], html.Span, str]:
        """
        更新算法列表显示及角标数量
        """
        backend = session_manager.get_backend(session_id)
        if not backend:
            return [], html.Span(""), "0"

        try:
            algorithms = backend.get_all_algorithms()
            logger.info(f"[PROCESS] 更新算法列表: 共 {len(algorithms)} 个算法")
            
            algo_count = str(len(algorithms))

            if not algorithms:
                return [], html.Span("暂无算法，请上传文件", style={'color': '#6c757d'}), algo_count

            algorithm_items = []
            for alg_info in algorithms:
                # 处理算法激活状态
                alg_name = alg_info['algorithm_name']
                display_name = alg_info.get('display_name', alg_name)

                if alg_info.get('is_active') is None:
                    alg_info['is_active'] = _ensure_algorithm_active(backend, alg_name, display_name)

                # 创建算法卡片
                algorithm_items.append(_create_algorithm_card(alg_info))

            # 创建状态文本
            status_text = html.Span(f"共 {len(algorithms)} 个算法", style={'color': '#6c757d'})

            return algorithm_items, status_text, algo_count

        except Exception as e:
            logger.error(f"[ERROR] 更新算法列表失败: {e}")
            logger.error(traceback.format_exc())
            return [], html.Span(f"更新失败: {str(e)}", style={'color': '#dc3545'}), "0"

    @app.callback(
        [Output('algorithm-list-trigger', 'data', allow_duplicate=True),
         Output('multi-algorithm-file-list', 'children', allow_duplicate=True),
         Output('multi-algorithm-upload-status', 'children', allow_duplicate=True),
         Output('multi-algorithm-files-store', 'data', allow_duplicate=True)],
        [Input({'type': 'algorithm-toggle', 'index': dash.dependencies.ALL}, 'value'),
         Input({'type': 'algorithm-delete-btn', 'index': dash.dependencies.ALL}, 'n_clicks')],
        [State({'type': 'algorithm-toggle', 'index': dash.dependencies.ALL}, 'id'),
         State({'type': 'algorithm-delete-btn', 'index': dash.dependencies.ALL}, 'id'),
         State('session-id', 'data'),
         State('multi-algorithm-files-store', 'data')],
        prevent_initial_call=True
    )
    def handle_algorithm_management(
        toggle_values: List[Optional[bool]],
        delete_clicks_list: List[Optional[int]],
        toggle_ids: List[Optional[Dict[str, str]]],
        delete_ids: List[Optional[Dict[str, str]]],
        session_id: str,
        store_data: Optional[Dict[str, Any]]
    ) -> Tuple[
        Union[float, Any],
        Union[html.Div, List, Any],
        Union[html.Span, Any],
        Union[Dict[str, List], Any]
    ]:
        """
        处理算法管理操作（显示/隐藏、删除）

        Args:
            toggle_values: 开关值列表
            delete_clicks_list: 删除点击列表
            toggle_ids: 开关ID列表
            delete_ids: 删除ID列表
            session_id: 会话ID
            store_data: 存储的数据

        Returns:
            Tuple: (触发时间, 文件列表, 上传状态, 存储数据)
        """
        logger.info("[PROCESS] handle_algorithm_management 被触发")

        backend = session_manager.get_backend(session_id)
        if not backend:
            logger.warning("[WARNING] handle_algorithm_management: 无法获取backend")
            return no_update, no_update, no_update, no_update

        # multi_algorithm_manager 在初始化时已创建

        ctx = callback_context
        if not ctx.triggered:
            logger.warning("[WARNING] handle_algorithm_management: 没有触发上下文")
            return no_update, no_update, no_update, no_update

        trigger_id = ctx.triggered[0]['prop_id']
        logger.info(f"[PROCESS] 触发源: {trigger_id}")

        try:
            # 解析触发器ID
            algorithm_name = _parse_trigger_id(trigger_id)
            if algorithm_name is None:
                logger.warning(f"[WARNING] 无法解析算法名称")
                return no_update, no_update, no_update, no_update

            # 处理不同的操作
            algorithm_deleted = False

            if 'algorithm-toggle' in trigger_id:
                logger.debug(f"[DEBUG] 切换算法显示状态: {algorithm_name}")
                _handle_toggle_action(backend, algorithm_name, toggle_values, toggle_ids)
            elif 'algorithm-delete-btn' in trigger_id:
                logger.debug(f"[DEBUG] 处理算法删除: {algorithm_name}")
                # 使用delete_clicks_list来检查是否有点击
                # 找到对应算法的索引
                clicked = False
                for i, delete_id in enumerate(delete_ids):
                    if delete_id and delete_id.get('index') == algorithm_name:
                        if i < len(delete_clicks_list) and delete_clicks_list[i] and delete_clicks_list[i] > 0:
                            clicked = True
                        break
                
                if clicked:
                    deleted_filename = _handle_delete_action_simple(backend, algorithm_name)
                    algorithm_deleted = deleted_filename is not None
            else:
                logger.warning(f"[WARNING] 未知触发源: {trigger_id}")
                return no_update, no_update, no_update, no_update

            # 触发算法列表更新，让update_algorithm_list回调重新生成完整的UI
            # 这样可以确保所有UI组件都反映最新的算法状态
            trigger_time = time.time()

            # 更新文件列表（只有在删除算法时才需要）
            if algorithm_deleted:
                algorithms = backend.get_all_algorithms()
                file_list_children, upload_status_text, updated_store_data = _update_file_list_after_algorithm_change(
                    backend, algorithms, algorithm_deleted, store_data
                )
            else:
                file_list_children = no_update
                upload_status_text = no_update
                updated_store_data = no_update

            # 算法列表的UI更新由algorithm-list-trigger触发update_algorithm_list回调来处理
            return (
                trigger_time,  # algorithm-list-trigger - 触发更新
                file_list_children,
                upload_status_text,
                updated_store_data
            )

        except Exception as e:
            logger.error(f"[ERROR] 处理算法管理操作失败: {e}")
            logger.error(traceback.format_exc())
            return no_update, no_update, no_update, no_update



