import dash_bootstrap_components as dbc
from dash import dcc, html

def create_consistency_analysis_card(id_prefix='consistency', index=None):
    """
    创建按键一致性分析卡片
    
    Args:
        id_prefix (str): 组件ID前缀，默认 'consistency'。
                         用于区别不同页面上的同类组件。
        index (str, optional): 如果提供，将使用 Pattern Matching ID 格式
                               {'type': 'consistency-xxx', 'index': index}。
                               用于在一个页面通过回调自动生成多个实例的情况。
    """
    if index is not None:
        # 使用 Pattern Matching ID
        key_selector_id = {'type': 'consistency-key-selector', 'index': index}
        plot_id = {'type': 'consistency-plot', 'index': index}
        slider_id = {'type': 'consistency-time-slider', 'index': index}
        loading_id = {'type': 'consistency-loading', 'index': index}
    else:
        # 使用字符串 ID
        key_selector_id = f'{id_prefix}-key-selector'
        plot_id = f'{id_prefix}-plot'
        slider_id = f'{id_prefix}-time-slider'
        loading_id = f'{id_prefix}-loading'

    return dbc.Card([
        dbc.CardHeader([
            html.H5([
                html.I(className="fas fa-wave-square me-2"),
                "按键波形一致性分析 (Key Consistency Analysis)"
            ], className="mb-0")
        ]),
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.Label("选择按键 ID:", className="fw-bold"),
                    dcc.Dropdown(
                        id=key_selector_id,
                        options=[],  # 初始为空，由回调填充
                        placeholder="请选择要分析的按键...",
                        searchable=True,
                        clearable=False
                    ),
                    html.Small("选择一个按键以查看该按键所有匹配对的波形叠加，用于发现异常匹配。", className="text-muted mt-1")
                ], md=4),
            ], className="mb-3"),
            
            dcc.Loading(
                id=loading_id,
                type="default",
                children=[
                    dcc.Graph(
                        id=plot_id,
                        figure={},
                        style={'height': '800px'},
                        config={'displayModeBar': True, 'scrollZoom': True}
                    ),
                    html.Div([
                        html.Label("时间范围导航 (秒) - 拖动滑块查看更多数据:"),
                        dcc.RangeSlider(
                            id=slider_id,
                            min=0,
                            max=100,
                            step=1,
                            value=[0, 30],
                            marks=None,
                            tooltip={'placement': 'bottom', 'always_visible': True}
                        )
                    ], style={'padding': '20px 40px'})
                ]
            )
        ])
    ], className="shadow-sm mb-4 mt-4")
