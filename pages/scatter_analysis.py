"""
散点图分析页面
"""

import traceback
from dash import html, dcc, Input, Output, State, no_update, callback_context
import dash_bootstrap_components as dbc
from utils.logger import Logger
from pages.scatter_helper_functions import _parse_customdata_by_type, _handle_scatter_click_logic, _handle_scatter_click_logic_enhanced
from ui.delay_time_series_handler import delay_time_series_handler
from ui.scatter_callbacks import register_scatter_callbacks

logger = Logger.get_logger()

# 页面元数据
page_info = {
    'path': '/scatter',
    'name': '散点图分析',
    'title': 'SPMID分析 - 散点图分析'
}

SCATTER_DESCRIPTIONS = {
    'key-delay': '展示每个音符按键（Key ID）的录制延时分布，用于观察特定按键的硬件偏差。',
    'zscore': '展示延时分布的Z-Score标准化结果，帮助识别异常离群点。',
    'hammer-velocity': '展示不同按键下的播放锤速与录制锤速之差，用于分析播放机构的力度还原。',
    'key-force': '展示在不同播放键位和力度（锤速）下的交互效应，反映算法对不同力度的响应特征。',
    'relative-delay': '展示按键相对于其平均延时的分布，用于评估算法在不同按键上的稳定性。',
    'time-series': '展示延时随时间的变化趋势，用于检测是否存在随时间漂移的系统误差。',
}

