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
from ui.layout_components import create_report_layout
from utils.logger import Logger
from plotly.graph_objects import Figure
import plotly.graph_objects as go

logger = Logger.get_logger()



def _create_empty_figure_for_callback(title: str) -> Figure:
    """创建用于回调的空Plotly figure对象"""
    fig = go.Figure()
    fig.add_annotation(
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        text=title,
        showarrow=False,
        font=dict(size=16, color="gray"),
        align="center"
    )

    fig.update_layout(
        title=title,
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        height=600,
        template='plotly_white',
        margin=dict(l=20, r=20, t=60, b=20)
    )
    return fig


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

    # 确保多算法模式已启用
    if not backend.multi_algorithm_manager:
        backend._ensure_multi_algorithm_manager()

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

    error_fig = _create_empty_figure_for_callback(f"更新失败: {str(error)}")

    # 尝试创建错误报告
    try:
        error_report = create_report_layout(backend)
    except:
        # 如果 create_report_layout 也失败，返回包含必需组件的错误布局
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


def _create_migration_alert(existing_filename: str) -> dbc.Alert:
    """
    创建数据迁移提示UI

    Args:
        existing_filename: 现有文件的名称

    Returns:
        dbc.Alert: 迁移提示组件
    """
    return dbc.Alert([
        html.H6("检测到现有分析数据", className="mb-2", style={'fontWeight': 'bold'}),
        html.P(f"文件: {existing_filename}", style={'fontSize': '14px', 'marginBottom': '10px'}),
        html.P("请为这个算法输入名称，以便在多算法模式下进行对比：", style={'fontSize': '14px', 'marginBottom': '10px'}),
        html.Div(id='migration-components-placeholder', children=[
            html.P("请在下方输入算法名称并点击确认迁移按钮", style={'fontSize': '12px', 'color': '#6c757d'})
        ])
    ], color='info', className='mb-3')


def _create_error_alert(message: str, title: str = "迁移失败") -> dbc.Alert:
    """
    创建错误提示UI

    Args:
        message: 错误消息
        title: 错误标题

    Returns:
        dbc.Alert: 错误提示组件
    """
    return dbc.Alert([
        html.H6(title, className="mb-2", style={'fontWeight': 'bold', 'color': '#dc3545'}),
        html.P(message, style={'fontSize': '14px'})
    ], color='danger', className='mb-3')


def _check_existing_data(backend) -> Tuple[bool, Optional[str]]:
    """
    检查是否有现有分析数据

    Args:
        backend: 后端实例

    Returns:
        Tuple[bool, Optional[str]]: (是否有数据, 文件名)
    """
    try:
        analyzer = backend._get_current_analyzer()
        if analyzer and analyzer.note_matcher and hasattr(analyzer, 'matched_pairs') and len(analyzer.matched_pairs) > 0:
            data_source_info = backend.get_data_source_info()
            existing_filename = data_source_info.get('filename', '未知文件')
            logger.info(f"[OK] 检测到现有分析数据: {existing_filename}")
            return True, existing_filename
    except Exception as e:
        logger.warning(f"[WARNING] 检查现有数据时出错: {e}")

    return False, None


def _handle_session_trigger(backend) -> Tuple[dict, Optional[dbc.Alert]]:
    """
    处理会话初始化触发

    Args:
        backend: 后端实例

    Returns:
        Tuple[dict, Optional[dbc.Alert]]: (样式, 组件)
    """
    logger.info("[INFO] 多算法模式始终启用")

    has_existing_data, existing_filename = _check_existing_data(backend)

    if has_existing_data:
        migration_area = _create_migration_alert(existing_filename)
        logger.info("[OK] 显示迁移提示区域")
        return {'display': 'block'}, migration_area
    else:
        logger.info("[INFO] 没有现有数据需要迁移")
        return {'display': 'none'}, None


