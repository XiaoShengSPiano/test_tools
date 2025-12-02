"""
UI布局模块 - 定义Dash应用的界面布局
包含主界面、报告布局等UI组件
"""
import dash_bootstrap_components as dbc
from dash import dcc, html, dash_table
import plotly.graph_objects as go

from utils.logger import Logger
logger = Logger.get_logger()


# 创建空白图形
empty_figure = go.Figure()
empty_figure.add_annotation(
    text="请上传数据文件并点击加载数据按钮",
    xref="paper", yref="paper",
    x=0.5, y=0.5, showarrow=False,
    font=dict(size=20, color='gray')
)
empty_figure.update_layout(
    title='钢琴数据分析工具 - 等待数据加载',
    xaxis_title='Time (ms)',
    yaxis_title='Key ID (1-88: keys, 89-90: pedals)',
    height=None,
    width=None,
    template='simple_white',
    autosize=True,
    margin=dict(l=60, r=60, t=100, b=60),
    showlegend=False,
    paper_bgcolor='rgba(0,0,0,0)',
    plot_bgcolor='rgba(0,0,0,0)',
    font=dict(size=12)
)


def create_multi_algorithm_upload_area():
    """创建多算法上传区域"""
    return html.Div([
        html.Label("多算法上传", style={
            'fontWeight': 'bold',
            'color': '#2c3e50',
            'marginBottom': '10px',
            'fontSize': '16px'
        }),
        dcc.Upload(
            id='upload-multi-algorithm-data',
            children=html.Div([
                html.I(className="fas fa-upload",
                      style={'fontSize': '32px', 'color': '#28a745', 'marginBottom': '10px'}),
                html.Br(),
                html.Span('上传算法文件（支持多选）', style={'fontSize': '14px', 'color': '#6c757d'})
            ], style={
                'textAlign': 'center',
                'padding': '20px',
                'border': '2px dashed #28a745',
                'borderRadius': '8px',
                'backgroundColor': '#f8f9fa',
                'cursor': 'pointer'
            }),
            multiple=True
        ),
        html.Div(id='multi-algorithm-upload-status', style={'marginTop': '10px', 'fontSize': '12px'}),
        # 文件列表区域（上传后显示）
        html.Div(id='multi-algorithm-file-list', style={'marginTop': '15px'})
    ])


def create_multi_algorithm_management_area():
    """创建多算法管理区域"""
    return html.Div([
        html.Label("📊 算法管理", style={
            'fontWeight': 'bold',
            'color': '#2c3e50',
            'marginBottom': '10px',
            'fontSize': '16px'
        }),
        # 现有数据迁移提示区域（默认隐藏，由回调动态更新）
        html.Div(id='existing-data-migration-area', style={'display': 'none'}, className='mb-3'),
        # 迁移相关的组件（始终存在，但默认隐藏，由回调控制显示）
        dbc.Input(
            id='existing-data-algorithm-name-input',
            type='text',
            placeholder='输入算法名称',
            style={'display': 'none', 'marginBottom': '10px'}
        ),
        dbc.Button(
            "确认迁移",
            id='confirm-migrate-existing-data-btn',
            color='primary',
            size='sm',
            n_clicks=0,
            style={'display': 'none'}
        ),
        html.Div(id='algorithm-list', children=[]),
        html.Div(id='algorithm-management-status', 
                style={'fontSize': '12px', 'color': '#6c757d', 'marginTop': '10px'})
    ])



