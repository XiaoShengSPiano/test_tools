"""
瀑布图分析页面
"""
from dash import html, dcc, callback, Input, Output, State
import dash_bootstrap_components as dbc
from utils.logger import Logger
from typing import List, Dict, Any

logger = Logger.get_logger()

# 页面元数据
page_info = {
    'path': '/waterfall',
    'name': '瀑布图分析',
    'title': 'SPMID分析 - 瀑布图分析'
}


def parse_key_selection(key_string: str) -> List[int]:
    """
    解析按键选择字符串

    支持的格式：
    - 单个ID: "36"
    - 逗号分隔: "36,37,38"
    - 范围: "40-48"
    - 混合: "36,40-45,50"

    Args:
        key_string: 按键选择字符串

    Returns:
        List[int]: 解析后的按键ID列表
    """
    if not key_string or not key_string.strip():
        return None

    key_ids = set()  # 使用set避免重复

    try:
        # 分割逗号
        parts = [part.strip() for part in key_string.split(',')]

        for part in parts:
            if '-' in part:
                # 处理范围，如 "40-48"
                start_end = part.split('-')
                if len(start_end) == 2:
                    start = int(start_end[0].strip())
                    end = int(start_end[1].strip())
                    if start <= end:
                        key_ids.update(range(start, end + 1))
            else:
                # 处理单个ID
                key_id = int(part.strip())
                key_ids.add(key_id)

        return sorted(list(key_ids)) if key_ids else None

    except (ValueError, AttributeError) as e:
        logger.warning(f"解析按键选择字符串失败: '{key_string}' - {e}")
        return None