def _handle_migration_trigger(backend, algorithm_name: str) -> Tuple[Any, Optional[dbc.Alert]]:
    """
    处理迁移按钮触发

    Args:
        backend: 后端实例
        algorithm_name: 算法名称

    Returns:
        Tuple[Any, Optional[dbc.Alert]]: (样式更新, 错误组件)
    """
    try:
        # 确保multi_algorithm_manager已初始化
        if not backend.multi_algorithm_manager:
            backend._ensure_multi_algorithm_manager()

        algorithm_name = algorithm_name.strip()
        logger.info(f"📤 开始迁移现有数据到算法: {algorithm_name}")
        success, error_msg = backend.migrate_existing_data_to_algorithm(algorithm_name)

        if success:
            logger.info("[OK] 数据迁移成功")
            return {'display': 'none'}, None
        else:
            logger.error(f"[ERROR] 数据迁移失败: {error_msg}")
            error_alert = _create_error_alert(f"错误: {error_msg}")
            return no_update, error_alert

    except Exception as e:
        logger.error(f"[ERROR] 迁移数据时发生异常: {e}")
        logger.error(traceback.format_exc())
        error_alert = _create_error_alert(f"异常: {str(e)}")
        return no_update, error_alert


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

    # 生成报告内容（多算法模式下的报告）
    report_content = create_report_layout(backend)

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

        # 过滤出未添加的文件
        filtered_contents = []
        filtered_filenames = []
        filtered_file_ids = []

        for i, filename in enumerate(filenames_list):
            if filename not in added_filenames:
                if i < len(contents_list):
                    filtered_contents.append(contents_list[i])
                filtered_filenames.append(filename)
                if i < len(file_ids):
                    filtered_file_ids.append(file_ids[i])

        # 更新存储数据
        updated_store_data = {
            'contents': filtered_contents,
            'filenames': filtered_filenames,
            'file_ids': filtered_file_ids
        }

        # 生成文件列表UI
        from ui.multi_file_upload_handler import MultiFileUploadHandler
        upload_handler = MultiFileUploadHandler()
        file_items = []
        for content, filename, file_id in zip(filtered_contents, filtered_filenames, filtered_file_ids):
            if filename not in added_filenames:
                file_card = upload_handler.create_file_card(file_id, filename)
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
        Output({'type': 'algorithm-status', 'index': dash.dependencies.MATCH}, 'children'),
        [Input({'type': 'confirm-algorithm-btn', 'index': dash.dependencies.MATCH}, 'n_clicks')],
        [State({'type': 'algorithm-name-input', 'index': dash.dependencies.MATCH}, 'value'),
         State({'type': 'confirm-algorithm-btn', 'index': dash.dependencies.MATCH}, 'id'),
         State('multi-algorithm-files-store', 'data'),
         State('session-id', 'data')],
        prevent_initial_call=True
    )
    def confirm_add_algorithm(n_clicks, algorithm_name, button_id, store_data, session_id):
        """确认添加算法"""
        # 验证输入参数
        if not n_clicks or not algorithm_name or not algorithm_name.strip():
            return _create_error_span("请输入算法名称", '#ffc107')

        # 验证后端和数据
        is_valid, error_span = _validate_backend_and_data(session_manager, session_id, store_data)
        if not is_valid:
            return error_span

        backend = session_manager.get_backend(session_id)

        try:
            # 获取文件数据
            upload_handler = MultiFileUploadHandler()
            file_id = button_id['index']
            file_data = upload_handler.get_file_data_by_id(file_id, store_data)

            if not file_data:
                return _create_error_span("文件数据无效")

            content, filename = file_data
            algorithm_name = algorithm_name.strip()

            # 解码base64文件内容
            import base64
            if ',' in content:
                # 处理 "data:mime;base64,data" 格式
                decoded_bytes = base64.b64decode(content.split(',')[1])
            else:
                # 处理纯base64字符串
                decoded_bytes = base64.b64decode(content)

            # 异步添加算法
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            success, error_msg = loop.run_until_complete(
                backend.add_algorithm(algorithm_name, filename, decoded_bytes)
            )
            loop.close()

            if success:
                # 确保新添加的算法默认显示
                algorithm = backend.multi_algorithm_manager.get_algorithm(algorithm_name) if hasattr(backend, 'multi_algorithm_manager') else None
                if algorithm:
                    algorithm.is_active = True
                    logger.info(f"[OK] 确保算法 '{algorithm_name}' 默认显示: is_active={algorithm.is_active}")
                logger.info(f"[OK] 算法 '{algorithm_name}' 添加成功")
                return _create_success_span("[OK] 添加成功")
            else:
                return _create_error_span(f"[ERROR] {error_msg}")

        except Exception as e:
            logger.error(f"[ERROR] 添加算法失败: {e}")
            logger.error(traceback.format_exc())
            return _create_error_span(f"添加失败: {str(e)}")

    @app.callback(
        [Output('algorithm-list-trigger', 'data', allow_duplicate=True),
         Output('algorithm-management-trigger', 'data', allow_duplicate=True)],
        [Input({'type': 'algorithm-status', 'index': dash.dependencies.ALL}, 'children'),
         Input('confirm-migrate-existing-data-btn', 'n_clicks')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def trigger_algorithm_list_update(status_children, migrate_clicks, session_id):
        """当算法状态改变时触发算法列表和文件列表更新"""
        trigger_value = time.time()
        logger.info(f"[PROCESS] 触发算法列表更新")
        return trigger_value, trigger_value

    @app.callback(
        [Output('main-plot', 'figure', allow_duplicate=True),
         Output('report-content', 'children', allow_duplicate=True)],
        [Input('algorithm-list-trigger', 'data'),
         Input({'type': 'algorithm-toggle', 'index': dash.dependencies.ALL}, 'value')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def update_plot_on_algorithm_change(
        trigger_data: Any,
        toggle_values: List[Any],
        session_id: str
    ) -> Tuple[Union[Figure, Any], Union[html.Div, Any]]:
        """
        当算法添加/删除/切换时，自动更新瀑布图和报告

        Args:
            trigger_data: 触发数据
            toggle_values: 切换值列表
            session_id: 会话ID

        Returns:
            Tuple[Union[Figure, Any], Union[html.Div, Any]]: (图表, 报告内容)
        """
        backend = session_manager.get_backend(session_id)
        if not backend:
            return no_update, no_update

        # 确保多算法模式已启用
        if not backend.multi_algorithm_manager:
            backend._ensure_multi_algorithm_manager()

        # 检查是否有激活的算法
        active_algorithms = backend.get_active_algorithms()
        if not active_algorithms:
            # 没有激活的算法，显示空图表
            empty_fig = _create_empty_figure_for_callback("请至少激活一个算法以查看瀑布图")
            empty_report = create_report_layout(backend)
            return empty_fig, empty_report

        try:
            # 生成图表和报告
            return _generate_plot_and_report(backend, active_algorithms)

        except Exception as e:
            # 处理错误情况
            return _handle_plot_update_error(e, backend)

    @app.callback(
        [Output('existing-data-migration-area', 'style'),
         Output('existing-data-migration-area', 'children')],
        [Input('session-id', 'data'),
         Input('confirm-migrate-existing-data-btn', 'n_clicks')],
        [State('existing-data-algorithm-name-input', 'value')],
        prevent_initial_call=True
    )
    def handle_existing_data_migration(
        session_id_trigger: Optional[str],
        migrate_clicks: Optional[int],
        algorithm_name: Optional[str]
    ) -> Tuple[dict, Optional[dbc.Alert]]:
        """
        处理现有数据迁移区域的显示和迁移操作

        Args:
            session_id_trigger: 会话ID触发器
            migrate_clicks: 迁移按钮点击次数
            algorithm_name: 算法名称

        Returns:
            Tuple[dict, Optional[dbc.Alert]]: (样式, 组件)
        """
        logger.info(f"[PROCESS] handle_existing_data_migration: migrate_clicks={migrate_clicks}")

        # 从 session_id_trigger 获取 session_id（它可能是 None 或实际值）
        session_id = session_id_trigger if session_id_trigger else None

        backend = session_manager.get_backend(session_id)
        if not backend:
            logger.warning("[WARNING] 无法获取backend实例（handle_existing_data_migration）")
            return {'display': 'none'}, None

        ctx = callback_context
        if not ctx.triggered:
            return {'display': 'none'}, None

        trigger_id = ctx.triggered[0]['prop_id']
        logger.info(f"🔍 触发源: {trigger_id}")

        try:
            # 处理不同的触发源
            if 'session-id' in trigger_id:
                return _handle_session_trigger(backend)
            elif 'confirm-migrate-existing-data-btn' in trigger_id:
                if not migrate_clicks or not algorithm_name or not algorithm_name.strip():
                    return no_update, no_update
                return _handle_migration_trigger(backend, algorithm_name)
            else:
                # 未知触发源
                logger.warning(f"[WARNING] 未知触发源: {trigger_id}")
                return {'display': 'none'}, None

        except Exception as e:
            logger.error(f"[ERROR] handle_existing_data_migration 发生异常: {e}")
            logger.error(traceback.format_exc())
            return {'display': 'none'}, None

    @app.callback(
        [Output('algorithm-list', 'children', allow_duplicate=True),
         Output('algorithm-management-status', 'children', allow_duplicate=True)],
        [Input('algorithm-list-trigger', 'data')],
        [State('session-id', 'data')],
        prevent_initial_call=True
    )
    def update_algorithm_list(trigger_data: Any, session_id: str) -> Tuple[List[dbc.Card], html.Span]:
        """
        更新算法列表显示

        Args:
            trigger_data: 触发数据
            session_id: 会话ID

        Returns:
            Tuple[List[dbc.Card], html.Span]: (算法列表, 状态文本)
        """
        backend = session_manager.get_backend(session_id)
        if not backend:
            return [], html.Span("")

        # 确保多算法模式已启用
        if not backend.multi_algorithm_manager:
            backend._ensure_multi_algorithm_manager()

        try:
            algorithms = backend.get_all_algorithms()
            logger.info(f"[PROCESS] 更新算法列表: 共 {len(algorithms)} 个算法")

            if not algorithms:
                return [], html.Span("暂无算法，请上传文件", style={'color': '#6c757d'})

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

            return algorithm_items, status_text

        except Exception as e:
            logger.error(f"[ERROR] 更新算法列表失败: {e}")
            logger.error(traceback.format_exc())
            return [], html.Span(f"更新失败: {str(e)}", style={'color': '#dc3545'})

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

        # 确保多算法模式已启用
        if not backend.multi_algorithm_manager:
            backend._ensure_multi_algorithm_manager()

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
                logger.info(f"[PROCESS] 切换算法显示状态: {algorithm_name}")
                _handle_toggle_action(backend, algorithm_name, toggle_values, toggle_ids)
            elif 'algorithm-delete-btn' in trigger_id:
                logger.info(f"[PROCESS] 处理算法删除: {algorithm_name}")
                
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



