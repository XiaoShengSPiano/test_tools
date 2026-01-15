"""
瀑布图分析页面
"""
from dash import html, dcc, callback, Input, Output, State
import dash_bootstrap_components as dbc
from utils.logger import Logger

logger = Logger.get_logger()

# 页面元数据
page_info = {
    'path': '/waterfall',
    'name': '瀑布图分析',
    'title': 'SPMID分析 - 瀑布图分析'
}


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
                    html.Small("自定义时间和按键范围", className="text-muted"),
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


def load_waterfall_plot(session_id, session_manager, time_start, time_end, key_start, key_end):
    """
    加载瀑布图
    
    Args:
        session_id: 会话ID
        session_manager: SessionManager实例（通过参数传入，避免多实例问题）
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
        
        # 生成瀑布图
        logger.info(f"[开始生成瀑布图] session={session_id}, 算法数={len(active_algorithms)}")
        logger.info(f"  时间筛选: {time_filter}, 按键筛选: {key_filter}")
        
        waterfall_fig = backend.generate_waterfall_plot(
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
    
    @app.callback(
        Output('waterfall-plot-container', 'children'),
        [
            Input('session-id', 'data'),
            Input('apply-waterfall-filter-btn', 'n_clicks'),
        ],
        [
            State('waterfall-time-start', 'value'),
            State('waterfall-time-end', 'value'),
            State('waterfall-key-start', 'value'),
            State('waterfall-key-end', 'value'),
        ]
    )
    def update_waterfall_plot(session_id, apply_clicks, time_start, time_end, key_start, key_end):
        """
        更新瀑布图
        
        Args:
            session_id: 会话ID
            apply_clicks: 应用筛选按钮点击次数
            time_start: 开始时间
            time_end: 结束时间
            key_start: 最低按键号
            key_end: 最高按键号
            
        Returns:
            更新后的瀑布图组件
        """
        return load_waterfall_plot(session_id, session_manager, time_start, time_end, key_start, key_end)
    
    @app.callback(
        [
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
            重置后的筛选值（全部为None）
        """
        if n_clicks:
            logger.info("[瀑布图] 用户重置筛选条件")
            return None, None, None, None
        return None, None, None, None