def layout():
    """
    瀑布图分析页面布局
    
    包含：
    1. 筛选控制区域（时间范围、按键范围）
    2. 瀑布图可视化区域
    """
    return dbc.Container([
        # 页面标题和导航
        dbc.Row([
            dbc.Col([
                html.Div([
                    html.H2([
                        html.I(className="fas fa-chart-waterfall me-2", style={'color': '#00897b'}),
                        "瀑布图分析"
                    ], className="mb-2"),
                    html.P("可视化MIDI事件的时序关系，支持时间和按键筛选", 
                           className="text-muted mb-3"),
                ], className="mb-3")
            ], md=8),
            dbc.Col([
                html.Div([
                    html.Label("🔙 返回", className="fw-bold mb-2 d-block"),
                    dbc.Button([
                        html.I(className="fas fa-arrow-left me-2"),
                        "异常检测报告"
                    ], href="/", color="primary", size="sm", outline=True, className="w-100")
                ], className="text-center")
            ], md=4)
        ], className="mt-3 mb-3"),
        
        html.Hr(className="mb-4"),
        
        # 筛选控制区域（可折叠）
        dbc.Card([
            dbc.CardHeader([
                html.Div([
                    html.H5([
                        html.I(className="fas fa-filter me-2", style={'color': '#7e57c2'}),
                        "筛选控制"
                    ], className="mb-0 d-inline-block"),
                    html.Span(" · ", className="mx-2 text-muted"),
                    html.Small("自定义数据类型、时间和按键范围", className="text-muted"),
                ], className="d-inline-block"),
                dbc.Button(
                    html.I(className="fas fa-chevron-down", id="waterfall-filter-collapse-icon"),
                    id="collapse-waterfall-filter-btn",
                    color="link",
                    size="sm",
                    className="float-end",
                    style={'textDecoration': 'none'}
                )
            ], style={'backgroundColor': '#f3e5f5'}),
            dbc.Collapse([
                dbc.CardBody([
                    # 数据类型选择
                    dbc.Row([
                        dbc.Col([
                            html.Label("📊 数据类型", className="fw-bold mb-2"),
                            dbc.Checklist(
                                id='waterfall-data-types',
                                options=[
                                    {'label': '精确匹配', 'value': 'matched_pairs'},
                                    {'label': '丢锤错误', 'value': 'drop_hammers'},
                                    {'label': '多锤错误', 'value': 'multi_hammers'},
                                    {'label': '异常匹配', 'value': 'abnormal_matches'}
                                ],
                                value=['matched_pairs'],  # 默认只显示匹配对
                                inline=True,
                                className="mb-3"
                            ),
                            html.Small("选择要显示的数据类型，至少选择一种", className="text-muted"),
                        ], md=12)
                    ]),

                    html.Hr(style={'borderTop': '1px dashed #e0e0e0', 'margin': '15px 0'}),

                    # 按键选择
                    dbc.Row([
                        dbc.Col([
                            html.Label("🎹 按键选择", className="fw-bold mb-2"),
                            html.Div([
                                html.Small("选择要显示的按键，不选择表示显示所有按键", className="text-muted mb-2 d-block"),

                                # 按键统计信息显示
                                html.Div(id="waterfall-key-stats", className="mb-2"),

                                # 按键下拉多选框
                                dcc.Dropdown(
                                    id='waterfall-selected-keys',
                                    options=[],  # 动态加载按键选项
                                    value=[],    # 默认不选择任何按键
                                    multi=True,  # 支持多选
                                    placeholder="选择要显示的按键...",
                                    className="mb-2",
                                    style={'width': '100%'}
                                ),

                                # 快速选择按钮
                                dbc.ButtonGroup([
                                    dbc.Button("全选", id="waterfall-select-all-keys", color="outline-secondary", size="sm"),
                                    dbc.Button("异常按键", id="waterfall-select-exception-keys", color="outline-warning", size="sm"),
                                    dbc.Button("清空", id="waterfall-clear-key-selection", color="outline-danger", size="sm"),
                                ], size="sm", className="mt-2"),
                            ]),
                        ], md=12)
                    ]),

                    html.Hr(style={'borderTop': '1px dashed #e0e0e0', 'margin': '15px 0'}),

                    dbc.Row([
                        # 时间范围筛选
                        dbc.Col([
                            html.Label("⏱️ 时间范围 (ms)", className="fw-bold mb-2"),
                            html.Div([
                                dbc.InputGroup([
                                    dbc.InputGroupText("开始"),
                                    dbc.Input(
                                        id="waterfall-time-start",
                                        type="number",
                                        placeholder="开始时间",
                                        value=None,
                                        className="form-control-sm"
                                    ),
                                ], size="sm", className="mb-2"),
                                dbc.InputGroup([
                                    dbc.InputGroupText("结束"),
                                    dbc.Input(
                                        id="waterfall-time-end",
                                        type="number",
                                        placeholder="结束时间",
                                        value=None,
                                        className="form-control-sm"
                                    ),
                                ], size="sm"),
                            ])
                        ], md=6),

                        # 按键范围筛选
                        dbc.Col([
                            html.Label("🎹 按键范围", className="fw-bold mb-2"),
                            html.Div([
                                dbc.InputGroup([
                                    dbc.InputGroupText("最低键"),
                                    dbc.Input(
                                        id="waterfall-key-start",
                                        type="number",
                                        placeholder="最低按键号",
                                        value=None,
                                        min=0,
                                        max=127,
                                        className="form-control-sm"
                                    ),
                                ], size="sm", className="mb-2"),
                                dbc.InputGroup([
                                    dbc.InputGroupText("最高键"),
                                    dbc.Input(
                                        id="waterfall-key-end",
                                        type="number",
                                        placeholder="最高按键号",
                                        value=None,
                                        min=0,
                                        max=127,
                                        className="form-control-sm"
                                    ),
                                ], size="sm"),
                            ])
                        ], md=6),
                    ]),

                    # 预设筛选快捷按钮
                    dbc.Row([
                        dbc.Col([
                            html.Label("⚡ 快速筛选", className="fw-bold mb-2 d-block"),
                            dbc.ButtonGroup([
                                dbc.Button("前5秒", id="preset-time-5s", color="info", size="sm", outline=True),
                                dbc.Button("前10秒", id="preset-time-10s", color="info", size="sm", outline=True),
                                dbc.Button("前30秒", id="preset-time-30s", color="info", size="sm", outline=True),
                                dbc.Button("全部时间", id="preset-time-all", color="info", size="sm", outline=True),
                            ], size="sm", className="mb-2 w-100"),
                        ], md=12, className="mt-3")
                    ]),

                    html.Hr(style={'borderTop': '1px dashed #e0e0e0', 'margin': '15px 0'}),

                    # 应用筛选按钮
                    dbc.Row([
                        dbc.Col([
                            dbc.Button(
                                [html.I(className="fas fa-sync-alt me-2"), "应用筛选"],
                                id="apply-waterfall-filter-btn",
                                color="primary",
                                size="sm",
                                className="mt-2"
                            ),
                            dbc.Button(
                                [html.I(className="fas fa-undo me-2"), "重置"],
                                id="reset-waterfall-filter-btn",
                                color="secondary",
                                size="sm",
                                className="mt-2 ms-2"
                            ),
                        ])
                    ])
                ])
            ], id="waterfall-filter-collapse", is_open=True)
        ], className="mb-4 shadow-sm"),
        
        # 瀑布图显示区域
        dbc.Card([
            dbc.CardHeader([
                html.H5([
                    html.I(className="fas fa-chart-line me-2"),
                    "瀑布图"
                ], className="mb-0")
            ]),
            dbc.CardBody([
                dcc.Loading(
                    id="waterfall-loading",
                    type="default",
                    children=[
                        html.Div(id='waterfall-plot-container')
                    ]
                )
            ])
        ], className="shadow-sm"),
        
    ], fluid=True, className="mt-3")