def layout():
    """
    散点图分析页面布局
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
            dbc.CardBody([
                dbc.Row([
                    dbc.Col([
                        html.Label("📈 选择分析维度", className="fw-bold mb-2"),
                        dcc.Dropdown(
                            id='scatter-analysis-type-selector',
                            options=[
                                {'label': '按键与延时散点图 (Key ID vs Delay)', 'value': 'key-delay'},
                                {'label': 'Z-Score标准化散点图 (Outlier Detection)', 'value': 'zscore'},
                                {'label': '锤速对比图 (Velocity Diff)', 'value': 'hammer-velocity'},
                                {'label': '按键-力度交互效应图 (Key-Force Interaction)', 'value': 'key-force'},
                                {'label': '相对延时分布图 (Relative Delay Dist)', 'value': 'relative-delay'},
                                {'label': '延时时间序列图 (Time Series)', 'value': 'time-series'},
                            ],
                            value='key-delay',
                            clearable=False,
                            className="mb-2"
                        ),
                    ], md=6),
                    dbc.Col([
                        html.Div(id='scatter-analysis-description', className="text-muted small p-2 bg-light rounded border-start border-3 border-info", style={'minHeight': '60px'})
                    ], md=6),
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
        
        # 隐藏的存储组件
        dcc.Store(id='scatter-analysis-clicked-point-info', data=None),
        dcc.Store(id='key-force-interaction-selected-keys', data=[]),

    ], fluid=True, className="mt-3")

# ==================== 页面回调注册 ====================

def register_callbacks(app, session_manager):
    """
    注册散点图页面的回调
    """
    # 注册通用散点图交互回调 (处理点击、模态框等)
    register_scatter_callbacks(app, session_manager)
    
    @app.callback(
        [
            Output('scatter-analysis-description', 'children'),
            Output('scatter-analysis-title', 'children'),
        ],
        Input('scatter-analysis-type-selector', 'value')
    )
    def update_scatter_info(analysis_type):
        description = SCATTER_DESCRIPTIONS.get(analysis_type, '')
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
            Input('algorithm-management-trigger', 'data'),
        ]
    )
    def update_scatter_plot(session_id, analysis_type, management_trigger):
        if not session_id:
            return _create_no_data_alert()
        
        try:
            backend = session_manager.get_backend(session_id)
            if not backend:
                return _create_no_backend_alert()

            if analysis_type == 'key-delay':
                figure = backend.generate_key_delay_scatter_plot()
            elif analysis_type == 'zscore':
                figure = backend.generate_key_delay_zscore_scatter_plot()
            elif analysis_type == 'hammer-velocity':
                from ui.velocity_comparison_handler import VelocityComparisonHandler
                handler = VelocityComparisonHandler(session_manager)
                figure = handler.handle_generate_hammer_velocity_comparison_plot(None, session_id)
            elif analysis_type == 'key-force':
                figure = backend.generate_key_force_interaction_plot()
            elif analysis_type == 'relative-delay':
                figure = backend.generate_relative_delay_distribution_plot()
            elif analysis_type == 'time-series':
                result = backend.generate_delay_time_series_plot()
                if isinstance(result, dict) and 'raw_delay_plot' in result and 'relative_delay_plot' in result:
                    return html.Div([
                        html.H6('原始延时时间序列图', className='mb-2', style={'color': '#2c3e50', 'fontWeight': 'bold'}),
                        dcc.Graph(
                            id={'type': 'scatter-plot', 'id': 'raw-delay-time-series-plot'},
                            figure=result['raw_delay_plot'],
                            style={'height': '500px', 'marginBottom': '30px'},
                            config={'displayModeBar': True, 'displaylogo': False, 'modeBarButtonsToRemove': ['lasso2d', 'select2d']}
                        ),
                        html.Hr(),
                        html.H6('相对延时时间序列图', className='mb-2', style={'color': '#2c3e50', 'fontWeight': 'bold'}),
                        dcc.Graph(
                            id={'type': 'scatter-plot', 'id': 'relative-delay-time-series-plot'},
                            figure=result['relative_delay_plot'],
                            style={'height': '500px'},
                            config={'displayModeBar': True, 'displaylogo': False, 'modeBarButtonsToRemove': ['lasso2d', 'select2d']}
                        )
                    ])
                else:
                    figure = result
            
            if figure:
                # 为按键-力度交互量身定做布局
                if analysis_type == 'key-force':
                    return html.Div([
                        dbc.Row([
                            dbc.Col([
                                html.Label("🔍 筛选按键：", className="fw-bold mb-2"),
                                dcc.Dropdown(
                                    id='key-force-interaction-key-selector',
                                    placeholder="选择按键进行过滤...",
                                    className="mb-3"
                                )
                            ], md=4),
                            dbc.Col([
                                html.Div([
                                    html.Small("💡 提示：点击图例中的算法名称可显示/隐藏特定算法，使用下拉框可过滤特定按键", 
                                              className="text-muted d-block mt-4")
                                ])
                            ], md=8)
                        ], className="mb-2"),
                        dcc.Graph(
                            id={'type': 'scatter-plot', 'id': 'key-force-interaction-plot'}, 
                            figure=figure, 
                            style={'height': '700px'}, 
                            config={'displayModeBar': True, 'displaylogo': False, 'modeBarButtonsToRemove': ['lasso2d', 'select2d']}
                        )
                    ])
                
                # 其他图表使用专用ID
                plot_id_map = {
                    'key-delay': 'key-delay-scatter-plot',
                    'zscore': 'key-delay-zscore-scatter-plot',
                    'hammer-velocity': 'hammer-velocity-comparison-plot',
                    'relative-delay': 'relative-delay-distribution-plot',
                }
                plot_id = plot_id_map.get(analysis_type, 'scatter-analysis-dynamic-plot')
                
                return dcc.Graph(
                    id={'type': 'scatter-plot', 'id': plot_id}, 
                    figure=figure, 
                    style={'height': '700px'}, 
                    config={'displayModeBar': True, 'displaylogo': False, 'modeBarButtonsToRemove': ['lasso2d', 'select2d']}
                )
            else:
                return _create_error_alert('图表生成失败，请检查数据是否已加载')
        except Exception as e:
            logger.error(f"[ERROR] 加载散点图失败: {e}")
            return _create_error_alert(str(e))

def _create_no_data_alert():
    return dbc.Alert([
        html.H5("📊 无可用数据", className="alert-heading"),
        html.P("请先在首页上传并分析数据后再访问此页面。")
    ], color="info", className="mt-4 shadow-sm border-0")

def _create_no_backend_alert():
    return dbc.Alert([
        html.H5("⚠️ 后端未初始化", className="alert-heading"),
        html.P("无法找到有效的分析后端，请刷新页面重试。")
    ], color="warning", className="mt-4 shadow-sm border-0")

def _create_error_alert(message):
    return dbc.Alert([
        html.H5("❌ 图表生成失败", className="alert-heading"),
        html.P(message)
    ], color="danger", className="mt-4 shadow-sm border-0")