def create_main_layout():
    """创建主界面布局"""
    return html.Div([
        # 隐藏的会话ID存储
        dcc.Store(id='session-id', storage_type='session'),
        # 存储多算法上传的文件内容（用于确认添加时获取）
        dcc.Store(id='multi-algorithm-files-store', data={'contents': [], 'filenames': []}),
        # 触发算法列表更新的 Store（当算法添加/删除时更新）
        dcc.Store(id='algorithm-list-trigger', data=0),
        # 存储当前点击的数据点信息，用于跳转到瀑布图
        dcc.Store(id='current-clicked-point-info', data=None),


        # 页面标题
        dbc.Container([
            dbc.Row([
                dbc.Col([
                    html.H1("🎹 钢琴数据分析工具",
                           className="text-center mb-4",
                           style={'color': '#2c3e50', 'fontWeight': 'bold'})
                ])
            ])
        ], fluid=True, className="mb-3"),

        # 上传容器 - 位于顶部
        dbc.Container([
            dbc.Card([
                dbc.CardBody([
                    dbc.Row([
                        # 左侧上传区域（多算法模式，默认显示）
                        dbc.Col([
                            html.Div(id='multi-algorithm-upload-area', children=create_multi_algorithm_upload_area())
                        ], width=5),

                        # 中间算法管理区域（多算法模式，默认显示）
                        dbc.Col([
                            html.Div(id='multi-algorithm-management-area', children=create_multi_algorithm_management_area())
                        ], width=3),

                        # 右侧历史记录和按钮区域
                        dbc.Col([
                            # 历史记录区域
                            html.Div([
                                html.Label("📚 历史记录", style={
                                    'fontWeight': 'bold',
                                    'color': '#2c3e50',
                                    'marginBottom': '10px',
                                    'fontSize': '16px'
                                }),
                                dcc.Input(
                                    id='history-search',
                                    type='text',
                                    placeholder='搜索历史记录...',
                                    style={
                                        'width': '100%',
                                        'padding': '8px 12px',
                                        'fontSize': '14px',
                                        'border': '1px solid #ced4da',
                                        'borderRadius': '5px',
                                        'marginBottom': '10px'
                                    }
                                ),
                                dcc.Dropdown(
                                    id='history-dropdown',
                                    options=[],
                                    placeholder="选择历史记录...",
                                    style={'marginBottom': '20px'},
                                    clearable=True,
                                    searchable=True
                                )
                            ]),


                            # 时间轴筛选组件
                            html.Div([
                                html.Label("⏰ 时间范围筛选", style={
                                    'fontWeight': 'bold',
                                    'color': '#2c3e50',
                                    'marginBottom': '10px',
                                    'fontSize': '16px'
                                }),
                                
                                # 新增：直接时间范围输入组件
                                html.Div([
                                    html.Label("直接设置时间范围 (100us):", style={'fontSize': '14px', 'marginBottom': '5px', 'fontWeight': 'bold'}),
                                    dbc.Row([
                                        dbc.Col([
                                            html.Label("开始时间:", style={'fontSize': '12px'}),
                                            dbc.Input(
                                                id='time-range-start-input',
                                                type='number',
                                                placeholder='开始时间',
                                                min=0,
                                                step=1,
                                                size='sm'
                                            )
                                        ], width=4),
                                        dbc.Col([
                                            html.Label("结束时间:", style={'fontSize': '12px'}),
                                            dbc.Input(
                                                id='time-range-end-input',
                                                type='number',
                                                placeholder='结束时间',
                                                min=0,
                                                step=1,
                                                size='sm'
                                            )
                                        ], width=4),
                                        dbc.Col([
                                            html.Label("操作:", style={'fontSize': '12px'}),
                                            html.Div([
                                                dbc.Button("确认更新", id='btn-confirm-time-range', 
                                                         color='success', size='sm',
                                                         className='btn btn-success btn-sm'),
                                                dbc.Button("重置", id='btn-reset-display-time-range', 
                                                         color='warning', size='sm',
                                                         className='btn btn-warning btn-sm',
                                                         style={'marginLeft': '5px'})
                                            ])
                                        ], width=4)
                                    ], className='mb-2'),
                                    html.Div(id='time-range-input-status', style={'fontSize': '12px', 'marginBottom': '10px'})
                                ], style={'backgroundColor': '#f8f9fa', 'padding': '10px', 'borderRadius': '5px', 'marginBottom': '15px'}),
                                
                                html.Div([
                                    html.Label("滑块时间范围 (100us):", style={'fontSize': '14px', 'marginBottom': '5px'}),
                                    dcc.RangeSlider(
                                        id='time-filter-slider',
                                        min=0, max=1000, step=10,
                                        value=[0, 1000],
                                        tooltip={"placement": "bottom", "always_visible": False},
                                        marks={i: str(i) for i in range(0, 1001, 500)},
                                        updatemode='mouseup'
                                    ),
                                    html.Div([
                                        dbc.Button("应用时间筛选", id='btn-apply-time-filter', 
                                                 color='info', size='sm', 
                                                 className='btn btn-outline-info btn-sm'),
                                        dbc.Button("重置时间范围", id='btn-reset-time-filter', 
                                                 color='secondary', size='sm', 
                                                 className='btn btn-outline-secondary btn-sm',
                                                 style={'marginLeft': '10px'})
                                    ], style={'marginBottom': '10px'}),
                                    html.Div(id='time-filter-status', 
                                            style={'fontSize': '12px', 'color': '#17a2b8', 'fontWeight': 'bold'})
                                ])
                            ], style={'marginBottom': '20px'}),

                            # 操作按钮组
                            html.Div([
                                html.Label("🔧 分析功能", style={
                                    'fontWeight': 'bold',
                                    'color': '#2c3e50',
                                    'marginBottom': '10px',
                                    'fontSize': '16px'
                                }),
                                # 自动生成瀑布图和报告，无需按钮
                                html.Div(style={'height': '10px'})
                            ])
                        ], width=6)
                    ])
                ])
            ])
        ], fluid=True, className="mb-4"),

        # 标签页容器
        dbc.Container([
            dcc.Tabs(id="main-tabs", value="waterfall-tab", children=[
                dcc.Tab(label="🌊 瀑布图分析", value="waterfall-tab", children=[
                    html.Div(id="waterfall-content", style={'padding': '20px', 'width': '100%'}, children=[
                        # 返回按钮 - 返回到报告界面
                        html.Div([
                            dbc.Button([
                                html.I(className="fas fa-arrow-left me-2"),
                                "返回报告界面"
                            ], id='btn-return-to-report', color='secondary', size='md', className='mb-3')
                        ], style={'marginBottom': '15px'}),
                        dcc.Graph(
                            id='main-plot', 
                            figure=empty_figure, 
                            style={"height": "1500px", "width": "100%"},  # 固定高度和宽度，避免Tab切换时大小变化
                            config={
                                'displayModeBar': True,
                                'displaylogo': False,
                                'modeBarButtonsToRemove': ['lasso2d', 'select2d'],  # 保留pan2d按钮，支持拖动
                                'scrollZoom': True,  # 启用鼠标滚轮缩放
                                'doubleClick': 'reset'  # 双击重置缩放
                            }
                        )
                    ]),
                    # 模态框 - 用于显示点击后的详细信息
                    html.Div([
                        html.Div([
                            # 模态框头部
                            html.Div([
                                html.H3("钢琴按键力度曲线详情", className="modal-title", style={
                                    'color': '#333',
                                    'fontWeight': 'bold',
                                    'margin': '0'
                                }),
                                html.Button(
                                    "×",
                                    id="close-modal-old",
                                    className="close",
                                    style={
                                        'float': 'right',
                                        'fontSize': '28px',
                                        'fontWeight': 'bold',
                                        'border': 'none',
                                        'background': 'none',
                                        'color': '#666',
                                        'cursor': 'pointer',
                                        'padding': '0',
                                        'width': '30px',
                                        'height': '30px',
                                        'lineHeight': '30px'
                                    }
                                )
                            ], className="modal-header", style={
                                'borderBottom': '1px solid #dee2e6',
                                'padding': '15px 20px',
                                'display': 'flex',
                                'justifyContent': 'space-between',
                                'alignItems': 'center'
                            }),

                            # 模态框主体 - 合并对比图表
                            html.Div([
                                html.Div([
                                    html.H4("合并对比力度曲线", style={
                                            'textAlign': 'center',
                                            'color': '#2c3e50',
                                            'marginBottom': '15px',
                                            'fontWeight': 'bold'
                                        }),
                                        dcc.Graph(
                                        id='detail-plot-combined-old',
                                        style={'height': '800px'},
                                            config={
                                                'displayModeBar': True,
                                                'displaylogo': False,
                                                'modeBarButtonsToRemove': ['pan2d', 'lasso2d', 'select2d']
                                            }
                                        )
                                    ], style={
                                    'width': '100%',
                                        'padding': '10px'
                                })
                            ], id='modal-content-old', className="modal-body", style={
                                'padding': '20px',
                                'maxHeight': '90vh',
                                'overflowY': 'auto'
                                    }),

                            # 模态框底部
                                    html.Div([
                                html.Button(
                                    "关闭",
                                    id="close-modal-btn-old",
                                    className="btn btn-primary",
                                    style={
                                        'backgroundColor': '#007bff',
                                        'borderColor': '#007bff',
                                        'padding': '8px 20px',
                                        'borderRadius': '5px',
                                        'border': 'none',
                                        'color': 'white',
                                        'cursor': 'pointer'
                                    }
                                )
                            ], className="modal-footer", style={
                                'borderTop': '1px solid #dee2e6',
                                'padding': '15px 20px',
                                'textAlign': 'right'
                            })

                        ], className="modal-content", style={
                            'backgroundColor': 'white',
                            'margin': '1% auto',
                            'padding': '0',
                            'border': 'none',
                            'width': '95%',
                            'maxWidth': '1600px',
                            'borderRadius': '10px',
                            'boxShadow': '0 4px 20px rgba(0,0,0,0.3)',
                            'maxHeight': '98vh',
                            'overflow': 'hidden'
                        })

                    ], id="detail-modal-old", className="modal", style={
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

                ]),
                dcc.Tab(label="📊 异常检测报告", value="report-tab", children=[
                    html.Div(id="report-content", style={'padding': '20px'})
                ])
            ])
        ], fluid=True),
        # 关键：这些组件必须在主布局的顶层直接存在，用于支持回调
        # Dash 在注册回调时会检查 Input 组件是否存在，即使设置了 suppress_callback_exceptions=True
        # 重要：这些组件必须直接放在主布局的顶层，不能放在任何容器中，否则 Dash 可能无法识别
        # 这些组件会被 report-content 中的同名组件覆盖（当 report-content 有内容时）
        # 但当 report-content 为空时，这些隐藏版本会确保回调函数不会报错
        dcc.Graph(id='key-delay-scatter-plot', figure={}, style={'display': 'none'}),
        dcc.Graph(id='key-delay-zscore-scatter-plot', figure={}, style={'display': 'none'}),
        dcc.Graph(id='hammer-velocity-delay-scatter-plot', figure={}, style={'display': 'none'}),
        dcc.Graph(id='key-force-interaction-plot', figure={}, style={'display': 'none'}),
        dcc.Store(id='key-force-interaction-selected-algorithms', data=[]),  # 存储选中的算法列表
        dcc.Store(id='key-force-interaction-selected-keys', data=[]),  # 存储选中的按键列表
        dcc.Graph(id='relative-delay-distribution-plot', figure={}, style={'display': 'none'}),
        html.Div(id='offset-alignment-plot', style={'display': 'none'}),
        dcc.Graph(id='delay-time-series-plot', figure={}, style={'display': 'none'}),
        dcc.Graph(id='delay-histogram-plot', figure={}, style={'display': 'none'}),
        html.Div([
            dash_table.DataTable(
                id='offset-alignment-table',
                data=[],
                columns=[]
            )
        ], style={'display': 'none'}),
        html.Div([
            dash_table.DataTable(
                id='delay-histogram-detail-table',
                data=[],
                columns=[
                    {"name": "算法名称", "id": "algorithm_name"},
                    {"name": "按键ID", "id": "key_id"},
                    {"name": "延时(ms)", "id": "delay_ms"},
                    {"name": "录制索引", "id": "record_index"},
                    {"name": "播放索引", "id": "replay_index"},
                    {"name": "录制开始(0.1ms)", "id": "record_keyon"},
                    {"name": "播放开始(0.1ms)", "id": "replay_keyon"},
                    {"name": "持续时间差(0.1ms)", "id": "duration_offset"},
                ]
            )
        ], style={'display': 'none'}),
        html.Div(id='delay-histogram-selection-info', style={'display': 'none'}),
        # 相对延时分布图相关组件
        html.Div([
            html.Div(id='relative-delay-distribution-subplot-title', style={'display': 'none'}),
            html.Div(id='relative-delay-distribution-selection-info', style={'display': 'none'}),
            dash_table.DataTable(
                id='relative-delay-distribution-detail-table',
                data=[],
                columns=[
                    {"name": "算法名称", "id": "algorithm_name"},
                    {"name": "按键ID", "id": "key_id"},
                    {"name": "相对延时(ms)", "id": "relative_delay_ms", "type": "numeric", "format": {"specifier": ".2f"}},
                    {"name": "绝对延时(ms)", "id": "absolute_delay_ms", "type": "numeric", "format": {"specifier": ".2f"}},
                    {"name": "录制索引", "id": "record_index"},
                    {"name": "播放索引", "id": "replay_index"},
                    {"name": "录制开始(0.1ms)", "id": "record_keyon"},
                    {"name": "播放开始(0.1ms)", "id": "replay_keyon"},
                    {"name": "持续时间差(0.1ms)", "id": "duration_offset"},
                ],
                page_action='none',
                style_cell={
                    'textAlign': 'center',
                    'fontSize': '12px',
                    'fontFamily': 'Arial, sans-serif',
                    'padding': '8px',
                    'overflow': 'hidden',
                    'textOverflow': 'ellipsis',
                },
                style_header={
                    'backgroundColor': '#f8f9fa',
                    'fontWeight': 'bold',
                    'border': '1px solid #dee2e6',
                    'position': 'sticky',
                    'top': 0,
                    'zIndex': 1
                },
                style_data={
                    'whiteSpace': 'normal',
                    'height': 'auto',
                },
                style_table={
                    'overflowX': 'auto',
                    'overflowY': 'auto',
                    'maxHeight': '600px',
                }
            )
        ], style={'display': 'none'}, id='relative-delay-distribution-table-container'),
        # 存储跳转来源图表ID，用于返回时滚动定位
        dcc.Store(id='jump-source-plot-id', data=None),
        # 滚动触发Store，用于客户端回调
        dcc.Store(id='scroll-to-plot-trigger', data=None),
        # 相对延时分布图滚动触发Store
        dcc.Store(id='relative-delay-distribution-scroll-trigger', data=None),
        # 将模态框移到主布局顶层，确保在所有Tab中都能显示
        html.Div([
            html.Div([
                html.Div([
                    html.Div([
                        html.H4("详细分析", style={'margin': '0', 'padding': '15px 20px', 'borderBottom': '1px solid #dee2e6'}),
                        html.Button("×", id="close-modal", className="close", style={
                            'position': 'absolute',
                            'right': '15px',
                            'top': '15px',
                            'fontSize': '28px',
                            'fontWeight': 'bold',
                            'background': 'none',
                            'border': 'none',
                            'cursor': 'pointer',
                            'color': '#aaa'
                        })
                    ], style={'position': 'relative', 'borderBottom': '1px solid #dee2e6'}),
                    html.Div([
                        html.Div([
                                    dcc.Graph(
                                        id='detail-plot-combined',
                                style={'height': '800px'},
                                        config={
                                            'displayModeBar': True,
                                            'displaylogo': False,
                                            'modeBarButtonsToRemove': ['pan2d', 'lasso2d', 'select2d']
                                        }
                                    )
                                ], style={
                                    'width': '100%',
                                    'padding': '10px'
                                })
                            ], id='modal-content', className="modal-body", style={
                                'padding': '20px',
                                'maxHeight': '90vh',
                                'overflowY': 'auto'
                            }),
                            html.Div([
                                html.Button(
                                    "关闭",
                                    id="close-modal-btn",
                                    className="btn btn-primary",
                                    style={
                                        'backgroundColor': '#007bff',
                                        'borderColor': '#007bff',
                                        'padding': '8px 20px',
                                        'borderRadius': '5px',
                                        'border': 'none',
                                        'color': 'white',
                                        'cursor': 'pointer'
                                    }
                                )
                            ], className="modal-footer", style={
                                'borderTop': '1px solid #dee2e6',
                                'padding': '15px 20px',
                                'textAlign': 'right'
                            })
                        ], className="modal-content", style={
                            'backgroundColor': 'white',
                            'margin': '1% auto',
                            'padding': '0',
                            'border': 'none',
                            'width': '95%',
                            'maxWidth': '1600px',
                            'borderRadius': '10px',
                            'boxShadow': '0 4px 20px rgba(0,0,0,0.3)',
                            'maxHeight': '98vh',
                            'overflow': 'hidden'
                        })
                    ], id="detail-modal", className="modal", style={
                        'display': 'none',
                        'position': 'fixed',
                'zIndex': '9999',
                        'left': '0',
                        'top': '0',
                        'width': '100%',
                        'height': '100%',
                        'backgroundColor': 'rgba(0,0,0,0.6)',
                        'backdropFilter': 'blur(5px)'
            }),
            # 按键曲线对比模态框（悬浮窗）
            html.Div([
                html.Div([
                    html.Div([
                        html.Div([
                            html.H4("按键曲线对比", style={'margin': '0', 'padding': '10px 20px', 'borderBottom': '1px solid #dee2e6'}),  # 减少顶部padding：从15px改为10px
                            html.Button("×", id="close-key-curves-modal", className="close", style={
                                'position': 'absolute',
                                'right': '15px',
                                'top': '15px',
                                'fontSize': '28px',
                                'fontWeight': 'bold',
                                'background': 'none',
                                'border': 'none',
                                'cursor': 'pointer',
                                'color': '#aaa'
                            })
                        ], style={'position': 'relative', 'borderBottom': '1px solid #dee2e6'}),
                        html.Div([
                            html.Div(id='key-curves-comparison-container', children=[])
                        ], id='key-curves-modal-content', className="modal-body", style={
                            'padding': '10px 20px 20px 20px',  # 减少顶部padding：从20px改为10px
                            'maxHeight': '90vh',
                            'overflowY': 'auto'
                        }),
                        html.Div([
                            html.Button(
                                "跳转到瀑布图",
                                id="jump-to-waterfall-btn",
                                className="btn btn-success",
                                style={
                                    'backgroundColor': '#28a745',
                                    'borderColor': '#28a745',
                                    'padding': '8px 20px',
                                    'borderRadius': '5px',
                                    'border': 'none',
                                    'color': 'white',
                                    'cursor': 'pointer',
                                    'marginRight': '10px'
                                }
                            ),
                            html.Button(
                                "关闭",
                                id="close-key-curves-modal-btn",
                                className="btn btn-primary",
                                style={
                                    'backgroundColor': '#007bff',
                                    'borderColor': '#007bff',
                                    'padding': '8px 20px',
                                    'borderRadius': '5px',
                                    'border': 'none',
                                    'color': 'white',
                                    'cursor': 'pointer'
                                }
                            )
                        ], className="modal-footer", style={
                            'borderTop': '1px solid #dee2e6',
                            'padding': '15px 20px',
                            'textAlign': 'right'
                        })
                    ], className="modal-content", style={
                        'backgroundColor': 'white',
                        'margin': '0.5% auto',  # 减少顶部margin：从1%改为0.5%
                        'padding': '0',
                        'border': 'none',
                        'width': '95%',
                        'maxWidth': '1600px',
                        'borderRadius': '10px',
                        'boxShadow': '0 4px 20px rgba(0,0,0,0.3)',
                        'maxHeight': '98vh',
                        'overflow': 'hidden'
                    })
                ], id="key-curves-modal", className="modal", style={
                    'display': 'none',
                    'position': 'fixed',
                    'zIndex': '9999',
                    'left': '0',
                    'top': '0',
                    'width': '100%',
                    'height': '100%',
                    'backgroundColor': 'rgba(0,0,0,0.6)',
                    'backdropFilter': 'blur(5px)'
                })
            ]),
            # 瀑布图专用曲线对比模态框（避免与其他功能冲突）
            html.Div([
                html.Div([
                    html.Div([
                        html.Div([
                            html.H4("按键曲线对比 (瀑布图)", style={'margin': '0', 'padding': '10px 20px', 'borderBottom': '1px solid #dee2e6'}),
                            html.Button("×", id="close-waterfall-curves-modal", className="close", style={
                                'position': 'absolute',
                                'right': '15px',
                                'top': '15px',
                                'fontSize': '28px',
                                'fontWeight': 'bold',
                                'background': 'none',
                                'border': 'none',
                                'cursor': 'pointer',
                                'color': '#aaa'
                            })
                        ], style={'position': 'relative', 'borderBottom': '1px solid #dee2e6'}),
                        html.Div([
                            html.Div(id='waterfall-curves-comparison-container', children=[])
                        ], id='waterfall-curves-modal-content', className="modal-body", style={
                            'padding': '10px 20px 20px 20px',
                            'maxHeight': '90vh',
                            'overflowY': 'auto'
                        }),
                        html.Div([
                            html.Button(
                                "跳转到瀑布图",
                                id="jump-to-waterfall-btn-from-modal",
                                className="btn btn-success",
                                style={
                                    'backgroundColor': '#28a745',
                                    'borderColor': '#28a745',
                                    'padding': '8px 20px',
                                    'borderRadius': '5px',
                                    'border': 'none',
                                    'color': 'white',
                                    'cursor': 'pointer',
                                    'marginRight': '10px'
                                }
                            ),
                            html.Button(
                                "关闭",
                                id="close-waterfall-curves-modal-btn",
                                className="btn btn-primary",
                                style={
                                    'backgroundColor': '#007bff',
                                    'borderColor': '#007bff',
                                    'padding': '8px 20px',
                                    'borderRadius': '5px',
                                    'border': 'none',
                                    'color': 'white',
                                    'cursor': 'pointer'
                                }
                            )
                        ], className="modal-footer", style={
                            'borderTop': '1px solid #dee2e6',
                            'padding': '15px 20px',
                            'textAlign': 'right'
                        })
                    ], className="modal-content", style={
                        'backgroundColor': 'white',
                        'margin': '0.5% auto',
                        'padding': '0',
                        'border': 'none',
                        'width': '95%',
                        'maxWidth': '1600px',
                        'borderRadius': '10px',
                        'boxShadow': '0 4px 20px rgba(0,0,0,0.3)',
                        'maxHeight': '98vh',
                        'overflow': 'hidden'
                    })
                ], id="waterfall-curves-modal", className="modal", style={
                    'display': 'none',
                    'position': 'fixed',
                    'zIndex': '9999',
                    'left': '0',
                    'top': '0',
                    'width': '100%',
                    'height': '100%',
                    'backgroundColor': 'rgba(0,0,0,0.6)',
                    'backdropFilter': 'blur(5px)'
                })
            ])
        ])

    ], style={
        'fontFamily': 'Arial, sans-serif',
        'backgroundColor': '#f8f9fa',
        'minHeight': '100vh'
    })


def _create_single_algorithm_overview_row(algorithm, algorithm_name):
    """为单个算法创建数据概览行（不包含卡片，只返回行内容）"""
    
    try:
        # 获取算法的统计数据
        if not algorithm.analyzer:
            return None
        
        # 计算基础统计
        # 使用初始有效数据（第一次过滤后）来计算总有效音符数，这样才能正确反映准确率
        initial_valid_record = getattr(algorithm.analyzer, 'initial_valid_record_data', None)
        initial_valid_replay = getattr(algorithm.analyzer, 'initial_valid_replay_data', None)
        
        total_valid_record = len(initial_valid_record) if initial_valid_record else 0
        total_valid_replay = len(initial_valid_replay) if initial_valid_replay else 0
        
        # 获取匹配对和错误统计
        matched_pairs = algorithm.analyzer.matched_pairs if hasattr(algorithm.analyzer, 'matched_pairs') else []
        drop_hammers = algorithm.analyzer.drop_hammers if hasattr(algorithm.analyzer, 'drop_hammers') else []
        multi_hammers = algorithm.analyzer.multi_hammers if hasattr(algorithm.analyzer, 'multi_hammers') else []
        
        # 计算准确率
        # 公式：成功匹配的音符对数 * 2 / (初始有效录制音符数 + 初始有效播放音符数) * 100
        matched_count = len(matched_pairs)
        total_valid = total_valid_record + total_valid_replay
        accuracy = (matched_count * 2 / total_valid * 100) if total_valid > 0 else 0.0
        
        # 生成数据概览行（带算法名称标识）
        overview_row = html.Div([
            dbc.Row([
                dbc.Col([
                    html.Div([
                        html.Small(f"算法: {algorithm_name}", className="text-muted", style={'fontSize': '12px', 'fontWeight': 'bold', 'display': 'block', 'marginBottom': '8px'})
                    ])
                ], width=12)
            ], className="mb-2"),
                            dbc.Row([
                                dbc.Col([
                                    html.Div([
                        html.H3(f"{accuracy:.1f}%", className="text-success mb-1"),
                                        html.P("准确率", className="text-muted mb-0"),
                                        html.Small("成功匹配音符数/总有效音符数", className="text-muted", style={'fontSize': '10px'})
                                    ], className="text-center")
                                ], width=3),
                                dbc.Col([
                                    html.Div([
                        html.H3(f"{len(drop_hammers)}", className="text-warning mb-1"),
                                        html.P("丢锤数", className="text-muted mb-0"),
                                        html.Small("录制有但播放没有", className="text-muted", style={'fontSize': '10px'})
                                    ], className="text-center")
                                ], width=3),
                                dbc.Col([
                                    html.Div([
                        html.H3(f"{len(multi_hammers)}", className="text-info mb-1"),
                                        html.P("多锤数", className="text-muted mb-0"),
                                        html.Small("播放有但录制没有", className="text-muted", style={'fontSize': '10px'})
                                    ], className="text-center")
                                ], width=3),
                                dbc.Col([
                                    html.Div([
                        html.H3(f"{matched_count}", className="text-secondary mb-1"),
                                        html.P("已配对音符数", className="text-muted mb-0"),
                                        html.Small("成功匹配的record-play配对数量", className="text-muted", style={'fontSize': '10px'})
                                    ], className="text-center")
                                ], width=3)
            ], className="mb-3")
        ], className="mb-3", style={'borderBottom': '1px solid #dee2e6', 'paddingBottom': '15px'})
        
        return overview_row
        
    except Exception as e:
        logger.error(f"❌ 获取算法 '{algorithm_name}' 的数据概览失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None


def _create_single_algorithm_error_stats_row(algorithm, algorithm_name):
    """为单个算法创建延时误差统计指标行（不包含卡片，只返回行内容）"""
    try:
        # 获取算法的统计数据
        if not algorithm.analyzer:
            return None
        
        # 计算延时误差统计指标
        mae_0_1ms = algorithm.analyzer.get_mean_absolute_error() if hasattr(algorithm.analyzer, 'get_mean_absolute_error') else 0.0
        variance_0_1ms_squared = algorithm.analyzer.get_variance() if hasattr(algorithm.analyzer, 'get_variance') else 0.0
        std_0_1ms = algorithm.analyzer.get_standard_deviation() if hasattr(algorithm.analyzer, 'get_standard_deviation') else 0.0
        me_0_1ms = algorithm.analyzer.get_mean_error() if hasattr(algorithm.analyzer, 'get_mean_error') else 0.0
        rmse_0_1ms = algorithm.analyzer.get_root_mean_squared_error() if hasattr(algorithm.analyzer, 'get_root_mean_squared_error') else 0.0
        cv = algorithm.analyzer.get_coefficient_of_variation() if hasattr(algorithm.analyzer, 'get_coefficient_of_variation') else 0.0
        
        variance_ms_squared = variance_0_1ms_squared / 100.0
        std_ms = std_0_1ms / 10.0
        mae_ms = mae_0_1ms / 10.0
        me_ms = me_0_1ms / 10.0
        rmse_ms = rmse_0_1ms / 10.0
        
        # 计算按键延时的最大值和最小值（从已匹配按键的keyon_offset）
        max_delay_ms = None
        min_delay_ms = None
        max_delay_item = None  # 保存最大延迟对应的完整数据项
        min_delay_item = None  # 保存最小延迟对应的完整数据项
        if hasattr(algorithm.analyzer, 'note_matcher') and algorithm.analyzer.note_matcher:
            try:
                offset_data = algorithm.analyzer.note_matcher.get_offset_alignment_data()
                if offset_data:
                    # 提取所有keyon_offset（单位：0.1ms，带符号）
                    keyon_offsets = [item.get('keyon_offset', 0) for item in offset_data]
                    if keyon_offsets:
                        # 转换为ms单位
                        keyon_offsets_ms = [offset / 10.0 for offset in keyon_offsets]
                        max_delay_ms = max(keyon_offsets_ms)
                        min_delay_ms = min(keyon_offsets_ms)
                        
                        # 找到对应的数据项
                        for item in offset_data:
                            item_delay_ms = item.get('keyon_offset', 0) / 10.0
                            if max_delay_item is None or item_delay_ms == max_delay_ms:
                                max_delay_item = item
                            if min_delay_item is None or item_delay_ms == min_delay_ms:
                                min_delay_item = item
            except Exception as e:
                logger.warning(f"⚠️ 计算按键延时最大值/最小值失败: {e}")
        
        # 生成延时误差统计指标行（带算法名称标识）
        error_stats_row = html.Div([
                            dbc.Row([
                                dbc.Col([
                                    html.Div([
                        html.Small(f"算法: {algorithm_name}", className="text-muted", style={'fontSize': '12px', 'fontWeight': 'bold', 'display': 'block', 'marginBottom': '8px'})
                    ])
                ], width=12)
            ], className="mb-2"),
            dbc.Row([
                dbc.Col([
                    html.Div([
                        html.H3(f"{me_ms:.2f} ms", className="text-secondary mb-1"),
                        html.P("平均延时", className="text-muted mb-0"),
                        html.Small("所有已匹配按键对的keyon_offset的算术平均（带符号）", className="text-muted", style={'fontSize': '10px'})
                    ], className="text-center")
                ], width=4),
                dbc.Col([
                    html.Div([
                        html.H3(f"{variance_ms_squared:.2f} ms²", className="text-danger mb-1"),
                        html.P("方差", className="text-muted mb-0"),
                        html.Small("所有已匹配按键对的keyon_offset的方差", className="text-muted", style={'fontSize': '10px'})
                    ], className="text-center")
                ], width=4),
                dbc.Col([
                    html.Div([
                        html.H3(f"{std_ms:.2f} ms", className="text-info mb-1"),
                        html.P("标准差", className="text-muted mb-0"),
                        html.Small("所有已匹配按键对的keyon_offset的标准差", className="text-muted", style={'fontSize': '10px'})
                    ], className="text-center")
                ], width=4)
            ], className="mb-3"),
            dbc.Row([
                dbc.Col([
                    html.Div([
                        html.H3(f"{mae_ms:.2f} ms", className="text-warning mb-1"),
                        html.P("平均绝对误差(MAE)", className="text-muted mb-0"),
                        html.Small("已匹配按键对的延时绝对值的平均", className="text-muted", style={'fontSize': '10px'})
                    ], className="text-center")
                ], width=4),
                dbc.Col([
                    html.Div([
                        html.H3(f"{rmse_ms:.2f} ms", className="text-success mb-1"),
                        html.P("均方根误差(RMSE)", className="text-muted mb-0"),
                        html.Small("对大偏差更敏感", className="text-muted", style={'fontSize': '10px'})
                    ], className="text-center")
                ], width=4),
                dbc.Col([
                    html.Div([
                        html.H3(f"{cv:.2f}%", className="text-primary mb-1"),
                        html.P("变异系数(CV)", className="text-muted mb-0"),
                        html.Small("标准差与均值的比值，反映相对变异程度", className="text-muted", style={'fontSize': '10px'})
                    ], className="text-center")
                ], width=4)
            ], className="mb-3"),
            dbc.Row([
                dbc.Col([
                    html.Div([
                        html.Div(
                            f"{max_delay_ms:.2f} ms" if max_delay_ms is not None else "N/A", 
                            className="text-danger mb-1",
                            id={"type": "max-delay-value", "algorithm": algorithm_name},
                            style={
                                'cursor': 'pointer', 
                                'userSelect': 'none',
                                'fontSize': '1.75rem',
                                'fontWeight': '500',
                                'lineHeight': '1.2'
                            },
                            title="点击查看对应按键的曲线对比图"
                        ),
                        html.P("最大偏差", className="text-muted mb-0"),
                        html.Small("已匹配按键中的最大延时（点击数值查看曲线）", className="text-muted", style={'fontSize': '10px'})
                    ], className="text-center")
                ], width=6),
                dbc.Col([
                    html.Div([
                        html.Div(
                            f"{min_delay_ms:.2f} ms" if min_delay_ms is not None else "N/A", 
                            className="text-info mb-1",
                            id={"type": "min-delay-value", "algorithm": algorithm_name},
                            style={
                                'cursor': 'pointer', 
                                'userSelect': 'none',
                                'fontSize': '1.75rem',
                                'fontWeight': '500',
                                'lineHeight': '1.2'
                            },
                            title="点击查看对应按键的曲线对比图"
                        ),
                        html.P("最小偏差", className="text-muted mb-0"),
                        html.Small("已匹配按键中的最小偏差（点击数值查看曲线）", className="text-muted", style={'fontSize': '10px'})
                    ], className="text-center")
                ], width=6)
            ])
        ], className="mb-3", style={'borderBottom': '1px solid #dee2e6', 'paddingBottom': '15px'})
        
        return error_stats_row
        
    except Exception as e:
        logger.error(f"❌ 获取算法 '{algorithm_name}' 的延时误差统计指标失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None


def _create_single_algorithm_error_tables(algorithm, algorithm_name):
    """
    为单个算法创建丢锤和多锤问题表格
    
    Args:
        algorithm: AlgorithmDataset实例
        algorithm_name: 算法名称
        
    Returns:
        Tuple[html.Div, html.Div]: (丢锤表格区域, 多锤表格区域)
    """
    try:
        if not algorithm.analyzer:
            return None, None
        
        # 获取错误数据（ErrorNote对象列表）
        drop_hammers = algorithm.analyzer.drop_hammers if hasattr(algorithm.analyzer, 'drop_hammers') else []
        multi_hammers = algorithm.analyzer.multi_hammers if hasattr(algorithm.analyzer, 'multi_hammers') else []
        
        # 获取匹配失败原因（用于更详细的分析）
        failure_reasons = {}
        if algorithm.analyzer and hasattr(algorithm.analyzer, 'note_matcher'):
            failure_reasons = getattr(algorithm.analyzer.note_matcher, 'failure_reasons', {})
        
        # 转换为表格数据格式
        drop_hammers_data = []
        for error_note in drop_hammers:
            # ErrorNote对象包含infos列表，每个元素是NoteInfo对象
            if len(error_note.infos) > 0:
                rec = error_note.infos[0]  # 获取第一个NoteInfo对象
                
                # 获取详细的匹配失败原因
                analysis_reason = '丢锤（录制有，播放无）'
                if ('record', rec.index) in failure_reasons:
                    analysis_reason = failure_reasons[('record', rec.index)]
                
                # NoteInfo的keyOn和keyOff单位是0.1ms，需要除以10转换为ms
                row = {
                    'data_type': 'record',
                    'keyId': rec.keyId,
                    'keyOn': f"{rec.keyOn/10:.2f}",
                    'keyOff': f"{rec.keyOff/10:.2f}",
                    'index': rec.index,
                    'analysis_reason': analysis_reason
                }
                drop_hammers_data.append(row)
                
                # 播放行显示"无匹配"
                drop_hammers_data.append({
                    'data_type': 'play',
                    'keyId': '无匹配',
                    'keyOn': '无匹配',
                    'keyOff': '无匹配',
                    'index': '无匹配',
                    'analysis_reason': ''
                })
        
        multi_hammers_data = []
        for error_note in multi_hammers:
            # ErrorNote对象包含infos列表，每个元素是NoteInfo对象
            if len(error_note.infos) > 0:
                play = error_note.infos[0]  # 获取第一个NoteInfo对象
                
                # 多锤的分析原因
                analysis_reason = '多锤（播放有，录制无）'
                
                # 录制行显示"无匹配"
                multi_hammers_data.append({
                    'data_type': 'record',
                    'keyId': '无匹配',
                    'keyOn': '无匹配',
                    'keyOff': '无匹配',
                    'index': '无匹配',
                    'analysis_reason': ''
                })
                
                # 播放行显示实际数据
                # NoteInfo的keyOn和keyOff单位是0.1ms，需要除以10转换为ms
                row = {
                    'data_type': 'play',
                    'keyId': play.keyId,
                    'keyOn': f"{play.keyOn/10:.2f}",
                    'keyOff': f"{play.keyOff/10:.2f}",
                    'index': play.index,
                    'analysis_reason': analysis_reason
                }
                multi_hammers_data.append(row)
        
        # 创建丢锤表格
        drop_hammers_table = html.Div([
            dbc.Row([
                dbc.Col([
                    html.H6(f"丢锤问题列表 - {algorithm_name}", className="mb-2",
                           style={'color': '#721c24', 'fontWeight': 'bold', 'fontSize': '16px', 'borderBottom': '2px solid #721c24', 'paddingBottom': '5px'}),
                ], width=12)
            ]),
            dash_table.DataTable(
                id={'type': 'drop-hammers-table', 'index': algorithm_name},
                columns=[
                    {"name": "数据类型", "id": "data_type"},
                    {"name": "键位ID", "id": "keyId"},
                    {"name": "按下时间(ms)", "id": "keyOn"},
                    {"name": "释放时间(ms)", "id": "keyOff"},
                    {"name": "index", "id": "index"},
                    {"name": "未匹配原因", "id": "analysis_reason"},
                ],
                data=drop_hammers_data,
                page_action='none',
                style_cell={
                    'textAlign': 'center',
                    'fontSize': '13px',
                    'fontFamily': 'Arial, sans-serif',
                    'padding': '8px',
                    'overflow': 'hidden',
                    'textOverflow': 'ellipsis',
                    'minWidth': '70px',
                },
                style_cell_conditional=[
                    {'if': {'column_id': 'data_type'}, 'width': '14%'},
                    {'if': {'column_id': 'keyId'}, 'width': '12%'},
                    {'if': {'column_id': 'keyOn'}, 'width': '16%'},
                    {'if': {'column_id': 'keyOff'}, 'width': '16%'},
                    {'if': {'column_id': 'index'}, 'width': '10%'},
                    {'if': {'column_id': 'analysis_reason'}, 'width': '32%'},
                ],
                style_header={
                    'backgroundColor': '#f8d7da',
                    'fontWeight': 'bold',
                    'border': '2px solid #dee2e6',
                    'fontSize': '14px',
                    'color': '#721c24',
                    'textAlign': 'center',
                    'padding': '10px',
                    'whiteSpace': 'normal',
                    'height': 'auto',
                    'position': 'sticky',
                    'top': 0,
                    'zIndex': 1
                },
                style_data={
                    'border': '1px solid #dee2e6',
                    'fontSize': '13px',
                    'padding': '8px'
                },
                style_data_conditional=[
                    {
                        'if': {'filter_query': '{data_type} = record'},
                        'fontWeight': 'bold',
                        'backgroundColor': '#ffeaea'
                    },
                    {
                        'if': {'row_index': 'odd'},
                        'backgroundColor': '#fafafa'
                    }
                ],
                row_selectable=False,
                sort_action="native",
                filter_action="none",
                style_table={
                    'height': '300px',
                    'overflowY': 'auto',
                    'overflowX': 'auto',
                    'border': '2px solid #dee2e6',
                    'borderRadius': '8px',
                    'minHeight': '150px'
                }
            ),
        ], style={'backgroundColor': '#ffffff', 'padding': '15px', 'borderRadius': '8px', 'boxShadow': '0 2px 6px rgba(0,0,0,0.1)', 'marginBottom': '15px'})
        
        # 创建多锤表格
        multi_hammers_table = html.Div([
                            dbc.Row([
                                dbc.Col([
                    html.H6(f"多锤问题列表 - {algorithm_name}", className="mb-2",
                           style={'color': '#856404', 'fontWeight': 'bold', 'fontSize': '16px', 'borderBottom': '2px solid #856404', 'paddingBottom': '5px'}),
                ], width=12)
            ]),
            dash_table.DataTable(
                id={'type': 'multi-hammers-table', 'index': algorithm_name},
                columns=[
                    {"name": "数据类型", "id": "data_type"},
                    {"name": "键位ID", "id": "keyId"},
                    {"name": "按下时间(ms)", "id": "keyOn"},
                    {"name": "释放时间(ms)", "id": "keyOff"},
                    {"name": "index", "id": "index"},
                    {"name": "未匹配原因", "id": "analysis_reason"},
                ],
                data=multi_hammers_data,
                page_action='none',
                style_cell={
                    'textAlign': 'center',
                    'fontSize': '13px',
                    'fontFamily': 'Arial, sans-serif',
                    'padding': '8px',
                    'overflow': 'hidden',
                    'textOverflow': 'ellipsis',
                    'minWidth': '70px',
                },
                style_cell_conditional=[
                    {'if': {'column_id': 'data_type'}, 'width': '14%'},
                    {'if': {'column_id': 'keyId'}, 'width': '12%'},
                    {'if': {'column_id': 'keyOn'}, 'width': '16%'},
                    {'if': {'column_id': 'keyOff'}, 'width': '16%'},
                    {'if': {'column_id': 'index'}, 'width': '10%'},
                    {'if': {'column_id': 'analysis_reason'}, 'width': '32%'},
                ],
                style_header={
                    'backgroundColor': '#fff3cd',
                    'fontWeight': 'bold',
                    'border': '2px solid #dee2e6',
                    'fontSize': '14px',
                    'color': '#856404',
                    'textAlign': 'center',
                    'padding': '10px',
                    'whiteSpace': 'normal',
                    'height': 'auto',
                    'position': 'sticky',
                    'top': 0,
                    'zIndex': 1
                },
                style_data={
                    'border': '1px solid #dee2e6',
                    'fontSize': '13px',
                    'padding': '8px'
                },
                style_data_conditional=[
                    {
                        'if': {'filter_query': '{data_type} = play'},
                        'backgroundColor': '#fffef5'
                    },
                    {
                        'if': {'row_index': 'odd'},
                        'backgroundColor': '#fafafa'
                    }
                ],
                row_selectable=False,
                sort_action="native",
                filter_action="none",
                style_table={
                    'height': '300px',
                    'overflowY': 'auto',
                    'overflowX': 'auto',
                    'border': '2px solid #dee2e6',
                    'borderRadius': '8px',
                    'minHeight': '150px'
                }
            ),
        ], style={'backgroundColor': '#ffffff', 'padding': '15px', 'borderRadius': '8px', 'boxShadow': '0 2px 6px rgba(0,0,0,0.1)', 'marginBottom': '15px'})
        
        return drop_hammers_table, multi_hammers_table
        
    except Exception as e:
        logger.error(f"❌ 创建算法 {algorithm_name} 错误表格失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None, None


def _create_error_tables_row_for_algorithm(algorithm):
    """
    为单个算法创建一行错误表格（丢锤和多锤左右并排）
    
    Args:
        algorithm: AlgorithmDataset实例
        
    Returns:
        dbc.Row: 包含丢锤和多锤表格的行
    """
    algorithm_name = algorithm.metadata.algorithm_name
    drop_table, multi_table = _create_single_algorithm_error_tables(algorithm, algorithm_name)
    
    if drop_table and multi_table:
        return dbc.Row([
            dbc.Col([drop_table], width=6, className="pr-2"),
            dbc.Col([multi_table], width=6, className="pl-2"),
        ], className="mb-3")
    else:
        # 如果没有数据，返回空行
        return dbc.Row([
                dbc.Col([
                    html.Div([
                    html.P(f"算法 {algorithm_name} 暂无错误数据", className="text-center text-muted", style={'padding': '20px'})
                ], style={'backgroundColor': '#ffffff', 'padding': '20px', 'borderRadius': '8px'})
            ], width=12)
        ], className="mb-3")


def _hex_to_rgba(hex_color, alpha=0.3):
    """将十六进制颜色转换为RGBA格式，用于表格背景色
    
    Args:
        hex_color: 十六进制颜色值（如 '#1f77b4'）
        alpha: 透明度（0-1），默认0.3，确保颜色足够明显
    
    Returns:
        RGBA格式的颜色字符串（如 'rgba(31, 119, 180, 0.3)'）
    """
    hex_color = hex_color.lstrip('#')
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return f'rgba({r}, {g}, {b}, {alpha})'

def create_report_layout(backend):
    """创建完整的报告分析布局（仅支持多算法模式）"""
    # 多算法模式：为每个算法生成一行数据概览和一行延时误差统计指标
    active_algorithms = backend.get_active_algorithms() if hasattr(backend, 'get_active_algorithms') else []
    
    # 获取算法颜色映射（用于表格行背景色）
    algorithm_colors = {}
    for algorithm in active_algorithms:
        if hasattr(algorithm, 'color'):
            algorithm_colors[algorithm.metadata.algorithm_name] = algorithm.color
    
    if not active_algorithms:
        # 没有激活的算法，显示提示
        # 关键：必须包含所有回调函数需要的组件，否则 Dash 会报错
        empty_fig = {}
        return html.Div([
            html.H4("暂无数据", className="text-center text-muted"),
            html.P("请至少激活一个算法以查看分析报告", className="text-center text-muted"),
            # 包含所有必需的图表组件（隐藏），确保回调函数不会报错
            dcc.Graph(id='key-delay-scatter-plot', figure=empty_fig, style={'display': 'none'}),
            dcc.Graph(id='key-delay-zscore-scatter-plot', figure=empty_fig, style={'display': 'none'}),
            dcc.Graph(id='hammer-velocity-delay-scatter-plot', figure=empty_fig, style={'display': 'none'}),
            dcc.Graph(id='hammer-velocity-comparison-plot', figure=empty_fig, style={'display': 'none'}),
            # key-hammer-velocity-scatter-plot 已删除（功能与按键-力度交互效应图重复）
            # force-delay-by-key-scatter-plot 已删除（功能与按键-力度交互效应图重复）
            dcc.Graph(id='key-force-interaction-plot', figure=empty_fig, style={'display': 'none'}),
            dcc.Store(id='key-force-interaction-selected-algorithms', data=[]),
            dcc.Store(id='key-force-interaction-selected-keys', data=[]),
            dcc.Graph(id='relative-delay-distribution-plot', figure=empty_fig, style={'display': 'none'}),
            html.Div(id='offset-alignment-plot', style={'display': 'none'}),
            dcc.Graph(id='delay-time-series-plot', figure=empty_fig, style={'display': 'none'}),
            dcc.Graph(id='delay-histogram-plot', figure=empty_fig, style={'display': 'none'}),
            html.Div([
                dash_table.DataTable(
                    id='offset-alignment-table',
                    data=[],
                    columns=[]
                )
            ], style={'display': 'none'}),
            html.Div([
                dash_table.DataTable(
                    id='delay-histogram-detail-table',
                    data=[],
                    columns=[
                        {"name": "算法名称", "id": "algorithm_name"},
                        {"name": "按键ID", "id": "key_id"},
                        {"name": "延时(ms)", "id": "delay_ms"},
                        {"name": "录制索引", "id": "record_index"},
                        {"name": "播放索引", "id": "replay_index"},
                        {"name": "录制开始(0.1ms)", "id": "record_keyon"},
                        {"name": "播放开始(0.1ms)", "id": "replay_keyon"},
                        {"name": "持续时间差(0.1ms)", "id": "duration_offset"},
                    ]
                )
            ], style={'display': 'none'}),
            html.Div(id='delay-histogram-selection-info', style={'display': 'none'})
        ])
    
    # 为每个算法生成数据概览和延时误差统计指标（合并到同一个卡片中）
    overview_rows = []
    error_stats_rows = []
    
    for algorithm in active_algorithms:
        algorithm_name = algorithm.metadata.algorithm_name
        overview_row = _create_single_algorithm_overview_row(algorithm, algorithm_name)
        error_stats_row = _create_single_algorithm_error_stats_row(algorithm, algorithm_name)
        
        if overview_row:
            overview_rows.append(overview_row)
        if error_stats_row:
            error_stats_rows.append(error_stats_row)
    
    # 创建合并的数据概览卡片（包含所有算法）
    all_rows = []
    if overview_rows:
        all_rows.append(
                dbc.Row([
                    dbc.Col([
                        dbc.Card([
                            dbc.CardHeader([
                                html.H4([
                                    html.I(className="fas fa-chart-pie", style={'marginRight': '10px', 'color': '#28a745'}),
                                    "数据统计概览"
                                ], className="mb-0")
                            ]),
                            dbc.CardBody([
                                *overview_rows
                        ])
                    ], className="shadow-sm mb-4")
                    ], width=12)
                ])
            )
    
    # 创建合并的延时误差统计指标卡片（包含所有算法）
    if error_stats_rows:
        all_rows.append(
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader([
                            html.H4([
                                html.I(className="fas fa-chart-bar", style={'marginRight': '10px', 'color': '#dc3545'}),
                                "延时误差统计指标"
                            ], className="mb-0")
                        ]),
                        dbc.CardBody([
                            *error_stats_rows
                        ])
                    ], className="shadow-sm mb-4")
                ], width=12)
            ])
        )
    
    # 获取数据源信息（使用第一个算法的文件名）
    source_info = backend.get_data_source_info()
    data_source = source_info.get('filename') or "多算法对比"
    
    # 注意：由于这些UI组件（dcc.Graph、dash_table.DataTable等）需要在布局中定义
    # 否则回调函数无法找到它们，所以我们必须在这里包含它们
    
    return html.Div([
        dcc.Download(id='download-pdf'),
        dbc.Container([
            dbc.Row([
                dbc.Col([
                    html.H2(f"分析报告 - {data_source}", className="text-center mb-3",
                           style={'color': '#2E86AB', 'fontWeight': 'bold', 'textShadow': '1px 1px 2px rgba(0,0,0,0.1)'}),
                ], width=8),
                dbc.Col([
                    html.Div([
                        dbc.Button([
                            html.I(className="fas fa-file-pdf", style={'marginRight': '8px'}),
                            "导出PDF报告"
                        ], id='btn-export-pdf', color='danger', size='sm', className='mb-2'),
                        html.Div(id='pdf-status')
                    ], className="text-end")
                ], width=4)
            ], className="mb-4"),

                # 多算法数据概览和延时误差统计指标（每个算法一行）
                *all_rows,
                
                # 为每个算法创建独立的丢锤和多锤表格
                *[_create_error_tables_row_for_algorithm(alg) for alg in active_algorithms if alg.analyzer],
                
                # 其余内容（图表、表格等）- 与单算法模式保持一致
        # 柱状图分析区域 - 独立全宽区域
        dbc.Row([
            dbc.Col([
                html.Div([
                    dbc.Row([
                        dbc.Col([
                                    html.H6("按键延时分析条形图", className="mb-2",
                                   style={'color': '#6f42c1', 'fontWeight': 'bold', 'borderBottom': '2px solid #6f42c1', 'paddingBottom': '5px'}),
                                ], width=12)
                    ]),
                    html.Div(
                        id='offset-alignment-plot',
                        children=[],
                        style={'minHeight': '500px'}
                    ),
                ], className="mb-4", style={'backgroundColor': '#ffffff', 'padding': '20px', 'borderRadius': '8px', 'boxShadow': '0 2px 8px rgba(0,0,0,0.1)'}),
            ], width=12)
        ]),
        
        # 按键与延时Z-Score标准化散点图区域
        dbc.Row([
            dbc.Col([
                html.Div([
                    dbc.Row([
                        dbc.Col([
                                    html.H6("按键与延时Z-Score标准化散点图", className="mb-2",
                                           style={'color': '#9c27b0', 'fontWeight': 'bold', 'borderBottom': '2px solid #9c27b0', 'paddingBottom': '5px'}),
                        ], width=12)
                    ]),
                    dcc.Graph(
                                id='key-delay-zscore-scatter-plot',
                        figure={},
                        style={'height': '500px'}
                    ),
                ], className="mb-4", style={'backgroundColor': '#ffffff', 'padding': '20px', 'borderRadius': '8px', 'boxShadow': '0 2px 8px rgba(0,0,0,0.1)'}),
                    ], width=12)
                ]),
                
                # 锤速与延时散点图区域
                dbc.Row([
                    dbc.Col([
                        html.Div([
                            dbc.Row([
                                dbc.Col([
                            html.H6("锤速与延时散点图", className="mb-2",
                                   style={'color': '#d32f2f', 'fontWeight': 'bold', 'borderBottom': '2px solid #d32f2f', 'paddingBottom': '5px'}),
                                ], width=12)
                            ]),
                            dcc.Graph(
                        id='hammer-velocity-delay-scatter-plot',
                                figure={},
                                style={'height': '500px'}
                            ),
                        ], className="mb-4", style={'backgroundColor': '#ffffff', 'padding': '20px', 'borderRadius': '8px', 'boxShadow': '0 2px 8px rgba(0,0,0,0.1)'}),
            ], width=12)
        ]),

        # 锤速对比图区域
        dbc.Row([
            dbc.Col([
                html.Div([
                    dbc.Row([
                        dbc.Col([
                            html.H6("锤速对比图", className="mb-2",
                                   style={'color': '#ff9800', 'fontWeight': 'bold', 'borderBottom': '2px solid #ff9800', 'paddingBottom': '5px'}),
                        ], width=12)
                    ]),
                    dcc.Graph(
                        id='hammer-velocity-comparison-plot',
                        figure={},
                        style={'height': '500px'}
                    ),
                ], className="mb-4", style={'backgroundColor': '#ffffff', 'padding': '20px', 'borderRadius': '8px', 'boxShadow': '0 2px 8px rgba(0,0,0,0.1)'}),
            ], width=12)
        ]),

        # 按键-力度交互效应图
        dbc.Row([
            dbc.Col([
                html.Div([
                    dbc.Row([
                        dbc.Col([
                            html.H6("按键-力度交互效应图", className="mb-2",
                                   style={'color': '#c2185b', 'fontWeight': 'bold', 'borderBottom': '2px solid #c2185b', 'paddingBottom': '5px'}),
                        ], width=8),
                        dbc.Col([
                            dcc.Dropdown(
                                id='key-force-interaction-key-selector',
                                placeholder='选择按键（留空显示全部）',
                                clearable=True,
                                style={'fontSize': '12px'}
                            )
                        ], width=4)
                    ]),
                    dcc.Graph(
                        id='key-force-interaction-plot',
                        figure={},
                        style={'height': '600px'}
                    ),
                    dcc.Store(id='key-force-interaction-selected-algorithms', data=[]),  # 存储选中的算法列表
                    dcc.Store(id='key-force-interaction-selected-keys', data=[]),  # 存储选中的按键列表
                ], className="mb-4", style={'backgroundColor': '#ffffff', 'padding': '20px', 'borderRadius': '8px', 'boxShadow': '0 2px 8px rgba(0,0,0,0.1)'}),
            ], width=12)
        ]),
        
        # 同种算法相对延时分布图
        dbc.Row([
            dbc.Col([
                html.Div([
                    dbc.Row([
                        dbc.Col([
                            html.H6("同种算法不同曲子的相对延时分布图", className="mb-2",
                                   style={'color': '#9c27b0', 'fontWeight': 'bold', 'borderBottom': '2px solid #9c27b0', 'paddingBottom': '5px'}),
                        ], width=12)
                    ]),
                    html.Div(id='relative-delay-distribution-container', children=[])
                ], className="mb-4", style={'backgroundColor': '#ffffff', 'padding': '20px', 'borderRadius': '8px', 'boxShadow': '0 2px 8px rgba(0,0,0,0.1)'}),
            ], width=12)
        ]),
        
        # 曲线对齐测试区域
        create_curve_alignment_test_area(),

        # 延时时间序列图
        dbc.Row([
            dbc.Col([
                html.Div([
                    dbc.Row([
                        dbc.Col([
                            html.H6("延时时间序列图", className="mb-2",
                                   style={'color': '#2c3e50', 'fontWeight': 'bold', 'borderBottom': '2px solid #2c3e50', 'paddingBottom': '5px'}),
                        ], width=12)
                    ]),
                    dcc.Graph(
                        id='delay-time-series-plot',
                        figure={},
                        style={'height': '500px'}
                    ),
                ], className="mb-4", style={'backgroundColor': '#ffffff', 'padding': '20px', 'borderRadius': '8px', 'boxShadow': '0 2px 8px rgba(0,0,0,0.1)'}),
            ], width=12)
        ]),
        
        # 延时分布直方图（附正态拟合曲线）- 使用相对时延
        dbc.Row([
            dbc.Col([
                html.Div([
                    dbc.Row([
                        dbc.Col([
                            html.H6("延时分布直方图（附正态拟合曲线）", className="mb-2",
                                   style={'color': '#2c3e50', 'fontWeight': 'bold', 'borderBottom': '2px solid #2c3e50', 'paddingBottom': '5px'}),
                        ], width=12)
                    ]),
                    dcc.Graph(
                        id='delay-histogram-plot',
                        figure={},
                        style={'height': '500px'}
                    ),
                    html.Div([
                        html.P("💡 提示：点击直方图中的柱状图区域，可查看该延时范围内的数据点详情", 
                               className="text-muted", 
                               style={'fontSize': '12px', 'marginTop': '10px', 'marginBottom': '10px'}),
                        html.Div(id='delay-histogram-selection-info', 
                                style={'marginBottom': '10px', 'fontSize': '14px', 'fontWeight': 'bold', 'color': '#2c3e50'}),
                        dash_table.DataTable(
                            id='delay-histogram-detail-table',
                            columns=[
                                {"name": "算法名称", "id": "algorithm_name"},
                                {"name": "按键ID", "id": "key_id"},
                                {"name": "延时(ms)", "id": "delay_ms", "type": "numeric", "format": {"specifier": ".2f"}},
                                {"name": "录制索引", "id": "record_index"},
                                {"name": "播放索引", "id": "replay_index"},
                                {"name": "录制开始(0.1ms)", "id": "record_keyon"},
                                {"name": "播放开始(0.1ms)", "id": "replay_keyon"},
                                {"name": "持续时间差(0.1ms)", "id": "duration_offset"},
                            ],
                            data=[],
                            page_action='none',
                            style_cell={
                                'textAlign': 'center',
                                'fontSize': '12px',
                                'fontFamily': 'Arial, sans-serif',
                                'padding': '8px',
                                'overflow': 'hidden',
                                'textOverflow': 'ellipsis',
                            },
                            style_header={
                                'backgroundColor': '#f8f9fa',
                                'fontWeight': 'bold',
                                'border': '1px solid #dee2e6',
                                'position': 'sticky',
                                'top': 0,
                                'zIndex': 1
                            },
                            style_data={
                                'border': '1px solid #dee2e6'
                            },
                            style_data_conditional=[
                                {
                                    'if': {'row_index': 'odd'},
                                    'backgroundColor': '#f8f9fa'
                                }
                            ],
                            style_table={'overflowX': 'auto', 'display': 'none'}  # 默认隐藏，点击后显示
                        )
                    ])
                ], className="mb-4", style={'backgroundColor': '#ffffff', 'padding': '20px', 'borderRadius': '8px', 'boxShadow': '0 2px 8px rgba(0,0,0,0.1)'}),
            ], width=12)
        ]),
        
        # 主要内容区域：为每个算法创建独立的丢锤和多锤表格（已在上面通过列表展开添加）
        # 这里保留原有的单算法模式表格（用于向后兼容，但多算法模式下不会使用）
        dbc.Row([
                # 左侧：丢锤问题表格
                dbc.Col([
                    html.Div([
                        dbc.Row([
                            dbc.Col([
                                html.H5("丢锤问题列表", className="mb-3",
                                       style={'color': '#721c24', 'fontWeight': 'bold', 'fontSize': '18px', 'borderBottom': '3px solid #721c24', 'paddingBottom': '8px'}),
                            ], width=12)
                        ]),
                        dash_table.DataTable(
                            id='drop-hammers-table',
                            columns=[
                                {"name": "数据类型", "id": "data_type"},
                                {"name": "键位ID", "id": "keyId"},
                                {"name": "按下时间(ms)", "id": "keyOn"},
                                {"name": "释放时间(ms)", "id": "keyOff"},
                                {"name": "index", "id": "index"},
                                {"name": "未匹配原因", "id": "analysis_reason"},
                            ],
                            data=backend.get_error_table_data('丢锤'),
                            page_action='none',
                            style_cell={
                                'textAlign': 'center',
                                    'fontSize': '14px',
                                'fontFamily': 'Arial, sans-serif',
                                    'padding': '10px',
                                'overflow': 'hidden',
                                'textOverflow': 'ellipsis',
                                'minWidth': '80px',
                            },
                                style_cell_conditional=(
                                    # 多算法模式：添加算法名称列的宽度
                                    [{'if': {'column_id': 'algorithm_name'}, 'width': '12%'}] if (
                                        hasattr(backend, 'is_multi_algorithm_mode') and 
                                        backend.is_multi_algorithm_mode()
                                    ) else []
                                ) + [
                                    {'if': {'column_id': 'data_type'}, 'width': '14%'},
                                    {'if': {'column_id': 'keyId'}, 'width': '12%'},
                                    {'if': {'column_id': 'keyOn'}, 'width': '16%'},
                                    {'if': {'column_id': 'keyOff'}, 'width': '16%'},
                                    {'if': {'column_id': 'index'}, 'width': '10%'},
                                    {'if': {'column_id': 'analysis_reason'}, 'width': '20%'},
                            ],
                            style_header={
                                'backgroundColor': '#f8d7da',
                                'fontWeight': 'bold',
                                'border': '2px solid #dee2e6',
                                    'fontSize': '15px',
                                'color': '#721c24',
                                'textAlign': 'center',
                                    'padding': '12px',
                                'whiteSpace': 'normal',
                                'height': 'auto',
                                'position': 'sticky',
                                'top': 0,
                                'zIndex': 1
                            },
                            style_data={
                                'border': '1px solid #dee2e6',
                                    'fontSize': '14px',
                                'padding': '10px'
                            },
                            style_data_conditional=[
                                {
                                    'if': {'filter_query': '{data_type} = record'},
                                    'fontWeight': 'bold',
                                    'backgroundColor': '#ffeaea'
                                },
                                {
                                    'if': {'filter_query': '{data_type} = play'},
                                    'backgroundColor': '#fffafa'
                                },
                                {
                                    'if': {'filter_query': '{keyOn} = 无匹配'},
                                    'backgroundColor': '#f5f5f5',
                                    'color': '#6c757d',
                                    'fontStyle': 'italic'
                                },
                                {
                                    'if': {'row_index': 'odd'},
                                    'backgroundColor': '#fafafa'
                                }
                            ],
                                row_selectable=False,
                            sort_action="native",
                                filter_action="none",
                            style_table={
                                    'height': 'calc(75vh - 200px)',
                                'overflowY': 'auto', 
                                'overflowX': 'auto',
                                'border': '2px solid #dee2e6', 
                                'borderRadius': '8px',
                                'minHeight': '400px'
                            }
                        ),
                    ], style={'backgroundColor': '#ffffff', 'padding': '20px', 'borderRadius': '10px', 'boxShadow': '0 4px 12px rgba(0,0,0,0.15)', 'height': '100%'}),
                    ], width=6, className="pr-2"),
                
                # 右侧：多锤问题表格
                dbc.Col([
                    html.Div([
                        dbc.Row([
                            dbc.Col([
                                html.H5("多锤问题列表", className="mb-3",
                                       style={'color': '#856404', 'fontWeight': 'bold', 'fontSize': '18px', 'borderBottom': '3px solid #856404', 'paddingBottom': '8px'}),
                            ], width=12)
                        ]),
                        dash_table.DataTable(
                            id='multi-hammers-table',
                                columns=(
                                    # 多算法模式：添加"算法名称"列
                                [{"name": "算法名称", "id": "algorithm_name"}]
                                ) + [
                                {"name": "数据类型", "id": "data_type"},
                                {"name": "键位ID", "id": "keyId"},
                                {"name": "按下时间(ms)", "id": "keyOn"},
                                {"name": "释放时间(ms)", "id": "keyOff"},
                                {"name": "index", "id": "index"},
                                {"name": "未匹配原因", "id": "analysis_reason"},
                            ],
                            data=backend.get_error_table_data('多锤'),
                            page_action='none',
                            style_cell={
                                'textAlign': 'center',
                                    'fontSize': '14px',
                                'fontFamily': 'Arial, sans-serif',
                                    'padding': '10px',
                                'overflow': 'hidden',
                                'textOverflow': 'ellipsis',
                                'minWidth': '80px',
                            },
                                style_cell_conditional=(
                                    # 多算法模式：添加算法名称列的宽度
                                    [{'if': {'column_id': 'algorithm_name'}, 'width': '12%'}] if (
                                        hasattr(backend, 'is_multi_algorithm_mode') and 
                                        backend.is_multi_algorithm_mode()
                                    ) else []
                                ) + [
                                    {'if': {'column_id': 'data_type'}, 'width': '14%'},
                                    {'if': {'column_id': 'keyId'}, 'width': '12%'},
                                    {'if': {'column_id': 'keyOn'}, 'width': '16%'},
                                    {'if': {'column_id': 'keyOff'}, 'width': '16%'},
                                    {'if': {'column_id': 'index'}, 'width': '10%'},
                                    {'if': {'column_id': 'analysis_reason'}, 'width': '20%'},
                            ],
                            style_header={
                                'backgroundColor': '#fff3cd',
                                'fontWeight': 'bold',
                                'border': '2px solid #dee2e6',
                                    'fontSize': '15px',
                                'color': '#856404',
                                'textAlign': 'center',
                                    'padding': '12px',
                                'whiteSpace': 'normal',
                                'height': 'auto',
                                'position': 'sticky',
                                'top': 0,
                                'zIndex': 1
                            },
                            style_data={
                                'border': '1px solid #dee2e6',
                                    'fontSize': '14px',
                                'padding': '10px'
                            },
                            style_data_conditional=[
                                {
                                    'if': {'filter_query': '{data_type} = record'},
                                    'fontWeight': 'bold',
                                    'backgroundColor': '#fff8e1'
                                },
                                {
                                    'if': {'filter_query': '{data_type} = play'},
                                    'backgroundColor': '#fffef5'
                                },
                                {
                                    'if': {'filter_query': '{keyOn} = 无匹配'},
                                    'backgroundColor': '#f5f5f5',
                                    'color': '#6c757d',
                                    'fontStyle': 'italic'
                                },
                                {
                                    'if': {'row_index': 'odd'},
                                    'backgroundColor': '#fafafa'
                                }
                            ],
                                row_selectable=False,
                            sort_action="native",
                                filter_action="none",
                            style_table={
                                    'height': 'calc(75vh - 200px)',
                                'overflowY': 'auto', 
                                'overflowX': 'auto',
                                'border': '2px solid #dee2e6', 
                                'borderRadius': '8px',
                                'minHeight': '400px'
                            }
                        ),
                    ], style={'backgroundColor': '#ffffff', 'padding': '20px', 'borderRadius': '10px', 'boxShadow': '0 4px 12px rgba(0,0,0,0.15)', 'height': '100%'}),
                    ], width=6, className="pl-2"),
                ], className="mb-4", style={'display': 'none'}),  # 多算法模式下隐藏，使用上面的独立表格
            
            # 无效音符统计表格（单独一行）
            dbc.Row([
                dbc.Col([
                    html.Div([
                        dbc.Row([
                            dbc.Col([
                                html.H6("无效音符统计", className="mb-2",
                                       style={'color': '#6c757d', 'fontWeight': 'bold', 'borderBottom': '2px solid #6c757d', 'paddingBottom': '5px'}),
                            ], width=12)
                        ]),
                        dash_table.DataTable(
                            id='invalid-notes-table',
                                columns=(
                                    [{"name": "算法名称", "id": "algorithm_name"}] if True else []
                                ) + [
                                {"name": "数据类型", "id": "data_type"},
                                {"name": "总音符数", "id": "total_notes"},
                                {"name": "有效音符", "id": "valid_notes"},
                                {"name": "无效音符", "id": "invalid_notes"},
                                {"name": "持续时间过短", "id": "duration_too_short"},
                                {"name": "数据为空", "id": "empty_data"},
                                {"name": "不发声音符", "id": "silent_notes"},
                                {"name": "其他错误", "id": "other_errors"}
                            ],
                            data=backend.get_invalid_notes_table_data(),
                                page_action='none',
                            style_cell={
                                'textAlign': 'center',
                                    'fontSize': '14px',
                                'fontFamily': 'Arial, sans-serif',
                                    'padding': '10px',
                                'overflow': 'hidden',
                                'textOverflow': 'ellipsis',
                                'minWidth': '100px',
                            },
                                style_cell_conditional=(
                                    [{'if': {'column_id': 'algorithm_name'}, 'width': '12%'}] if True else []
                                ) + [
                                    {'if': {'column_id': 'data_type'}, 'width': '13%' if True else '15%'},
                                    {'if': {'column_id': 'total_notes'}, 'width': '11%' if True else '13%'},
                                    {'if': {'column_id': 'valid_notes'}, 'width': '11%' if True else '13%'},
                                    {'if': {'column_id': 'invalid_notes'}, 'width': '11%' if True else '13%'},
                                    {'if': {'column_id': 'duration_too_short'}, 'width': '13%' if True else '15%'},
                                    {'if': {'column_id': 'empty_data'}, 'width': '10%' if True else '12%'},
                                    {'if': {'column_id': 'silent_notes'}, 'width': '10%' if True else '12%'},
                                    {'if': {'column_id': 'other_errors'}, 'width': '9%' if True else '10%'},
                            ],
                            style_header={
                                'backgroundColor': '#e9ecef',
                                'fontWeight': 'bold',
                                'border': '2px solid #dee2e6',
                                    'fontSize': '15px',
                                'color': '#495057',
                                'textAlign': 'center',
                                    'padding': '12px',
                                'whiteSpace': 'normal',
                                'height': 'auto',
                                'position': 'sticky',
                                'top': 0,
                                'zIndex': 1
                            },
                            style_data={
                                'border': '1px solid #dee2e6',
                                    'fontSize': '14px',
                                'padding': '10px'
                            },
                                style_data_conditional=(
                                    # 多算法模式：为算法名称列添加特殊样式
                                    [
                                        {
                                            'if': {'column_id': 'algorithm_name'},
                                            'fontWeight': 'bold',
                                            'fontSize': '15px',
                                            'backgroundColor': '#e3f2fd',
                                            'borderLeft': '4px solid #1976d2',
                                            'color': '#1976d2'
                                        }
                                    ] if True else []
                                ) + [
                                {
                                    'if': {'filter_query': '{data_type} = 录制数据'},
                                    'backgroundColor': '#f8f9fa',
                                    'fontWeight': 'bold'
                                },
                                {
                                        'if': {'filter_query': '{data_type} = 回放数据'},
                                    'backgroundColor': '#ffffff'
                                },
                                {
                                    'if': {'row_index': 'odd'},
                                    'backgroundColor': '#fafafa'
                                }
                            ],
                            sort_action="native",
                                filter_action="none",
                            style_table={
                                    'height': 'calc(40vh - 120px)',
                                'overflowY': 'auto', 
                                'overflowX': 'auto',
                                'border': '2px solid #dee2e6', 
                                'borderRadius': '8px',
                                'minHeight': '250px'
                            }
                        ),
                    ], className="mb-3", style={'backgroundColor': '#ffffff', 'padding': '15px', 'borderRadius': '8px', 'boxShadow': '0 2px 8px rgba(0,0,0,0.1)'}),

                    # 偏移对齐数据表格
                    html.Div([
                        dbc.Row([
                            dbc.Col([
                                    html.H6("按键延时分析", className="mb-2",
                                       style={'color': '#6f42c1', 'fontWeight': 'bold', 'borderBottom': '2px solid #6f42c1', 'paddingBottom': '5px'}),
                            ], width=12)
                        ]),
                        dash_table.DataTable(
                            id='offset-alignment-table',
                                columns=(
                                    # 多算法模式：添加"算法名称"列
                                    [{"name": "算法名称", "id": "algorithm_name"}] if True else []
                                ) + [
                                {"name": "键位ID", "id": "key_id"},
                                {"name": "配对数", "id": "count"},
                                {"name": "中位数(ms)", "id": "median"},
                                {"name": "均值(ms)", "id": "mean"},
                                {"name": "标准差(ms)", "id": "std"},
                                    {"name": "方差(ms²)", "id": "variance"},
                                    {"name": "最小值(ms)", "id": "min"},
                                    {"name": "最大值(ms)", "id": "max"},
                                    {"name": "极差(ms)", "id": "range"},
                                {"name": "状态", "id": "status"}
                            ],
                            data=backend.get_offset_alignment_data(),
                                page_action='none',
                            style_cell={
                                'textAlign': 'center',
                                    'fontSize': '14px',
                                'fontFamily': 'Arial, sans-serif',
                                    'padding': '10px',
                                'overflow': 'hidden',
                                'textOverflow': 'ellipsis',
                                'minWidth': '100px',
                            },
                                style_cell_conditional=(
                                    # 多算法模式：添加"算法名称"列的样式
                                    [{'if': {'column_id': 'algorithm_name'}, 'width': '10%'}] if True else []
                                ) + [
                                    {'if': {'column_id': 'key_id'}, 'width': '8%' if True else '10%'},
                                    {'if': {'column_id': 'count'}, 'width': '8%' if True else '10%'},
                                    {'if': {'column_id': 'median'}, 'width': '8%' if True else '10%'},
                                    {'if': {'column_id': 'mean'}, 'width': '8%' if True else '10%'},
                                    {'if': {'column_id': 'std'}, 'width': '8%' if True else '10%'},
                                    {'if': {'column_id': 'variance'}, 'width': '9%' if True else '10%'},
                                    {'if': {'column_id': 'min'}, 'width': '8%' if True else '10%'},
                                    {'if': {'column_id': 'max'}, 'width': '8%' if True else '10%'},
                                    {'if': {'column_id': 'range'}, 'width': '8%' if True else '10%'},
                                    {'if': {'column_id': 'status'}, 'width': '15%' if True else '10%'},
                            ],
                            style_header={
                                    'backgroundColor': '#e3f2fd',
                                'fontWeight': 'bold',
                                'border': '2px solid #dee2e6',
                                    'fontSize': '15px',
                                    'color': '#1976d2',
                                'textAlign': 'center',
                                    'padding': '12px',
                                'whiteSpace': 'normal',
                                'height': 'auto',
                                'position': 'sticky',
                                'top': 0,
                                'zIndex': 1
                            },
                            style_data={
                                'border': '1px solid #dee2e6',
                                    'fontSize': '14px',
                                'padding': '10px'
                            },
                                style_data_conditional=(
                                    # 多算法模式：为算法名称列添加特殊样式
                                    # 注意：算法名称列的背景色会与行背景色叠加，所以只设置字体样式
                                    [
                                        {
                                            'if': {'column_id': 'algorithm_name'},
                                            'fontWeight': 'bold',
                                            'fontSize': '15px',
                                            'color': '#1976d2'
                                        }
                                    ] if True else []
                                ) + [
                                    # 多算法模式：为每种算法添加不同的行背景色（放在最后，确保优先级最高）
                                    # 每种算法的所有行使用相同的背景色，便于区分不同算法
                                    *([
                                        {
                                            # 使用filter_query匹配算法名称
                                            'if': {'filter_query': f'{{algorithm_name}} = "{alg_name}"'},
                                            'backgroundColor': _hex_to_rgba(alg_color, alpha=0.25)
                                        }
                                        for alg_name, alg_color in algorithm_colors.items()
                                    ] if True else []),
                                    # 为每种算法的奇偶行添加轻微的颜色差异（像多锤表格一样）
                                    *([
                                        {
                                            'if': {
                                                'filter_query': f'{{algorithm_name}} = "{alg_name}"',
                                                'row_index': 'odd'
                                            },
                                            'backgroundColor': _hex_to_rgba(alg_color, alpha=0.35)
                                        }
                                        for alg_name, alg_color in algorithm_colors.items()
                                    ] if True else []),
                                {
                                    'if': {'filter_query': '{key_id} = 总体'},
                                    'color': '#6f42c1',
                                    'fontWeight': 'bold'
                                },
                                    {
                                        'if': {'filter_query': '{key_id} = 汇总'},
                                        'fontWeight': 'bold',
                                        'color': '#1976d2'
                                },
                                {
                                    'if': {'filter_query': '{status} = matched'},
                                    'color': '#155724'
                                },
                                {
                                    'if': {'filter_query': '{status} contains invalid'},
                                    'color': '#721c24'
                                    },
                                    # 多算法模式：为按键ID列添加特殊样式，便于区分不同按键组
                                    # 注意：这里只设置字体和颜色，不设置背景色，避免覆盖行背景色
                                    {
                                        'if': {'column_id': 'key_id'},
                                        'fontWeight': 'bold',
                                        'fontSize': '15px',
                                        'color': '#856404'
                                    } if True else {}
                            ],
                            sort_action="native",
                                filter_action="none",
                            style_table={
                                    'height': 'calc(50vh - 150px)',
                                'overflowY': 'auto', 
                                'overflowX': 'auto',
                                'border': '2px solid #dee2e6', 
                                'borderRadius': '8px',
                                'minHeight': '300px'
                            }
                        ),
                    ], className="mb-3", style={'backgroundColor': '#ffffff', 'padding': '15px', 'borderRadius': '8px', 'boxShadow': '0 2px 8px rgba(0,0,0,0.1)'}),
                    ], width=12)
            ])
        ], fluid=True, style={'padding': '20px', 'backgroundColor': '#f5f5f5', 'minHeight': '100vh'})
    ], id='report-layout-container')