def load_waterfall_plot(session_id, session_manager, data_types, selected_keys, time_start, time_end, key_start, key_end):
    """
    加载瀑布图

    Args:
        session_id: 会话ID
        session_manager: SessionManager实例（通过参数传入，避免多实例问题）
        data_types: 选择的数据类型列表
        selected_keys: 选择的按键ID字符串（如"36,37,38"或"40-48"）
        time_start: 开始时间 (ms)
        time_end: 结束时间 (ms)
        key_start: 最低按键号
        key_end: 最高按键号

    Returns:
        瀑布图组件或提示信息
    """
    logger.info(f"[DEBUG] load_waterfall_plot 被调用, session_id={session_id}")

    if not session_id:
        logger.warning("[WARN] load_waterfall_plot: session_id 为空")
        return _create_no_data_alert()

    # 检查是否有任何筛选条件被设置
    has_any_filter = (
        (data_types and len(data_types) > 0) or
        (selected_keys and selected_keys.strip()) or
        (time_start is not None) or
        (time_end is not None) or
        (key_start is not None) or
        (key_end is not None)
    )

    if not has_any_filter:
        logger.info("[INFO] 用户没有设置任何筛选条件，返回提示信息")
        return _create_filter_required_alert()
    
    try:
        # 获取后端实例（不创建新的）
        backend = session_manager.get_backend(session_id)
        logger.info(f"[DEBUG] waterfall - session_manager.get_backend({session_id}) 返回: {backend}")
        
        if not backend:
            logger.warning(f"[WARN] Backend尚未初始化 (session={session_id})")
            return _create_no_backend_alert()
        
        # 检查是否有活跃算法
        active_algorithms = backend.get_active_algorithms()
        if not active_algorithms:
            logger.info(f"[INFO] 没有活跃算法 (session={session_id})")
            return _create_no_algorithm_alert()
        
        # 构建筛选条件
        time_filter = None
        if time_start is not None or time_end is not None:
            time_filter = {
                'start': time_start,
                'end': time_end
            }
        
        key_filter = None
        if key_start is not None or key_end is not None:
            key_filter = {
                'min': key_start,
                'max': key_end
            }
        
        # 解析按键选择
        key_ids = None
        if selected_keys and selected_keys.strip():
            key_ids = parse_key_selection(selected_keys.strip())
            logger.info(f"  按键选择: {selected_keys} -> {key_ids}")

        logger.info(f"[开始生成瀑布图] session={session_id}, 算法数={len(active_algorithms)}")
        logger.info(f"  数据类型: {data_types}")
        logger.info(f"  按键ID: {key_ids}")
        logger.info(f"  时间筛选: {time_filter}, 按键筛选: {key_filter}")

        waterfall_fig = backend.generate_waterfall_plot(
            data_types=data_types,
            key_ids=key_ids,
            time_filter=time_filter,
            key_filter=key_filter
        )

        if waterfall_fig:
            logger.info(f"[OK] 瀑布图生成成功 (session={session_id})")
            return dcc.Graph(
                id='waterfall-graph',
                figure=waterfall_fig,
                config={'displayModeBar': True, 'displaylogo': False},
                style={'height': '800px'}
            )
        else:
            logger.warning(f"[WARN] 瀑布图生成失败，返回None (session={session_id})")
            return _create_generation_failed_alert()

    except Exception as e:
        logger.error(f"[ERROR] 加载瀑布图失败: {e}")
        import traceback
        traceback.print_exc()
        return _create_error_alert(str(e))


