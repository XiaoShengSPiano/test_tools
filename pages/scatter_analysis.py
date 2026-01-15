"""
散点图分析页面
"""
from dash import html, dcc, callback, Input, Output, State
import dash_bootstrap_components as dbc
from utils.logger import Logger

logger = Logger.get_logger()

# 页面元数据
page_info = {
    'path': '/scatter',
    'name': '散点图分析',
    'title': 'SPMID分析 - 散点图分析'
}


def layout():
    """
    散点图分析页面布局
    
    包含所有交互式散点图和详细分析：
    1. 按键与延时散点图
    2. Z-Score标准化散点图
    3. 锤速对比图
    4. 按键-力度交互效应图
    5. 相对延时分布图
    6. 延时时间序列图
    """
    return dbc.Container([
        # 页面标题和导航
        dbc.Row([
            dbc.Col([
                html.Div([
                    html.H2([
                        html.I(className="fas fa-chart-scatter me-2", style={'color': '#e91e63'}),
                        "散点图分析"
                    ], className="mb-2"),
                    html.P("深入分析MIDI数据的各种维度关系，支持交互式探索", 
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
        
        # 图表选择器
        dbc.Card([
            dbc.CardHeader([
                html.H5([
                    html.I(className="fas fa-layer-group me-2", style={'color': '#9c27b0'}),
                    "图表选择"
                ], className="mb-0")
            ], style={'backgroundColor': '#fce4ec'}),
            dbc.CardBody([
                dbc.Row([
                    dbc.Col([
                        html.Label("选择分析类型：", className="fw-bold mb-2"),
                        dcc.Dropdown(
                            id='scatter-analysis-type-selector',
                            options=[
                                {'label': '📊 按键与延时散点图', 'value': 'key-delay'},
                                {'label': '📈 Z-Score标准化散点图', 'value': 'zscore'},
                                {'label': '🔨 锤速对比图', 'value': 'hammer-velocity'},
                                {'label': '🎹 按键-力度交互效应图', 'value': 'key-force'},
                                {'label': '📉 相对延时分布图', 'value': 'relative-delay'},
                                {'label': '⏱️ 延时时间序列图', 'value': 'time-series'},
                            ],
                            value='key-delay',
                            clearable=False,
                            className="mb-3",
                            style={'fontSize': '15px'}
                        ),
                    ], md=6),
                    dbc.Col([
                        html.Div([
                            html.Label("💡 图表说明：", className="fw-bold mb-2"),
                            html.Div(
                                id='scatter-analysis-description', 
                                className="text-muted",
                                style={
                                    'backgroundColor': '#f5f5f5',
                                    'padding': '12px',
                                    'borderRadius': '6px',
                                    'borderLeft': '4px solid #e91e63',
                                    'minHeight': '60px'
                                }
                            )
                        ])
                    ], md=6)
                ])
            ])
        ], className="mb-4 shadow-sm border-0"),
        
        # 散点图显示区域
        dbc.Card([
            dbc.CardHeader([
                html.H5(id='scatter-analysis-title', className="mb-0")
            ]),
            dbc.CardBody([
                dcc.Loading(
                    id="scatter-analysis-loading",
                    type="default",
                    children=[
                        html.Div(id='scatter-analysis-plot-container')
                    ]
                )
            ])
        ], className="shadow-sm mb-4"),
        
        # 模态对话框 - 用于显示详细曲线对比
        html.Div([
            html.Div([
                html.Div([
                    html.Div([
                        html.H4("🎵 按键曲线对比", className="modal-title"),
                        html.Button("×", id="close-scatter-analysis-modal", className="close-btn", style={
                            'background': 'none',
                            'border': 'none',
                            'fontSize': '28px',
                            'cursor': 'pointer',
                            'color': '#666'
                        })
                    ], style={'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'center', 'marginBottom': '15px'}),
                    html.Div(id='scatter-analysis-modal-content'),
                    html.Div([
                        dbc.Button("关闭", id="close-scatter-analysis-modal-btn", color="secondary", className="mt-3")
                    ], style={'textAlign': 'right'})
                ], className="modal-content-inner", style={
                    'backgroundColor': '#fff',
                    'margin': '5% auto',
                    'padding': '25px',
                    'borderRadius': '12px',
                    'width': '85%',
                    'maxWidth': '1400px',
                    'maxHeight': '85vh',
                    'overflowY': 'auto',
                    'boxShadow': '0 10px 40px rgba(0,0,0,0.3)'
                })
            ], className="modal-content-wrapper")
        ], id="scatter-analysis-modal", className="modal", style={
            'display': 'none',
            'position': 'fixed',
            'zIndex': '1000',
            'left': '0',
            'top': '0',
            'width': '100%',
            'height': '100%',
            'backgroundColor': 'rgba(0,0,0,0.6)',
            'backdropFilter': 'blur(5px)'
        }),
        
    ], fluid=True, className="mt-3")


# 图表描述字典
SCATTER_DESCRIPTIONS = {
    'key-delay': '展示每个按键的平均延时分布，帮助识别特定按键的延时异常',
    'zscore': '使用Z-Score标准化延时数据，更清晰地识别异常值',
    'hammer-velocity': '分析锤速与延时的关系，评估不同力度下的响应特性',
    'key-force': '探索按键位置与演奏力度的交互效应，识别不均匀的响应',
    'relative-delay': '展示相对延时的分布情况，帮助理解延时的变化模式',
    'time-series': '按时间序列展示延时变化，识别时间相关的趋势'
}


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
    注册散点图页面的回调
    
    Args:
        app: Dash应用实例
        session_manager: SessionManager实例
    """
    @app.callback(
        [
            Output('scatter-analysis-description', 'children'),
            Output('scatter-analysis-title', 'children'),
        ],
        Input('scatter-analysis-type-selector', 'value')
    )
    def update_scatter_info(analysis_type):
        """
        更新图表说明和标题
        
        Args:
            analysis_type: 分析类型
            
        Returns:
            (描述文本, 标题)
        """
        description = SCATTER_DESCRIPTIONS.get(analysis_type, '')
        
        # 生成标题
        title_map = {
            'key-delay': [html.I(className="fas fa-chart-scatter me-2"), "按键与延时散点图"],
            'zscore': [html.I(className="fas fa-chart-line me-2"), "Z-Score标准化散点图"],
            'hammer-velocity': [html.I(className="fas fa-hammer me-2"), "锤速对比图"],
            'key-force': [html.I(className="fas fa-keyboard me-2"), "按键-力度交互效应图"],
            'relative-delay': [html.I(className="fas fa-chart-area me-2"), "相对延时分布图"],
            'time-series': [html.I(className="fas fa-clock me-2"), "延时时间序列图"],
        }
        
        title = title_map.get(analysis_type, [html.I(className="fas fa-chart-scatter me-2"), "散点图分析"])
        
        return description, title
    
    @app.callback(
        Output('scatter-analysis-plot-container', 'children'),
        [
            Input('session-id', 'data'),
            Input('scatter-analysis-type-selector', 'value'),
        ]
    )
    def update_scatter_plot(session_id, analysis_type):
        """
        更新散点图
        
        Args:
            session_id: 会话ID
            analysis_type: 分析类型
            
        Returns:
            散点图组件或提示信息
        """
        logger.info(f"[DEBUG] update_scatter_plot 被调用, session_id={session_id}, type={analysis_type}")
        
        if not session_id:
            logger.warning("[WARN] update_scatter_plot: session_id 为空")
            return _create_no_data_alert()
        
        try:
            # 获取后端实例（不创建新的）
            backend = session_manager.get_backend(session_id)
            logger.info(f"[DEBUG] scatter - session_manager.get_backend({session_id}) 返回: {backend}")
            
            if not backend:
                logger.warning(f"[WARN] Backend尚未初始化 (session={session_id})")
                return _create_no_backend_alert()
            
            logger.info(f"[开始生成散点图] session={session_id}, 类型={analysis_type}")
            
            # 根据类型生成对应的图表
            # 注意：这里需要调用相应的生成函数，具体实现需要根据实际情况调整
            # 暂时返回提示信息
            return dbc.Alert([
                html.H4("🚧 开发中", className="alert-heading"),
                html.P(f"图表类型: {analysis_type}"),
                html.P("此功能正在开发中，即将上线"),
            ], color="info", className="mt-4")
            
        except Exception as e:
            logger.error(f"[ERROR] 加载散点图失败: {e}")
            import traceback
            traceback.print_exc()
            return _create_error_alert(str(e))