def create_detail_content(error_note):
    """创建详细信息内容"""
    details = []

    # 异常类型标签
    details.append(
        dbc.Row([
            dbc.Col([
                dbc.Badge(f"{error_note.error_type}",
                         color="danger" if error_note.error_type == '丢锤' else "warning",
                         className="me-2"),
                html.Span("异常类型", style={'fontSize': '14px', 'fontWeight': 'bold'})
            ], width=12)
        ], className="mb-3")
    )

    # 录制数据信息
    if len(error_note.infos) > 0:
        record_info = error_note.infos[0]
        record_diff = error_note.diffs[0] if len(error_note.diffs) > 0 else None

        details.append(
            dbc.Card([
                dbc.CardHeader([
                    html.I(className="fas fa-microphone me-2", style={'color': '#0d6efd'}),
                    html.Strong("录制数据", style={'color': '#0d6efd', 'fontSize': '13px'})
                ], style={'padding': '8px 12px', 'backgroundColor': '#e7f3ff', 'border': 'none'}),
                dbc.CardBody([
                    dbc.Row([
                        dbc.Col([
                            html.Small("键位ID", className="text-muted d-block"),
                            html.Strong(f"{record_info.keyId}", style={'fontSize': '14px'})
                        ], width=6),
                        dbc.Col([
                            html.Small("持续时间", className="text-muted d-block"),
                            html.Strong(f"{record_info.keyOff - record_info.keyOn}", style={'fontSize': '14px'})
                        ], width=6)
                    ], className="mb-2"),
                    dbc.Row([
                        dbc.Col([
                            html.Small("按下时间", className="text-muted d-block"),
                            html.Span(f"{record_info.keyOn}", style={'fontSize': '12px'})
                        ], width=6),
                        dbc.Col([
                            html.Small("释放时间", className="text-muted d-block"),
                            html.Span(f"{record_info.keyOff}", style={'fontSize': '12px'})
                        ], width=6)
                    ])
                ], style={'padding': '10px'})
            ], className="mb-2", style={'border': '1px solid #dee2e6'})
        )

        if record_diff:
            details.append(
                dbc.Card([
                    dbc.CardHeader([
                        html.I(className="fas fa-chart-bar me-2", style={'color': '#0d6efd'}),
                        html.Strong("录制统计数据", style={'color': '#0d6efd', 'fontSize': '13px'})
                    ], style={'padding': '8px 12px', 'backgroundColor': '#e7f3ff', 'border': 'none'}),
                    dbc.CardBody([
                        dbc.Row([
                            dbc.Col([
                                html.Small("均值", className="text-muted d-block"),
                                html.Strong(f"{record_diff.mean:.3f}", style={'fontSize': '12px'})
                            ], width=6),
                            dbc.Col([
                                html.Small("标准差", className="text-muted d-block"),
                                html.Strong(f"{record_diff.std:.3f}", style={'fontSize': '12px'})
                            ], width=6)
                        ], className="mb-1"),
                        dbc.Row([
                            dbc.Col([
                                html.Small("最大值", className="text-muted d-block"),
                                html.Span(f"{record_diff.max:.3f}", style={'fontSize': '12px'})
                            ], width=6),
                            dbc.Col([
                                html.Small("最小值", className="text-muted d-block"),
                                html.Span(f"{record_diff.min:.3f}", style={'fontSize': '12px'})
                            ], width=6)
                        ])
                    ], style={'padding': '10px'})
                ], className="mb-2", style={'border': '1px solid #dee2e6'})
            )

    # 播放数据信息（如果有）
    if len(error_note.infos) > 1:
        play_info = error_note.infos[1]
        play_diff = error_note.diffs[1] if len(error_note.diffs) > 1 else None

        details.append(
            dbc.Card([
                dbc.CardHeader([
                    html.I(className="fas fa-play me-2", style={'color': '#dc3545'}),
                    html.Strong("播放数据", style={'color': '#dc3545', 'fontSize': '13px'})
                ], style={'padding': '8px 12px', 'backgroundColor': '#f8d7da', 'border': 'none'}),
                dbc.CardBody([
                    dbc.Row([
                        dbc.Col([
                            html.Small("键位ID", className="text-muted d-block"),
                            html.Strong(f"{play_info.keyId}", style={'fontSize': '14px'})
                        ], width=6),
                        dbc.Col([
                            html.Small("持续时间", className="text-muted d-block"),
                            html.Strong(f"{play_info.keyOff - play_info.keyOn}", style={'fontSize': '14px'})
                        ], width=6)
                    ], className="mb-2"),
                    dbc.Row([
                        dbc.Col([
                            html.Small("按下时间", className="text-muted d-block"),
                            html.Span(f"{play_info.keyOn}", style={'fontSize': '12px'})
                        ], width=6),
                        dbc.Col([
                            html.Small("释放时间", className="text-muted d-block"),
                            html.Span(f"{play_info.keyOff}", style={'fontSize': '12px'})
                        ], width=6)
                    ])
                ], style={'padding': '10px'})
            ], className="mb-2", style={'border': '1px solid #dee2e6'})
        )

        if play_diff:
            details.append(
                dbc.Card([
                    dbc.CardHeader([
                        html.I(className="fas fa-chart-bar me-2", style={'color': '#dc3545'}),
                        html.Strong("播放统计数据", style={'color': '#dc3545', 'fontSize': '13px'})
                    ], style={'padding': '8px 12px', 'backgroundColor': '#f8d7da', 'border': 'none'}),
                    dbc.CardBody([
                        dbc.Row([
                            dbc.Col([
                                html.Small("均值", className="text-muted d-block"),
                                html.Strong(f"{play_diff.mean:.3f}", style={'fontSize': '12px'})
                            ], width=6),
                            dbc.Col([
                                html.Small("标准差", className="text-muted d-block"),
                                html.Strong(f"{play_diff.std:.3f}", style={'fontSize': '12px'})
                            ], width=6)
                        ], className="mb-1"),
                        dbc.Row([
                            dbc.Col([
                                html.Small("最大值", className="text-muted d-block"),
                                html.Span(f"{play_diff.max:.3f}", style={'fontSize': '12px'})
                            ], width=6),
                            dbc.Col([
                                html.Small("最小值", className="text-muted d-block"),
                                html.Span(f"{play_diff.min:.3f}", style={'fontSize': '12px'})
                            ], width=6)
                        ])
                    ], style={'padding': '10px'})
                ], className="mb-2", style={'border': '1px solid #dee2e6'})
            )
    else:
        # 没有播放数据的情况（主要针对丢锤或部分多锤）
        details.append(
            dbc.Alert([
                html.I(className="fas fa-exclamation-triangle me-2"),
                html.Strong("无播放数据匹配")
            ], color="warning", className="mb-2")
        )

    return details