def _create_filter_required_alert():
    """创建需要筛选条件的提示"""
    return dbc.Alert([
        html.H4("🔍 请设置筛选条件", className="alert-heading"),
        html.P("请选择数据类型、按键范围或其他筛选条件，然后点击\"应用筛选\"按钮查看瀑布图"),
        html.Hr(),
        html.P([
            html.Strong("提示："),
            "您可以选择特定的数据类型（如精确匹配、丢锤、多锤）和按键范围来减少显示的数据量，提高分析效率。"
        ], className="mb-0")
    ], color="info", className="mt-4")


def _create_no_data_alert():
    """创建无数据提示"""
    return dbc.Alert([
        html.H4("📁 暂无数据", className="alert-heading"),
        html.P("请先在异常检测报告页面上传SPMID文件"),
        html.Hr(),
        dbc.Button("前往上传文件", href="/", color="primary")
    ], color="info", className="mt-4")


def _create_no_backend_alert():
    """创建无后端提示"""
    return dbc.Alert([
        html.H4("⚠️ 后端未初始化", className="alert-heading"),
        html.P("未找到分析后端实例，请重新上传文件"),
        html.Hr(),
        dbc.Button("返回首页", href="/", color="primary")
    ], color="warning", className="mt-4")


def _create_no_algorithm_alert():
    """创建无活跃算法提示"""
    return dbc.Alert([
        html.H4("📊 没有活跃算法", className="alert-heading"),
        html.P("请在异常检测报告页面激活至少一个算法"),
        html.Hr(),
        dbc.Button("返回报告页面", href="/", color="primary")
    ], color="warning", className="mt-4")


def _create_generation_failed_alert():
    """创建生成失败提示"""
    return dbc.Alert([
        html.H4("❌ 生成失败", className="alert-heading"),
        html.P("瀑布图生成失败，请检查数据或筛选条件"),
        html.Hr(),
        html.P("请查看日志文件获取详细信息", className="mb-0 text-muted")
    ], color="danger", className="mt-4")


def _create_error_alert(error_message):
    """创建错误提示"""
    return dbc.Alert([
        html.H4("❌ 加载失败", className="alert-heading"),
        html.P(f"错误信息: {error_message}"),
        html.Hr(),
        html.P("请检查日志文件获取详细信息", className="mb-0 text-muted")
    ], color="danger", className="mt-4")


def _create_key_stats_display(key_stats: Dict[str, Any]) -> html.Div:
    """创建按键统计信息显示"""
    if not key_stats or not key_stats.get('summary'):
        return html.Div("暂无按键数据", className="text-muted")

    summary = key_stats['summary']
    available_keys = key_stats.get('available_keys', [])

    return html.Div([
        dbc.Row([
            dbc.Col([
                html.Span(f"📊 总按键数: {summary['total_keys']}", className="me-3"),
                html.Span(f"📈 总数据点: {summary['total_data_points']}", className="me-3"),
                html.Span([
                    "⚠️ 异常数据: ",
                    html.Span(f"{summary['total_exception_points']}", className="text-warning fw-bold"),
                    f" ({summary['exception_rate']:.1%})"
                ]),
            ], md=12)
        ]),
        html.Hr(className="my-2"),
        html.Small([
            f"检测到 {len([k for k in available_keys if k['exception_count'] > 0])} 个存在异常的按键，",
            "建议优先检查这些按键的数据。"
        ], className="text-muted")
    ], className="p-2 bg-light rounded")


def _create_key_options(key_stats: Dict[str, Any]) -> List[Dict]:
    """创建按键选择选项"""
    if not key_stats or not key_stats.get('available_keys'):
        return []

    options = []
    for key_info in key_stats['available_keys']:
        key_id = key_info['key_id']
        total_count = key_info['total_count']
        exception_count = key_info['exception_count']
        exception_rate = key_info['exception_rate']

        # 根据异常率设置标签样式
        if exception_rate > 0.3:
            status_icon = "🔴"
            status_text = "高异常"
        elif exception_rate > 0.1:
            status_icon = "🟡"
            status_text = "中异常"
        elif exception_count > 0:
            status_icon = "🟢"
            status_text = "低异常"
        else:
            status_icon = "⚪"
            status_text = "正常"

        label = f"{status_icon} 按键{key_id} - {total_count}数据点"
        if exception_count > 0:
            label += f" ({exception_count}异常)"

        options.append({
            'label': label,
            'value': key_id
        })

    return options


def _create_key_options_for_dropdown(key_stats: Dict[str, Any]) -> List[Dict]:
    """创建适合下拉框的按键选择选项"""
    if not key_stats or not key_stats.get('available_keys'):
        return []

    options = []
    for key_info in key_stats['available_keys']:
        key_id = key_info['key_id']
        total_count = key_info['total_count']
        exception_count = key_info['exception_count']
        exception_rate = key_info['exception_rate']

        # 根据异常率设置标签样式
        if exception_rate > 0.3:
            status_icon = "🔴"
        elif exception_rate > 0.1:
            status_icon = "🟡"
        elif exception_count > 0:
            status_icon = "🟢"
        else:
            status_icon = "⚪"

        # 为下拉框创建更简洁的标签
        label = f"{status_icon} 按键{key_id} ({total_count}个"
        if exception_count > 0:
            label += f", {exception_count}异常"
        label += ")"

        options.append({
            'label': label,
            'value': key_id
        })

    return options


def _create_key_stats_display(key_stats: Dict[str, Any]) -> html.Div:
    """创建按键统计信息显示"""
    if not key_stats or not key_stats.get('summary'):
        return html.Div("暂无按键数据", className="text-muted")

    summary = key_stats['summary']
    available_keys = key_stats.get('available_keys', [])

    return html.Div([
        dbc.Row([
            dbc.Col([
                html.Span(f"📊 总按键数: {summary['total_keys']}", className="me-3"),
                html.Span(f"📈 总数据点: {summary['total_data_points']}", className="me-3"),
                html.Span([
                    "⚠️ 异常数据: ",
                    html.Span(f"{summary['total_exception_points']}", className="text-warning fw-bold"),
                    f" ({summary['exception_rate']:.1%})"
                ]),
            ], md=12)
        ]),
        html.Hr(className="my-2"),
        html.Small([
            f"检测到 {len([k for k in available_keys if k['exception_count'] > 0])} 个存在异常的按键，",
            "建议优先检查这些按键的数据。"
        ], className="text-muted")
    ], className="p-2 bg-light rounded")


def _create_key_options(key_stats: Dict[str, Any]) -> List[Dict]:
    """创建按键选择选项"""
    if not key_stats or not key_stats.get('available_keys'):
        return []

    options = []
    for key_info in key_stats['available_keys']:
        key_id = key_info['key_id']
        total_count = key_info['total_count']
        exception_count = key_info['exception_count']
        exception_rate = key_info['exception_rate']

        # 根据异常率设置标签样式
        if exception_rate > 0.3:
            status_icon = "🔴"
            status_text = "高异常"
        elif exception_rate > 0.1:
            status_icon = "🟡"
            status_text = "中异常"
        elif exception_count > 0:
            status_icon = "🟢"
            status_text = "低异常"
        else:
            status_icon = "⚪"
            status_text = "正常"

        label = f"{status_icon} 按键{key_id} - {total_count}数据点"
        if exception_count > 0:
            label += f" ({exception_count}异常)"

        options.append({
            'label': label,
            'value': key_id
        })

    return options