def create_curve_alignment_test_area():
    """创建曲线对齐测试区域"""
    return dbc.Row([
        dbc.Col([
            html.Div([
                dbc.Row([
                    dbc.Col([
                        html.H6("曲线对齐测试", className="mb-2",
                               style={'color': '#2c3e50', 'fontWeight': 'bold', 'borderBottom': '2px solid #2c3e50', 'paddingBottom': '5px'}),
                        html.P("使用延时时间序列图的第一个数据点测试曲线对齐功能", 
                               className="text-muted", 
                               style={'fontSize': '12px', 'marginBottom': '10px'}),
                    ], width=12)
                ]),
                dbc.Row([
                    dbc.Col([
                        dbc.Button([
                            html.I(className="fas fa-play me-2"),
                            "开始测试"
                        ], id='btn-test-curve-alignment', color='primary', size='md', className='mb-3'),
                    ], width=12)
                ]),
                html.Div(id='curve-alignment-test-result', children=[
                    html.Div("点击按钮开始测试", 
                            className="text-muted text-center",
                            style={'padding': '20px', 'fontSize': '14px'})
                ])
            ], className="mb-4", style={'backgroundColor': '#ffffff', 'padding': '20px', 'borderRadius': '8px', 'boxShadow': '0 2px 8px rgba(0,0,0,0.1)'}),
        ], width=12)
    ])