# ==================== 页面回调注册 ====================

def register_callbacks(app, session_manager):
    """
    注册瀑布图页面的回调
    
    Args:
        app: Dash应用实例
        session_manager: SessionManager实例
    """
    @app.callback(
        [
            Output('waterfall-filter-collapse', 'is_open'),
            Output('waterfall-filter-collapse-icon', 'className'),
        ],
        Input('collapse-waterfall-filter-btn', 'n_clicks'),
        State('waterfall-filter-collapse', 'is_open'),
        prevent_initial_call=True
    )
    def toggle_waterfall_filter(n_clicks, is_open):
        """
        切换筛选控制区域的折叠状态，并更新图标

        Args:
            n_clicks: 按钮点击次数
            is_open: 当前折叠状态

        Returns:
            (新的折叠状态, 图标类名)
        """
        if n_clicks:
            new_state = not is_open
            icon_class = "fas fa-chevron-down" if new_state else "fas fa-chevron-right"
            return new_state, icon_class
        return is_open, "fas fa-chevron-down"
    
    @app.callback(
        [
            Output('waterfall-time-start', 'value', allow_duplicate=True),
            Output('waterfall-time-end', 'value', allow_duplicate=True),
        ],
        [
            Input('preset-time-5s', 'n_clicks'),
            Input('preset-time-10s', 'n_clicks'),
            Input('preset-time-30s', 'n_clicks'),
            Input('preset-time-all', 'n_clicks'),
        ],
        prevent_initial_call=True
    )
    def apply_preset_time_filter(clicks_5s, clicks_10s, clicks_30s, clicks_all):
        """
        应用预设时间筛选
        
        Args:
            clicks_5s: 前5秒按钮点击次数
            clicks_10s: 前10秒按钮点击次数
            clicks_30s: 前30秒按钮点击次数
            clicks_all: 全部时间按钮点击次数
            
        Returns:
            (开始时间, 结束时间)
        """
        from dash import callback_context
        
        if not callback_context.triggered:
            return None, None
        
        button_id = callback_context.triggered[0]['prop_id'].split('.')[0]
        
        # 根据按钮ID返回相应的时间范围
        presets = {
            'preset-time-5s': (0, 5000),    # 0-5秒
            'preset-time-10s': (0, 10000),  # 0-10秒
            'preset-time-30s': (0, 30000),  # 0-30秒
            'preset-time-all': (None, None), # 全部时间
        }
        
        start, end = presets.get(button_id, (None, None))
        logger.info(f"[瀑布图] 应用预设时间筛选: {button_id} -> ({start}, {end})")
        
        return start, end

    # 按键选择快速操作
    @app.callback(
        Output('waterfall-selected-keys', 'value', allow_duplicate=True),
        [
            Input('waterfall-select-all-keys', 'n_clicks'),
            Input('waterfall-select-exception-keys', 'n_clicks'),
            Input('waterfall-clear-key-selection', 'n_clicks'),
        ],
        State('waterfall-selected-keys', 'options'),
        prevent_initial_call=True
    )
    def handle_key_quick_selection(select_all_clicks, select_exception_clicks, clear_clicks, key_options):
        """
        处理按键快速选择操作

        Args:
            select_all_clicks: 全选按钮点击次数
            select_exception_clicks: 选择异常按键按钮点击次数
            clear_clicks: 清空按钮点击次数
            key_options: 按键选项列表

        Returns:
            选中的按键ID列表
        """
        from dash import callback_context

        if not callback_context.triggered:
            return []

        button_id = callback_context.triggered[0]['prop_id'].split('.')[0]

        if button_id == 'waterfall-clear-key-selection':
            return []
        elif button_id == 'waterfall-select-all-keys':
            return [option['value'] for option in key_options]
        elif button_id == 'waterfall-select-exception-keys':
            # 选择包含异常的按键（标签中包含异常信息的按键）
            exception_keys = []
            for option in key_options:
                label = option.get('label', '')
                if '异常' in label or '🔴' in label or '🟡' in label:
                    exception_keys.append(option['value'])
            return exception_keys

        return []
    
    # 页面初始加载时的默认显示
    @app.callback(
        [
            Output('waterfall-plot-container', 'children', allow_duplicate=True),
            Output('waterfall-key-stats', 'children'),
            Output('waterfall-selected-keys', 'options')
        ],
        Input('session-id', 'data'),
        prevent_initial_call='initial_duplicate'  # 允许初始调用时的重复输出
    )
    def initialize_waterfall_display(session_id):
        """
        页面初始加载时的显示内容和按键信息

        Args:
            session_id: 会话ID

        Returns:
            (图表容器内容, 按键统计信息, 按键选择选项)
        """
        if not session_id:
            return _create_no_data_alert(), "", []

        try:
            # 获取后端实例
            backend = session_manager.get_backend(session_id)

            if not backend:
                return _create_no_backend_alert(), "", []

            # 获取按键统计信息
            key_stats = backend.get_waterfall_key_statistics()

            # 生成按键统计显示
            stats_display = _create_key_stats_display(key_stats)

            # 生成按键选择选项
            key_options = _create_key_options_for_dropdown(key_stats)

            logger.info(f"[INFO] 瀑布图页面初始化完成，找到 {len(key_options)} 个按键")

            return _create_filter_required_alert(), stats_display, key_options

        except Exception as e:
            logger.error(f"[ERROR] 初始化瀑布图页面失败: {e}")
            return _create_error_alert(str(e)), "", []

    @app.callback(
        Output('waterfall-plot-container', 'children', allow_duplicate=True),
        Input('apply-waterfall-filter-btn', 'n_clicks'),
        [
            State('session-id', 'data'),
            State('waterfall-data-types', 'value'),
            State('waterfall-selected-keys', 'value'),
            State('waterfall-time-start', 'value'),
            State('waterfall-time-end', 'value'),
            State('waterfall-key-start', 'value'),
            State('waterfall-key-end', 'value'),
        ],
        prevent_initial_call=True  # 防止页面加载时自动触发
    )
    def update_waterfall_plot(apply_clicks, session_id, data_types, selected_keys, time_start, time_end, key_start, key_end):
        """
        更新瀑布图 - 只有当用户点击应用筛选时才触发

        Args:
            apply_clicks: 应用筛选按钮点击次数
            session_id: 会话ID
            data_types: 选择的数据类型列表
            selected_keys: 选择的按键ID列表（从下拉框获得）
            time_start: 开始时间
            time_end: 结束时间
            key_start: 最低按键号
            key_end: 最高按键号

        Returns:
            更新后的瀑布图组件
        """
        # 将按键ID列表转换为字符串格式传递给后端
        selected_keys_str = ','.join(map(str, selected_keys)) if selected_keys else None

        return load_waterfall_plot(session_id, session_manager, data_types, selected_keys_str, time_start, time_end, key_start, key_end)
    
    @app.callback(
        [
            Output('waterfall-data-types', 'value'),
            Output('waterfall-time-start', 'value'),
            Output('waterfall-time-end', 'value'),
            Output('waterfall-key-start', 'value'),
            Output('waterfall-key-end', 'value'),
        ],
        Input('reset-waterfall-filter-btn', 'n_clicks'),
        prevent_initial_call=True
    )
    def reset_waterfall_filters(n_clicks):
        """
        重置所有筛选条件

        Args:
            n_clicks: 重置按钮点击次数

        Returns:
            重置后的筛选值（数据类型恢复默认，时间和按键为None）
        """
        if n_clicks:
            logger.info("[瀑布图] 用户重置筛选条件")
            return ['matched_pairs'], None, None, None, None  # 数据类型恢复默认只显示匹配对
        return ['matched_pairs'], None, None, None, None
